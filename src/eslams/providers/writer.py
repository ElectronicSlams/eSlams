"""Writer direct Chat API; documented raw wire shapes, without an SDK dependency."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "writer"
API_KEY_ENV = "WRITER_API_KEY"
CHAT_ENDPOINT = "https://api.writer.com/v1/chat"
MODELS_ENDPOINT = "https://api.writer.com/v1/models"
ALIASES = {"writer", "writer-ai", "writerai"}


def validate_model(model: Any) -> str:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Writer requires an explicit nonempty model ID")
    return model


def configuration_error(runtime: ProviderRuntimeConfig | None) -> str | None:
    if runtime and (runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    ))):
        return "Writer Chat API has no documented reasoning control; use native auto defaults"
    return None


def _credential_values(
    environment: str = API_KEY_ENV, primary: str | None = None,
) -> tuple[str, ...]:
    # Include a custom primary environment and other configured credentials:
    # secondary/gateway keys can be echoed too. Never emit or send this snapshot.
    values = {primary} if primary else set()
    for name, value in os.environ.items():
        if (name == environment or re.search(
            r"API_?KEY|(?:ACCESS|BEARER|AUTH|SESSION|REFRESH)_TOKEN|SECRET|PASSWORD|CREDENTIAL",
            name.upper(),
        ) or name.upper().endswith(("_TOKEN", "_KEY"))) and value.strip():
            values.update((value, value.strip()))
    return tuple(sorted(values, key=len, reverse=True))


def _contains_credential(value: Any, credentials: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(secret in value for secret in credentials)
    if isinstance(value, dict):
        return any(_contains_credential(key, credentials) or _contains_credential(item, credentials)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_credential(item, credentials) for item in value)
    return False


def _public_value(value: Any, credentials: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in credentials:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _contains_credential(key, credentials):
                continue
            if key in {"request_id", "gateway_request_id", "provider_response_id",
                       "locked_model_id"} and _contains_credential(item, credentials):
                result[key] = None
            else:
                result[key] = _public_value(item, credentials)
        if "locked_model_id" in result and result["locked_model_id"] is None:
            result["model_identity_source"] = None
        return result
    if isinstance(value, (list, tuple)):
        return [_public_value(item, credentials) for item in value]
    return value


def models_live() -> list[str]:
    """Discover Writer model IDs without exposing echoed credentials or partial lists."""
    from eslams.agents import ProviderCallError, _strict_provider_json
    from eslams.provider_credentials import provider_key

    try:
        key = provider_key(API_KEY_ENV)
    except ValueError:
        raise ProviderCallError("invalid Writer API key", error_kind="provider_auth_failed",
                                provider=PROVIDER_ID) from None
    if key is None:
        raise ProviderCallError("missing Writer API key", error_kind="provider_auth_failed",
                                provider=PROVIDER_ID)
    credentials = _credential_values(primary=key)
    response: httpx.Response | None = None
    failure_kind = "provider_transport_error"
    try:
        response = httpx.get(MODELS_ENDPOINT, headers={"Accept": "application/json",
            "Authorization": f"Bearer {key}"}, params={}, timeout=20.0)
    except httpx.TimeoutException:
        failure_kind = "provider_timeout"
    except httpx.HTTPError:
        pass
    if response is None:
        raise ProviderCallError("Writer model discovery transport failed",
            error_kind=failure_kind, provider=PROVIDER_ID)
    if response.is_error:
        status = response.status_code
        kind = ("provider_auth_failed" if status in {401, 403} else
                "provider_rate_limited" if status == 429 else
                "provider_unavailable" if status >= 500 else "provider_request_rejected")
        raise ProviderCallError(f"Writer model discovery returned HTTP {status}",
                                status_code=status, error_kind=kind, provider=PROVIDER_ID)
    models: list[str] = []
    invalid = False
    try:
        payload = _strict_provider_json(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError
        for row in payload["models"]:
            model = validate_model(row.get("id") if isinstance(row, dict) else None)
            if _contains_credential(model, credentials):
                raise ValueError
            models.append(model)
    except (ValueError, UnicodeError, RecursionError):
        invalid = True
    if invalid:
        raise ProviderCallError("Writer model discovery returned an invalid model list",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID)
    return sorted(set(models))


def usage_fields(usage: dict[str, Any]) -> dict[str, Any]:
    """Translate only documented fields; reasoning inclusion remains unverified."""
    prompt = usage.get("prompt_token_details")
    # REST example uses singular completion_token_details; the generated
    # OpenAPI SDK uses completion_tokens_details. Neither is a second charge.
    details = [usage[key] for key in ("completion_tokens_details", "completion_token_details")
               if usage.get(key) is not None]
    reasoning = details[0].get("reasoning_tokens") if details and isinstance(
        details[0], dict
    ) else None
    if len(details) == 2 and details[0] != details[1]:
        reasoning = "conflicting_writer_reasoning_details"
    return {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": prompt.get("cached_tokens") if isinstance(prompt, dict) else None,
        "reasoning_tokens": reasoning,
    }


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError
    from eslams.model_actions import extract_json

    validate_model(agent.model)
    credentials = _credential_values(agent.api_key_env, api_key)
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        exc.args = (_public_value(str(exc), credentials),)
        exc.model = _public_value(exc.model, credentials)
        exc.receipt = _public_value(exc.receipt, credentials)
        exc.retry_permitted = False
        exc.__context__ = None
        raise exc from None
    except TimeoutError as exc:
        exc.args = ("Writer request timed out",)
        exc.__context__ = None
        raise exc from None
    receipt = _public_value(receipt, credentials)
    if (_contains_credential(text, credentials)
            or _contains_credential(extract_json(text), credentials)):
        receipt["outcome"] = "provider_response_schema_mismatch"
        raise ProviderCallError(
            "Writer response contained a configured credential; no action accepted",
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
            error_kind="provider_response_schema_mismatch")
    return text, receipt


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy import reuses the existing transport/receipt custody without a cycle.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    error = configuration_error(runtime)
    if error:
        raise ProviderCallError(
            error,
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [{"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(CHAT_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"writer:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    if "tpe" in data or "errors" in data or "error" in data:
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome="provider_unavailable",
            usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["finish_status"] = "failed"
        raise ProviderCallError(
            "Writer reported an error inside the response body", error_kind="provider_unavailable",
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=usage_fields(data["usage"]) if isinstance(data.get("usage"), dict) else None,
        capabilities=agent.capabilities, runtime_config=runtime,
    )

    def fail(kind: str, message: str, *, finish: str | None = None) -> NoReturn:
        receipt.update(outcome=kind, finish_status=finish)
        raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID,
                                model=agent.model, receipt=receipt)

    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch", "Writer response has no unique chat completion")
    choice = choices[0]
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls",
    } else "unknown"
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch", "Writer response has no assistant message")
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        fail("provider_response_schema_mismatch", "Writer returned malformed refusal")
    if reason == "content_filter" or refusal:
        fail("provider_refused", "Writer refused or filtered the requested action",
             finish="refused")
    if reason == "length":
        fail("provider_output_truncated", "Writer output was truncated; no action accepted",
             finish="incomplete")
    if reason == "tool_calls" or message.get("tool_calls"):
        fail("provider_request_rejected", "Writer returned unsupported tool calls",
             finish="incomplete")
    content = message.get("content")
    if reason != "stop" or not isinstance(content, str) or not content:
        fail("provider_response_schema_mismatch", "Writer returned incomplete or malformed text")
    receipt["finish_status"] = "completed"
    return content, receipt
