"""StepFun direct Chat Completions wire contract (not Step Plan or a router).

Provenance and scope: docs/providers/STEPFUN.md. Transport, deadlines, retry
admission, action parsing and receipt custody remain owned by the shared agent.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "stepfun"
API_KEY_ENV = "STEPFUN_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.stepfun.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.stepfun.ai/v1/models"
ENDPOINT_KIND = "stepfun_chat_completions"
PARSER_VERSION = "stepfun-chat-completions-raw-v1"


def validate_model_id(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("StepFun requires an explicit nonblank model ID (stepfun:<model>)")


def validate_configuration(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    validate_model_id(model)
    if runtime is not None and any(value is not None for value in (
        runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError(
            "StepFun does not support reasoning_budget_tokens or gemini_thinking_budget; "
            "use an explicit reasoning_effort or native defaults"
        )


def _credential_values(primary: str) -> frozenset[str]:
    # Snapshot only for this physical attempt; no process-global secret cache.
    # Secondary credentials are never sent to StepFun, but an untrusted echo
    # must not publish them either. No key-format/prefix heuristic is sufficient.
    values = {primary}
    for name, value in os.environ.items():
        if re.search(r"(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?|AUTHORIZATION)(?:_|$)",
                     name.upper()):
            values.update((value, value.strip()))
    return frozenset(value for value in values if value)


def _contains_credential(value: str, credentials: frozenset[str]) -> bool:
    return any(secret in value for secret in credentials)


def _clean_receipt(receipt: dict[str, Any], credentials: frozenset[str]) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return None if _contains_credential(value, credentials) else value
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()
                    if not _contains_credential(key, credentials)}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    cleaned: dict[str, Any] = clean(receipt)
    if cleaned.get("locked_model_id") is None:
        cleaned["model_identity_source"] = None
    # Work-observation flags and retry admission were established before
    # redaction. Removing an unsafe generation ID cannot authorize a replay.
    return cleaned


def usage_fields(usage: dict[str, Any]) -> dict[str, Any]:
    """Project documented counters; never infer a reasoning breakdown or cost."""
    return {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        # StepFun reports this at usage.cached_tokens, not inside details.
        "cached_input_tokens": usage.get("cached_tokens"),
    }


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy import keeps the provider module usable for CLI/preflight metadata
    # while reusing the established physical-attempt transport and custody.
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
    try:
        validate_configuration(agent.model, runtime)
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_request_rejected", provider=PROVIDER_ID,
            model=agent.model,
        ) from None
    credentials = _credential_values(api_key)
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
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning_effort"] = runtime.reasoning_effort
    receipt: dict[str, Any] | None = None
    try:
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload,
            runtime_config=runtime,
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
        # The pricing guide explicitly attests inclusive output for Step 5.
        # Other model families have no such assertion in the reviewed docs.
        if data.get("model") == "step-5-preview" and receipt["usage"]:
            receipt["usage"]["reasoning_included_in_output"] = True
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        action_text = text(data, model=agent.model)
        if _contains_credential(action_text, credentials):
            raise ProviderCallError(
                "StepFun returned credential material in action text",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        return action_text, _clean_receipt(receipt, credentials)
    except ProviderCallError as exc:
        if _contains_credential(str(exc), credentials):
            exc.args = ("StepFun provider failure (credential material removed)",)
        # StepFun documents HTTP 451 for request/response safety review.
        if exc.status_code == 451:
            exc.error_kind = "provider_refused"
        if receipt is not None:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
        elif exc.receipt is not None:
            exc.receipt = {**exc.receipt, "outcome": exc.error_kind}
        if exc.status_code == 451 and exc.receipt is not None:
            exc.receipt["finish_status"] = "refused"
        if exc.receipt is not None:
            exc.receipt = _clean_receipt(exc.receipt, credentials)
        raise


def text(data: dict[str, Any], *, model: str) -> str:
    """Accept one completed assistant text choice, never reasoning or tool output."""
    from eslams.agents import ProviderCallError

    choices = data.get("choices")
    if data.get("object") == "chat.completion" and isinstance(choices, list) and len(choices) == 1:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if (choice.get("index") == 0 and not isinstance(choice.get("index"), bool)
                    and choice.get("finish_reason") == "stop" and isinstance(message, dict)
                    and message.get("role") == "assistant" and not message.get("tool_calls")
                    and isinstance(message.get("content"), str) and message["content"].strip()):
                return str(message["content"])
    raise ProviderCallError(
        "StepFun returned an invalid Chat Completions text envelope",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=model,
    )
