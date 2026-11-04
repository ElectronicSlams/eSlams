"""Upstage direct Chat Completions; documented REST shapes, no SDK or broker."""

from __future__ import annotations

import math
import os
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "upstage"
API_KEY_ENV = "UPSTAGE_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.upstage.ai/v1/chat/completions"
ENDPOINT_KIND = "upstage_chat_completions"
PARSER_VERSION = "upstage-chat-completions-raw-v1"
REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


def validate_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Upstage requires an explicit nonblank model ID")


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


def _credential_values(api_key: str) -> tuple[str, ...]:
    from eslams.agents import _sensitive_receipt_key

    # Snapshot per invocation; include secondary provider/gateway credentials,
    # including a custom api_key_env, without persisting them on the agent.
    return tuple({api_key, *(value.strip() for name, value in os.environ.items()
                             if _sensitive_receipt_key(name) and value.strip())})


def _scrub_echoes(value: Any, credentials: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return None if any(secret in value for secret in credentials) else value
    if isinstance(value, dict):
        return {key: _scrub_echoes(item, credentials) for key, item in value.items()
                if not any(secret in key for secret in credentials)}
    if isinstance(value, list):
        return [_scrub_echoes(item, credentials) for item in value]
    return value


def _scrub_receipt(receipt: dict[str, Any], credentials: tuple[str, ...]) -> dict[str, Any]:
    sanitized: dict[str, Any] = _scrub_echoes(receipt, credentials)
    if sanitized.get("locked_model_id") is None:
        sanitized["model_identity_source"] = None
    return sanitized


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    validate_model(agent.model)
    credentials = _credential_values(api_key)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _scrub_receipt(exc.receipt, credentials)
        raise
    receipt = _scrub_receipt(receipt, credentials)
    if _scrub_echoes(text, credentials) is None:
        # Never rewrite credential-bearing prose into an apparently valid action.
        raise ProviderCallError(
            "Upstage answer contains a credential echo; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model, receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
        )
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
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
