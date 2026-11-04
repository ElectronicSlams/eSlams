"""Direct Morph text inference; no SDK, router, search, or tool execution.

Contract checked 2026-11-04 against Morph's official llms.txt, endpoints,
Open Source Models, Apply response schema, and caching documentation.
"""

from __future__ import annotations

import json
import math
import os
import re
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus, unquote, unquote_plus

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ActRequest, ActResponse, validate_json_payload

if TYPE_CHECKING:
    import httpx

    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "morph"
API_KEY_ENV = "MORPH_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.morphllm.com/v1/chat/completions"
MODELS_ENDPOINT = "https://api.morphllm.com/v1/models"
SOURCES = [
    "https://docs.morphllm.com/llms.txt",
    "https://docs.morphllm.com/sdk/components/fast-models",
]

_COMMON_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
MODEL_EFFORTS: dict[str, tuple[str, ...]] = dict.fromkeys((
    "morph-glm53-744b", "morph-glm52-744b", "morph-glm53flash",
    "morph-dsv41flash", "morph-dsv41flash-1017", "morph-dsv41flash-abliterated",
    "morph-dsv4flash",
), _COMMON_EFFORTS)
MODEL_EFFORTS["morph-kimik3"] = ("none", "low", "medium", "high", "xhigh", "max")
MODEL_EFFORTS["morph-kimik3-fast"] = ("none", "low", "medium", "high")

_CREDENTIAL_NAME = re.compile(
    r"(?:^|_)(?:API_?KEY(?:_[A-Z0-9]+)?|ACCESS_KEY(?:_ID)?|SECRET_ACCESS_KEY|"
    r"PRIVATE_KEY|BEARER_TOKEN(?:_[A-Z0-9]+)?|TOKEN|PASSWORD|PASSWD|CREDENTIALS?|SECRET|KEY)$",
    re.IGNORECASE,
)
_ACTIVE_CREDENTIALS: ContextVar[tuple[str, ...]] = ContextVar("morph_credentials", default=())


def validate_configuration(model: str, runtime: ProviderRuntimeConfig) -> str | None:
    """Return an explicit native effort; never choose one from the game."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Morph requires an explicit nonblank model ID")
    if any(character.isspace() or ord(character) < 33 for character in model):
        raise ValueError("Morph model ID cannot contain whitespace or control characters")
    if is_specialized(model):
        raise ValueError("Morph specialized and automatic models cannot select text game actions")
    if runtime.history_window_turns is not None:
        raise ValueError("Morph text actions require full supplied history")
    if (runtime.reasoning_budget_tokens is not None
            or runtime.gemini_thinking_budget is not None
            or runtime.openrouter_provider_order):
        raise ValueError("Morph does not support the supplied provider-specific control")
    effort = "none" if runtime.reasoning == "disabled" else runtime.reasoning_effort
    if runtime.reasoning == "enabled" and (effort is None or effort == "none"):
        raise ValueError("Morph enabled reasoning requires an explicit supported non-none effort")
    if effort is not None and effort not in MODEL_EFFORTS.get(model, ()):
        raise ValueError("Morph reasoning effort is unsupported or unverified for this model")
    return effort


def is_specialized(model: str) -> bool:
    candidate = model.removeprefix("morph/")
    return candidate in {"auto", "reflex", "morph-v0", "morph-v2", "morph-compactor"} or (
        candidate.startswith(("morph-v3-", "morph-warp-", "morph-router"))
    )


def capability_records() -> list[dict[str, Any]]:
    """Documentation evidence only; account access and prices remain unverified."""
    return [{
        "provider": PROVIDER_ID, "model": model,
        "game_agent_supported": True, "available_from_api": None,
        "endpoints": ["chat/completions"], "supports_temperature": True,
        "supports_reasoning": True, "reasoning_efforts": list(efforts),
        "supported_reasoning_modes": ["native-default", *efforts],
        "default_reasoning_track": "native-default",
        "accepted_control_fields": ["reasoning_effort"],
        "last_verified_at": "2026-11-04", "sources": SOURCES,
        "lifecycle": "account-dependent",
    } for model, efforts in MODEL_EFFORTS.items()]


def credential_values(environment: str = API_KEY_ENV) -> tuple[str, ...]:
    """Private redaction-only snapshot; secondary credentials are never sent."""
    values = set(_ACTIVE_CREDENTIALS.get())
    for name, raw in os.environ.items():
        if (name in {environment, API_KEY_ENV} or _CREDENTIAL_NAME.search(name)) and raw.strip():
            values.add(raw.strip())
    return tuple(values)


def _unsafe(value: str, secrets: tuple[str, ...]) -> bool:
    from eslams.agents import _SECRET_TEXT_PATTERNS, _sanitize_receipt_value

    variants = {variant for secret in secrets for variant in (
        secret, quote(secret, safe=""), quote_plus(secret), json.dumps(secret)[1:-1],
    )}
    return (
        any(part in candidate for part in variants if part
            for candidate in (value, unquote(value), unquote_plus(value)))
        or any(pattern.search(value) for pattern in _SECRET_TEXT_PATTERNS)
        or _sanitize_receipt_value(value) != value
    )


def _scrub(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {key: _scrub(item, secrets) for key, item in value.items()
                if not _unsafe(str(key), secrets)}
    if isinstance(value, list):
        return [_scrub(item, secrets) for item in value]
    if isinstance(value, str) and _unsafe(value, secrets):
        return None
    return value


def sanitize_receipt(receipt: dict[str, Any], environment: str) -> dict[str, Any]:
    cleaned: dict[str, Any] = _scrub(receipt, credential_values(environment))
    if cleaned.get("locked_model_id") is None:
        cleaned["model_identity_source"] = None
    return cleaned


def contains_credentials(value: Any, secrets: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(_unsafe(str(key), secrets) or contains_credentials(item, secrets)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(contains_credentials(item, secrets) for item in value)
    return isinstance(value, str) and _unsafe(value, secrets)


def discovery_payload(response: httpx.Response) -> Any:
    from eslams.agents import _strict_provider_json

    data = _strict_provider_json(response)
    validate_json_payload(data)
    if isinstance(data, dict) and data.get("error") is not None:
        raise ValueError("Morph model discovery failed")
    return data


def act(agent: ModelProviderAgent, request: ActRequest) -> ActResponse:
    """Check decoded action fields too, before returning anything to the caller."""
    validate_configuration(agent.model, agent.runtime_config or ProviderRuntimeConfig())
    secrets = credential_values(agent.api_key_env)
    token = _ACTIVE_CREDENTIALS.set(secrets)
    try:
        return _act_checked(agent, request, secrets)
    finally:
        _ACTIVE_CREDENTIALS.reset(token)


def _act_checked(
    agent: ModelProviderAgent, request: ActRequest, secrets: tuple[str, ...],
) -> ActResponse:
    from eslams.agents import ProviderCallError

    try:
        result = agent._act(request)
    except ProviderCallError as exc:
        raise ProviderCallError(
            "Morph request failed", status_code=exc.status_code,
            error_kind=exc.error_kind, retry_after_seconds=exc.retry_after_seconds,
            provider=PROVIDER_ID, model=_scrub(agent.model, secrets),
            receipt=(sanitize_receipt(exc.receipt, agent.api_key_env)
                     if exc.receipt is not None else None),
        ) from None
    except TimeoutError:
        raise TimeoutError("Morph request timed out") from None
    if contains_credentials(result.to_dict(), credential_values(agent.api_key_env)):
        receipt = {**(agent.last_receipt or {}), "outcome": "provider_response_schema_mismatch"}
        agent._replace_last_receipt(receipt)
        raise ProviderCallError(
            "Morph action contains sensitive data", provider=PROVIDER_ID,
            error_kind="provider_response_schema_mismatch", receipt=agent.last_receipt,
        ) from None
    return result


def usage_fields(value: Any) -> Any:
    """Accept documented Chat Completions positions, retaining absent counters."""
    if not isinstance(value, dict):
        return value
    result = {key: value[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in value}
    for group, field in (("prompt_tokens_details", "cached_tokens"),
                         ("completion_tokens_details", "reasoning_tokens")):
        details = value.get(group)
        if isinstance(details, dict) and field in details:
            result[group] = {field: details[field]}
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _extract_json,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config or ProviderRuntimeConfig()
    effort = validate_configuration(agent.model, runtime)
    secrets = (*credential_values(agent.api_key_env), api_key)
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
    if effort is not None:
        payload["reasoning_effort"] = effort
    if agent.temperature is not None:
        if isinstance(agent.temperature, bool) or not math.isfinite(agent.temperature):
            raise ValueError("Morph temperature must be a finite number")
        payload["temperature"] = agent.temperature
    try:
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime,
            control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
    except ProviderCallError as exc:
        raise ProviderCallError(
            "Morph response could not be verified", status_code=exc.status_code,
            error_kind=exc.error_kind, provider=PROVIDER_ID, model=_scrub(agent.model, secrets),
            retry_after_seconds=exc.retry_after_seconds,
            receipt=(sanitize_receipt(exc.receipt, agent.api_key_env)
                     if exc.receipt is not None else None),
            # No Morph-specific proof of safe replay is established here.
        ) from None
    secrets = (*secrets, *credential_values(agent.api_key_env))
    receipt = sanitize_receipt(_receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=_scrub(data.get("id"), secrets),
        resolved_model=_scrub(data.get("model"), secrets),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    ), agent.api_key_env)
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    if data.get("error") is not None or (
        isinstance(first, dict) and first.get("error") is not None
    ):
        receipt.update(locked_model_id=None, model_identity_source=None)
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt = sanitize_receipt(receipt, agent.api_key_env)
    try:
        text = _completion_text(data, receipt)
        if _unsafe(text, secrets) or contains_credentials(_extract_json(text), secrets):
            raise ProviderCallError(
                "Morph action contains sensitive data",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            )
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _completion_text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError, _body_error_status, _provider_error_kind

    def fail(kind: str = "provider_response_schema_mismatch") -> None:
        raise ProviderCallError("Morph did not return a completed text action",
                                error_kind=kind, provider=PROVIDER_ID)

    def error_kind(error: Any) -> str:
        code = error.get("code") if isinstance(error, dict) else None
        status = {"unauthorized": 401, "rate_limited": 429,
                  "resource_unavailable": 429, "member_budget_exceeded": 429}.get(
                      code if isinstance(code, str) else "",
                  ) or _body_error_status(error)
        return _provider_error_kind(status) if status is not None else (
            "provider_response_schema_mismatch"
        )

    if data.get("error") is not None:
        fail(error_kind(data["error"]))
    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail()
    # The guard above guarantees a single dictionary, even for malformed input.
    assert isinstance(choices, list)
    choice = choices[0]
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if reason in ("stop", "length", "content_filter",
                                                       "tool_calls", "function_call") else "unknown"
    receipt["finish_status"] = "completed" if reason == "stop" else "incomplete"
    if choice.get("error") is not None:
        fail(error_kind(choice["error"]))
    message = choice.get("message")
    if not isinstance(message, dict):
        fail()
    assert isinstance(message, dict)
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        fail()
    if refusal or reason == "content_filter":
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if reason == "length":
        fail("provider_output_truncated")
    tools = message.get("tool_calls")
    if tools is not None and not isinstance(tools, list):
        fail()
    if reason in ("tool_calls", "function_call") or tools or (
        message.get("function_call") is not None
    ):
        fail("provider_request_rejected")
    if (reason != "stop" or message.get("role") != "assistant"
            or not isinstance(choice.get("index"), int)
            or choice.get("index") != 0 or isinstance(choice.get("index"), bool)):
        fail()
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        fail()
    assert isinstance(text, str)
    return text
