"""BytePlus ModelArk direct Chat API (ap-southeast-1), not Volcengine Ark.

Wire provenance and operational constraints: docs/providers/BYTEPLUS.md.
Shared transport/receipts are imported inside calls to avoid an agents cycle.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import quote, quote_plus

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "byteplus"
API_KEY_ENV = "BYTEPLUS_API_KEY"
ALIASES = {"byteplus", "byteplus-modelark", "byteplus-ark", "modelark"}
CHAT_ENDPOINT = "https://ark.ap-southeast.bytepluses.com/api/v3/chat/completions"
ENDPOINT_KIND = "byteplus_modelark_chat_completions"
PARSER_VERSION = "byteplus-modelark-chat-raw-v1"


def canonical_provider(value: str) -> str | None:
    return PROVIDER_ID if value.strip().lower().replace("_", "-") in ALIASES else None


def model_error(model: Any) -> str | None:
    if not isinstance(model, str) or not model.strip():
        return "BytePlus requires an explicit model or ep-* endpoint ID"
    return None


def configuration_error(model: Any, runtime: ProviderRuntimeConfig | None) -> str | None:
    error = model_error(model)
    if error:
        return error
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        return "BytePlus does not support the selected token reasoning budget; no request submitted"
    return None


def _redact_echoes(value: Any, credentials: set[str]) -> Any:
    if isinstance(value, str):
        # Syntax checks cannot detect an opaque key, including inside an ID.
        # Null removes tainted identity without inventing a replacement ID.
        return None if any(secret in value for secret in credentials) else value
    if isinstance(value, dict):
        return {key: _redact_echoes(item, credentials) for key, item in value.items()
                if not any(secret in key for secret in credentials)}
    if isinstance(value, list):
        return [_redact_echoes(item, credentials) for item in value]
    return value


def _private_receipt(receipt: dict[str, Any] | None,
                     credentials: set[str]) -> dict[str, Any] | None:
    if receipt is None:
        return None
    result: dict[str, Any] = _redact_echoes(receipt, credentials)
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams.agents import _normalize_usage

    # Only documented Ark fields count. completion_tokens includes reasoning;
    # never accept an extension claiming otherwise or harvest raw private data.
    mapped: dict[str, Any] = {
        key: usage[key] for key in (
            "prompt_tokens", "completion_tokens", "total_tokens",
        ) if isinstance(usage, dict) and key in usage
    }
    for detail, field in (("prompt_tokens_details", "cached_tokens"),
                          ("completion_tokens_details", "reasoning_tokens")):
        nested = usage.get(detail) if isinstance(usage, dict) else None
        if isinstance(nested, dict) and field in nested:
            mapped[detail] = {field: nested[field]}
    return _normalize_usage("openai", mapped)


def error_kind(data: Any, status: int | None) -> str:
    from eslams.agents import _provider_error_kind

    error = data.get("error") if isinstance(data, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str) and (status is None or status == 400) and (
        code == "SensitiveContentDetected"
        or code.startswith(("InputTextSensitiveContentDetected",
                            "OutputTextSensitiveContentDetected"))
    ):
        return "provider_refused"
    if status is not None:
        return _provider_error_kind(status)
    kind = error.get("type") if isinstance(error, dict) else None
    codes = {
        "AuthenticationError": 401, "AccessDenied": 403,
        "InvalidEndpointOrModel.NotFound": 404, "ModelNotOpen": 404,
        "InvalidEndpointOrModel.ModelIDAccessDisabled": 404,
        "MissingParameter": 400, "InvalidParameter": 400,
        "InternalServiceError": 500,
    }
    types = {"BadRequest": 400, "Unauthorized": 401, "Forbidden": 403,
             "NotFound": 404, "TooManyRequests": 429, "InternalServerError": 500}
    code_status = (
        codes.get(code) if isinstance(code, str) and code in codes
        else types.get(kind) if isinstance(kind, str) else None
    )
    return _provider_error_kind(code_status) if code_status is not None else "provider_unavailable"


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    error = configuration_error(agent.model, agent.runtime_config)
    if error:
        raise ProviderCallError(
            error, provider=PROVIDER_ID, model=agent.model, error_kind="provider_request_rejected",
        )
    # Snapshot only relevant credentials for this invocation. ARK_API_KEY is
    # redaction-only; it still cannot authenticate this adapter. The standard
    # key may differ from the active custom api_key_env credential.
    credentials = {value for value in (
        api_key, os.getenv(API_KEY_ENV, "").strip(), os.getenv("ARK_API_KEY", "").strip(),
    ) if value}
    credentials |= {encoded for value in credentials for encoded in (
        quote(value, safe=""), quote_plus(value, safe=""), json.dumps(value)[1:-1],
    )}
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        exc.receipt = _private_receipt(exc.receipt, credentials)
        if any(secret in str(exc) for secret in credentials):
            exc.args = ("BytePlus returned a private diagnostic; details withheld",)
        raise exc from None
    receipt = _private_receipt(receipt, credentials) or {}
    # Use the same JSON extraction as action parsing: Unicode escapes must not
    # turn an apparently clean raw string into a credential-bearing explanation.
    try:
        decoded_text = json.dumps(extract_json(text), ensure_ascii=False)
    except (ValueError, RecursionError):
        decoded_text = ""
    if any(secret in text or secret in decoded_text for secret in credentials):
        receipt["outcome"] = "provider_response_schema_mismatch"
        raise ProviderCallError(
            "BytePlus echoed a credential in action text; no action accepted",
            provider=PROVIDER_ID, model=agent.model, error_kind="provider_response_schema_mismatch",
            receipt=receipt,
        )
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [{"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                     {"role": "user", "content": prompt}],
        "stream": False,
    }
    if agent._effective_max_output_tokens() is not None:
        # Ark max_tokens may exclude reasoning; max_completion_tokens bounds
        # the complete output when the operator explicitly chooses a limit.
        payload["max_completion_tokens"] = agent._effective_max_output_tokens()
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime:
        if runtime.reasoning != "auto":
            payload["thinking"] = {"type": runtime.reasoning}
        if runtime.reasoning_effort is not None:
            payload["reasoning_effort"] = runtime.reasoning_effort
    response = _post_json(
        _provider_endpoint(CHAT_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    resolved = data.get("model")
    # An ep-* deployment is mutable configuration, not an attestation of weights.
    if isinstance(resolved, str) and resolved.startswith("ep-"):
        resolved = None
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=resolved,
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )

    def fail(kind: str, message: str) -> NoReturn:
        receipt["outcome"] = kind
        raise ProviderCallError(
            message, error_kind=kind, provider=PROVIDER_ID, model=agent.model,
            receipt=receipt,
        )

    if "error" in data:
        # An error envelope's telemetry is diagnostic, not attested weights or
        # verified billing. Reuse the shared error custody projection.
        request_id = receipt["request_id"]
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=error_kind(data, None),
            usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
        )
        receipt["request_id"] = request_id
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["finish_status"] = "failed"
        fail(error_kind(data, None), "BytePlus reported an error in the response body")
    service = data.get("service_status", {})
    if not isinstance(service, dict):
        fail("provider_response_schema_mismatch", "BytePlus returned malformed service status")
    fallback = service.get("model_fallback", {})
    if not isinstance(fallback, dict) or (
        "fallback_triggered" in fallback and not isinstance(fallback["fallback_triggered"], bool)
    ):
        fail("provider_response_schema_mismatch", "BytePlus returned malformed fallback status")
    if fallback.get("fallback_triggered") is True or (
        isinstance(resolved, str) and not agent.model.startswith("ep-") and resolved != agent.model
    ):
        fail("provider_request_rejected", "BytePlus reported model fallback or a different model")
    if data.get("object") != "chat.completion":
        fail("provider_response_schema_mismatch", "BytePlus returned an invalid completion object")
    choices = data.get("choices")
    if (not isinstance(choices, list) or len(choices) != 1
            or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch", "BytePlus returned an invalid choices envelope")
    choice = choices[0]
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls",
    } else "unknown"
    message = choice.get("message")
    if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        receipt["finish_status"] = "refused"
        fail("provider_refused", "BytePlus refused or filtered the action")
    if reason == "length":
        receipt["finish_status"] = "incomplete"
        fail("provider_output_truncated", "BytePlus truncated the output; no action accepted")
    if reason != "stop":
        receipt["finish_status"] = "incomplete"
        fail("provider_response_schema_mismatch", "BytePlus did not return a completed text action")
    if (not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or not isinstance(message.get("content"), str)
            or not message["content"].strip()):
        fail("provider_response_schema_mismatch", "BytePlus returned no assistant text action")
    receipt["finish_status"] = "completed"
    # reasoning_content and encrypted_content are deliberately never exposed.
    return str(message["content"]), receipt
