"""Direct Reka Chat Completions adapter (not the retired v0 /chat API)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "reka-ai"
API_KEY_ENV = "REKA_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.reka.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.reka.ai/v1/models"


def configuration_error(model: str, runtime: ProviderRuntimeConfig | None = None) -> str | None:
    """Check only adapter-owned requirements, without choosing a model or policy."""
    if not isinstance(model, str) or not model.strip():
        return "Reka requires an explicit nonblank model ID"
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        return "Reka does not support explicit reasoning token budgets; use reasoning_effort"
    return None


def _credentials(api_key: str = "", environment_name: str = API_KEY_ENV) -> tuple[str, ...]:
    """Keep known credential values private and scoped to this invocation."""
    values = {api_key} if api_key else set()
    for name, value in os.environ.items():
        upper = name.upper()
        if (name == environment_name or any(
            marker in upper for marker in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        ) or upper.endswith("_KEY")) and value.strip():
            values.add(value.strip())
    return tuple(sorted(values, key=len, reverse=True))


def _contains_credential(value: str, credentials: tuple[str, ...]) -> bool:
    return any(secret in value for secret in credentials)


def credential_echo(value: str) -> bool:
    """Detect credential-bearing discovery IDs before they reach CLI/preflight output."""
    return _contains_credential(value, _credentials())


def _private_receipt(receipt: dict[str, Any], credentials: tuple[str, ...]) -> dict[str, Any]:
    def scrub(value: Any, field: str = "") -> Any:
        if isinstance(value, str):
            if _contains_credential(value, credentials) and field.endswith("_id"):
                return None  # A redacted identifier cannot attest identity.
            for secret in credentials:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {key: scrub(item, key) for key, item in value.items()
                    if not _contains_credential(key, credentials)}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    result: dict[str, Any] = scrub(receipt)
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    error = configuration_error(agent.model, agent.runtime_config)
    if error:
        raise ProviderCallError(
            error, error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    credentials = _credentials(api_key, agent.api_key_env)
    try:
        text, receipt = _call(agent, api_key, prompt)
        if _contains_credential(text, credentials):
            raise ProviderCallError(
                "Reka response contained credential material; no action accepted",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model, receipt=receipt,
            )
    except ProviderCallError as exc:
        # Covers HTTP errors, malformed JSON and partial-body header observations,
        # before the common agent can publish a receipt or decide on a retry.
        if exc.receipt is not None:
            exc.receipt = _private_receipt(exc.receipt, credentials)
            exc.receipt["outcome"] = exc.error_kind
        raise exc from None
    return text, _private_receipt(receipt, credentials)


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at invocation time: agents owns the common transport/receipt helpers.
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
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning_effort is not None:
        # Endpoint validation is authoritative, including for uncatalogued models.
        payload["reasoning_effort"] = runtime.reasoning_effort
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
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    usage = data.get("usage")
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    conflicting_reasoning = (
        isinstance(usage, dict) and isinstance(details, dict)
        and "reasoning_tokens" in usage and "reasoning_tokens" in details
        and (type(usage["reasoning_tokens"]) is not type(details["reasoning_tokens"])
             or usage["reasoning_tokens"] != details["reasoning_tokens"])
    )
    if receipt["usage"].get("usage_validation_errors") or conflicting_reasoning:
        # Incoherent usage must not turn into complete preflight accounting or cost.
        receipt["usage"] = {}
        receipt["usage_unavailable_reason"] = "provider_usage_malformed"
        receipt["estimated_cost"] = {
            "status": "cost_unavailable", "unavailable_reason": "provider_usage_malformed",
        }
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if (not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or not isinstance(content, str) or not content):
            raise ProviderCallError(
                "Reka response has no single completed assistant text message",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    # reasoning_content/reasoning are private traces, never action text or receipt data.
    return content, receipt
