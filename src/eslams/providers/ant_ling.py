"""Direct Ant Ling API; routed InclusionAI model IDs are separate identities."""

from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import quote, quote_plus

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "ant-group"
API_KEY_ENV = "ANT_LING_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.ant-ling.com/v1/chat/completions"
THINKING_MODELS = frozenset({
    "Ling-3.1-flash", "Ling-3.0-flash", "Ling-3.0-flash-VL", "Ling-3.0-tiny",
})


def validate_config(
    model: str, runtime: ProviderRuntimeConfig, temperature: float | None = None,
) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Ant Ling requires an explicit nonblank model ID")
    if model != model.strip():
        raise ValueError("Ant Ling model ID must not contain surrounding whitespace")
    if model.lower().startswith("inclusionai/"):
        raise ValueError("use the exact direct Ant Ling model ID, not a routed InclusionAI ID")
    if any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Ant Ling supports thinking.type, not reasoning effort or token budgets")
    if runtime.reasoning != "auto" and model not in THINKING_MODELS:
        raise ValueError("Ant Ling thinking control is not documented for this exact model ID")
    if runtime.gateway_base_url or runtime.gateway_mode != "direct_provider":
        raise ValueError("Ant Ling native adapter requires the direct official endpoint")
    if runtime.gateway_auth_mode != "disabled" or runtime.openrouter_provider_order:
        raise ValueError("Ant Ling native adapter does not support gateway or routed controls")
    if runtime.bedrock_region != "us-east-1":
        raise ValueError("Ant Ling has no documented region selector; "
                         "bedrock_region is unsupported")
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature) or not 0 <= temperature <= 1
    ):
        raise ValueError("Ant Ling temperature must be finite and between 0 and 1")


def _credential_forms(api_key: str) -> tuple[str, ...]:
    # Additional configured values are redaction-only. The selected bearer is
    # still the sole authentication source; no alias enables key fallback.
    configured = [api_key, *(os.getenv(name, "").strip() for name in (
        API_KEY_ENV, "BAILING_API_KEY", "OPENAI_API_KEY",
    ))]
    return tuple(dict.fromkeys(
        form for secret in configured if secret
        for form in (secret, quote(secret, safe=""), quote_plus(secret))
    ))


def _contains_key(value: str, credentials: tuple[str, ...]) -> bool:
    return any(secret in value for secret in credentials)


def _echoes_key(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return _contains_key(value, credentials)
    if isinstance(value, list):
        return any(_echoes_key(item, credentials) for item in value)
    if isinstance(value, dict):
        return any(_contains_key(key, credentials) or _echoes_key(item, credentials)
                   for key, item in value.items())
    return False


def _clean_receipt(value: Any, credentials: tuple[str, ...]) -> Any:
    """Drop credential-bearing metadata, including otherwise valid identifier strings.

    A redaction marker is not model identity evidence. Do not persist the key in
    the agent or in a receipt sanitizer closure after the call finishes.
    """
    if isinstance(value, str):
        return None if _contains_key(value, credentials) else value
    if isinstance(value, list):
        return [_clean_receipt(item, credentials) for item in value]
    if isinstance(value, dict):
        cleaned = {
            key: _clean_receipt(item, credentials) for key, item in value.items()
            if not _contains_key(key, credentials)
        }
        if str(cleaned.get("total_tokens_source", "")).startswith("derived_"):
            cleaned["total_tokens"] = None
            cleaned["total_tokens_source"] = "unavailable"
        return cleaned
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy import keeps provider metadata/validation usable without an agents cycle.
    from eslams.agents import ProviderCallError

    credentials = _credential_forms(api_key)
    try:
        return _call(agent, api_key, prompt, credentials=credentials)
    except TimeoutError:
        raise TimeoutError("Ant Ling provider timed out") from None
    except ProviderCallError as exc:
        receipt = _clean_receipt(exc.receipt, credentials)
        kind = ("provider_refused" if exc.status_code == 428 else
                "provider_timeout" if exc.status_code == 504 else exc.error_kind)
        if isinstance(receipt, dict):
            receipt["outcome"] = kind
        if isinstance(receipt, dict) and receipt.get("locked_model_id") is None:
            receipt["model_identity_source"] = None
        # The direct docs do not attest an error-body envelope proving rejection
        # before generation. No HTTP/body failure is safely replayable here.
        raise ProviderCallError(
            "Ant Ling request failed; inspect the sanitized receipt outcome",
            status_code=exc.status_code, error_kind=kind,
            retry_after_seconds=exc.retry_after_seconds, provider=PROVIDER_ID,
            model=agent.model, receipt=receipt, retry_permitted=False,
        ) from None


def _call(
    agent: ModelProviderAgent, api_key: str, prompt: str, *, credentials: tuple[str, ...],
) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _body_error_status,
        _capture_error_body_observations,
        _normalize_usage,
        _post_json,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
    )
    from eslams.model_actions import extract_json

    runtime = agent.runtime_config
    assert runtime is not None
    validate_config(agent.model, runtime, agent.temperature)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "enable_search": False,
    }
    if runtime.reasoning != "auto":
        payload["thinking"] = {"type": runtime.reasoning}
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if agent._effective_max_output_tokens() is not None:
        payload["max_tokens"] = agent._effective_max_output_tokens()
    response = _post_json(
        CHAT_COMPLETIONS_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    raw_usage = data.get("usage")
    usage = None
    if isinstance(raw_usage, dict):
        usage = {key: raw_usage[key] for key in (
            "prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details",
        ) if key in raw_usage}
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            usage["prompt_tokens_details"] = {
                key: details[key] for key in ("cached_tokens",) if key in details
            }
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=usage, capabilities=agent.capabilities, runtime_config=runtime,
    )
    normalized = _normalize_usage(PROVIDER_ID, usage)
    if normalized.get("usage_validation_errors"):
        receipt["usage"] = normalized
        receipt["usage_unavailable_reason"] = "provider_usage_invalid"
    receipt = _clean_receipt(receipt, credentials)
    if receipt.get("locked_model_id") is None:
        receipt["model_identity_source"] = None

    def reject(kind: str) -> NoReturn:
        raise ProviderCallError(
            "Ant Ling returned no complete text action", error_kind=kind,
            provider=PROVIDER_ID, model=agent.model, receipt={**receipt, "outcome": kind},
        )

    if data.get("error") or data.get("type") == "error":
        receipt["locked_model_id"] = None
        receipt["model_identity_source"] = None
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        code = _body_error_status(data.get("error"))
        reject(_provider_error_kind(code) if code is not None else "provider_unavailable")
    resolved = data.get("model")
    if isinstance(resolved, str) and resolved.strip() and resolved != agent.model:
        reject("provider_response_schema_mismatch")
    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        reject("provider_response_schema_mismatch")
    first = choices[0]
    reason = first.get("finish_reason")
    message = first.get("message")
    receipt["finish_reason"] = reason if reason in ("stop", "length", "content_filter",
                                                        "tool_calls") else "unknown"
    if reason == "length":
        receipt["finish_status"] = "incomplete"
        reject("provider_output_truncated")
    if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        receipt["finish_status"] = "refused"
        reject("provider_refused")
    if reason != "stop" or first.get("error"):
        receipt["finish_status"] = "incomplete"
        reject("provider_response_schema_mismatch")
    if (not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or message.get("function_call")):
        reject("provider_response_schema_mismatch")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip() or _contains_key(text, credentials):
        reject("provider_response_schema_mismatch")
    # A JSON string can hide a credential behind Unicode escapes until the
    # action parser decodes it. Inspect that decoded form before returning text.
    parsed = extract_json(text)
    if _echoes_key(parsed, credentials):
        reject("provider_response_schema_mismatch")
    receipt["finish_status"] = "completed"
    return text, receipt
