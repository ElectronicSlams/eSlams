"""Direct Reka Chat Completions adapter (not the retired v0 /chat API)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "reka-ai"
API_KEY_ENV = "REKA_API_KEY"
DEFAULT_MODEL = "reka-flash-3"
CHAT_COMPLETIONS_ENDPOINT = "https://api.reka.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.reka.ai/v1/models"


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at invocation time: agents owns the common transport/receipt helpers.
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
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning_effort is not None:
        # Endpoint validation is authoritative, including for uncatalogued models.
        payload["reasoning_effort"] = runtime.reasoning_effort
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime,
        control_key=f"{PROVIDER_ID}:{agent.model}",
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
    usage = data.get("usage")
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    conflicting_reasoning = (
        isinstance(usage, dict) and isinstance(details, dict)
        and "reasoning_tokens" in usage and "reasoning_tokens" in details
        and (type(usage["reasoning_tokens"]) is not type(details["reasoning_tokens"])
             or usage["reasoning_tokens"] != details["reasoning_tokens"])
    )
    if receipt["usage"].get("usage_validation_errors") or conflicting_reasoning:
        # Incoherent usage must not turn into complete preflight accounting or cost.
        receipt["usage"] = {}
        receipt["usage_unavailable_reason"] = "provider_usage_malformed"
        receipt["estimated_cost"] = {
            "status": "cost_unavailable", "unavailable_reason": "provider_usage_malformed",
        }
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if (not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or not isinstance(content, str) or not content):
            raise ProviderCallError(
                "Reka response has no single completed assistant text message",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    # reasoning_content/reasoning are private traces, never action text or receipt data.
    return content, receipt
