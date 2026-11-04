"""Direct Krutrim Cloud chat completions, without SDK defaults or routing."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "krutrim"
API_KEY_ENV = "KRUTRIM_CLOUD_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://cloud.olakrutrim.com/v1/chat/completions"


def validate_config(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Krutrim requires an explicit nonblank model ID")
    if runtime is None:
        return
    if runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Krutrim has no verified reasoning controls; use reasoning=auto")
    if runtime.gateway_base_url or runtime.gateway_mode != "direct_provider":
        raise ValueError("Krutrim requires its direct operator endpoint")
    if runtime.openrouter_provider_order:
        raise ValueError("Krutrim does not support OpenRouter routing controls")


def sanitize_receipt(
    agent: ModelProviderAgent, receipt: dict[str, Any], *, secret: str | None = None,
) -> dict[str, Any]:
    """Remove exact credential echoes, including keys and harmless-looking IDs."""
    if secret is None:
        secret = os.getenv(agent.api_key_env, "").strip()

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return None if secret and secret in value else value
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not (secret and secret in key)}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    result: dict[str, Any] = clean(receipt)
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def normalize_usage(usage: Any) -> dict[str, Any]:
    # OpenAI-compatible top-level counters are observations only. The official
    # SDK does not specify usage, caching or reasoning billing semantics.
    from eslams.agents import _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for source, target in (("prompt_tokens", "input_tokens"),
                           ("completion_tokens", "output_tokens"),
                           ("total_tokens", "total_tokens")):
        result[target] = _usage_int(usage.get(source), source, errors)
    result["total_tokens_source"] = (
        "provider" if result["total_tokens"] is not None else "unavailable"
    )
    result["usage_validation_errors"] = errors
    return result


def validate_action(action: Any, explanation: str | None, secret: str) -> None:
    from eslams.protocol import ProtocolError

    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return bool(secret and secret in value)
        if isinstance(value, dict):
            return any(contains(key) or contains(item) for key, item in value.items())
        if isinstance(value, list):
            return any(contains(item) for item in value)
        return False

    if contains(action) or contains(explanation):
        raise ProtocolError("Krutrim action contains a credential echo")


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    try:
        return _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        # No documented Krutrim rejection envelope establishes a safe replay.
        exc.retry_permitted = False
        if exc.receipt is not None:
            exc.receipt = sanitize_receipt(agent, exc.receipt, secret=api_key)
        if api_key in str(exc):
            exc.args = ("Krutrim response rejected",)
        if exc.model and api_key in exc.model:
            exc.model = None
        raise


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    validate_config(agent.model, agent.runtime_config)
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
        CHAT_COMPLETIONS_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=agent.runtime_config,
    )
    receipt = sanitize_receipt(agent, _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    ), secret=api_key)
    choices = data.get("choices")
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = choice.get("message") if isinstance(choice, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    kind = "provider_response_schema_mismatch"
    if data.get("error") or (isinstance(choice, dict) and choice.get("error")):
        kind = "provider_unavailable"
    elif reason == "length":
        kind = "provider_output_truncated"
    elif reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        kind = "provider_refused"
    elif (isinstance(choice, dict) and type(choice.get("index")) is int
          and choice["index"] == 0
          and reason == "stop" and isinstance(message, dict)
          and message.get("role") == "assistant" and not message.get("tool_calls")
          and not message.get("function_call") and isinstance(text, str) and text.strip()
          and api_key not in text):
        receipt.update(finish_reason="stop", finish_status="completed")
        return text, receipt
    receipt.update(
        outcome=kind,
        finish_reason=reason if reason in ("stop", "length", "content_filter") else "unknown",
        finish_status="incomplete" if kind == "provider_output_truncated" else "failed",
    )
    raise ProviderCallError(
        "Krutrim did not return one complete assistant text response",
        error_kind=kind, provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        status_code=response.status_code,
    )
