"""Arcee Platform direct Chat Completions adapter (no routing substitution)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, NoReturn

from eslams.agents import (
    _SYSTEM_INSTRUCTIONS,
    ProviderCallError,
    _check_provider_completion,
    _post_json,
    _provider_endpoint,
    _receipt,
    _response_json_with_receipt,
)

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

CHAT_COMPLETIONS_ENDPOINT = "https://api.arcee.ai/api/v1/chat/completions"
MODELS_ENDPOINT = "https://api.arcee.ai/api/v1/models"
API_KEY_ENV = "ARCEE_API_KEY"
PROVIDER = "arcee-ai"


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    runtime = agent.runtime_config
    # The direct API does not document reasoning switches/budgets. Never silently
    # ignore an operator's policy or borrow OpenRouter/self-hosted controls.
    if runtime and (
        runtime.reasoning != "auto"
        or runtime.reasoning_effort is not None
        or runtime.reasoning_budget_tokens is not None
        or runtime.gemini_thinking_budget is not None
        or runtime.openrouter_provider_order
    ):
        raise ProviderCallError(
            "Arcee direct API supports native reasoning defaults only; "
            "explicit reasoning or routing controls are undocumented",
            error_kind="provider_request_rejected", provider=PROVIDER, model=agent.model,
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
