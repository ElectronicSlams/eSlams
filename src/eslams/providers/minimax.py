"""MiniMax direct Chat Completions wire contract (no SDK or broker routing)."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "minimax"
API_KEY_ENV = "MINIMAX_API_KEY"
DEFAULT_MODEL = "MiniMax-M3.1-Flash"
CHAT_COMPLETIONS_ENDPOINT = "https://api.minimax.io/v1/chat/completions"
_CONVERSATION: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "minimax_conversation", default=None,
)

_ERROR_KINDS = {
    **dict.fromkeys((1004, 2049), "provider_auth_failed"),
    **dict.fromkeys((1026, 1027, 1046), "provider_refused"),
    **dict.fromkeys((1002, 1039, 1041, 1045, 2045, 2046, 2047, 2062),
                    "provider_rate_limited"),
    **dict.fromkeys((1001, 2066), "provider_timeout"),
    **dict.fromkeys((1000, 1024, 1033, 2022, 2064, 2069), "provider_unavailable"),
}


@contextmanager
def conversation() -> Iterator[None]:
    """Keep repair history local to this invocation, including concurrent calls."""
    token = _CONVERSATION.set([])
    try:
        yield
    finally:
        _CONVERSATION.reset(token)


def _code(data: dict[str, Any]) -> int | None:
    base = data.get("base_resp")
    if isinstance(base, dict):
        code = base.get("status_code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def require_model(model: object) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("MiniMax requires an explicit nonblank model ID")


def configuration_error(model: object, runtime: ProviderRuntimeConfig | None) -> str | None:
    try:
        require_model(model)
    except ValueError as exc:
        return str(exc)
    if runtime is None:
        return None
    if runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None:
        return "MiniMax does not support token-based reasoning budgets"
    if runtime.reasoning_effort is not None and (
        model != DEFAULT_MODEL
        or runtime.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}
    ):
        return "MiniMax reasoning_effort requires MiniMax-M3.1-Flash and a documented effort"
    if runtime.reasoning == "disabled" and model != "MiniMax-M3":
        return "MiniMax reasoning cannot be disabled for this model"
    if runtime.reasoning == "enabled" and model not in {DEFAULT_MODEL, "MiniMax-M3"}:
        return "MiniMax explicit thinking is not verified for this exact model ID"
    return None


def _error_kind(data: dict[str, Any]) -> str | None:
    from eslams.agents import _body_error_status, _provider_error_kind

    code = _code(data)
    if code:
        return _ERROR_KINDS.get(code, "provider_request_rejected")
    if data.get("error") is not None:
        status = _body_error_status(data["error"])
        return _provider_error_kind(status) if status else "provider_unavailable"
    return None


def observe_http_error(
    response: httpx.Response, receipt: dict[str, Any], default_kind: str,
) -> tuple[str, bool]:
    """Classify bounded error telemetry; permit replay only for a bare rejection.

    Even zero/malformed work observations, extensions or conflicting classifiers
    prevent retry. MiniMax's prose is never copied into exceptions or receipts.
    Shared transport has already quarantined any observed usage and cost.
    """
    from eslams.agents import _safe_rate_rejection, _strict_provider_json
    from eslams.protocol import validate_json_payload

    try:
        data = _strict_provider_json(response)
        validate_json_payload(data)
        if not isinstance(data, dict):
            return default_kind, False
    except (ValueError, UnicodeError, RecursionError):
        return default_kind, False
    kind = _error_kind(data) or default_kind
    code = _code(data)
    if code is not None:
        receipt["provider_error_code"] = code
    receipt["finish_status"] = "refused" if kind == "provider_refused" else "failed"
    # A 401/5xx and an alleged rate rejection do not establish safe replay.
    if response.status_code not in {200, 429}:
        return kind, False
    base = data.get("base_resp")
    bare_rate_rejection = (
        code == 1002
        and set(data) == {"base_resp"}
        and isinstance(base, dict)
        and not (set(base) - {"status_code", "status_msg"})
        and ("status_msg" not in base or isinstance(base["status_msg"], str))
    )
    return kind, bare_rate_rejection or (
        "base_resp" not in data and _safe_rate_rejection(data, response.status_code)
    )


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError
    from eslams.providers.minimax_privacy import (
        _action_contains_credential,
        _credential_variants,
        _scrub_receipt,
        _scrub_text,
    )

    secrets = _credential_variants(api_key)
    receipt: dict[str, Any] | None = None
    failure: ProviderCallError | TimeoutError
    try:
        error = configuration_error(agent.model, agent.runtime_config)
        if error:
            raise ProviderCallError(error, error_kind="provider_request_rejected",
                                    provider=PROVIDER_ID, model=agent.model)
        text, receipt = _complete(agent, api_key, prompt)
        try:
            contaminated = _action_contains_credential(text, secrets)
        except (ValueError, RecursionError, OverflowError):
            contaminated = True
        if contaminated:
            raise ProviderCallError("MiniMax action failed credential exclusion",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
                receipt={**receipt, "outcome": "provider_response_schema_mismatch"})
        return text, _scrub_receipt(receipt, secrets)
    except ProviderCallError as exc:
        failure = ProviderCallError(_scrub_text(str(exc), secrets),
            error_kind=exc.error_kind, status_code=exc.status_code,
            provider=PROVIDER_ID, model=agent.model,
            retry_after_seconds=exc.retry_after_seconds, retry_permitted=exc.retry_permitted,
            receipt=_scrub_receipt(exc.receipt, secrets))
    except TimeoutError:
        failure = (ProviderCallError("MiniMax response inspection timed out",
            error_kind="provider_timeout", provider=PROVIDER_ID, model=agent.model,
            receipt=_scrub_receipt({**receipt, "outcome": "provider_timeout"}, secrets))
            if receipt is not None else TimeoutError("MiniMax request timed out"))
    raise failure from None


def _complete(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy imports keep provider-specific behavior out of the shared agent and
    # avoid a circular import while reusing its safe transport/receipt contract.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
        _retry_after_seconds,
    )

    runtime = agent.runtime_config
    history = _CONVERSATION.get()
    messages = [*(history or []), {"role": "user", "content": prompt}]
    if not history:
        messages.insert(0, {"role": "system", "content": _SYSTEM_INSTRUCTIONS})
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": copy.deepcopy(messages),
        "stream": False,
        # Formatting only: this never selects an effort or enables reasoning.
        "reasoning_split": True,
        "max_completion_tokens": agent._effective_max_output_tokens(),
    }
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning_effort"] = runtime.reasoning_effort
    if runtime and runtime.reasoning != "auto":
        payload["thinking"] = {
            "type": "disabled" if runtime.reasoning == "disabled" else "adaptive",
        }
    # M3 temperature/top_p are fixed by the service. Never send an ineffective
    # sampling control, an invented thinking budget, tools or a fallback route.
    try:
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"minimax:{agent.model}",
        )
    except ProviderCallError as exc:
        # Even truncated or encoded transport prose can disclose part of a key.
        exc.args = ("MiniMax transport or HTTP request failed",)
        raise
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    kind = _error_kind(data)
    if kind is not None:
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
            retry_after_seconds=_retry_after_seconds(response),
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["request_id"] = _http_error_identifier(
            response.headers.get("x-request-id") or response.headers.get("request-id")
        )
        receipt["gateway_request_id"] = _http_error_identifier(
            response.headers.get("cf-aig-request-id")
            or response.headers.get("x-gateway-request-id")
        )
        kind, retry = observe_http_error(response, receipt, kind)
        raise ProviderCallError(
            "MiniMax reported an error inside the response body",
            # Logical 429 enables the existing safe retry policy; receipt keeps
            # the actual HTTP status (including HTTP 200).
            status_code=429 if kind == "provider_rate_limited" else response.status_code,
            error_kind=kind, retry_permitted=retry,
            retry_after_seconds=_retry_after_seconds(response),
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    try:
        message = _completed_message(data, receipt, agent.model)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    # Only an explicit action repair continues this private conversation. Keep
    # the complete assistant message (reasoning_content/reasoning_details too).
    # The caller clears this memory at the end of every /act invocation.
    if history is not None:
        history[:] = [*messages, copy.deepcopy(message)]
    return str(message["content"]), receipt


def _completed_message(
    data: dict[str, Any], receipt: dict[str, Any], requested_model: str,
) -> dict[str, Any]:
    from eslams.agents import ProviderCallError

    def fail(kind: str, message: str) -> NoReturn:
        raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID,
                                model=requested_model)

    base = data.get("base_resp")
    if "base_resp" in data and (not isinstance(base, dict) or _code(data) != 0):
        fail("provider_response_schema_mismatch", "MiniMax returned malformed base_resp")
    if data.get("object", "chat.completion") != "chat.completion":
        fail("provider_response_schema_mismatch", "MiniMax returned an unexpected response object")
    for key in ("input_sensitive", "output_sensitive"):
        if key in data and not isinstance(data[key], bool):
            fail("provider_response_schema_mismatch", "MiniMax sensitivity flags are malformed")
        if data.get(key) is True:
            receipt.update(finish_status="refused", finish_reason="content_filter")
            fail("provider_refused", "MiniMax refused or filtered the requested action")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch", "MiniMax response requires exactly one choice")
    choice = choices[0]
    if type(choice.get("index")) is not int or choice["index"] != 0:
        fail("provider_response_schema_mismatch", "MiniMax returned an invalid choice index")
    if choice.get("error") is not None:
        receipt["finish_status"] = "failed"
        fail("provider_unavailable", "MiniMax reported an error in the response choice")
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if reason in (
        "stop", "length", "content_filter", "tool_calls", "error"
    ) else "unknown"
    receipt["finish_status"] = "unknown"
    message = choice.get("message")
    if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        receipt["finish_status"] = "refused"
        fail("provider_refused", "MiniMax refused or filtered the requested action")
    if reason == "length":
        receipt["finish_status"] = "incomplete"
        fail("provider_output_truncated", "MiniMax token/context constraint interrupted output")
    if reason != "stop":
        fail("provider_response_schema_mismatch", "MiniMax did not return completed text")
    if (not isinstance(message, dict) or message.get("role") != "assistant"
            or not isinstance(message.get("content"), str) or not message["content"].strip()
            or message.get("tool_calls") or message.get("function_call")):
        fail("provider_response_schema_mismatch", "MiniMax has no completed assistant text")
    if "<think>" in message["content"] or "</think>" in message["content"]:
        fail("provider_response_schema_mismatch", "MiniMax did not separate reasoning from text")
    if "reasoning_content" in message and not isinstance(message["reasoning_content"], str):
        fail("provider_response_schema_mismatch", "MiniMax returned malformed reasoning content")
    if data.get("model") is not None and data["model"] != requested_model:
        fail("provider_request_rejected", "MiniMax returned a different model; no action accepted")
    receipt["finish_status"] = "completed"
    return message


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Only documented MiniMax token fields supply canonical accounting."""
    from eslams.agents import _empty_usage, _normalize_usage

    if not isinstance(usage, dict):
        return _empty_usage()
    canonical = {key: usage[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in usage}
    for group, field in (("prompt_tokens_details", "cached_tokens"),
                         ("completion_tokens_details", "reasoning_tokens")):
        details = usage.get(group)
        if isinstance(details, dict) and field in details:
            canonical[group] = {field: details[field]}
    normalized = _normalize_usage("openai", canonical)
    for key in ("prompt_tokens_details", "completion_tokens_details"):
        if key in usage and not isinstance(usage[key], dict):
            normalized["usage_validation_errors"].append(f"{key}_malformed")
    return normalized
