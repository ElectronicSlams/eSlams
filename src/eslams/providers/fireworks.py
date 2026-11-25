"""Fireworks direct Chat Completions wire contract (no SDK or broker fallback)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "fireworks"
PROVIDER_ALIASES = ("fireworks", "fireworks-ai", "fireworks_ai")
API_KEY_ENV = "FIREWORKS_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.fireworks.ai/inference/v1/chat/completions"
ENDPOINT_KIND = "fireworks_chat_completions"
PARSER_VERSION = "fireworks-chat-completions-raw-v1"


def reasoning_control(runtime: ProviderRuntimeConfig) -> str | bool | int | None:
    """Translate only explicit operator choices; model defaults stay native."""
    from eslams.agents import ProviderCallError

    effort = runtime.reasoning_effort
    budget = runtime.reasoning_budget_tokens
    if effort is not None and budget is not None:
        raise ProviderCallError(
            "Fireworks accepts one reasoning effort or token budget, not both",
            error_kind="provider_request_rejected",
            provider=PROVIDER_ID,
        )
    if runtime.gemini_thinking_budget is not None:
        raise ProviderCallError(
            "gemini_thinking_budget is not a Fireworks control",
            error_kind="provider_request_rejected",
            provider=PROVIDER_ID,
        )
    if runtime.reasoning == "disabled":
        return "none"
    if effort is not None:
        return effort
    if budget is not None:
        if budget == 0:
            raise ProviderCallError(
                "Fireworks reasoning token budgets must be positive; use reasoning=disabled",
                error_kind="provider_request_rejected",
                provider=PROVIDER_ID,
            )
        return budget
    return True if runtime.reasoning == "enabled" else None


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Normalize documented fields only; reasoning is part of generated tokens."""
    from eslams.agents import _normalize_usage

    if not isinstance(usage, dict):
        return _normalize_usage("fireworks_wire", None)
    prompt_details = usage.get("prompt_tokens_details")
    completion_details = usage.get("completion_tokens_details")
    output_details = usage.get("output_tokens_details")
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    output_details = output_details if isinstance(output_details, dict) else {}
    reasoning = completion_details.get("reasoning_tokens")
    if reasoning is None:
        reasoning = output_details.get("reasoning_tokens")
    normalized = _normalize_usage(
        "fireworks_wire",
        {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cached_input_tokens": prompt_details.get("cached_tokens"),
            "reasoning_tokens": reasoning,
            "reasoning_included_in_output": True,
        },
    )
    errors = normalized["usage_validation_errors"]
    for field in ("prompt_tokens_details", "completion_tokens_details", "output_tokens_details"):
        if usage.get(field) is not None and not isinstance(usage[field], dict):
            errors.append(f"invalid_{field}")
    if (
        completion_details.get("reasoning_tokens") is not None
        and output_details.get("reasoning_tokens") is not None
        and completion_details["reasoning_tokens"] != output_details["reasoning_tokens"]
    ):
        errors.append("conflicting_reasoning_tokens")
    normalized["usage_validation_errors"] = sorted(set(errors))
    return normalized


def call(
    agent: ModelProviderAgent,
    api_key: str,
    prompt: str,
    system_instructions: str,
) -> tuple[str, dict[str, Any]]:
    # Import the shared transport/receipt primitives at invocation time to keep
    # provider metadata importable independently of the agent dispatcher.
    from eslams.agents import (
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config or ProviderRuntimeConfig()
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
        "temperature": agent.temperature,
        "reasoning_effort": reasoning_control(runtime),
        "context_length_exceeded_behavior": "error",
    }
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
        runtime_config=runtime,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response,
        provider=PROVIDER_ID,
        model=agent.model,
        capabilities=agent.capabilities,
        runtime_config=runtime,
    )
    receipt = _receipt(
        provider=PROVIDER_ID,
        model=agent.model,
        response=response,
        provider_response_id=data.get("id"),
        resolved_model=data.get("model"),
        usage=data.get("usage"),
        capabilities=agent.capabilities,
        runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data,
            provider=PROVIDER_ID,
            model=agent.model,
            response=response,
            receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if (
            not isinstance(first, dict)
            or first.get("finish_reason") != "stop"
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or message.get("tool_calls")
            or message.get("function_call")
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ProviderCallError(
                "Fireworks response requires one completed assistant text choice",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID,
                model=agent.model,
            )
        # Some models put their trace inline instead of reasoning_content.
        # Never parse an action in a thinking block or expose it in diagnostics.
        content = content.lstrip()
        if content.startswith("<think>"):
            _, separator, content = content.partition("</think>")
            if not separator:
                content = ""
            content = content.lstrip()
        if not content or "<think>" in content or "</think>" in content:
            raise ProviderCallError(
                "Fireworks response has no separate completed answer after inline reasoning",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID,
                model=agent.model,
            )
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return content, receipt
