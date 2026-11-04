"""Upstage direct Chat Completions; documented REST shapes, no SDK or broker."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "upstage"
API_KEY_ENV = "UPSTAGE_API_KEY"
DEFAULT_MODEL = "solar-pro4"
CHAT_COMPLETIONS_ENDPOINT = "https://api.upstage.ai/v1/chat/completions"
ENDPOINT_KIND = "upstage_chat_completions"
PARSER_VERSION = "upstage-chat-completions-raw-v1"
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


def reasoning_effort(runtime: ProviderRuntimeConfig | None) -> str | None:
    # Lazy imports keep provider-specific code separate from shared custody.
    from eslams.agents import ProviderCallError

    if runtime is None:
        return None
    if runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None:
        raise ProviderCallError(
            "Upstage accepts reasoning_effort, not a numeric thinking budget",
            error_kind="provider_request_rejected", provider=PROVIDER_ID,
        )
    if runtime.reasoning == "disabled":
        return "none"
    effort = runtime.reasoning_effort
    if effort is not None and effort not in REASONING_EFFORTS:
        raise ProviderCallError(
            "unsupported Upstage reasoning_effort",
            error_kind="provider_request_rejected", provider=PROVIDER_ID,
        )
    if runtime.reasoning == "enabled" and effort in {None, "none", "minimal"}:
        raise ProviderCallError(
            "Upstage reasoning enabled requires an explicit effort from low through max",
            error_kind="provider_request_rejected", provider=PROVIDER_ID,
        )
    return effort


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Upstage category cooldowns are Unix seconds, not HTTP delta seconds."""
    if response.status_code != 429:
        return None
    delays = []
    now = time.time()
    for category in ("Requests", "Tokens", "Pages"):
        raw = response.headers.get(f"X-Upstage-RateLimit-Retry-After-{category}")
        if raw is None:
            continue
        try:
            timestamp = float(raw)
        except ValueError:
            continue
        if math.isfinite(timestamp) and timestamp >= 0:
            delays.append(max(0.0, timestamp - now))
    return max(delays) if delays else None


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
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
        "reasoning_effort": reasoning_effort(runtime),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
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
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        if (
            data.get("object") != "chat.completion"
            or not isinstance(first, dict)
            or first.get("index") != 0 or isinstance(first.get("index"), bool)
            or first.get("finish_reason") != "stop"
            or not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or message.get("function_call")
            or not isinstance(message.get("content"), str) or not message["content"].strip()
        ):
            raise ProviderCallError(
                "Upstage response is not a complete assistant text choice",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        # Visible reasoning is deliberately excluded from actions and receipts.
        text = message["content"]
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt
