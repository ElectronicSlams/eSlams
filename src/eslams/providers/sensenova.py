"""SenseTime's direct SenseNova Token Plan Chat Completions adapter.

The older SenseCore /v1/llm/chat-completions JWT API is a different contract.
See docs/providers/SENSENOVA.md for pinned official sources and limitations.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "sensetime"
PROVIDER_ALIASES = {"sensenova", "sense-nova", "sense-time"}
API_KEY_ENV = "SENSENOVA_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://token.sensenova.cn/v1/chat/completions"


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = redact_credentials(exc.receipt, api_key)
        raise
    return text, redact_credentials(receipt, api_key)


def configuration_error(model: str, runtime: ProviderRuntimeConfig | None) -> str | None:
    if not isinstance(model, str) or not model.strip():
        return "SenseNova requires an explicit nonblank model ID"
    if runtime and (
        runtime.reasoning != "auto"
        or runtime.reasoning_effort is not None
        or runtime.reasoning_budget_tokens is not None
        or runtime.gemini_thinking_budget is not None
    ):
        return "SenseNova Token Plan has no verified reasoning control; use native defaults"
    return None


def redact_credentials(receipt: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Remove reflected credentials, including unused legacy secondary secrets.

    Identifier syntax alone cannot distinguish an ID from an echoed API key.
    This projection also covers error and partial-body transport receipts.
    """
    secrets = {api_key}
    for name, value in os.environ.items():
        if name.upper().startswith(("SENSENOVA_", "SENSETIME_")) and any(
            part in name.upper() for part in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")
        ) and value.strip():
            secrets.add(value.strip())

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return None if any(secret and secret in value for secret in secrets) else value
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not any(secret and secret in key for secret in secrets)}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    result: dict[str, Any] = clean(receipt)
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Reuse Core's transport, strict JSON parsing and receipt projection. Local
    # imports avoid moving the existing provider infrastructure in this change.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    error = configuration_error(agent.model, runtime)
    if error is not None:
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
        "max_tokens": agent._effective_max_output_tokens(),
        "temperature": agent.temperature,
    }
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
    if receipt["request_id"] is None:
        receipt["request_id"] = _http_error_identifier(data.get("request_id"))
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        if data.get("model") is not None and data["model"] != agent.model:
            raise ProviderCallError(
                "SenseNova returned a different model identity; no action accepted",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        text = response_text(data, model=agent.model)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def response_text(data: dict[str, Any], *, model: str) -> str:
    """Accept one complete assistant answer; reasoning never becomes action text."""
    from eslams.agents import ProviderCallError

    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = first.get("message") if isinstance(first, dict) else None
    if (
        isinstance(first, dict) and first.get("finish_reason") == "stop"
        and isinstance(message, dict) and message.get("role") == "assistant"
        and not message.get("tool_calls") and not message.get("function_call")
        and isinstance(message.get("content"), str) and message["content"].strip()
    ):
        return str(message["content"])
    raise ProviderCallError(
        "SenseNova response must contain one completed assistant text message",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=model,
    )
