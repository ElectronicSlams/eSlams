"""Liquid-operated text inference; no router or local-runtime substitution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

CHAT_ENDPOINT = "https://api.liquid.ai/openai/v1/chat/completions"
SOURCE = "https://docs.liquid.ai/api/guides/text-generation"


def validate_config(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Liquid requires an explicit nonblank model ID")
    if runtime and (
        runtime.reasoning != "auto"
        or runtime.reasoning_effort is not None
        or runtime.reasoning_budget_tokens is not None
        or runtime.gemini_thinking_budget is not None
    ):
        raise ValueError("Liquid supports native-default reasoning only")
    if runtime and (runtime.gateway_base_url or runtime.openrouter_provider_order):
        raise ValueError("Liquid requires its direct endpoint without router controls")
    if runtime and runtime.history_window_turns is not None:
        raise ValueError("Liquid requires full supplied history")


def _scrub(value: Any, key: str) -> Any:
    """Remove credential echoes even from otherwise allowlisted receipt values."""
    if isinstance(value, str):
        return None if key in value else value
    if isinstance(value, dict):
        return {k: _scrub(v, key) for k, v in value.items() if key not in str(k)}
    if isinstance(value, (tuple, list)):
        return [_scrub(v, key) for v in value]
    return value


def _echoed(value: Any, key: str) -> bool:
    if isinstance(value, str):
        return key in value
    if isinstance(value, dict):
        return any(key in str(k) or _echoed(v, key) for k, v in value.items())
    if isinstance(value, list):
        return any(_echoed(v, key) for v in value)
    return False


def _safe_receipt(receipt: Any, key: str) -> Any:
    result = _scrub(receipt, key)
    if isinstance(result, dict) and result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Reuse Core's physical-attempt transport, custody and receipt implementation.
    from eslams import agents as core

    validate_config(agent.model, agent.runtime_config)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": core._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if agent._effective_max_output_tokens() is not None:
        payload["max_tokens"] = agent._effective_max_output_tokens()
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    receipt = None
    try:
        response = core._post_json(
            CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"liquid-ai:{agent.model}",
        )
        data = core._response_json_with_receipt(
            response, provider="liquid-ai", model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        receipt = core._receipt(
            provider="liquid-ai", model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=data.get("usage"), capabilities=agent.capabilities,
            runtime_config=agent.runtime_config,
        )
        # No documented hosted reasoning-token inclusion rule: retain unknown.
        usage = data.get("usage")
        cost = core._optional_float(usage.get("cost")) if isinstance(usage, dict) else None
        if cost is not None:
            receipt["estimated_cost"] = {
                "status": "ok", "currency": "USD", "cost_usd": cost,
                "source": "provider_native",
            }
            receipt["pricing_provenance"] = {"source": "provider_native", "source_uri": SOURCE}
        core._check_provider_completion(
            data, provider="liquid-ai", model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        try:
            decoded_echo = _echoed(extract_json(text), api_key) if isinstance(text, str) else False
        except (ValueError, RecursionError):
            raise core.ProviderCallError(
                "Liquid returned malformed action text",
                provider="liquid-ai", error_kind="provider_response_schema_mismatch",
            ) from None
        if (data.get("object") != "chat.completion" or not isinstance(first, dict)
                or first.get("finish_reason") != "stop" or not isinstance(message, dict)
                or message.get("role") != "assistant" or message.get("tool_calls")
                or not isinstance(text, str) or not text.strip() or api_key in text or decoded_echo
                or (data.get("model") is not None and data["model"] != agent.model)):
            raise core.ProviderCallError(
                "Liquid returned an unsupported or incomplete text envelope",
                provider="liquid-ai", error_kind="provider_response_schema_mismatch",
            )
        return text, _safe_receipt(receipt, api_key)
    except core.ProviderCallError as exc:
        safe = _safe_receipt(exc.receipt if exc.receipt is not None else receipt, api_key)
        raise core.ProviderCallError(
            "Liquid inference failed", provider="liquid-ai", model=agent.model,
            error_kind=exc.error_kind, status_code=exc.status_code,
            retry_after_seconds=exc.retry_after_seconds, receipt=safe,
            retry_permitted=exc.retry_permitted,
        ) from None
