"""Sarvam's direct V1 chat API; see docs/providers/SARVAM.md for evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "sarvam-ai"
API_KEY_ENV = "SARVAM_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.sarvam.ai/v1/chat/completions"
DEFAULT_MODEL = "sarvam-105b"

_ERROR_STATUS = {
    "invalid_api_key_error": 401,
    "invalid_request_error": 400,
    "unprocessable_entity_error": 422,
    "not_found_error": 404,
    "insufficient_quota_error": 402,
    "rate_limit_exceeded_error": 429,
    "model_rate_limit_exceeded_error": 429,
    "seat_budget_exhausted_error": 429,
    "internal_server_error": 500,
    "model_call_failed": 502,
    "model_overloaded": 503,
}


def http_error(response: httpx.Response) -> tuple[str, bool]:
    """Classify documented codes without publishing provider prose or extensions."""
    from eslams import agents as core

    kind = core._provider_error_kind(response.status_code)
    try:
        data = core._strict_provider_json(response)
    except (ValueError, UnicodeError, RecursionError):
        return kind, False
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return kind, False
    code = error.get("code")
    if response.status_code == 403 and code == "invalid_api_key_error":
        kind = "provider_auth_failed"
    safe = (
        response.status_code == 429
        and isinstance(code, str)
        and code in {"rate_limit_exceeded_error", "model_rate_limit_exceeded_error"}
        and set(data) == {"error"}
        and not set(error) - {"code", "message", "request_id"}
        and all(isinstance(value, str) for value in error.values())
    )
    return kind, safe


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Only documented token fields attest usage; absent counters remain unknown."""
    from eslams import agents as core

    if not isinstance(usage, dict):
        return core._empty_usage()
    fields = {
        key: usage[key] for key in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_tokens_details", "completion_tokens_details",
        ) if key in usage
    }
    fields["reasoning_included_in_output"] = True
    normalized = core._normalize_usage("sarvam-chat", fields)
    if normalized["total_tokens_source"] != "provider":
        normalized.update(total_tokens=None, total_tokens_source=None)
    return normalized


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    """Use Core's bounded transport, physical-attempt ledger and privacy controls."""
    from eslams import agents as core

    runtime = agent.runtime_config
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        raise core.ProviderCallError(
            "Sarvam supports reasoning_effort, not a token thinking budget",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": core._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
    }
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["max_tokens"] = limit
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning == "disabled":
        payload["reasoning_effort"] = None
    elif runtime and runtime.reasoning_effort is not None:
        # The guide and enum disagree on medium/max; preserve explicit choices
        # and let the actual endpoint reject unsupported values.
        payload["reasoning_effort"] = runtime.reasoning_effort
    response = core._post_json(
        core._provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = core._response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    if "error" in data:
        receipt = core._failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome="provider_unavailable",
            usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
        )
        core._capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        error = data["error"]
        code = error.get("code") if isinstance(error, dict) else None
        status = _ERROR_STATUS.get(code) if isinstance(code, str) else None
        kind = core._provider_error_kind(status) if status else "provider_unavailable"
        raise core.ProviderCallError(
            "Sarvam reported an error in the response body", error_kind=kind,
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        )
    receipt = core._receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    try:
        core._check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = choice.get("message") if isinstance(choice, dict) else None
        if (not isinstance(choice, dict) or choice.get("finish_reason") != "stop"
                or not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or message.get("function_call")
                or not isinstance(message.get("content"), str) or not message["content"].strip()):
            raise core.ProviderCallError(
                "Sarvam response requires one completed assistant text choice",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        return message["content"], receipt
    except core.ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
