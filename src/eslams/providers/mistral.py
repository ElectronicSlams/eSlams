"""Mistral AI's native, non-streaming Chat Completions adapter.

REST/schema provenance and deliberately unsupported features are documented in
docs/providers/MISTRAL.md. This module uses Core's shared attempt transport and
accounting; it does not introduce an SDK, fallback, or independent retry loop.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import replace
from functools import wraps
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent, ProviderCallError
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "mistral-ai"
API_KEY_ENV = "MISTRAL_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.mistral.ai/v1/models"
_JSON_ESCAPES = re.compile(r'(?:\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))+')


def configuration_error(model: object, runtime: ProviderRuntimeConfig | None) -> str | None:
    """Reject missing IDs and controls this adapter cannot honor, without I/O."""
    if not isinstance(model, str) or not model.strip():
        return "Mistral requires a non-empty explicit model ID"
    if runtime is not None and (
        runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None
    ):
        return "Mistral does not support explicit token-based reasoning budgets"
    return None


def _credential_variants(primary: str | None = None) -> tuple[str, ...]:
    # Include secondary provider/gateway credentials, including a primary key
    # supplied under a custom environment name. Never log these values.
    values = {primary} if primary else set()
    for name, value in os.environ.items():
        if name.upper() in {
            "ESLAMS_ARENA_SESSION_KEY_ID", "ESLAMS_RUNNER_REQUEST_KEY_ID",
            "ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS", "RUNNER_ARTIFACT_SIGNING_KEY_ID",
        }:
            continue  # Public credential identifiers are not credential values.
        if re.search(r"(?:^|_)(?:KEY|APIKEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?|AUTHORIZATION)"
                     r"(?:_|$)", name.upper()) and value.strip():
            values.add(value.strip())
    variants: set[str] = set()
    for value in values:
        variants.update((value, json.dumps(value)[1:-1],
                         json.dumps(value, ensure_ascii=False)[1:-1],
                         quote(value, safe=""), quote_plus(value, safe="")))
    return tuple(sorted(variants - {""}, key=len, reverse=True))


def contains_credential(value: str, primary: str | None = None) -> bool:
    return _contains_credential_text(value, _credential_variants(primary))


def _contains_credential_text(value: str, secrets: tuple[str, ...]) -> bool:
    if any(secret in value for secret in secrets):
        return True

    def decode(match: re.Match[str]) -> str:
        # Comparison only: the original action is never rewritten. A run of
        # escapes is decoded together so JSON surrogate pairs stay intact.
        return str(json.loads('"' + match.group(0) + '"'))

    decoded = _JSON_ESCAPES.sub(decode, value)
    return any(secret in decoded for secret in secrets)


def _action_contains_credential(text: str, secrets: tuple[str, ...]) -> bool:
    from eslams.model_actions import extract_json

    if _contains_credential_text(text, secrets):
        return True
    # Match Core's fenced/prose JSON recovery, then inspect every decoded key
    # and string value. Do not validate, choose, coerce or repair an action here.
    pending = [extract_json(text)]
    while pending:
        value = pending.pop()
        if isinstance(value, str) and _contains_credential_text(value, secrets):
            return True
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def _scrub_text(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    return value


def _scrub_receipt(value: Any, secrets: tuple[str, ...]) -> Any:
    # Core constructs this closed receipt shape itself. Only its identifier
    # fields carry untrusted provider strings; keep trusted protocol labels and
    # enum values intact even if an unrelated short secret matches their text.
    if isinstance(value, list):
        return [_scrub_receipt(item, secrets) for item in value]
    if isinstance(value, dict):
        result = {key: _scrub_receipt(item, secrets) for key, item in value.items()}
        for key in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id"):
            if isinstance(result.get(key), str) and (
                _scrub_text(result[key], secrets) != result[key]
                or "[REDACTED]" in result[key]
            ):
                result[key] = None
        if "locked_model_id" in result and result["locked_model_id"] is None:
            result["model_identity_source"] = None
        return result
    return value


def discovery_guard(
    discover: Callable[[str], list[str] | None],
) -> Callable[[str], list[str] | None]:
    """Drop raw exception contexts only for this provider's discovery calls."""
    @wraps(discover)
    def guarded(provider: str) -> list[str] | None:
        if provider.strip().lower().replace("_", "-") not in {"mistral", PROVIDER_ID}:
            return discover(provider)
        from eslams.agents import ProviderCallError

        secrets = _credential_variants()
        try:
            models = discover(provider)
            if any(_contains_credential_text(model, secrets) for model in models or []):
                raise ProviderCallError(
                    "Mistral model discovery returned a credential-contaminated identifier",
                    error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                )
            return models
        except ProviderCallError as exc:
            failure = ProviderCallError(
                _scrub_text(str(exc), secrets), status_code=exc.status_code,
                error_kind=exc.error_kind, provider=PROVIDER_ID, model=exc.model,
                receipt=_scrub_receipt(exc.receipt, secrets),
                retry_after_seconds=exc.retry_after_seconds, retry_permitted=exc.retry_permitted,
            )
        raise failure from None

    return guarded


def complete(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    secrets = _credential_variants(api_key)
    failure: ProviderCallError | TimeoutError | None = None
    receipt: dict[str, Any] | None = None
    try:
        error = configuration_error(agent.model, agent.runtime_config)
        if error:
            raise _error(error, "provider_request_rejected")
        text, receipt = _complete(agent, api_key, prompt)
        try:
            contaminated = _action_contains_credential(text, secrets)
        except (ValueError, RecursionError, OverflowError):
            raise ProviderCallError(
                "Mistral action could not be inspected safely; no action accepted",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
                receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
            ) from None
        if contaminated:
            raise ProviderCallError(
                "Mistral action contains configured credential material; no action accepted",
                error_kind="provider_request_rejected", provider=PROVIDER_ID,
                model=agent.model, receipt={**receipt, "outcome": "provider_request_rejected"},
            )
    except ProviderCallError as exc:
        # Preserve the original retry decision. Removing a contaminated ID must
        # never turn observed/ambiguous work into a safe rejection to replay.
        failure = ProviderCallError(
            _scrub_text(str(exc), secrets), status_code=exc.status_code,
            error_kind=exc.error_kind, retry_after_seconds=exc.retry_after_seconds,
            provider=PROVIDER_ID, model=agent.model,
            receipt=_scrub_receipt(exc.receipt, secrets), retry_permitted=exc.retry_permitted,
        )
    except TimeoutError as exc:
        failure = (
            ProviderCallError(
                "Mistral response inspection timed out; no action accepted",
                error_kind="provider_timeout", provider=PROVIDER_ID, model=agent.model,
                receipt=_scrub_receipt({**receipt, "outcome": "provider_timeout"}, secrets),
            ) if receipt is not None else TimeoutError(_scrub_text(str(exc), secrets))
        )
    if failure is not None:
        # Raise outside the handler so even private exception context cannot
        # retain the original transport/body exception and its credential echo.
        raise failure from None
    return text, _scrub_receipt(receipt, secrets)


def _complete(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    # Imported at invocation time to keep provider-specific parsing out of the
    # common agent while reusing its transport, redaction and receipt contracts.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

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
    if agent.runtime_config and agent.runtime_config.reasoning_effort is not None:
        # An explicit operator choice, subject to authoritative model rejection.
        # Never select prompt_mode or reasoning effort based on the game.
        payload["reasoning_effort"] = agent.runtime_config.reasoning_effort
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, agent.runtime_config),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=agent.runtime_config,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        # The frozen author catalogue includes third-party/broker pricing.
        # None of it is a verified rate card for this direct Mistral route.
        usage=data.get("usage"), capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=agent.runtime_config,
    )
    try:
        # Handles HTTP 200 error envelopes without exposing their private prose.
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = _text(data, receipt)
        resolved_model = data.get("model")
        if not isinstance(resolved_model, str) or not resolved_model.strip():
            raise _error("Mistral response must include a nonblank model identity")
        if resolved_model != agent.model:
            raise _error(
                "Mistral returned a conflicting model identity; no action accepted",
                "provider_request_rejected",
            )
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _error(message: str, kind: str = "provider_response_schema_mismatch") -> ProviderCallError:
    from eslams.agents import ProviderCallError

    return ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID)


def _text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    choices = data.get("choices")
    if (not isinstance(choices, list) or len(choices) != 1
            or not isinstance(choices[0], dict)):
        raise _error("Mistral response must contain one completion choice")
    choice = choices[0]
    reason = choice.get("finish_reason")
    known = {"stop", "length", "model_length", "error", "tool_calls", "content_filter", "refusal"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason in ("length", "model_length"):
        raise _error(
            "Mistral token/context limit interrupted the response", "provider_output_truncated",
        )
    if reason in ("content_filter", "refusal"):
        receipt["finish_status"] = "refused"
        raise _error("Mistral refused or filtered the requested action", "provider_refused")
    if reason == "error":
        receipt["finish_status"] = "failed"
        raise _error("Mistral reported a completion error", "provider_unavailable")
    if reason == "tool_calls":
        raise _error("Mistral returned an unsupported tool call", "provider_request_rejected")
    if reason != "stop":
        raise _error("Mistral response has no supported terminal finish reason")
    if (type(choice.get("index")) is not int or choice.get("index") != 0
            or data.get("status") not in (None, "completed")):
        raise _error("Mistral response has an invalid completion envelope")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise _error("Mistral response is missing an assistant message")
    if message.get("refusal"):
        receipt["finish_status"] = "refused"
        raise _error("Mistral refused the requested action", "provider_refused")
    if message.get("tool_calls"):
        raise _error("Mistral returned an unsupported tool call", "provider_request_rejected")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        receipt["finish_status"] = "completed"
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                raise _error("Mistral returned malformed content chunks")
            if part.get("type") == "thinking" and isinstance(part.get("thinking"), list):
                continue
            if part.get("type") != "text" or not isinstance(part.get("text"), str):
                raise _error("Mistral returned unsupported or malformed content chunks")
            chunks.append(part["text"])
        text = "".join(chunks)
        if text.strip():
            receipt["finish_status"] = "completed"
            return text
    raise _error("Mistral response has no answer text")
