"""Direct Krutrim Cloud chat completions, without SDK defaults or routing."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "krutrim"
API_KEY_ENV = "KRUTRIM_CLOUD_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://cloud.olakrutrim.com/v1/chat/completions"
_MAX_ACTION_JSON_DEPTH = 64
_CREDENTIAL_SNAPSHOT: ContextVar[tuple[str, ...]] = ContextVar(
    "krutrim_credential_snapshot", default=(),
)


def _credential_values(agent: ModelProviderAgent, active_key: str | None = None) -> tuple[str, ...]:
    # Other configured Krutrim credentials must not become public merely because
    # this request used a different key. This does not add authentication aliases.
    values = set(_CREDENTIAL_SNAPSHOT.get())
    if active_key:
        values.add(active_key)
    for name, value in dict(os.environ).items():
        credential_name = name == agent.api_key_env or (
            "KRUTRIM" in name.upper() and any(marker in name.upper() for marker in (
                "API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL",
            )))
        if credential_name and value.strip():
            values.add(value.strip())
    return tuple(sorted(values))


@contextmanager
def credential_scope(agent: ModelProviderAgent) -> Iterator[None]:
    # Scope covers action parsing and receipt publication too, and survives a
    # key being rotated/removed while an in-flight response is being received.
    token = _CREDENTIAL_SNAPSHOT.set(_credential_values(agent))
    try:
        yield
    finally:
        _CREDENTIAL_SNAPSHOT.reset(token)


def _contains_credential(value: Any, secrets: tuple[str, ...]) -> bool:
    pending = [value]
    visited: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(secret in item for secret in secrets):
                return True
        elif isinstance(item, (dict, list)) and id(item) not in visited:
            visited.add(id(item))
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
    return False


def _check_action_json_depth(text: str) -> None:
    """Bound structural nesting before the recursive JSON decoder can run."""
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_ACTION_JSON_DEPTH:
                raise ValueError("Krutrim action JSON exceeds the nesting safety limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("Krutrim action JSON has unbalanced containers")


def _unique_action_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Krutrim action JSON field")
        result[key] = value
    return result


def _reject_action_constant(_value: str) -> Any:
    raise ValueError("Krutrim action JSON must contain finite values")


def _load_action_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_unique_action_fields,
                      parse_constant=_reject_action_constant)


def _decode_action_json(text: str) -> Any:
    # Match the shared action extractor's fences and object fallback, but keep
    # duplicate/finite-value validation local to this provider. A duplicate is
    # not a syntax error and must never be retried as a different candidate.
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    _check_action_json_depth(stripped)
    try:
        return _load_action_json(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start != -1 and end > start:
            candidate = stripped[start:end + 1]
            _check_action_json_depth(candidate)
            try:
                return _load_action_json(candidate)
            except json.JSONDecodeError:
                return None
    return None


def _action_text_is_safe(text: str, secrets: tuple[str, ...]) -> bool:
    return (not _contains_credential(text, secrets)
            and not _contains_credential(_decode_action_json(text), secrets))


def validate_config(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Krutrim requires an explicit nonblank model ID")
    if runtime is None:
        return
    if runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Krutrim has no verified reasoning controls; use reasoning=auto")
    if runtime.gateway_base_url or runtime.gateway_mode != "direct_provider":
        raise ValueError("Krutrim requires its direct operator endpoint")
    if runtime.openrouter_provider_order:
        raise ValueError("Krutrim does not support OpenRouter routing controls")


def sanitize_receipt(
    agent: ModelProviderAgent, receipt: dict[str, Any], *, secret: str | None = None,
) -> dict[str, Any]:
    """Remove exact credential echoes, including keys and harmless-looking IDs."""
    secrets = _credential_values(agent, secret)

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return None if _contains_credential(value, secrets) else value
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not _contains_credential(key, secrets)}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    result: dict[str, Any] = clean(receipt)
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def normalize_usage(usage: Any) -> dict[str, Any]:
    # OpenAI-compatible top-level counters are observations only. The official
    # SDK does not specify usage, caching or reasoning billing semantics.
    from eslams.agents import _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for source, target in (("prompt_tokens", "input_tokens"),
                           ("completion_tokens", "output_tokens"),
                           ("total_tokens", "total_tokens")):
        result[target] = _usage_int(usage.get(source), source, errors)
    result["total_tokens_source"] = (
        "provider" if result["total_tokens"] is not None else "unavailable"
    )
    result["usage_validation_errors"] = errors
    return result


def validate_action(
    agent: ModelProviderAgent, action: Any, explanation: str | None, secret: str,
) -> None:
    from eslams.protocol import ProtocolError

    secrets = _credential_values(agent, secret)
    if _contains_credential(action, secrets) or _contains_credential(explanation, secrets):
        raise ProtocolError("Krutrim action contains a credential echo")


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    try:
        return _call(agent, api_key, prompt)
    except (ProviderCallError, TimeoutError) as exc:
        secrets = _credential_values(agent, api_key)
        # No documented Krutrim rejection envelope establishes a safe replay.
        if isinstance(exc, ProviderCallError):
            exc.retry_permitted = False
            if exc.receipt is not None:
                exc.receipt = sanitize_receipt(agent, exc.receipt, secret=api_key)
            if _contains_credential(exc.model, secrets):
                exc.model = None
        if _contains_credential(str(exc), secrets):
            exc.args = ("Krutrim response rejected",)
        # Raw transport/JSON exceptions can carry private bodies and headers.
        raise exc from None


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    validate_config(agent.model, agent.runtime_config)
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
    response = _post_json(
        CHAT_COMPLETIONS_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=agent.runtime_config,
    )
    receipt = sanitize_receipt(agent, _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    ), secret=api_key)
    choices = data.get("choices")
    choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = choice.get("message") if isinstance(choice, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    secrets = _credential_values(agent, api_key)
    kind = "provider_response_schema_mismatch"
    if data.get("error") or (isinstance(choice, dict) and choice.get("error")):
        kind = "provider_unavailable"
    elif reason == "length":
        kind = "provider_output_truncated"
    elif reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        kind = "provider_refused"
    elif (isinstance(choice, dict) and type(choice.get("index")) is int
          and choice["index"] == 0
          and reason == "stop" and isinstance(message, dict)
          and message.get("role") == "assistant" and not message.get("tool_calls")
          and not message.get("function_call") and isinstance(text, str) and text.strip()):
        try:
            safe = _action_text_is_safe(text, secrets)
        except (ValueError, RecursionError, OverflowError):
            # The HTTP envelope and its accounting were already observed.
            # Reject unsafe action JSON through the normal receipt-bearing path.
            safe = False
        if safe:
            receipt.update(finish_reason="stop", finish_status="completed")
            return text, receipt
    receipt.update(
        outcome=kind,
        finish_reason=reason if reason in ("stop", "length", "content_filter") else "unknown",
        finish_status="incomplete" if kind == "provider_output_truncated" else "failed",
    )
    raise ProviderCallError(
        "Krutrim did not return one complete assistant text response",
        error_kind=kind, provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        status_code=response.status_code,
    )
