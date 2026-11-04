"""AI21 Studio Jamba REST adapter; see docs/providers/AI21.md for provenance."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json
from eslams.protocol import ProtocolError

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "ai21-labs"
API_KEY_ENV = "AI21_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.ai21.com/studio/v1/chat/completions"
ENDPOINT_KIND = "ai21_chat_completions"
PARSER_VERSION = "ai21-chat-completions-raw-v1"


def validate_config(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("AI21 requires an explicit nonblank model ID")
    if runtime and (
        runtime.reasoning == "enabled"
        or runtime.reasoning_effort is not None
        or runtime.reasoning_budget_tokens is not None
        or runtime.gemini_thinking_budget is not None
    ):
        raise ValueError("AI21 Jamba Chat has no documented reasoning controls")


def _credential_values(api_key_env: str) -> tuple[str, ...]:
    # Protect both the selected credential (whose variable name is arbitrary)
    # and other configured credentials that a response might echo. Values stay
    # private; neither environment names nor credentials enter the receipt.
    suffixes = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIAL", "_CREDENTIALS",
                "_ACCESS_KEY_ID")
    return tuple(sorted({value.strip() for name, value in os.environ.items()
                         if value.strip() and (name in {api_key_env, API_KEY_ENV}
                         or name.upper() in {"API_KEY", "TOKEN", "SECRET", "PASSWORD"}
                         or name.upper().endswith(suffixes))}))


def _redact_credentials(value: Any, credentials: tuple[str, ...]) -> Any:
    """Drop credential-bearing observations, including otherwise valid identifiers.

    Provider values never become a redaction marker that could attest identity.
    Configured credentials are protected even without recognizable key prefixes.
    """
    variants = {variant for secret in credentials for variant in (
        secret, quote(secret, safe=""), quote_plus(secret),
        json.dumps(secret, ensure_ascii=True)[1:-1],
    )}

    def redact(item: Any) -> Any:
        if isinstance(item, str):
            return None if any(secret in item for secret in variants) else item
        if isinstance(item, list):
            return [redact(child) for child in item]
        if isinstance(item, dict):
            return {key: redact(child) for key, child in item.items() if redact(key) is not None}
        return item

    return redact(value)


def sanitize_receipt(receipt: dict[str, Any], api_key_env: str) -> dict[str, Any]:
    result: dict[str, Any] = _redact_credentials(receipt, _credential_values(api_key_env))
    return result


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams import agents as shared

    # Only these three token fields are part of the documented Jamba envelope.
    raw = usage if isinstance(usage, dict) else {}
    result = shared._normalize_usage("ai21-wire", {
        "input_tokens": raw.get("prompt_tokens"),
        "output_tokens": raw.get("completion_tokens"),
        "total_tokens": raw.get("total_tokens"),
    })
    if raw.get("total_tokens") is None:
        result.update(total_tokens=None, total_tokens_source="unavailable")
    result["cached_input_is_subset"] = None
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at dispatch time: shared transport/receipt helpers own physical
    # attempts, cancellation, byte limits, deadlines and admission controls.
    from eslams import agents as shared

    validate_config(agent.model, agent.runtime_config)
    credentials = (*_credential_values(agent.api_key_env), api_key)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": shared._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "n": 1,
    }
    if agent._effective_max_output_tokens() is not None:
        payload["max_tokens"] = agent._effective_max_output_tokens()
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    receipt = None
    try:
        response = shared._post_json(
            shared._provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, agent.runtime_config),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = shared._response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        receipt = shared._receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"),
            # The documented REST envelope does not attest a resolved model.
            resolved_model=None, usage=data.get("usage"),
            capabilities=replace(agent.capabilities, pricing={}),
            runtime_config=agent.runtime_config,
        )
        receipt = _redact_credentials(receipt, credentials)
        choices = data.get("choices")
        if (response.status_code != 200 or "error" in data
                or not isinstance(choices, list) or len(choices) != 1
                or not isinstance(choices[0], dict)):
            raise shared.ProviderCallError(
                "AI21 returned an error or invalid choices envelope",
                error_kind="provider_response_schema_mismatch",
            )
        choice = choices[0]
        reason = choice.get("finish_reason")
        if reason == "length":
            receipt["finish_reason"] = "length"
            raise shared.ProviderCallError(
                "AI21 output reached its token limit", error_kind="provider_output_truncated",
            )
        message = choice.get("message")
        if (reason != "stop" or type(choice.get("index")) is not int or choice["index"] != 0
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or choice.get("tool_calls")
                or choice.get("error") is not None
                or not isinstance(message.get("content"), str) or not message["content"].strip()):
            raise shared.ProviderCallError(
                "AI21 returned an incomplete or unsupported text response",
                error_kind="provider_response_schema_mismatch",
            )
        text = message["content"]
        # Decode action JSON as well: an escaped key must not become public
        # explanation/action text after the shared action parser decodes it.
        try:
            decoded = extract_json(text)
        except RecursionError:
            raise shared.ProviderCallError(
                "AI21 action JSON exceeded parser nesting limits",
                error_kind="provider_response_schema_mismatch",
            ) from None
        except (ValueError, ProtocolError):
            decoded = None
        if (_redact_credentials(text, credentials) is None
                or _redact_credentials(decoded, credentials) != decoded):
            raise shared.ProviderCallError(
                "AI21 returned credential-bearing action text",
                error_kind="provider_response_schema_mismatch",
            )
        receipt["finish_reason"] = "stop"
        return text, receipt
    except shared.ProviderCallError as exc:
        # AI21 does not document an error body proving rejected, unbilled work;
        # even an operator retry allowance cannot replay ambiguous outcomes.
        safe_receipt = _redact_credentials(exc.receipt or receipt, credentials)
        raise shared.ProviderCallError(
            "AI21 request failed: " + exc.error_kind,
            error_kind=exc.error_kind, status_code=exc.status_code,
            provider=PROVIDER_ID, model=agent.model, receipt=safe_receipt,
            retry_after_seconds=exc.retry_after_seconds, retry_permitted=False,
        ) from None
    except TimeoutError:
        raise TimeoutError("AI21 request timed out") from None
