"""Contextual AI's standalone Generate REST API (not the agent/RAG API)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "contextual-ai"
API_KEY_ENV = "CONTEXTUAL_API_KEY"
GENERATE_ENDPOINT = "https://api.contextual.ai/v1/generate"


def validate_configuration(
    model: str, runtime: ProviderRuntimeConfig | None,
    max_output_tokens: int | None = None, temperature: float | None = None,
) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Contextual AI requires an explicit nonblank model ID")
    if runtime is not None:
        if runtime.reasoning != "auto" or any(value is not None for value in (
            runtime.reasoning_effort, runtime.reasoning_budget_tokens,
            runtime.gemini_thinking_budget,
        )):
            raise ValueError("Contextual AI Generate exposes no reasoning controls; use auto")
        if runtime.history_window_turns is not None:
            raise ValueError("Contextual AI requires full supplied history")
        if runtime.openrouter_provider_order:
            raise ValueError("Contextual AI does not support OpenRouter routing controls")
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int)
        or not 1 <= max_output_tokens <= 2048
    ):
        raise ValueError("Contextual AI max_new_tokens must be an integer from 1 to 2048")
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, (int, float))
        or not 0 <= temperature <= 1 or not math.isfinite(temperature)
    ):
        raise ValueError("Contextual AI temperature must be from 0 to 1")


def _contains_credential(value: str, api_key: str) -> bool:
    return any(secret in value for secret in (
        api_key, quote(api_key, safe=""), quote_plus(api_key),
    ))


def _action_contains_credential(text: str, api_key: str) -> bool:
    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return _contains_credential(value, api_key)
        if isinstance(value, list):
            return any(contains(item) for item in value)
        if isinstance(value, dict):
            return any(contains(key) or contains(item) for key, item in value.items())
        return False

    if _contains_credential(text, api_key):
        return True
    try:
        # Inspect the same JSON projection as action parsing, including fenced
        # text and escaped strings. An encoded credential must never become a
        # decoded public explanation, action value or parse-error detail.
        return contains(extract_json(text))
    except (ValueError, RecursionError):
        return True


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Imports are local because shared dispatch imports this provider module.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _failure_receipt,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    maximum = agent._effective_max_output_tokens()
    validate_configuration(agent.model, agent.runtime_config, maximum, agent.temperature)
    try:
        response = _post_json(
            _provider_endpoint(GENERATE_ENDPOINT, agent.runtime_config),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload={
                "model": agent.model,
                "messages": [{"role": "user", "content": prompt}],
                # Provider-owned LangChain integration uses this when knowledge
                # is omitted. It supplies no documents and invokes no retrieval.
                "knowledge": [""],
                "system_prompt": _SYSTEM_INSTRUCTIONS,
                "max_new_tokens": maximum,
                "temperature": agent.temperature,
            },
            runtime_config=agent.runtime_config,
            control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=None, resolved_model=None, usage=None,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        for name in ("request_id", "gateway_request_id"):
            value = receipt.get(name)
            if isinstance(value, str) and _contains_credential(value, api_key):
                receipt[name] = None
        # Only the documented envelope is accepted. There is no published
        # model, usage, cost, finish or reasoning attestation to normalize.
        text = data.get("response")
        if (set(data) != {"response"} or not isinstance(text, str) or not text.strip()
                or _action_contains_credential(text, api_key)):
            raise ProviderCallError(
                "Contextual AI returned an unsupported Generate response",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model, status_code=response.status_code, receipt=receipt,
            )
        return text, receipt
    except ProviderCallError as exc:
        # Generic transport may observe undocumented error-body fields. Keep
        # physical status/headers, but never promote those to identity/accounting.
        observed = exc.receipt or {}
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=exc.error_kind,
            usage_unavailable_reason="provider_usage_absent",
            runtime_config=agent.runtime_config, status_code=exc.status_code,
            retry_after_seconds=exc.retry_after_seconds,
        )
        for name in ("request_id", "gateway_request_id"):
            value = observed.get(name)
            if isinstance(value, str) and not _contains_credential(value, api_key):
                receipt[name] = value
        exc.receipt = receipt
        # SDK retry defaults are not evidence that paid work was rejected.
        exc.retry_permitted = False
        raise
