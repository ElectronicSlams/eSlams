"""Meituan LongCat's native, non-streaming Chat Completions contract.

Official sources and accounting limitations: docs/providers/LONGCAT.md.
Shared transport/receipt imports are local to keep provider dispatch acyclic.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "meituan"
PROVIDER_ALIASES = ("meituan", "longcat", "meituan-longcat")
API_KEY_ENV = "LONGCAT_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.longcat.chat/openai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.longcat.chat/openai/v1/models"
ENDPOINT_KIND = "longcat_chat_completions"
PARSER_VERSION = "longcat-chat-completions-raw-v1"
_REQUEST_CREDENTIALS: ContextVar[tuple[str, ...]] = ContextVar("longcat_credentials", default=())


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in PROVIDER_ALIASES else provider.lower()


def validate_model(model: object) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("LongCat requires an explicit provider-native model ID")


def validate_configuration(model: object, runtime: ProviderRuntimeConfig | None) -> None:
    validate_model(model)
    if runtime and (runtime.reasoning_effort is not None
                    or runtime.gemini_thinking_budget is not None):
        raise ValueError(
            "LongCat accepts reasoning enabled/disabled/auto and reasoning_budget_tokens; "
            "reasoning_effort and gemini_thinking_budget are unsupported"
        )


def credential_values(primary: str, api_key_env: str) -> tuple[str, ...]:
    # Include the selected key and configured LongCat secondary credentials.
    # Do not retain this per-request snapshot on the agent or in public receipts.
    names = {API_KEY_ENV, api_key_env}
    names.update(name for name in os.environ if "LONGCAT" in name.upper()
                 and any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")))
    values = {primary}
    values.update(os.environ[name].strip() for name in names if os.environ.get(name, "").strip())
    return tuple(sorted(values - {""}, key=len, reverse=True))


def credential_echo(value: Any, credentials: tuple[str, ...] | None = None) -> bool:
    active = _REQUEST_CREDENTIALS.get() if credentials is None else credentials
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and any(secret in item for secret in active):
            return True
        if isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return False


@contextmanager
def credential_scope(primary: str, api_key_env: str) -> Iterator[None]:
    token = _REQUEST_CREDENTIALS.set(credential_values(primary, api_key_env))
    try:
        yield
    finally:
        _REQUEST_CREDENTIALS.reset(token)


def complete(
    agent: ModelProviderAgent, api_key: str, prompt: str, *, system_instructions: str,
) -> tuple[str, dict[str, Any]]:
    with credential_scope(api_key, agent.api_key_env):
        return _complete(agent, api_key, prompt, system_instructions=system_instructions)


def _complete(
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
    from eslams.model_actions import extract_json

    runtime = agent.runtime_config
    try:
        validate_configuration(agent.model, runtime)
    except ValueError as exc:
        raise ProviderCallError(
            str(exc),
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        ) from None
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
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        if isinstance(first, dict) and credential_echo(first.get("finish_reason")):
            raise ProviderCallError(
                "LongCat returned credential-bearing completion metadata; no action accepted",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID, model=agent.model,
            )
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        # Reasoning is private telemetry, never an alternate source of action text.
        if (not isinstance(choices, list) or len(choices) != 1
                or not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or message.get("function_call")
                or not isinstance(content, str) or not content.strip()):
            raise ProviderCallError(
                "LongCat returned no complete assistant text choice",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID, model=agent.model,
            )
        try:
            content_has_credentials = (
                credential_echo(content) or credential_echo(extract_json(content))
            )
        except (ValueError, RecursionError):
            raise ProviderCallError(
                "LongCat returned unverifiable action content; no action accepted",
                error_kind="provider_response_schema_mismatch",
                provider=PROVIDER_ID, model=agent.model,
            ) from None
        if content_has_credentials:
            raise ProviderCallError(
                "LongCat returned credential-bearing action content; no action accepted",
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
