"""Meituan LongCat's native, non-streaming Chat Completions contract.

Official sources and accounting limitations: docs/providers/LONGCAT.md.
Shared transport/receipt imports are local to keep provider dispatch acyclic.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "meituan"
PROVIDER_ALIASES = ("meituan", "longcat", "meituan-longcat")
API_KEY_ENV = "LONGCAT_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.longcat.chat/openai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.longcat.chat/openai/v1/models"
ENDPOINT_KIND = "longcat_chat_completions"
PARSER_VERSION = "longcat-chat-completions-raw-v1"


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in PROVIDER_ALIASES else provider.lower()


def complete(
    agent: ModelProviderAgent, api_key: str, prompt: str, *, system_instructions: str,
) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    if not agent.model.strip():
        raise ProviderCallError(
            "LongCat requires an explicit provider-native model ID",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    # Do not translate unrelated providers' effort/controls or silently ignore them.
    if runtime and (runtime.reasoning_effort is not None
                    or runtime.gemini_thinking_budget is not None):
        raise ProviderCallError(
            "LongCat accepts reasoning enabled/disabled/auto and reasoning_budget_tokens; "
            "reasoning_effort and gemini_thinking_budget are unsupported",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime:
        if runtime.reasoning != "auto":
            payload["thinking"] = {"type": runtime.reasoning}
        if runtime.reasoning_budget_tokens is not None:
            payload["thinking_budget"] = runtime.reasoning_budget_tokens
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
        usage=data.get("usage"), capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        # Reasoning is private telemetry, never an alternate source of action text.
        if (not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or message.get("function_call")
                or not isinstance(content, str) or not content.strip()):
            raise ProviderCallError(
                "LongCat returned no complete assistant text choice",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID, model=agent.model,
            )
    except ProviderCallError as exc:
        # Only an actual HTTP 429 can establish the documented LongCat rejection.
        # An error embedded in an HTTP 200 response may represent accepted work.
        exc.retry_permitted = False
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return content, receipt


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams.agents import _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for normalized, wire in (
        ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        result[normalized] = _usage_int(usage.get(wire), wire, errors)
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict):
        result["reasoning_tokens"] = _usage_int(
            details.get("reasoning_tokens"), "reasoning_tokens", errors,
        )
    elif details is not None:
        errors.append("completion_tokens_details_invalid")
    if result["total_tokens"] is not None:
        result["total_tokens_source"] = "provider"
    # The official example has reasoning > completion tokens. Neither inclusion,
    # cache accounting nor missing totals can be inferred from compatibility.
    result["usage_validation_errors"] = errors
    return result


def retry_after_seconds(data: Any) -> float | None:
    error = data.get("error") if isinstance(data, dict) else None
    value = error.get("retry_after") if isinstance(error, dict) else None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or value < 0):
        return None
    try:
        seconds = float(value)
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) else None


def response_retry_after_seconds(response: httpx.Response) -> float | None:
    from eslams.agents import _strict_provider_json
    from eslams.protocol import validate_json_payload

    try:
        data = _strict_provider_json(response)
        validate_json_payload(data)
    except (ValueError, UnicodeError, RecursionError):
        return None
    return retry_after_seconds(data)


def safe_rate_rejection(data: Any, status: int) -> bool:
    from eslams.agents import _safe_rate_rejection

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict) and "retry_after" in error:
        if retry_after_seconds(data) is None:
            return False
        data = {**data, "error": {key: value for key, value in error.items()
                                  if key != "retry_after"}}
    return _safe_rate_rejection(data, status)
