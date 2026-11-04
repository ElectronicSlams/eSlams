"""Inception Labs Mercury direct Chat Completions adapter.

This is api.inceptionlabs.ai, independent of Core42/G42 and broker routes.
Shared transport and receipt helpers are imported at call time to keep provider
wire behavior here without introducing a second transport or retry loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "inception"
PROVIDER_ALIASES = {"inception-labs": PROVIDER_ID, "inceptionlabs": PROVIDER_ID}
API_KEY_ENV = "INCEPTION_API_KEY"
DEFAULT_MODEL = "mercury-3"
CHAT_COMPLETIONS_ENDPOINT = "https://api.inceptionlabs.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.inceptionlabs.ai/v1/chat/completions/models"


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized, normalized)


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
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
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        raise ProviderCallError(
            "Inception accepts reasoning_effort, not a reasoning token budget",
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
