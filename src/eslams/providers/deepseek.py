"""Native DeepSeek Chat Completions adapter (documented REST, non-streaming)."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent, ProviderCallError
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "deepseek"
API_KEY_ENV = "DEEPSEEK_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.deepseek.com/chat/completions"
MODELS_ENDPOINT = "https://api.deepseek.com/models"


def canonical_provider(value: str) -> str:
    """Normalize only this adapter's names; leave other adapters' policy intact."""
    return PROVIDER_ID if value.strip().lower().replace("_", "-") in {
        "deepseek", "deep-seek",
    } else value


def validate_model(model: Any) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("DeepSeek requires an explicit nonblank model ID")


def configuration_error(model: Any, runtime: ProviderRuntimeConfig | None) -> str | None:
    try:
        validate_model(model)
    except ValueError as exc:
        return str(exc)
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        return "DeepSeek does not support explicit token reasoning budgets"
    return None


def credential_values(primary: str | None = None) -> tuple[str, ...]:
    """Private comparison material, including secondary credential environment values."""
    values = {primary} if primary else set()
    for name, value in os.environ.items():
        if re.search(
            r"(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?|ACCESS_KEY|PRIVATE_KEY|KEY)(?:$|_)",
            name.upper(),
        ) and value.strip():
            values.add(value.strip())
    return tuple(sorted({variant for value in values for variant in
                         (value, quote(value, safe=""), quote_plus(value, safe=""))},
                        key=len, reverse=True))


def has_credential_echo(value: Any, secrets: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    if isinstance(value, dict):
        return any(has_credential_echo(key, secrets) or has_credential_echo(item, secrets)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(has_credential_echo(item, secrets) for item in value)
    return False


def _redact_echoes(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return None if has_credential_echo(value, secrets) else value
    if isinstance(value, dict):
        return {key: _redact_echoes(item, secrets) for key, item in value.items()
                if not has_credential_echo(key, secrets)}
    if isinstance(value, list):
        return [_redact_echoes(item, secrets) for item in value]
    return value


def _redact_receipt(receipt: dict[str, Any], secrets: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = _redact_echoes(receipt, secrets)
    if not result.get("locked_model_id"):
        result["model_identity_source"] = None
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError
    from eslams.model_actions import extract_json

    problem = configuration_error(agent.model, agent.runtime_config)
    if problem:
        raise ProviderCallError(problem, error_kind="provider_request_rejected",
                                provider=PROVIDER_ID, model=agent.model)
    secrets = credential_values(api_key)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        # Preserve retry admission from the original evidence before removing echoes.
        # In particular, an accepted-work ID must not disappear into a safe retry.
        if exc.receipt is not None:
            exc.receipt = _redact_receipt(exc.receipt, secrets)
        if has_credential_echo(str(exc), secrets):
            exc.args = ("DeepSeek request failed; credential echo removed",)
        raise
    receipt = _redact_receipt(receipt, secrets)
    if has_credential_echo(text, secrets) or has_credential_echo(extract_json(text), secrets):
        raise ProviderCallError(
            "DeepSeek output contained a credential echo; no action accepted",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model, receipt=receipt,
        )
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at execution time: shared attempt/transport machinery owns the agent.
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
    }
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["max_tokens"] = limit
    if runtime and runtime.reasoning != "auto":
        payload["thinking"] = {"type": runtime.reasoning}
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning_effort"] = runtime.reasoning_effort
    # Temperature has no effect in thinking mode. Auto preserves the native default.
    if agent.temperature is not None and runtime and runtime.reasoning == "disabled":
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
        if (data.get("object") != "chat.completion" or not isinstance(choices, list)
                or len(choices) != 1 or not isinstance(choices[0], dict)):
            raise _schema_error()
        choice = choices[0]
        reason = choice.get("finish_reason")
        message = choice.get("message")
        if (reason != "stop" or type(choice.get("index")) is not int or choice["index"] != 0
                or not isinstance(message, dict) or message.get("role") != "assistant"):
            raise _schema_error()
        if message.get("tool_calls"):
            raise ProviderCallError(
                "DeepSeek returned unsolicited tool calls; no action accepted",
                error_kind="provider_request_rejected", provider=PROVIDER_ID,
            )
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise _schema_error()
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _schema_error() -> ProviderCallError:
    from eslams.agents import ProviderCallError

    return ProviderCallError(
        "DeepSeek response has no complete assistant text choice",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
    )


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Cache hits are an input subset; reasoning is part of completion tokens."""
    from eslams.agents import _normalize_usage, _usage_int

    # HTTP-agent receipts may already contain normalized usage.
    if "usage_source" in usage and "input_tokens" in usage:
        return _normalize_usage("openai", usage)
    details = usage.get("prompt_tokens_details")
    cached_detail = details.get("cached_tokens") if isinstance(details, dict) else None
    hit = usage.get("prompt_cache_hit_tokens", cached_detail)
    result = _normalize_usage("openai", {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": hit,
        "completion_tokens_details": usage.get("completion_tokens_details"),
    })
    errors = result["usage_validation_errors"]
    miss = _usage_int(usage.get("prompt_cache_miss_tokens"), "prompt_cache_miss_tokens", errors)
    detail = _usage_int(cached_detail, "prompt_tokens_details.cached_tokens", errors)
    if "prompt_tokens_details" in usage and not isinstance(details, dict):
        errors.append("prompt_tokens_details_invalid")
    output_details = usage.get("completion_tokens_details")
    if "completion_tokens_details" in usage and not isinstance(output_details, dict):
        errors.append("completion_tokens_details_invalid")
    cached = result["cache_read_input_tokens"]
    if detail is not None and cached is not None and detail != cached:
        errors.append("prompt_cache_hit_tokens_inconsistent")
    if (miss is not None and cached is not None and result["input_tokens"] is not None
            and miss + cached != result["input_tokens"]):
        errors.append("prompt_cache_tokens_inconsistent")
    result["usage_validation_errors"] = sorted(set(errors))
    return result
