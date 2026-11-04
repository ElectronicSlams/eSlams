"""Direct Spark HTTP inference; protocol research: docs/providers/IFLYTEK.md."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "iflytek"
ALIASES = {"spark", "iflytek-spark", "xfyun"}
V1_ENDPOINT = "https://spark-api-open.xf-yun.com/v1/chat/completions"
X2_ENDPOINT = "https://spark-api-open.xf-yun.com/x2/chat/completions"
V1_MODELS = {"lite", "generalv3", "pro-128k", "generalv3.5", "max-32k", "4.0Ultra"}


def canonical_provider(provider: str) -> str:
    return PROVIDER_ID if provider in ALIASES else provider


def normalize_usage(value: Any) -> dict[str, Any]:
    """Keep only documented counters; never derive missing totals or reasoning."""
    usage = value if isinstance(value, dict) else {}
    errors: list[str] = []

    def counter(name: str) -> int | None:
        raw = usage.get(name)
        if raw is None:
            return None
        if type(raw) is int and raw >= 0:
            return raw
        errors.append(f"invalid_{name}")
        return None

    prompt, completion, total = (
        counter("prompt_tokens"), counter("completion_tokens"), counter("total_tokens")
    )
    if (prompt is not None and completion is not None and total is not None
            and total != prompt + completion):
        errors.append("provider_total_tokens_inconsistent")
    # Search expansion has no proven mapping to the Core token categories.
    search = counter("search_prompt_tokens")
    if search:
        errors.append("search_prompt_tokens_accounting_unsupported")
    return {
        "input_tokens": prompt, "output_tokens": completion, "total_tokens": total,
        "cached_input_tokens": None, "cache_read_input_tokens": None,
        "cache_write_input_tokens": None, "reasoning_tokens": None,
        "reasoning_included_in_output": None, "cached_input_is_subset": None,
        "total_tokens_source": "provider" if total is not None else "unavailable",
        "usage_source": "provider", "usage_validation_errors": sorted(set(errors)),
    }


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Local import keeps shared transport/receipt ownership in the existing runtime.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
        _retry_after_seconds,
    )

    runtime = agent.runtime_config
    model = agent.model

    def reject(message: str) -> NoReturn:
        raise ProviderCallError(message, error_kind="provider_request_rejected",
                                provider=PROVIDER_ID, model=model)

    if model != "spark-x" and model not in V1_MODELS:
        reject("unverified Spark model/endpoint pair; no request submitted")
    is_x2 = model == "spark-x"
    if runtime and any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        reject("Spark supports thinking mode, not reasoning effort or token budget controls")
    if not is_x2 and runtime and runtime.reasoning == "enabled":
        reject("this Spark v1 route has no documented thinking control")
    temperature = agent.temperature
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature) or not 0 <= temperature <= 2
        or (is_x2 and temperature == 0)
    ):
        reject("temperature is outside the documented Spark range")

    # X2 omits system; v1 documents system support only for Max/Ultra.
    # A user message preserves the generic instructions and full request on all routes.
    messages = [{"role": "user", "content": f"{_SYSTEM_INSTRUCTIONS}\n\n{prompt}"}]
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if agent._request_max_output_tokens is not None:
        payload["max_tokens"] = agent._request_max_output_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if is_x2 and runtime and runtime.reasoning != "auto":
        payload["thinking"] = {"type": runtime.reasoning}
    # v1 enables built-in search by default. Disable it for text-only inference;
    # no provider tools, implicit retrieval, or search expansion is requested.
    if model != "lite":
        payload["tools"] = [{"type": "web_search", "web_search": {"enable": False}}]

    response = _post_json(
        _provider_endpoint(X2_ENDPOINT if is_x2 else V1_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{model}",
        handle_http_errors=False,
    )
    data = _response_json_with_receipt(response, provider=PROVIDER_ID, model=model,
                                      capabilities=agent.capabilities, runtime_config=runtime)
    receipt = _receipt(
        provider=PROVIDER_ID, model=model, response=response,
        provider_response_id=data.get("sid"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )

    def fail(kind: str, message: str) -> NoReturn:
        receipt["outcome"] = kind
        raise ProviderCallError(message, status_code=response.status_code, error_kind=kind,
                                provider=PROVIDER_ID, model=model, receipt=receipt,
                                retry_after_seconds=_retry_after_seconds(response))

    error = data.get("error")
    code = error.get("code") if isinstance(error, dict) else data.get("code")
    business_error = code is not None and (type(code) is not int or code != 0)
    if response.status_code >= 400 or error is not None or business_error:
        # Error accounting is quarantined using the shared error-body policy.
        kind = (_provider_error_kind(response.status_code) if response.status_code >= 400
                else "provider_unavailable")
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
            retry_after_seconds=_retry_after_seconds(response),
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["provider_response_id"] = _http_error_identifier(data.get("sid"))
        receipt["request_id"] = _http_error_identifier(response.headers.get("x-request-id"))
        receipt["gateway_request_id"] = _http_error_identifier(
            response.headers.get("cf-aig-request-id")
            or response.headers.get("x-gateway-request-id"),
        )
    else:
        kind = "provider_unavailable"

    if code is not None and type(code) is not int:
        fail("provider_response_schema_mismatch", "Spark returned a malformed business code")
    if code in {10013, 10014, 10019}:
        fail("provider_refused", "Spark refused or filtered the request")
    if code in {10007, 11201, 11202, 11203}:
        kind = "provider_rate_limited"
    elif code == 11200:
        kind = "provider_permission_failed"
    elif code == 10907:
        kind = "provider_request_rejected"
    if response.status_code >= 400 or error is not None or code not in {None, 0}:
        # Spark documents quota/concurrency errors, but does not guarantee safe
        # replay. Even opt-in retry settings never replay this accepted envelope.
        fail(kind, "Spark returned an HTTP or business error")
    if type(data.get("code")) is not int or data["code"] != 0:
        fail("provider_response_schema_mismatch", "Spark success code is missing")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch", "Spark response must contain one choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        fail("provider_response_schema_mismatch", "Spark response has no message")
    reason = choice.get("finish_reason")
    status = data.get("status")
    receipt["finish_reason"] = reason if reason in ("stop", "length", "content_filter") else None
    receipt["finish_status"] = "completed" if status == "complete" else None
    if reason == "content_filter" or message.get("refusal"):
        fail("provider_refused", "Spark refused or filtered the response")
    if reason == "length":
        fail("provider_output_truncated", "Spark response was truncated; no action accepted")
    if status not in (None, "complete") or reason not in (None, "stop"):
        fail("provider_interrupted", "Spark response did not complete; no action accepted")
    if message.get("tool_calls") or choice.get("error") or message.get("security_suggest"):
        fail("provider_refused", "Spark returned tools, an error, or filtered content")
    text = message.get("content")
    if message.get("role") != "assistant" or not isinstance(text, str) or not text.strip():
        fail("provider_response_schema_mismatch", "Spark response has no assistant answer text")
    # reasoning_content is private, is never parsed as an action, and is not
    # copied into receipts, public explanations, or response metadata.
    return text, receipt
