"""Mistral AI's native, non-streaming Chat Completions adapter.

REST/schema provenance and deliberately unsupported features are documented in
docs/providers/MISTRAL.md. This module uses Core's shared attempt transport and
accounting; it does not introduce an SDK, fallback, or independent retry loop.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent, ProviderCallError

PROVIDER_ID = "mistral-ai"
API_KEY_ENV = "MISTRAL_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.mistral.ai/v1/models"
DEFAULT_MODEL = "mistral-small-latest"


def complete(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    # Imported at invocation time to keep provider-specific parsing out of the
    # common agent while reusing its transport, redaction and receipt contracts.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
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
    if agent.runtime_config and agent.runtime_config.reasoning_effort is not None:
        # An explicit operator choice, subject to authoritative model rejection.
        # Never select prompt_mode or reasoning effort based on the game.
        payload["reasoning_effort"] = agent.runtime_config.reasoning_effort
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, agent.runtime_config),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=agent.runtime_config,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        # The frozen author catalogue includes third-party/broker pricing.
        # None of it is a verified rate card for this direct Mistral route.
        usage=data.get("usage"), capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=agent.runtime_config,
    )
    try:
        # Handles HTTP 200 error envelopes without exposing their private prose.
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = _text(data, receipt)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _error(message: str, kind: str = "provider_response_schema_mismatch") -> ProviderCallError:
    from eslams.agents import ProviderCallError

    return ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID)


def _text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    choices = data.get("choices")
    if (not isinstance(choices, list) or len(choices) != 1
            or not isinstance(choices[0], dict)):
        raise _error("Mistral response must contain one completion choice")
    choice = choices[0]
    reason = choice.get("finish_reason")
    known = {"stop", "length", "model_length", "error", "tool_calls", "content_filter", "refusal"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason in ("length", "model_length"):
        raise _error(
            "Mistral token/context limit interrupted the response", "provider_output_truncated",
        )
    if reason in ("content_filter", "refusal"):
        receipt["finish_status"] = "refused"
        raise _error("Mistral refused or filtered the requested action", "provider_refused")
    if reason == "error":
        receipt["finish_status"] = "failed"
        raise _error("Mistral reported a completion error", "provider_unavailable")
    if reason == "tool_calls":
        raise _error("Mistral returned an unsupported tool call", "provider_request_rejected")
    if reason != "stop":
        raise _error("Mistral response has no supported terminal finish reason")
    if (type(choice.get("index")) is not int or choice.get("index") != 0
            or data.get("status") not in (None, "completed")):
        raise _error("Mistral response has an invalid completion envelope")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise _error("Mistral response is missing an assistant message")
    if message.get("refusal"):
        receipt["finish_status"] = "refused"
        raise _error("Mistral refused the requested action", "provider_refused")
    if message.get("tool_calls"):
        raise _error("Mistral returned an unsupported tool call", "provider_request_rejected")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        receipt["finish_status"] = "completed"
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                raise _error("Mistral returned malformed content chunks")
            if part.get("type") == "thinking" and isinstance(part.get("thinking"), list):
                continue
            if part.get("type") != "text" or not isinstance(part.get("text"), str):
                raise _error("Mistral returned unsupported or malformed content chunks")
            chunks.append(part["text"])
        text = "".join(chunks)
        if text.strip():
            receipt["finish_status"] = "completed"
            return text
    raise _error("Mistral response has no answer text")
