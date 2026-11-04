"""NVIDIA-hosted API Catalog Chat Completions adapter (development entitlement).

This is not a self-hosted NIM or partner endpoint adapter. See docs/providers/NVIDIA.md.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "nvidia"
API_KEY_ENV = "NVIDIA_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
REFERENCE_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
ALIASES = ("nvidia-nim", "nvidia-hosted")
_THINKING_MODELS = {REFERENCE_MODEL, "nvidia/nemotron-3.5-bolt-e4b"}


def validate_options(model: str, runtime: ProviderRuntimeConfig | None) -> str | None:
    if not isinstance(model, str) or not model.strip():
        return "NVIDIA requires an explicit nonblank model ID"
    if runtime:
        mode = runtime.reasoning
        budget = runtime.reasoning_budget_tokens
        if (runtime.reasoning_effort is not None or runtime.gemini_thinking_budget is not None
                or (mode != "auto" and model not in _THINKING_MODELS)
                or (budget is not None and (
                    model != REFERENCE_MODEL or mode == "disabled" or budget > 32768
                ))):
            return "reasoning controls are unsupported for this NVIDIA model"
    return None


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    from eslams.agents import _normalize_usage

    result = _normalize_usage("nvidia-wire", usage)
    # The hosted contract does not promise a reasoning inclusion convention or
    # complete accounting. Keep absent totals absent, rather than manufacturing
    # them from the visible text or from incomplete counters.
    if result.get("total_tokens_source") != "provider":
        result.update(total_tokens=None, total_tokens_source="unavailable")
    return result


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        # A redacted identifier is not model/request identity evidence.
        return None if any(secret in value for secret in secrets) else value
    if isinstance(value, dict):
        result = {key: _redact(item, secrets) for key, item in value.items()}
        if "locked_model_id" in result and result["locked_model_id"] is None:
            result["model_identity_source"] = None
        return result
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    # Include secondary credentials: providers may echo unrelated process secrets
    # in syntactically valid identifiers. Never log or persist these values.
    secrets = tuple({api_key, *(value.strip() for name, value in os.environ.items()
                               if value.strip() and (name == agent.api_key_env or any(
                                   marker in name.upper() for marker in
                                   ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
                               )))})
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _redact(exc.receipt, secrets)
        raise
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text, _redact(receipt, secrets)


def _call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Keep transport, error custody, redaction and accounting centralized. Import
    # at invocation time to avoid a cycle with ModelProviderAgent's dispatch.
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
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime:
        error = validate_options(agent.model, runtime)
        if error:
            raise ProviderCallError(
                f"{error}; no request submitted",
                error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
            )
        mode = runtime.reasoning
        budget = runtime.reasoning_budget_tokens
        if mode != "auto":
            payload["chat_template_kwargs"] = {"enable_thinking": mode == "enabled"}
        if budget is not None:
            payload["reasoning_budget"] = budget

    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "Accept": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    try:
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
    except ProviderCallError as exc:
        if response.status_code == 202:
            raise ProviderCallError(
                "NVIDIA invocation is pending; no action accepted or polling attempted",
                error_kind="provider_pending", provider=PROVIDER_ID, model=agent.model,
                receipt={**(exc.receipt or {}), "outcome": "provider_pending"},
            ) from None
        raise
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=runtime,
    )
    try:
        if response.status_code == 202:
            raise ProviderCallError(
                "NVIDIA invocation is pending; no action accepted or polling attempted",
                error_kind="provider_pending", provider=PROVIDER_ID, model=agent.model,
            )
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if (not isinstance(first, dict) or first.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or message.get("function_call")
                or not isinstance(content, str) or not content.strip()):
            raise ProviderCallError(
                "NVIDIA response lacks one completed assistant text choice",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        # reasoning_content is never parsed as an action or copied to receipts.
        return content, receipt
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
