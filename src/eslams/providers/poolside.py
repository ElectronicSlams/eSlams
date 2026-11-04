"""Poolside-hosted inference, pinned to the public REST examples.

Detailed hosted API schemas are access restricted. See docs/POOLSIDE.md for
the verified contract and the deliberately unknown accounting/retry semantics.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "poolside"
API_KEY_ENV = "POOLSIDE_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://inference.poolside.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://inference.poolside.ai/v1/models"
ENDPOINT_KIND = "poolside_chat_completions"
PARSER_VERSION = "poolside-chat-completions-raw-v1"


def normalize_provider(value: str) -> str:
    candidate = value.strip().lower().replace("_", "-")
    return "poolside" if candidate in {"poolside", "poolside-ai", "poolsideai"} else value


def configuration_error(model: str, runtime: ProviderRuntimeConfig | None) -> str | None:
    if not model.strip():
        return "Poolside requires an explicit model: poolside:<model-id>"
    if runtime and any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        return "Poolside supports thinking on/off only; reasoning effort/budgets are unsupported"
    return None


def _redact(value: Any, api_key: str) -> Any:
    if isinstance(value, str):
        return value.replace(api_key, "[redacted]")
    if isinstance(value, dict):
        return {str(_redact(key, api_key)): _redact(item, api_key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, api_key) for item in value]
    return value


def _redact_receipt(receipt: dict[str, Any], api_key: str) -> dict[str, Any]:
    result: dict[str, Any] = _redact(receipt, api_key)
    for field in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id"):
        raw = receipt.get(field)
        if isinstance(raw, str) and api_key in raw:
            result[field] = None
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Keep only documented counters; never infer cost, cache or thinking usage."""
    from eslams.agents import _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for wire, normalized in (
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        result[normalized] = _usage_int(usage.get(wire), wire, errors)
    result.update(
        total_tokens_source="provider" if result["total_tokens"] is not None else "unavailable",
        usage_source="provider",
        usage_validation_errors=errors,
    )
    # Public examples do not establish whether completion_tokens includes all
    # reasoning. Do not assume an additive identity or inherit broker semantics.
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    try:
        text, receipt = _call(agent, api_key, prompt)
        return text.replace(api_key, "[redacted]"), _redact_receipt(receipt, api_key)
    except ProviderCallError as exc:
        exc.retry_permitted = False
        if exc.receipt is not None:
            exc.receipt = _redact_receipt(exc.receipt, api_key)
        raise


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Deferred import keeps shared receipt/transport machinery in one place.
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
    error = configuration_error(agent.model, runtime)
    if error:
        raise ProviderCallError(
            error + "; no request submitted",
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
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning != "auto":
        payload["chat_template_kwargs"] = {"enable_thinking": runtime.reasoning == "enabled"}
    try:
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
        )
    except ProviderCallError as exc:
        # Hosted rejection/body and no-work guarantees are not publicly specified.
        # Keep observed receipts, but never automatically replay an uncertain call.
        exc.retry_permitted = False
        raise
    # Registry rows may originate from OpenRouter. Broker prices are not native
    # Poolside prices, even when model strings happen to match exactly.
    capabilities = replace(agent.capabilities, pricing={})
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=capabilities, runtime_config=runtime,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=capabilities, runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        if (not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or message.get("function_call")):
            raise ProviderCallError(
                "Poolside response is not one completed assistant message",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ProviderCallError(
                "Poolside response has no answer text",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        # reasoning_content is private model reasoning, never an action or receipt.
        return text, receipt
    except ProviderCallError as exc:
        exc.retry_permitted = False
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
