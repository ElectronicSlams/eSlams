"""Direct KAT text inference through StreamLake; no Kling media integration.

Wire provenance and deliberate limitations: docs/providers/KUAISHOU.md.
Shared imports stay inside functions because agents dispatches into this module.
"""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, unquote_plus

import httpx

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

ENDPOINTS = {
    "international": "https://vanchin.streamlake.ai/api/gateway/v1/endpoints/chat/completions",
    "cn": "https://wanqing.streamlakeapi.com/api/gateway/v1/endpoints/chat/completions",
}
SOURCES = [
    "https://www.streamlake.ai/document/DOC/mj9z6fh8lxn87i86jrp",
    "https://www.streamlake.ai/document/DOC/mg6k6nlp8j6qxicx4c9",
    "https://www.streamlake.com/document/WANQING/me6z3u08sjus2mzplbj",
]
ERROR_STATUS = {
    "InvalidArgument.Authorization": 401, "Unauthorized": 401,
    "Forbidden": 403, "Forbidden.InsufficientBalance": 403,
    "Forbidden.Frozen": 403, "UnaccessibleUser": 403,
    "ResourceNotFound": 404, "TooManyRequests": 429,
    "InternalError": 500, "InternalServerError": 500,
}


def error_kind(response: httpx.Response, fallback: str, receipt: dict[str, Any]) -> str:
    """Interpret only documented classifiers, never the provider's error prose."""
    from eslams.agents import _http_error_identifier, _strict_provider_json

    try:
        data = _strict_provider_json(response)
    except (ValueError, UnicodeError, RecursionError):
        return fallback
    meta = data.get("ResponseMeta") if isinstance(data, dict) else None
    if isinstance(meta, dict) and receipt.get("request_id") is None:
        receipt["request_id"] = _http_error_identifier(meta.get("RequestId"))
    code = meta.get("ErrorCode") if isinstance(meta, dict) else None
    status = ERROR_STATUS.get(code) if isinstance(code, str) else None
    # Authentication can be documented as HTTP 400; other HTTP statuses remain decisive.
    return "provider_auth_failed" if response.status_code == 400 and status == 401 else fallback


def endpoint() -> str:
    region = os.getenv("ESLAMS_STREAMLAKE_REGION", "international")
    if region not in ENDPOINTS:
        raise ValueError("ESLAMS_STREAMLAKE_REGION must be international or cn")
    return ENDPOINTS[region]


def validate_configuration(
    model: str, runtime: ProviderRuntimeConfig | None, temperature: float | None = None,
) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("StreamLake requires an explicit nonblank model or inference endpoint ID")
    endpoint()
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature) or not 0 <= temperature <= 1
    ):
        raise ValueError("StreamLake temperature must be a finite number between 0 and 1")
    if runtime is None:
        return
    if runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("KAT supports native-default reasoning only; explicit controls unverified")
    if runtime.history_window_turns is not None:
        raise ValueError("StreamLake requires full supplied history")
    if (runtime.gateway_base_url is not None or runtime.gateway_mode != "direct_provider"
            or runtime.gateway_auth_mode != "disabled" or runtime.openrouter_provider_order):
        raise ValueError("StreamLake adapter requires a direct provider route without fallback")


def _configured_credentials(api_key: str) -> tuple[str, ...]:
    """Snapshot credentials for redaction only; secondary keys are never sent."""
    values = {api_key}
    for name, value in os.environ.items():
        sensitive_name = name.endswith((
            "_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIAL", "_CREDENTIALS",
        )) or name == "AWS_BEARER_TOKEN_BEDROCK"
        if sensitive_name and value.strip():
            values.add(value.strip())
    return tuple(values)


def _redact(value: Any, credentials: tuple[str, ...]) -> Any:
    """Drop credential-bearing observations, including opaque IDs without key-like prefixes."""
    if isinstance(value, str):
        forms = (value, unquote(value), unquote_plus(value))
        return None if any(secret in form for secret in credentials for form in forms) else value
    if isinstance(value, dict):
        return {key: _redact(item, credentials) for key, item in value.items()
                if _redact(str(key), credentials) is not None}
    if isinstance(value, list):
        return [_redact(item, credentials) for item in value]
    return value


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams.agents import _dict, _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for target, source in (
        ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        result[target] = _usage_int(usage.get(source), source, errors)
    result["cached_input_tokens"] = _usage_int(
        _dict(usage.get("prompt_tokens_details")).get("cached_tokens"), "cached_tokens", errors,
    )
    result["cache_read_input_tokens"] = result["cached_input_tokens"]
    result["reasoning_tokens"] = _usage_int(
        _dict(usage.get("completion_tokens_details")).get("reasoning_tokens"),
        "reasoning_tokens", errors,
    )
    result["cached_input_is_subset"] = True
    result["total_tokens_source"] = (
        "provider" if result["total_tokens"] is not None else "unavailable"
    )
    # The docs expose reasoning details but do not explicitly attest inclusion.
    # Keep that unknown; never infer missing totals, prices, or zero reasoning.
    if (result["input_tokens"] is not None and result["output_tokens"] is not None
            and result["total_tokens"] is not None
            and result["total_tokens"] != result["input_tokens"] + result["output_tokens"]):
        errors.append("provider_total_tokens_inconsistent")
    if (result["cached_input_tokens"] is not None and result["input_tokens"] is not None
            and result["cached_input_tokens"] > result["input_tokens"]):
        errors.append("cached_input_tokens_exceed_input_tokens")
    result["usage_validation_errors"] = errors
    return result


def _credential_echo(text: str, credentials: tuple[str, ...]) -> bool:
    if _redact(text, credentials) is None:
        return True
    try:
        decoded = extract_json(text)
    except (ValueError, RecursionError):
        return False
    return bool(_redact(decoded, credentials) != decoded)


def _safe_receipt(receipt: dict[str, Any], credentials: tuple[str, ...]) -> dict[str, Any]:
    safe: dict[str, Any] = _redact(receipt, credentials)
    if safe.get("locked_model_id") is None:
        safe["model_identity_source"] = None
    return safe


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
    )

    validate_configuration(agent.model, agent.runtime_config, agent.temperature)
    credentials = _configured_credentials(api_key)
    url = endpoint()
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if agent._effective_max_output_tokens() is not None:
        payload["max_tokens"] = agent._effective_max_output_tokens()
    receipt: dict[str, Any] | None = None
    try:
        response = _post_json(
            url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"{agent.provider}:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=agent.provider, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        if response.status_code != 200:
            raise ProviderCallError("StreamLake returned an unexpected success status",
                                    error_kind="provider_response_schema_mismatch")
        meta = data.get("ResponseMeta")
        if "ResponseMeta" in data or "error" in data:
            # Error envelopes never attest a successful model identity or price.
            code = meta.get("ErrorCode") if isinstance(meta, dict) else None
            code = code if isinstance(code, str) else None
            status = ERROR_STATUS.get(code) if code is not None else None
            if status is None and code is not None and code.startswith("Invalid"):
                status = 400
            kind = _provider_error_kind(status) if status else "provider_unavailable"
            receipt = _failure_receipt(
                provider=agent.provider, model=agent.model, agent_id="", agent_version="",
                turn_id=0, outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
                runtime_config=agent.runtime_config, status_code=response.status_code,
            )
            _capture_error_body_observations(response, provider=agent.provider, receipt=receipt)
            if isinstance(meta, dict):
                receipt["request_id"] = _http_error_identifier(meta.get("RequestId"))
            raise ProviderCallError("StreamLake returned an error envelope", error_kind=kind,
                                    status_code=response.status_code, receipt=receipt)
        receipt = _receipt(
            provider=agent.provider, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=data.get("usage"), capabilities=agent.capabilities,
            runtime_config=agent.runtime_config,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        reason = first.get("finish_reason") if isinstance(first, dict) else None
        receipt["finish_reason"] = (
            reason if reason in ("stop", "length", "content_filter") else None
        )
        receipt["finish_status"] = "completed" if reason == "stop" else "incomplete"
        kind = "provider_response_schema_mismatch"
        if reason == "length":
            kind = "provider_output_truncated"
        elif reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
            kind = "provider_refused"
        elif reason in ("tool_calls", "function_call"):
            kind = "provider_request_rejected"
        elif (data.get("object") == "chat.completion" and reason == "stop"
              and isinstance(first, dict) and type(first.get("index")) is int
              and first["index"] == 0
              and isinstance(message, dict) and message.get("role") == "assistant"
              and not message.get("tool_calls") and not message.get("function_call")):
            text = message.get("content")
            if isinstance(text, str) and text.strip() and not _credential_echo(text, credentials):
                receipt.update(provider_endpoint=url, capability_sources=list(SOURCES))
                return text, _safe_receipt(receipt, credentials)
        raise ProviderCallError("StreamLake response did not contain a complete text answer",
                                error_kind=kind, receipt=receipt)
    except ProviderCallError as exc:
        observed = exc.receipt if exc.receipt is not None else receipt
        safe = _safe_receipt(observed, credentials) if observed is not None else None
        if safe is not None:
            safe.update(
                provider_endpoint=url, capability_sources=list(SOURCES), outcome=exc.error_kind,
            )
        # No documented definitive non-billable rejection/replay guarantee.
        raise ProviderCallError(
            "StreamLake request failed", status_code=exc.status_code, error_kind=exc.error_kind,
            retry_after_seconds=exc.retry_after_seconds, provider=agent.provider, model=agent.model,
            receipt=safe, retry_permitted=False,
        ) from None
