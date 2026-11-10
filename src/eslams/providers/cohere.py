"""Native Cohere Platform Chat v2; no OpenAI compatibility or model routing.

Raw wire references and limitations: docs/providers/cohere.md.
Imports of Core's transport/receipt helpers are deferred to avoid a module cycle.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

import httpx

from eslams.provider_credentials import provider_key

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent, ProviderCallError
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "cohere"
API_KEY_ENV = "COHERE_API_KEY"
CHAT_ENDPOINT = "https://api.cohere.com/v2/chat"
MODELS_ENDPOINT = "https://api.cohere.com/v1/models"
THINKING_MODELS = frozenset({"command-a-reasoning-08-2025", "command-a-plus-05-2026"})


def canonical_provider(value: str) -> str | None:
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in {PROVIDER_ID, "cohere-ai"} else None


def validate_model(model: Any) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Cohere requires an explicit nonblank model ID")


def configuration_error(model: str, config: ProviderRuntimeConfig | None) -> str | None:
    if config is None:
        return None
    if config.reasoning_effort is not None or config.gemini_thinking_budget is not None:
        return "Cohere supports thinking type/token_budget, not effort or Gemini controls"
    if config.reasoning_budget_tokens == 0:
        return "Cohere thinking token_budget must be positive; use reasoning=disabled to disable it"
    if (config.reasoning != "auto" or config.reasoning_budget_tokens is not None
            ) and model not in THINKING_MODELS:
        return "Cohere explicit thinking controls require an exactly verified reasoning model ID"
    return None


def _credentials(api_key: str | None = None, api_key_env: str | None = None) -> tuple[str, ...]:
    # CO_API_KEY is a Cohere SDK name. It is redacted, never selected as an
    # implicit authentication fallback. Include custom agent credentials too.
    values = {api_key} if api_key else set()
    for name in (API_KEY_ENV, "CO_API_KEY", api_key_env):
        if name:
            value = os.environ.get(name, "").strip()
            if value:
                values.add(value)
    variants = {variant for value in values for variant in (
        value, json.dumps(value, ensure_ascii=False)[1:-1],
        quote(value, safe=""), quote_plus(value),
    )}
    return tuple(sorted(variants, key=len, reverse=True))


def _redact_text(value: str, credentials: tuple[str, ...]) -> str:
    for credential in credentials:
        value = value.replace(credential, "[REDACTED]")
    return value


def _contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return _redact_text(value, credentials) != value
    if isinstance(value, dict):
        return any(_contains_credential(key, credentials) or _contains_credential(item, credentials)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_credential(item, credentials) for item in value)
    return False


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams import agents as core
    from eslams.model_actions import extract_json

    config = agent.runtime_config
    try:
        validate_model(agent.model)
    except ValueError:
        raise core.ProviderCallError(
            "Cohere requires an explicit nonblank model ID",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        ) from None
    error = configuration_error(agent.model, config)
    if error:
        raise core.ProviderCallError(error, error_kind="provider_request_rejected",
                                     provider=PROVIDER_ID, model=agent.model)
    credentials = _credentials(api_key, agent.api_key_env)
    payload: dict[str, Any] = {
        "model": agent.model,
        "stream": False,
        "messages": [
            {"role": "system", "content": core._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    thinking: dict[str, Any] = {}
    if config and config.reasoning != "auto":
        thinking["type"] = config.reasoning
    if config and config.reasoning_budget_tokens is not None:
        thinking.setdefault("type", "enabled")
        thinking["token_budget"] = config.reasoning_budget_tokens
    if thinking:
        payload["thinking"] = thinking
    try:
        response = core._post_json(
            core._provider_endpoint(CHAT_ENDPOINT, config),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=config, control_key=f"{PROVIDER_ID}:{agent.model}",
        )
    except core.ProviderCallError as exc:
        # Cohere's documented native error is {"message": ...}. Neither that
        # prose nor an undocumented gateway envelope attests rejected work.
        exc.retry_permitted = False
        _redact_identifiers(exc.receipt, credentials)
        exc.args = (_redact_text(str(exc), credentials),)
        if exc.status_code in {498, 499}:
            exc.error_kind = _http_error_kind(exc.status_code)
            if exc.receipt is not None:
                exc.receipt["outcome"] = exc.error_kind
        raise exc from None
    except TimeoutError:
        raise TimeoutError("Cohere provider timed out") from None
    try:
        data = core._response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=config,
        )
    except core.ProviderCallError as exc:
        _redact_identifiers(exc.receipt, credentials)
        raise exc from None
    receipt = core._receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=None,
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=config,
    )
    _redact_identifiers(receipt, credentials)
    # V2 Chat attests a reply ID, not the served model. Processed tokens are
    # not billed units. Neither a catalogue price nor an echoed extension is
    # sufficient evidence for a canonical monetary cost.
    receipt["estimated_cost"] = {
        "status": "cost_unavailable",
        "unavailable_reason": "cohere_billing_and_model_identity_unverified",
    }
    normalized = normalize_usage(data.get("usage"))
    if any(normalized.get(key) is not None
           for key in ("billed_input_tokens", "billed_output_tokens")) or (
        normalized["usage_validation_errors"]
    ):
        receipt["usage"] = normalized
    try:
        # Reuse error-envelope classification before enforcing Cohere's enum.
        core._check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = _text(data, receipt, agent.model)
        if (_contains_credential(text, credentials)
                or _contains_credential(extract_json(text), credentials)):
            raise core.ProviderCallError(
                "Cohere returned credential-bearing action text; no action accepted",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
    except core.ProviderCallError as exc:
        exc.retry_permitted = False
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise exc from None
    return text, receipt


def _redact_identifiers(receipt: dict[str, Any] | None, credentials: tuple[str, ...]) -> None:
    # Shared sanitizers reject sensitive shapes; additionally reject an exact
    # credential echoed in an otherwise syntactically valid opaque identifier.
    if receipt is None:
        return
    for name in ("provider_response_id", "request_id", "gateway_request_id"):
        value = receipt.get(name)
        if isinstance(value, str) and _redact_text(value, credentials) != value:
            receipt[name] = None


def _text(data: dict[str, Any], receipt: dict[str, Any], model: str) -> str:
    from eslams.agents import ProviderCallError

    reason = data.get("finish_reason")
    if "error" in data or "status" in data:
        raise _schema_error(model)
    known = {"COMPLETE", "STOP_SEQUENCE", "MAX_TOKENS", "TOOL_CALL", "ERROR", "TIMEOUT"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    kind = {
        "MAX_TOKENS": "provider_output_truncated",
        "TOOL_CALL": "provider_request_rejected",
        "ERROR": "provider_unavailable",
        "TIMEOUT": "provider_timeout",
    }.get(reason) if isinstance(reason, str) else None
    if kind:
        receipt["finish_status"] = "failed" if reason == "ERROR" else "incomplete"
        raise ProviderCallError(
            "Cohere generation did not complete; no action accepted",
            error_kind=kind, provider=PROVIDER_ID, model=model,
        )
    if reason not in ("COMPLETE", "STOP_SEQUENCE"):
        raise _schema_error(model)
    receipt["finish_status"] = "completed"
    message = data.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise _schema_error(model)
    if message.get("tool_calls") is not None and not isinstance(message["tool_calls"], list):
        raise _schema_error(model)
    if message.get("tool_calls"):
        receipt["finish_status"] = "incomplete"
        raise ProviderCallError(
            "Cohere returned unsolicited tool calls; no action accepted",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=model,
        )
    content = message.get("content")
    if not isinstance(content, list) or not content:
        raise _schema_error(model)
    texts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            raise _schema_error(model)
        if part.get("type") == "thinking" and isinstance(part.get("thinking"), str):
            continue
        if part.get("type") != "text" or not isinstance(part.get("text"), str):
            raise _schema_error(model)
        texts.append(part["text"])
    if not texts or not "".join(texts).strip():
        raise _schema_error(model)
    return "".join(texts)


def _schema_error(model: str) -> ProviderCallError:
    from eslams.agents import ProviderCallError

    return ProviderCallError(
        "Cohere returned malformed or unsupported Chat v2 data",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=model,
    )


def _http_error_kind(code: int) -> str:
    from eslams.agents import _provider_error_kind

    return {498: "provider_auth_failed", 499: "provider_cancelled"}.get(
        code, _provider_error_kind(code),
    )


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams import agents as core

    tokens = usage.get("tokens") if isinstance(usage, dict) else None
    billed = usage.get("billed_units") if isinstance(usage, dict) else None
    # Pass only documented fields. No completion-token alias or missing-to-zero
    # conversion, and no separate reasoning/cache breakdown is claimed.
    result = core._normalize_usage(
        "cohere_processed_tokens",
        {name: tokens.get(name) for name in ("input_tokens", "output_tokens")}
        if isinstance(tokens, dict) else None,
    )
    errors = result["usage_validation_errors"]
    if usage is not None and not isinstance(usage, dict):
        errors.append("usage_invalid")
    if isinstance(usage, dict):
        for name in ("tokens", "billed_units"):
            if usage.get(name) is not None and not isinstance(usage[name], dict):
                errors.append(f"{name}_invalid")
    result["billed_input_tokens"] = core._usage_int(
        billed.get("input_tokens") if isinstance(billed, dict) else None,
        "billed_input_tokens", errors,
    )
    result["billed_output_tokens"] = core._usage_int(
        billed.get("output_tokens") if isinstance(billed, dict) else None,
        "billed_output_tokens", errors,
    )
    return result


def models_live() -> list[str]:
    """Explicit opt-in discovery; all pages or no visibility claim, no retries."""
    from eslams import agents as core

    try:
        key = provider_key(API_KEY_ENV)
    except ValueError:
        key = None
    if not key:
        raise core.ProviderCallError(
            f"missing or invalid API key environment variable {API_KEY_ENV}",
            error_kind="provider_auth_failed", provider=PROVIDER_ID,
        )
    credentials = _credentials(key)
    params = {"endpoint": "chat", "page_size": "1000"}
    models: set[str] = set()
    cursors: set[str] = set()
    for _ in range(20):
        try:
            response = httpx.get(
                MODELS_ENDPOINT, headers={"Authorization": f"Bearer {key}",
                                          "Accept": "application/json"},
                params=dict(params), timeout=20.0,
            )
        except httpx.TimeoutException:
            raise core.ProviderCallError(
                "Cohere model discovery timed out", error_kind="provider_timeout",
                provider=PROVIDER_ID,
            ) from None
        except httpx.HTTPError:
            raise core.ProviderCallError(
                "Cohere model discovery transport failed", error_kind="provider_transport_error",
                provider=PROVIDER_ID,
            ) from None
        if response.is_error:
            raise core.ProviderCallError(
                f"Cohere model discovery returned HTTP {response.status_code}",
                status_code=response.status_code, provider=PROVIDER_ID,
                error_kind=_http_error_kind(response.status_code),
            )
        data = core._response_json(response, provider=PROVIDER_ID, model="")
        rows = data.get("models")
        if not isinstance(rows, list) or "error" in data:
            raise _schema_error("")
        for row in rows:
            name = row.get("name") if isinstance(row, dict) else None
            if (not isinstance(name, str) or not name.strip()
                    or _redact_text(name, credentials) != name):
                raise _schema_error("")
            models.add(name)
        cursor = data.get("next_page_token")
        if cursor is None:
            return sorted(models)
        if (not isinstance(cursor, str) or not cursor or cursor in cursors
                or _redact_text(cursor, credentials) != cursor):
            raise _schema_error("")
        cursors.add(cursor)
        params["page_token"] = cursor
    raise core.ProviderCallError(
        "Cohere model discovery exceeded the 20-page limit; visibility is unverified",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
    )
