"""Perplexity Agent API: explicit model, no search, tools, or fallback chain."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote_plus

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "perplexity"
API_KEY_ENV = "PERPLEXITY_API_KEY"
AGENT_ENDPOINT = "https://api.perplexity.ai/v1/agent"
MODELS_ENDPOINT = "https://api.perplexity.ai/v1/models"
ENDPOINT_KIND = "perplexity_agent"
PARSER_VERSION = "perplexity-agent-raw-v1"

# Model-specific support verified in the Agent API Models documentation.
_EFFORTS = {
    "perplexity/kimi-k3": {"minimal", "low", "medium", "high", "xhigh", "max"},
}


def validate_config(model: str, config: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Perplexity requires an explicit nonblank model ID")
    if (model != model.strip() or "/" not in model or any(c.isspace() for c in model)
            or not all(model.split("/"))):
        raise ValueError("Perplexity requires the exact provider/model ID")
    if config is None:
        return
    if config.reasoning != "auto":
        raise ValueError("Perplexity requires reasoning=auto; choose a verified reasoning_effort")
    if config.reasoning_budget_tokens is not None or config.gemini_thinking_budget is not None:
        raise ValueError("Perplexity does not support reasoning token budgets")
    if (config.reasoning_effort is not None
            and config.reasoning_effort not in _EFFORTS.get(model, set())):
        raise ValueError("Perplexity reasoning effort is not verified for this exact model")
    if config.history_window_turns is not None:
        raise ValueError("Perplexity requires the full public history")
    if config.openrouter_provider_order or config.openrouter_allow_fallbacks:
        raise ValueError("Perplexity does not support provider routing or fallback controls")


def _credentials(api_key: str) -> tuple[str, ...]:
    # A custom primary environment does not make the canonical key safe to echo.
    values = {api_key, os.getenv(API_KEY_ENV, "").strip()} - {""}
    return tuple(sorted(values, key=len, reverse=True))


def _contains_credential(value: str, credentials: tuple[str, ...]) -> bool:
    return any(secret in candidate for secret in credentials
               for candidate in (value, unquote_plus(value)))


def _clean(value: Any, credentials: tuple[str, ...]) -> Any:
    # Drop contaminated identifiers rather than inventing a replacement identity.
    if isinstance(value, str):
        return None if _contains_credential(value, credentials) else value
    if isinstance(value, dict):
        return {key: _clean(item, credentials) for key, item in value.items()
                if not _contains_credential(key, credentials)}
    if isinstance(value, list):
        return [_clean(item, credentials) for item in value]
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import lazily: shared transport and receipt custody remain the authority.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _optional_float,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    validate_config(agent.model, agent.runtime_config)
    credentials = _credentials(api_key)
    payload: dict[str, Any] = {
        "model": agent.model,
        "instructions": _SYSTEM_INSTRUCTIONS,
        "input": [{"role": "user", "content": prompt}],
        "tools": [],
        "tool_choice": "none",
        "stream": False,
        "store": False,
    }
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["max_output_tokens"] = limit
    elif agent.model.startswith("anthropic/"):
        raise ProviderCallError(
            "Perplexity Anthropic models require an explicit operator max_output_tokens",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if agent.runtime_config and agent.runtime_config.reasoning_effort is not None:
        payload["reasoning"] = {"effort": agent.runtime_config.reasoning_effort}
    receipt = None
    try:
        response = _post_json(
            _provider_endpoint(AGENT_ENDPOINT, agent.runtime_config),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        raw_usage = data.get("usage")
        usage = ({key: raw_usage[key] for key in (
            "input_tokens", "output_tokens", "total_tokens", "input_tokens_details",
        ) if key in raw_usage} if isinstance(raw_usage, dict) else None)
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=usage, capabilities=agent.capabilities,
            runtime_config=agent.runtime_config,
        )
        if isinstance(raw_usage, dict):
            # No inference of absent totals or reasoning inclusion from another API.
            total = raw_usage.get("total_tokens")
            if (receipt["usage"] and (isinstance(total, bool)
                                      or not isinstance(total, int) or total < 0)):
                receipt["usage"].update(total_tokens=None, total_tokens_source="unavailable")
            cost = raw_usage.get("cost")
            if isinstance(cost, dict) and cost.get("currency") == "USD":
                total_cost = _optional_float(cost.get("total_cost"))
                if total_cost is not None:
                    receipt["estimated_cost"] = {
                        "status": "ok", "currency": "USD", "cost_usd": total_cost,
                        "source": "provider_native",
                    }
        # Reuse semantic error classification without claiming OpenAI as provider.
        _check_provider_completion(
            data, provider="openai", model=agent.model, response=response, receipt=receipt,
        )
        if data.get("object") != "response" or data.get("status") != "completed":
            raise ProviderCallError("Perplexity response is not a completed response",
                                    error_kind="provider_response_schema_mismatch")
        resolved = data.get("model")
        if (resolved != agent.model or _contains_credential(resolved, credentials)
                or receipt["locked_model_id"] is None):
            raise ProviderCallError("Perplexity response model identity is missing or mismatched",
                                    error_kind="provider_response_schema_mismatch")
        if not isinstance(data.get("id"), str) or not data["id"].strip():
            raise ProviderCallError("Perplexity response ID is missing",
                                    error_kind="provider_response_schema_mismatch")
        tool_usage = raw_usage.get("tool_calls_details") if isinstance(raw_usage, dict) else None
        cost = raw_usage.get("cost") if isinstance(raw_usage, dict) else None
        tool_cost = _optional_float(cost.get("tool_calls_cost")) if isinstance(cost, dict) else None
        if (data.get("effort") is not None or data.get("preset") is not None
                or data.get("tools") or tool_usage or (tool_cost is not None and tool_cost > 0)):
            raise ProviderCallError("Perplexity returned an unexpected tool or preset run",
                                    error_kind="provider_response_schema_mismatch")
        chunks: list[str] = []
        output = data.get("output")
        if not isinstance(output, list) or not output:
            raise ProviderCallError("Perplexity response is missing output",
                                    error_kind="provider_response_schema_mismatch")
        for item in output:
            if (not isinstance(item, dict) or item.get("type") != "message"
                    or item.get("role") != "assistant" or item.get("status") != "completed"
                    or not isinstance(item.get("content"), list) or not item["content"]):
                raise ProviderCallError("Perplexity returned unexpected or incomplete output",
                                        error_kind="provider_response_schema_mismatch")
            for part in item["content"]:
                if (not isinstance(part, dict) or part.get("type") != "output_text"
                        or not isinstance(part.get("text"), str)):
                    raise ProviderCallError("Perplexity returned non-text action output",
                                            error_kind="provider_response_schema_mismatch")
                chunks.append(part["text"])
        text = "".join(chunks)
        if not text.strip() or _contains_credential(text, credentials):
            raise ProviderCallError("Perplexity action text is empty or contains credentials",
                                    error_kind="provider_response_schema_mismatch")
        return text, _clean(receipt, credentials)
    except ProviderCallError as exc:
        safe_receipt = _clean(exc.receipt if exc.receipt is not None else receipt, credentials)
        if safe_receipt is not None:
            safe_receipt["outcome"] = exc.error_kind
        raise ProviderCallError(
            _clean(str(exc), credentials) or "Perplexity request failed; see classified outcome",
            status_code=exc.status_code, error_kind=exc.error_kind,
            retry_after_seconds=exc.retry_after_seconds, provider=PROVIDER_ID, model=agent.model,
            receipt=safe_receipt, retry_permitted=exc.retry_permitted,
        ) from None
