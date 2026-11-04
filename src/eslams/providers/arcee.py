"""Arcee Platform direct Chat Completions adapter (no routing substitution)."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import quote

from eslams.agents import (
    _SYSTEM_INSTRUCTIONS,
    ProviderCallError,
    _check_provider_completion,
    _post_json,
    _provider_endpoint,
    _receipt,
    _response_json_with_receipt,
)
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

CHAT_COMPLETIONS_ENDPOINT = "https://api.arcee.ai/api/v1/chat/completions"
MODELS_ENDPOINT = "https://api.arcee.ai/api/v1/models"
API_KEY_ENV = "ARCEE_API_KEY"
PROVIDER = "arcee-ai"


def validate_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Arcee requires a nonblank explicit exact model ID: arcee-ai:<model>")


def validate_configuration(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    validate_model(model)
    # The direct API does not document reasoning switches/budgets. Never silently
    # ignore an operator's policy or borrow OpenRouter/self-hosted controls.
    if runtime and (
        runtime.reasoning != "auto"
        or runtime.reasoning_effort is not None
        or runtime.reasoning_budget_tokens is not None
        or runtime.gemini_thinking_budget is not None
        or runtime.openrouter_provider_order
    ):
        raise ValueError(
            "Arcee direct API supports native reasoning defaults only; "
            "explicit reasoning or routing controls are undocumented"
        )


def _credential_tokens(agent: ModelProviderAgent, api_key: str) -> tuple[str, ...]:
    # Protect both the standard credential and an explicitly selected alternate
    # environment. The standard one may remain configured when the alternate is
    # used. Read only these named credentials, never scan unrelated environments.
    values = {api_key}
    for name in {API_KEY_ENV, agent.api_key_env}:
        value = os.getenv(name, "").strip()
        if value:
            values.add(value)
    return tuple(values | {quote(value, safe="") for value in values})


def _contains_credential(value: str, credentials: tuple[str, ...]) -> bool:
    return any(credential in value for credential in credentials)


def _action_contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return _contains_credential(value, credentials)
    if isinstance(value, dict):
        return any(
            _contains_credential(key, credentials) or _action_contains_credential(item, credentials)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_action_contains_credential(item, credentials) for item in value)
    return False


def _private_receipt(value: Any, credentials: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        # Dropping the entire field avoids turning a redacted model identifier
        # into an apparent provider attestation of a fabricated model name.
        return None if _contains_credential(value, credentials) else value
    if isinstance(value, dict):
        return {
            key: _private_receipt(item, credentials)
            for key, item in value.items()
            if not _contains_credential(key, credentials)
        }
    if isinstance(value, list):
        return [_private_receipt(item, credentials) for item in value]
    return value


def _protect_receipt(receipt: dict[str, Any], credentials: tuple[str, ...]) -> dict[str, Any]:
    sanitized: dict[str, Any] = _private_receipt(receipt, credentials)
    if sanitized.get("locked_model_id") is None:
        sanitized["model_identity_source"] = None
    return sanitized


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    try:
        validate_configuration(agent.model, agent.runtime_config)
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_request_rejected", provider=PROVIDER, model=agent.model,
        ) from None
    credentials = _credential_tokens(agent, api_key)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _protect_receipt(exc.receipt, credentials)
        # Transport causes can contain private URLs/header values or echoed
        # credentials; expose only the shared sanitized provider diagnostic.
        raise exc from None
    except TimeoutError:
        raise TimeoutError("Arcee request timed out") from None
    receipt = _protect_receipt(receipt, credentials)
    try:
        private_action = (
            _contains_credential(text, credentials)
            or _action_contains_credential(extract_json(text), credentials)
        )
    except (ValueError, RecursionError):
        raise ProviderCallError(
            "Arcee action text could not be safely inspected; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER, model=agent.model,
            receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
        ) from None
    if private_action:
        raise ProviderCallError(
            "Arcee returned credential material in action text; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER, model=agent.model,
            receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
        )
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    runtime = agent.runtime_config
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    # Catalogue author rows can carry OpenRouter prices. Those are not evidence
    # for direct Arcee billing; no direct per-request cost contract is documented.
    receipt = _receipt(
        provider=PROVIDER, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data, provider=PROVIDER, model=agent.model, response=response, receipt=receipt,
        )
        text = _text(data, model=agent.model, receipt=receipt)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _text(data: dict[str, Any], *, model: str, receipt: dict[str, Any]) -> str:
    def fail(kind: str) -> NoReturn:
        raise ProviderCallError(
            "Arcee returned an unsuccessful or malformed chat completion",
            error_kind=kind, provider=PROVIDER, model=model,
        )

    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch")
    choice = choices[0]
    message = choice.get("message")
    reason = choice.get("finish_reason")
    if choice.get("error"):
        fail("provider_unavailable")
    if not isinstance(reason, str):
        fail("provider_response_schema_mismatch")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls", "function_call",
    } else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if reason == "length":
        fail("provider_output_truncated")
    if reason in {"tool_calls", "function_call"}:
        fail("provider_request_rejected")
    if not isinstance(message, dict) or reason != "stop":
        fail("provider_response_schema_mismatch")
    if (message.get("role") != "assistant"
            or message.get("tool_calls") or message.get("function_call")):
        fail("provider_response_schema_mismatch")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        fail("provider_response_schema_mismatch")
    # reasoning/reasoning_content are private and never used as action text.
    receipt["finish_status"] = "completed"
    return str(content)
