"""Relace Open Models REST adapter; no apply/search harness or SDK defaults."""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote_plus

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "relace"
API_KEY_ENV = "RELACE_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://models.relace.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://models.relace.ai/v1/models"
ENDPOINT_KIND = "relace_chat_completions"
PARSER_VERSION = "relace-chat-completions-raw-v1"

_CREDENTIAL_ENV = re.compile(
    r"^RELACE_.*(?:KEY|TOKEN|SECRET|PASSWORD)(?:_|$)"
    r"|(?:^|_)(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?|ACCESS_KEY|PRIVATE_KEY)(?:_|$)",
    re.IGNORECASE,
)
_CREDENTIAL_TEXT = re.compile(
    r"\brlc-[A-Za-z0-9_-]+|\b(?:sk|key|token)-[A-Za-z0-9_-]{8,}\b"
    r"|\bbearer\s+(?!\[REDACTED\])[^\s,;\"']+"
    r"|\b(?:authorization|x[-_]?api[-_]?key|api[-_]?key|token|secret|password)"
    r"\s*[:=]\s*(?!\[REDACTED\])[^\s,;\"']+"
    r"|[?&;](?:key|access_token|refresh_token)=[^\s&#;]+",
    re.IGNORECASE,
)


def validate_configuration(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Relace requires an explicit nonblank model ID")
    runtime = runtime or ProviderRuntimeConfig()
    if runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Relace supports only native automatic reasoning; controls are unverified")
    if runtime.history_window_turns is not None:
        raise ValueError("Relace requires full supplied history")
    if runtime.gateway_base_url or runtime.gateway_mode != "direct_provider":
        raise ValueError("Relace requires its direct official endpoint")
    if runtime.openrouter_provider_order:
        raise ValueError("Relace does not support OpenRouter routing controls")
    if runtime.gateway_auth_mode != "disabled" or runtime.bedrock_region != "us-east-1":
        raise ValueError("Relace does not support gateway authentication or region controls")


def credential_values(api_key: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(api_key, tuple):
        return api_key
    # Capture once per invocation, including canonical/secondary credentials
    # when the caller uses a custom primary environment name. Values never
    # leave this private comparison set or become transport inputs.
    return tuple({api_key, *(value.strip() for name, value in os.environ.items()
                            if _CREDENTIAL_ENV.search(name) and value.strip())} - {""})


def contains_credential(value: Any, api_key: str | tuple[str, ...]) -> bool:
    """Check decoded strings too, including JSON-escaped text and URL echoes."""
    credentials = credential_values(api_key)
    if isinstance(value, dict):
        return any(contains_credential(key, credentials) or contains_credential(item, credentials)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_credential(item, credentials) for item in value)
    if not isinstance(value, str):
        return False
    decoded = value
    for _ in range(3):
        if any(secret in decoded for secret in credentials) or _CREDENTIAL_TEXT.search(decoded):
            return True
        updated = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)),
                         unquote_plus(decoded))
        if updated == decoded:
            break
        decoded = updated
    try:
        parsed = json.loads(value)
    except (ValueError, RecursionError):
        return False
    return parsed != value and contains_credential(parsed, credentials)


def _safe_receipt(value: Any, api_key: str | tuple[str, ...]) -> Any:
    credentials = credential_values(api_key)
    if isinstance(value, dict):
        result = {key: _safe_receipt(item, credentials) for key, item in value.items()
                  if not contains_credential(key, credentials)}
        if result.get("locked_model_id") is None and "model_identity_source" in result:
            result["model_identity_source"] = None
        return result
    if isinstance(value, list):
        return [_safe_receipt(item, credentials) for item in value]
    return None if contains_credential(value, credentials) else value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Runtime import keeps shared wiring small without making agents import itself.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    validate_configuration(agent.model, agent.runtime_config)
    credentials = credential_values(api_key)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
        "temperature": agent.temperature,
    }
    receipt: dict[str, Any] | None = None
    try:
        response = _post_json(
            CHAT_COMPLETIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"relace:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        # Only documented usage fields are accounting sources. Do not accept
        # arbitrary cost extensions or invented per-model catalogue rates.
        usage = data.get("usage")
        if isinstance(usage, dict):
            usage = {key: usage[key] for key in (
                "prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details",
            ) if key in usage}
            usage["reasoning_included_in_output"] = True
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=usage, capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        receipt = _safe_receipt(receipt, credentials)
        if response.status_code != 200:
            raise ValueError("unexpected completion HTTP status")
        if isinstance(usage, dict) and usage.get("total_tokens") is None and receipt["usage"]:
            # Shared normalization can derive totals for other providers. Here
            # an omitted provider count remains explicitly unobserved.
            receipt["usage"]["total_tokens"] = None
            receipt["usage"]["total_tokens_source"] = None
        if receipt["locked_model_id"] not in (None, agent.model):
            raise ValueError("served model differs from requested model")
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError("expected exactly one completion")
        choice = choices[0]
        message = choice.get("message")
        if choice.get("finish_reason") != "stop" or not isinstance(message, dict):
            raise ValueError("completion is not final")
        if message.get("role") != "assistant":
            raise ValueError("completion is not an assistant message")
        text = message.get("content")
        if (message.get("tool_calls") or message.get("function_call")
                or not isinstance(text, str) or not text.strip()):
            raise ValueError("completion has no standalone text")
        if (contains_credential(text, credentials)
                or contains_credential(extract_json(text), credentials)):
            raise ValueError("credential in completion")
        return text, receipt
    except ValueError:
        raise ProviderCallError(
            "Relace returned an invalid or unsafe text completion",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=agent.model,
            receipt=_safe_receipt(receipt, credentials) if receipt is not None else None,
        ) from None
    except ProviderCallError as exc:
        exc.receipt = _safe_receipt(exc.receipt or receipt, credentials)
        raise
