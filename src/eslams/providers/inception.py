"""Inception Labs Mercury direct Chat Completions adapter.

This is api.inceptionlabs.ai, independent of Core42/G42 and broker routes.
Shared transport and receipt helpers are imported at call time to keep provider
wire behavior here without introducing a second transport or retry loop.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "inception"
PROVIDER_ALIASES = {"inception-labs": PROVIDER_ID, "inceptionlabs": PROVIDER_ID}
API_KEY_ENV = "INCEPTION_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.inceptionlabs.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.inceptionlabs.ai/v1/chat/completions/models"


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized, normalized)


def validate_model_id(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Inception requires an explicit nonblank model ID")


def configuration_error(runtime: ProviderRuntimeConfig | None) -> str | None:
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        return "Inception accepts reasoning_effort, not a reasoning token budget"
    return None


def _credential_values(primary: str) -> tuple[str, ...]:
    # Include secondary provider/gateway credentials, even when they have no
    # recognizable token prefix. Values are used only for local redaction.
    values = {primary}
    for name, value in os.environ.items():
        upper = name.upper()
        credential_name = upper.endswith("_KEY") or any(marker in upper for marker in (
            "API_KEY", "ACCESS_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION",
        ))
        if credential_name and value.strip() and not any(marker in upper for marker in (
            "ALLOW_", "ENABLE_", "KEY_ID", "TOKEN_ID", "SECRET_ID",
        )):
            values.add(value.strip())
    return tuple(value for value in values if value)


def credential_echo(value: str, primary: str) -> bool:
    return any(secret in value for secret in _credential_values(primary))


def _contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(secret in value for secret in credentials)
    if isinstance(value, dict):
        return any(_contains_credential(key, credentials) or _contains_credential(item, credentials)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_credential(item, credentials) for item in value)
    return False


def _private_receipt(receipt: dict[str, Any], credentials: tuple[str, ...]) -> dict[str, Any]:
    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            return None if any(secret in value for secret in credentials) else value
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()
                    if not any(secret in key for secret in credentials)}
        return value

    sanitized: dict[str, Any] = scrub(receipt)
    if sanitized.get("locked_model_id") is None:
        sanitized["model_identity_source"] = None
    return sanitized


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError
    from eslams.model_actions import extract_json

    credentials = _credential_values(api_key)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _private_receipt(exc.receipt, credentials)
        if any(secret in str(exc) for secret in credentials):
            exc.args = ("Inception request failed; sensitive details omitted",)
        # Retry permission was computed from the complete unsanitized wire
        # observations. Removing an echoed ID must never authorize replay.
        raise
    sanitized = _private_receipt(receipt, credentials)
    try:
        private_text = (_contains_credential(text, credentials)
                        or _contains_credential(extract_json(text), credentials))
    except (ValueError, RecursionError):
        private_text = True
    if private_text:
        raise ProviderCallError(
            "Inception response failed privacy validation; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model,
            receipt={**sanitized, "outcome": "provider_response_schema_mismatch"},
        )
    return text, sanitized


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    validate_model_id(agent.model)
    error = configuration_error(runtime)
    if error:
        raise ProviderCallError(
            error,
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_completion_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning_effort"] = runtime.reasoning_effort
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = _text(data, model=agent.model)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _text(data: dict[str, Any], *, model: str) -> str:
    from eslams.agents import ProviderCallError

    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if (isinstance(first, dict) and type(first.get("index")) is int
            and first["index"] == 0 and first.get("finish_reason") == "stop"
            and isinstance(message, dict) and message.get("role") == "assistant"
            and not message.get("tool_calls") and not message.get("function_call")
            and isinstance(content, str) and content.strip()):
        return content
    raise ProviderCallError(
        "Inception response requires one completed assistant text choice",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=model,
    )
