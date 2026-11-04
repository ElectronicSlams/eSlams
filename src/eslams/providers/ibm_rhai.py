"""Red Hat AI Inference on IBM Cloud, a host distinct from watsonx and Granite.

Pinned wire scope, sources and limitations: docs/PROVIDER_IBM_RHAI.md.
"""
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, NoReturn

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER = "ibm-rhai"
API_KEY_ENV = "IBM_RHAI_API_KEY"
ALIASES = {PROVIDER, "rhai", "redhat-ai-inference"}


def normalize_alias(provider: str) -> str:
    value = provider.strip().lower().replace("_", "-")
    return PROVIDER if value in ALIASES else provider


def validate_model(model: object) -> None:
    if not isinstance(model, str) or not model.strip() or model != model.strip():
        raise ValueError(
            "ibm-rhai requires an exact explicit model ID without surrounding whitespace"
        )


def configuration(runtime: ProviderRuntimeConfig | None) -> str:
    if runtime and (runtime.gateway_base_url or runtime.gateway_mode not in {
        "direct_provider", "disabled",
    }):
        raise ValueError("ibm-rhai supports the direct public IBM Cloud endpoint only")
    if os.environ.get("IBM_RHAI_REGION") != "us-east":
        raise ValueError("IBM_RHAI_REGION must explicitly select the documented us-east endpoint")
    project = os.environ.get("IBM_RHAI_PROJECT_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9-]+", project):
        raise ValueError("IBM_RHAI_PROJECT_ID must contain letters, digits or hyphens")
    if runtime and (runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    ))):
        raise ValueError("ibm-rhai supports native reasoning defaults only; explicit controls "
                         "are not verified for this hosted API")
    return f"https://us-east.rhai.ibm.com/v1/projects/{project}/inference/chat/completions"


def configuration_error(runtime: ProviderRuntimeConfig | None) -> str | None:
    try:
        configuration(runtime)
    except ValueError as exc:
        return str(exc)
    return None


def call(agent: ModelProviderAgent, api_key: str, prompt: str,
         system: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        ProviderCallError,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    try:
        endpoint = configuration(runtime)
        validate_model(agent.model)
    except ValueError as exc:
        raise ProviderCallError(str(exc), error_kind="provider_request_rejected",
                                provider=PROVIDER, model=agent.model) from None
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [{"role": "developer", "content": system},
                     {"role": "user", "content": prompt}],
    }
    maximum = agent._effective_max_output_tokens()
    if maximum is not None:
        payload["max_completion_tokens"] = maximum
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    try:
        response = _post_json(endpoint,
                              headers={"Authorization": f"Bearer {api_key}",
                                       "Content-Type": "application/json",
                                       "Accept": "application/json"},
                              payload=payload, runtime_config=runtime,
                              control_key=f"{PROVIDER}:{agent.model}")
        data = _response_json_with_receipt(response, provider=PROVIDER, model=agent.model,
                                         capabilities=agent.capabilities, runtime_config=runtime)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            _exclude_credentials(exc.receipt, api_key)
        # A diagnostic may have been truncated upstream in the middle of a key.
        # Retain structured status/receipt evidence, never raw transport prose.
        exc.args = ("ibm-rhai request failed; inspect the sanitized receipt",)
        # Compatibility and billing documentation do not attest a safe replay
        # rejection envelope. Never replay inference based on guessed semantics.
        exc.retry_permitted = False
        raise
    receipt = _receipt(provider=PROVIDER, model=agent.model, response=response,
                       provider_response_id=data.get("id"), resolved_model=data.get("model"),
                       usage=data.get("usage"), capabilities=agent.capabilities,
                       runtime_config=runtime)
    _exclude_credentials(receipt, api_key)
    try:
        text = _text(data, receipt)
        if api_key in text:
            raise ProviderCallError("ibm-rhai response contains credential material; "
                                    "no action accepted",
                                    error_kind="provider_response_schema_mismatch",
                                    provider=PROVIDER)
        reported = data.get("model")
        if reported is not None and reported != agent.model:
            raise ProviderCallError("ibm-rhai returned a different or malformed model identity",
                                    error_kind="provider_request_rejected", provider=PROVIDER)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str) -> NoReturn:
        raise ProviderCallError("ibm-rhai response did not contain a completed text action",
                                error_kind=kind, provider=PROVIDER)

    if data.get("error") or data.get("errors"):
        receipt["finish_status"] = "failed"
        fail("provider_unavailable")
    if data.get("object") != "chat.completion":
        fail("provider_response_schema_mismatch")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch")
    choice = choices[0]
    message = choice.get("message")
    reason = choice.get("finish_reason")
    known = {"stop", "length", "content_filter", "tool_calls", "function_call"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason == "content_filter" or isinstance(message, dict) and message.get("refusal"):
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if reason == "length":
        fail("provider_output_truncated")
    if reason in ("tool_calls", "function_call"):
        fail("provider_request_rejected")
    if reason != "stop" or not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch")
    if message.get("tool_calls") or message.get("function_call"):
        fail("provider_request_rejected")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        fail("provider_response_schema_mismatch")
    receipt["finish_status"] = "completed"
    # Reasoning fields are private and never action or receipt sources.
    return content


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    from eslams.agents import _normalize_usage

    # IBM delegates the envelope to OpenAI, but does not attest hosted reasoning
    # inclusion or cache accounting. Do not infer these from a compatible shape.
    documented = {key: usage[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in usage}
    normalized = _normalize_usage("generic", documented)
    raw_total = documented.get("total_tokens")
    if isinstance(raw_total, bool) or not isinstance(raw_total, int) or raw_total < 0:
        normalized["total_tokens"] = None
        normalized["total_tokens_source"] = "unavailable"
    return normalized


def _exclude_credentials(receipt: dict[str, Any], *secrets: str) -> None:
    for key in ("locked_model_id", "provider_response_id", "request_id", "gateway_request_id"):
        value = receipt.get(key)
        if isinstance(value, str) and any(secret and secret in value for secret in secrets):
            receipt[key] = None
    if receipt.get("locked_model_id") is None:
        receipt["model_identity_source"] = None
    sanitized = _redact_credential_values(receipt, secrets)
    receipt.clear()
    receipt.update(sanitized)


def _redact_credential_values(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_redact_credential_values(item, secrets) for item in value]
    if isinstance(value, dict):
        return {_redact_credential_values(key, secrets): _redact_credential_values(item, secrets)
                for key, item in value.items()}
    return value
