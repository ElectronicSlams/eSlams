"""NAVER Cloud CLOVA Studio native, non-streaming Chat Completions v3.

Contract sources and regional limitations: docs/providers/NAVER.md.
No SDK, router, tool execution, model substitution, or inferred billing.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import quote

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "naver"
API_KEY_ENV = "CLOVASTUDIO_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://clovastudio.stream.ntruss.com/v3/chat-completions"


def validate_settings(model: str, runtime: ProviderRuntimeConfig) -> None:
    if (not isinstance(model, str) or not model.strip() or model != model.strip()
            or model in {".", ".."} or any(ord(char) < 32 for char in model)):
        raise ValueError("NAVER requires an explicit nonblank model ID without outer whitespace")
    if runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None:
        raise ValueError("NAVER does not support reasoning token budgets")
    effort = runtime.reasoning_effort
    if effort is not None and effort not in {"none", "low", "medium", "high"}:
        raise ValueError("NAVER reasoning effort must be none, low, medium, or high")
    if model != "HCX-007" and (effort is not None or runtime.reasoning != "auto"):
        raise ValueError("NAVER reasoning controls are documented only for HCX-007")
    if runtime.reasoning == "enabled" and effort == "none":
        raise ValueError("NAVER enabled reasoning conflicts with effort none")


def _credential_values(api_key: str) -> tuple[str, ...]:
    # Legacy keys are never sent by this adapter. Still protect configured
    # values if a provider/gateway echoes them in unrelated response fields.
    names = (API_KEY_ENV, "NCP_CLOVASTUDIO_API_KEY", "NCP_APIGW_API_KEY")
    values = {api_key, *(os.getenv(name, "").strip() for name in names)}
    return tuple(sorted(values - {""}, key=len, reverse=True))


def _without_credentials(value: Any, credentials: tuple[str, ...]) -> Any:
    """Discard echoed identifiers instead of creating fictitious redacted identities."""
    if isinstance(value, str):
        return None if any(credential in value for credential in credentials) else value
    if isinstance(value, dict):
        return {key: _without_credentials(item, credentials) for key, item in value.items()
                if not any(credential in key for credential in credentials)}
    if isinstance(value, list):
        return [_without_credentials(item, credentials) for item in value]
    return value


def _contains_credentials(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(credential in value for credential in credentials)
    if isinstance(value, dict):
        return any(
            _contains_credentials(key, credentials) or _contains_credentials(item, credentials)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_credentials(item, credentials) for item in value)
    return False


def wire_usage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    details = value.get("completionTokensDetails")
    return {
        "input_tokens": value.get("promptTokens"),
        "output_tokens": value.get("completionTokens"),
        "total_tokens": value.get("totalTokens"),
        "reasoning_tokens": details.get("thinkingTokens") if isinstance(details, dict) else None,
        "reasoning_included_in_output": True,
    }


def call_provider(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    # Local import keeps the shared agent's dispatch independent of provider internals.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
    )
    from eslams.model_actions import extract_json

    runtime = agent.runtime_config or ProviderRuntimeConfig()
    validate_settings(agent.model, runtime)
    credentials = _credential_values(api_key)
    payload: dict[str, Any] = {
        "messages": [{"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                     {"role": "user", "content": prompt}],
    }
    effort = runtime.reasoning_effort
    if agent.model == "HCX-007":
        if runtime.reasoning == "disabled":
            effort = "none"
        elif runtime.reasoning == "enabled" and effort is None:
            effort = "low"  # Documented native enabled default, never arena-derived.
        if effort is not None:
            payload["thinking"] = {"effort": effort}
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["maxCompletionTokens" if agent.model == "HCX-007" else "maxTokens"] = limit
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    try:
        response = _post_json(
            _provider_endpoint(
                f"{CHAT_COMPLETIONS_ENDPOINT}/{quote(agent.model, safe='')}", runtime,
            ),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "Accept": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"naver:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider="naver", model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        result = data.get("result")
        result = result if isinstance(result, dict) else {}
        receipt = _receipt(
            provider="naver", model=agent.model, response=response,
            provider_response_id=None,
            # v3 names the model in the direct endpoint; it has no response model field.
            resolved_model=agent.model if not runtime.gateway_base_url else None,
            model_identity_source="pinned_endpoint" if not runtime.gateway_base_url else None,
            usage=wire_usage(result.get("usage")),
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        receipt["request_id"] = _http_error_identifier(
            response.headers.get("x-ncp-clovastudio-request-id")
        ) or receipt["request_id"]
        receipt["endpoint_region"] = "Korea" if not runtime.gateway_base_url else None
        receipt = _without_credentials(receipt, credentials)
        status = data.get("status")
        code = status.get("code") if isinstance(status, dict) else None

        def fail(kind: str) -> NoReturn:
            raise ProviderCallError(
                "NAVER response did not establish a completed text answer",
                provider="naver", model=agent.model, error_kind=kind,
                status_code=response.status_code, receipt={**receipt, "outcome": kind},
            )

        if code != "20000" or not response.is_success:
            # Error telemetry is observed, never trusted as billing or model attestation.
            receipt.update(locked_model_id=None, model_identity_source=None)
            receipt["pricing_provenance"] = {
                "source": "unverified_provider_error_body", "accounting_status": "quarantined",
            }
            kind = ("provider_timeout" if code == "40800" else
                    _provider_error_kind(int(code[:3]))
                    if isinstance(code, str) and len(code) == 5 and code.isascii()
                    and code.isdigit() and int(code[:3]) >= 400
                    else "provider_response_schema_mismatch")
            fail(kind)
        reason = result.get("finishReason")
        receipt["finish_reason"] = reason if reason in ("length", "stop", "tool_calls") else None
        receipt["finish_status"] = "completed" if reason == "stop" else "incomplete"
        if reason == "length":
            fail("provider_output_truncated")
        if reason == "tool_calls":
            fail("provider_request_rejected")
        if reason != "stop":
            fail("provider_response_schema_mismatch")
        message = result.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            fail("provider_response_schema_mismatch")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip() or message.get("toolCalls"):
            fail("provider_response_schema_mismatch")
        # Scan the same decoded action envelope used by Core, including JSON escapes.
        try:
            echoed = (_contains_credentials(text, credentials)
                      or _contains_credentials(extract_json(text), credentials))
        except (ValueError, RecursionError):
            fail("provider_response_schema_mismatch")
        if echoed:
            fail("provider_response_schema_mismatch")
        return text, receipt
    except ProviderCallError as exc:
        # A foreign/unknown error envelope cannot authorize replay of native calls.
        exc.retry_permitted = False
        if exc.receipt is not None:
            exc.receipt = _without_credentials(exc.receipt, credentials)
        message = str(exc)
        for credential in credentials:
            message = message.replace(credential, "[REDACTED]")
        exc.args = (message,)
        raise exc from None
    except TimeoutError:
        raise TimeoutError("NAVER provider request timed out") from None
