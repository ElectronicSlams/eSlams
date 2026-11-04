"""Huawei MaaS direct text inference; China Guiyang contract, verified 2026-11-04.

This is not ModelArts deployment management, OpenRouter, or a weights runner.
See docs/providers/HUAWEI.md for the official sources and scope.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, NoReturn

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

CHAT_COMPLETIONS_ENDPOINT = "https://api.modelarts-maas.com/openai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.modelarts-maas.com/v2/models"
API_KEY_ENV = "HUAWEI_MAAS_API_KEY"
DOCUMENTATION = "https://support.huaweicloud.com/model-call-maas/model-call-021.html"
PANGU_MODELS = ("openpangu-2.0-pro", "openpangu-2.0-flash")


def validate_config(model: str, runtime: ProviderRuntimeConfig) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Huawei requires an explicit nonblank model ID")
    if model != model.strip():
        raise ValueError("Huawei model ID must not have surrounding whitespace")
    if any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Huawei Pangu supports a thinking switch, not effort or token budgets")
    if runtime.reasoning != "auto" and model not in PANGU_MODELS:
        raise ValueError("Huawei thinking controls are verified only for the documented Pangu IDs")
    if runtime.gateway_base_url is not None or runtime.gateway_mode not in {
        "direct_provider", "disabled",
    }:
        raise ValueError("Huawei adapter requires the documented direct Guiyang endpoint")
    if runtime.history_window_turns is not None:
        raise ValueError("Huawei adapter preserves full history; history windows are unsupported")
    if runtime.openrouter_provider_order:
        raise ValueError("Huawei direct inference does not support broker routing")


def model_records() -> list[dict[str, Any]]:
    return [{
        "provider": "huawei", "model": model, "game_agent_supported": True,
        "endpoints": [CHAT_COMPLETIONS_ENDPOINT], "supports_temperature": True,
        "supports_reasoning": True, "supported_reasoning_modes": ["native-default", "on", "off"],
        "accepted_control_fields": ["chat_template_kwargs.thinking"],
        "default_reasoning_track": "native-default", "reasoning_track_kind": "provider_native",
        "sources": [DOCUMENTATION], "last_verified_at": "2026-11-04",
        "lifecycle": "account-dependent", "available_from_api": None,
    } for model in PANGU_MODELS]


def normalize_usage(usage: Any) -> dict[str, Any]:
    # Only documented fields can become accounting. Do not infer missing counts.
    from eslams.agents import _normalize_usage

    source = usage if isinstance(usage, dict) else {}
    wire = {key: source[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in source}
    for name, field in (("prompt_tokens_details", "cached_tokens"),
                        ("completion_tokens_details", "reasoning_tokens")):
        details = source.get(name)
        if isinstance(details, dict) and field in details:
            wire[name] = {field: details[field]}
    normalized = _normalize_usage("openai", wire)
    if normalized["total_tokens_source"] != "provider":
        normalized.update(total_tokens=None, total_tokens_source="unavailable")
    return normalized


def credential_values(primary: str, environment_name: str) -> tuple[str, ...]:
    """Snapshot configured provider credentials for echo checks, without logging them."""
    from eslams.provider_preflight import DEFAULT_PROVIDER_ENV

    names = {*DEFAULT_PROVIDER_ENV.values(), API_KEY_ENV, environment_name}
    # Custom provider credentials conventionally use *_API_KEY, including
    # alternate Huawei keys which discovery does not itself authenticate with.
    names.update(name for name in os.environ if name.endswith("_API_KEY"))
    values = {primary}
    values.update(value for name in names if (value := os.environ.get(name, "").strip()))
    return tuple(value for value in values if value)


def contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        # Check Unicode JSON escapes even in prose surrounding the action JSON;
        # the shared action parser may accept that prose and retain raw text.
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), value)
        return any(credential in value or credential in decoded for credential in credentials)
    if isinstance(value, list):
        return any(contains_credential(item, credentials) for item in value)
    if isinstance(value, dict):
        return any(contains_credential(key, credentials) or contains_credential(item, credentials)
                   for key, item in value.items())
    return False


def _without_credentials(value: Any, credentials: tuple[str, ...]) -> Any:
    """Discard credential-bearing identity/telemetry, including wrapped echoes."""
    if isinstance(value, str):
        return None if contains_credential(value, credentials) else value
    if isinstance(value, list):
        return [_without_credentials(item, credentials) for item in value]
    if isinstance(value, dict):
        return {key: _without_credentials(item, credentials) for key, item in value.items()
                if not contains_credential(key, credentials)}
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy imports keep provider policy out of the shared adapter implementation.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config or ProviderRuntimeConfig()
    validate_config(agent.model, runtime)
    credentials = credential_values(api_key, agent.api_key_env)
    payload: dict[str, Any] = {
        "model": agent.model, "stream": False,
        "messages": [{"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                     {"role": "user", "content": prompt}],
    }
    if runtime.reasoning != "auto":
        payload["chat_template_kwargs"] = {"thinking": runtime.reasoning == "enabled"}
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if agent._effective_max_output_tokens() is not None:
        payload["max_completion_tokens"] = agent._effective_max_output_tokens()
    try:
        response = _post_json(
            CHAT_COMPLETIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"huawei:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider="huawei", model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        receipt = _without_credentials(_receipt(
            provider="huawei", model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
        ), credentials)
        # Sanitized-away model evidence must never retain an identity claim.
        if receipt["locked_model_id"] is None:
            receipt["model_identity_source"] = None
        try:
            text = _text(data, agent.model, credentials, receipt)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _without_credentials(exc.receipt, credentials)
        # Huawei error envelopes do not establish safe rejection replay semantics.
        exc.retry_permitted = False
        raise exc from None
    except TimeoutError:
        # Shared transport already supplies a generic message. Suppress private
        # underlying transport exceptions when tracebacks are rendered.
        raise TimeoutError("provider timed out") from None


def _text(
    data: dict[str, Any], model: str, credentials: tuple[str, ...], receipt: dict[str, Any],
) -> str:
    from eslams.agents import ProviderCallError
    from eslams.model_actions import extract_json

    def reject(kind: str = "provider_response_schema_mismatch") -> NoReturn:
        raise ProviderCallError(
            "Huawei response did not establish a completed text action", error_kind=kind,
            provider="huawei", model=model,
        )

    if any(key in data for key in ("error", "error_code", "error_msg")):
        reject("provider_unavailable")
    resolved = data.get("model")
    if resolved is not None and (not isinstance(resolved, str) or resolved != model):
        reject()
    choices = data.get("choices")
    if (data.get("object") != "chat.completion"
            or not isinstance(choices, list) or len(choices) != 1):
        reject()
    choice = choices[0]
    if not isinstance(choice, dict) or type(choice.get("index")) is not int or choice["index"] != 0:
        reject()
    message = choice.get("message")
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if reason in ("stop", "length", "tool_calls") else "unknown"
    if reason == "length":
        reject("provider_output_truncated")
    if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        reject("provider_refused")
    if reason == "tool_calls" or (isinstance(message, dict) and message.get("tool_calls")):
        reject("provider_request_rejected")
    if reason != "stop" or not isinstance(message, dict) or message.get("role") != "assistant":
        reject()
    content = message.get("content")
    if (not isinstance(content, str) or not content.strip()
            or contains_credential(content, credentials)):
        reject()
    # JSON escapes in action fields must not decode into a credential later.
    action_payload = extract_json(content)
    if contains_credential(action_payload, credentials):
        reject()
    # reasoning_content is private and can never be an action-text source.
    receipt["finish_status"] = "completed"
    return content
