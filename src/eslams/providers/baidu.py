"""Baidu Qianfan direct, non-streaming Chat Completions adapter.

Official contract and fixture provenance: docs/BAIDU_QIANFAN.md.
Import shared transport/receipt helpers only at call time to avoid a cycle.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import quote, quote_plus

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "baidu"
API_KEY_ENV = "QIANFAN_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://qianfan.baidubce.com/v2/chat/completions"
MODELS_ENDPOINT = "https://qianfan.baidubce.com/v2/models"

# Frozen documented control support, not a model-availability catalogue. Do not
# guess controls for new names, model families, aliases or fine-tuned endpoints.
_THINKING_MODELS = frozenset({
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3.2", "kimi-k2.5",
    "glm-5.3-flash", "glm-5.3", "glm-5.2-fast", "glm-5.2", "glm-5.1", "glm-5",
})
_ENABLE_THINKING_MODELS = frozenset({
    "qwen3-32b", "qwen3-14b", "qwen3-8b", "ernie-4.5-turbo-vl-preview",
    "ernie-4.5-turbo-vl-32k-preview", "ernie-4.5-vl-28b-a3b", "ernie-5.0-thinking-preview",
})
_BUDGET_MODELS = frozenset({"ernie-5.1", "ernie-5.0-thinking-preview", "deepseek-v3.2-think"})
_EFFORT_MODELS = frozenset({"deepseek-v4-pro", "deepseek-v4-flash"})


def validate_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Baidu Qianfan requires an explicit nonblank model API name")


def credential_values(api_key: str, api_key_env: str = API_KEY_ENV) -> tuple[str, ...]:
    """Protect the selected key and configured Qianfan credentials, never log them.

    Legacy/secondary keys are redaction inputs only; this adapter authenticates
    with exactly the caller-selected API key, without credential fallback.
    """
    values = {api_key}
    for name in (api_key_env, API_KEY_ENV, "QIANFAN_SECRET_KEY", "QIANFAN_AK", "QIANFAN_SK",
                 "BAIDU_API_KEY", "BAIDU_SECRET_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            values.add(value)
    return tuple(sorted({variant for value in values if value for variant in (
        value, quote(value, safe=""), quote_plus(value, safe=""),
    )}, key=len, reverse=True))


def contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    return isinstance(value, str) and any(secret in value for secret in credentials)


def _redact_public(value: Any, credentials: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in credentials:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_redact_public(item, credentials) for item in value]
    if isinstance(value, dict):
        result = {_redact_public(key, credentials): _redact_public(item, credentials)
                  for key, item in value.items()}
        for name in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id"):
            if contains_credential(value.get(name), credentials):
                result[name] = None
        if "locked_model_id" in value and result.get("locked_model_id") is None:
            result["model_identity_source"] = None
        return result
    return value


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Project documented fields; absent counts remain unknown, including total."""
    from eslams.agents import _empty_usage, _normalize_usage

    if not isinstance(usage, dict):
        return _empty_usage()
    projected = {key: usage[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in usage}
    for details_key, count_key in (
        ("prompt_tokens_details", "cached_tokens"),
        ("completion_tokens_details", "reasoning_tokens"),
    ):
        details = usage.get(details_key)
        if isinstance(details, dict) and count_key in details:
            projected[details_key] = {count_key: details[count_key]}
    # The official deep-thinking guide explicitly includes reasoning in output.
    projected["reasoning_included_in_output"] = True
    result = _normalize_usage("qianfan_wire", projected)
    total = usage.get("total_tokens")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        result.update(total_tokens=None, total_tokens_source="unavailable")
    return result


def _reject(message: str, *, model: str, kind: str = "provider_request_rejected") -> NoReturn:
    from eslams.agents import ProviderCallError

    raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID, model=model)


def reasoning_controls(model: str, runtime: ProviderRuntimeConfig | None) -> dict[str, Any]:
    """Omit native defaults; map only explicit supported operator choices."""
    if runtime is None:
        return {}
    controls: dict[str, Any] = {}
    if runtime.reasoning == "enabled":
        if model in _THINKING_MODELS:
            controls["thinking"] = {"type": "enabled"}
        elif model in _ENABLE_THINKING_MODELS:
            controls["enable_thinking"] = True
        else:
            _reject("Qianfan has no verified enable-thinking control for this model", model=model)
    if runtime.gemini_thinking_budget is not None:
        _reject("Gemini thinking controls are unsupported by Qianfan", model=model)
    if runtime.reasoning_effort is not None:
        if model not in _EFFORT_MODELS or runtime.reasoning_effort not in {"high", "max"}:
            _reject("Qianfan reasoning effort requires a verified model and high or max",
                    model=model)
        controls["reasoning_effort"] = runtime.reasoning_effort
    if runtime.reasoning_budget_tokens is not None:
        if model not in _BUDGET_MODELS or runtime.reasoning_budget_tokens < 100:
            _reject("Qianfan thinking budget requires a verified model and at least 100 tokens",
                    model=model)
        controls["thinking_budget"] = runtime.reasoning_budget_tokens
    return controls


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    """Scrub all receipt paths, including transport and body-parser failures."""
    from eslams.agents import ProviderCallError

    credentials = credential_values(api_key, agent.api_key_env)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _redact_public(exc.receipt, credentials)
        exc.args = tuple(_redact_public(item, credentials) for item in exc.args)
        raise
    receipt = _redact_public(receipt, credentials)
    if contains_credential(text, credentials):
        raise ProviderCallError(
            "Qianfan returned credential material in final text; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=agent.model,
            receipt=receipt,
        )
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    """Use Core's cancellation-aware transport and invocation-scoped receipts."""
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
    validate_model(agent.model)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        **reasoning_controls(agent.model, runtime),
    }
    if agent._request_max_output_tokens is not None:
        payload["max_tokens"] = agent._request_max_output_tokens
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    if data.get("error") is not None:
        # A 2xx envelope is not proof of completion. Error-body observations
        # stay quarantined using the same custody rules as HTTP errors.
        error = data["error"]
        kind = "provider_unavailable"
        if isinstance(error, dict):
            error_type = error.get("type")
            kind = {
                "rate_limit_exceeded": "provider_rate_limited",
                "unsafe_request": "provider_refused",
                "access_denied": "provider_auth_failed",
                "invalid_request_error": "provider_request_rejected",
            }.get(error_type, kind) if isinstance(error_type, str) else kind
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["request_id"] = _http_error_identifier(response.headers.get("x-request-id"))
        raise ProviderCallError(
            "Qianfan reported an error inside the response body", error_kind=kind,
            provider=PROVIDER_ID, model=agent.model, status_code=response.status_code,
            retry_after_seconds=_retry_after_seconds(response), receipt=receipt,
        )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    try:
        text = _completed_text(data, receipt, agent.model)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _completed_text(data: dict[str, Any], receipt: dict[str, Any], model: str) -> str:
    if data.get("object", "chat.completion") != "chat.completion":
        _reject("Qianfan returned an unexpected response object", model=model,
                kind="provider_response_schema_mismatch")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        _reject("Qianfan response requires exactly one choice", model=model,
                kind="provider_response_schema_mismatch")
    choice = choices[0]
    index = choice.get("index", 0)
    if isinstance(index, bool) or not isinstance(index, int) or index != 0 or choice.get("error"):
        _reject("Qianfan returned an invalid or failed choice", model=model,
                kind="provider_response_schema_mismatch")
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls",
    } else "unknown"
    receipt["finish_status"] = "unknown"
    flag = choice.get("flag", 0)
    if isinstance(flag, bool) or not isinstance(flag, int) or flag not in {0, 1, 2, 3, 4}:
        _reject("Qianfan returned an invalid safety flag", model=model,
                kind="provider_response_schema_mismatch")
    message = choice.get("message")
    if flag or reason == "content_filter" or (
        isinstance(message, dict) and message.get("refusal")
    ):
        receipt["finish_status"] = "refused"
        _reject("Qianfan refused or filtered the response", model=model, kind="provider_refused")
    if reason == "length":
        receipt["finish_status"] = "incomplete"
        _reject("Qianfan token/context constraint interrupted the response; no action accepted",
                model=model, kind="provider_output_truncated")
    if reason == "tool_calls" or isinstance(message, dict) and message.get("tool_calls"):
        receipt["finish_status"] = "incomplete"
        _reject("Qianfan requested unsupported tool execution; no action accepted", model=model)
    if reason != "stop" or not isinstance(message, dict) or message.get("role") != "assistant":
        _reject("Qianfan returned malformed completion fields", model=model,
                kind="provider_response_schema_mismatch")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        _reject("Qianfan response has no final text content", model=model,
                kind="provider_response_schema_mismatch")
    receipt["finish_status"] = "completed"
    # reasoning_content is private and must never be parsed as an action.
    return content
