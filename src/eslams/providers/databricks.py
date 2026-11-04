"""Native Databricks serving-endpoint chat contract (no SDK or route fallback)."""

from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "databricks-mosaicml"
API_KEY_ENV = "DATABRICKS_TOKEN"
HOST_ENV = "DATABRICKS_HOST"
ENDPOINT_KIND = "databricks_serving_endpoint_chat"
PARSER_VERSION = "databricks-serving-chat-raw-v1"


def is_databricks(provider: str) -> bool:
    return provider.lower().replace("_", "-") in {"databricks", PROVIDER_ID}


def invocation_endpoint(model: str) -> str:
    """Use the exact operator-selected deployment; never strip catalogue prefixes."""
    host = os.environ.get(HOST_ENV, "").strip()
    try:
        parsed = urlsplit(host)
        valid = (
            parsed.scheme == "https" and parsed.hostname is not None
            and parsed.username is None and parsed.password is None
            and parsed.port is None and parsed.path in {"", "/"}
            and "?" not in host and "#" not in host
            and not any(char.isspace() or ord(char) < 32 for char in host)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("DATABRICKS_HOST must be an HTTPS workspace origin without credentials")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", model):
        raise ValueError("Databricks model must be an explicit serving endpoint name")
    return f"{host.rstrip('/')}/serving-endpoints/{quote(model, safe='')}/invocations"


def normalize_usage(usage: Any) -> dict[str, Any]:
    # The reference exposes top-level cache and reasoning fields. It does not
    # promise reasoning inclusion for every hosted/external model. Keep it unknown.
    from eslams.agents import _normalize_usage

    if not isinstance(usage, dict):
        return _normalize_usage("databricks-wire", usage)
    projected = {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
        "input_tokens_details": {
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        },
    }
    normalized = _normalize_usage("databricks-wire", projected)
    if usage.get("total_tokens") is None:
        normalized.update(total_tokens=None, total_tokens_source="unavailable")
    return normalized


def _redact_credential(value: Any, credential: str) -> Any:
    if isinstance(value, str):
        return None if credential in value else value
    if isinstance(value, dict):
        return {key: _redact_credential(item, credential) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_credential(item, credential) for item in value]
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        # Even identifier-shaped echoes of the active credential are private.
        if exc.receipt is not None:
            exc.receipt = _redact_credential(exc.receipt, api_key)
        raise
    return text, _redact_credential(receipt, api_key)


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Local imports keep the provider implementation separate while using Core's
    # transport, error custody, privacy projection and physical-attempt accounting.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    try:
        endpoint = invocation_endpoint(agent.model)
        if runtime and (
            runtime.reasoning_budget_tokens is not None
            or runtime.gemini_thinking_budget is not None
        ):
            raise ValueError("Databricks chat adapter supports reasoning_effort, not token budgets")
        if runtime and runtime.reasoning == "enabled" and runtime.reasoning_effort is None:
            raise ValueError("Databricks enabled reasoning requires an explicit reasoning_effort")
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_request_rejected",
            provider=agent.provider, model=agent.model,
        ) from None
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning == "disabled":
        payload["reasoning_effort"] = "none"
    elif runtime and runtime.reasoning_effort is not None:
        # Endpoint/model validation is authoritative; never guess from an arena
        # or a deployment name, clamp the choice, or retry without the control.
        payload["reasoning_effort"] = runtime.reasoning_effort
    response = _post_json(
        _provider_endpoint(endpoint, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime,
        control_key=f"{agent.provider}:{agent.model}",
    )
    # A deployment may use provisioned pricing or traffic splitting. Catalogue
    # token prices do not attest this deployment's cost.
    capabilities = replace(agent.capabilities, pricing={})
    data = _response_json_with_receipt(
        response, provider=agent.provider, model=agent.model,
        capabilities=capabilities, runtime_config=runtime,
    )
    receipt = _receipt(
        provider=agent.provider, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=capabilities, runtime_config=runtime,
    )
    receipt["served_model_name"] = _http_error_identifier(response.headers.get("served-model-name"))
    try:
        if response.status_code != 200:
            raise ProviderCallError(
                "Databricks returned a non-success invocation status",
                status_code=response.status_code, error_kind="provider_request_rejected",
                provider=agent.provider, model=agent.model,
            )
        # Embedded errors take precedence even when no choice is supplied.
        _check_provider_completion(
            data, provider=agent.provider, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError
        first = choices[0]
        if ("finish_reason" in first and "finishReason" in first
                and first["finish_reason"] != first["finishReason"]):
            raise ValueError
        reason = first.get("finish_reason", first.get("finishReason"))
        message = first.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError
        content = message.get("content")
        if reason != "stop":
            # Null/missing/unknown termination is not proof of a complete action.
            raise ValueError
        if message.get("tool_calls") or message.get("function_call"):
            raise ValueError
        if isinstance(content, list):
            chunks = []
            for part in content:
                if not isinstance(part, dict):
                    raise ValueError
                if part.get("type") == "reasoning":
                    continue
                if part.get("type") != "text" or not isinstance(part.get("text"), str):
                    raise ValueError
                chunks.append(part["text"])
            content = "".join(chunks)
        if not isinstance(content, str) or not content:
            raise ValueError
    except ValueError:
        raise ProviderCallError(
            "Databricks response is missing a complete assistant text choice",
            error_kind="provider_response_schema_mismatch", provider=agent.provider,
            model=agent.model, receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
        ) from None
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return content, receipt
