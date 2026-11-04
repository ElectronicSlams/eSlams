"""Xiaomi MiMo direct, non-streaming Chat Completions wire adapter.

Provenance and scope: docs/providers/XIAOMI_MIMO.md. No broker routing,
model substitution, SDK response properties, or private reasoning projection.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "xiaomi"
API_KEY_ENV = "MIMO_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.xiaomimimo.com/v1/chat/completions"
MODELS_ENDPOINT = "https://api.xiaomimimo.com/v1/models"


def canonical_provider(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in {"xiaomi", "xiaomi-mimo", "mimo"} else value


def call_mimo(
    agent: ModelProviderAgent, api_key: str, prompt: str, *, system: str,
) -> tuple[str, dict[str, Any]]:
    # Import at call time: the common layer dispatches here and owns the safe
    # transport, attempt ledger, deadlines and public receipt projection.
    from eslams import agents as common

    runtime = agent.runtime_config
    if runtime and any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise common.ProviderCallError(
            "MiMo supports reasoning auto/enabled/disabled; effort and token budgets "
            "are not supported by this adapter; no request submitted",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["max_completion_tokens"] = limit
    if runtime and runtime.reasoning != "auto":
        payload["thinking"] = {"type": runtime.reasoning}
    if agent.temperature is not None:
        # Current MiMo thinking models override sampling controls. Only forward
        # an explicit temperature when the operator disables thinking.
        if not runtime or runtime.reasoning != "disabled":
            raise common.ProviderCallError(
                "MiMo custom temperature requires explicitly disabled reasoning; "
                "no request submitted",
                error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
            )
        payload["temperature"] = agent.temperature
    response = common._post_json(
        common._provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
        headers={"api-key": api_key, "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = common._response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    if data.get("error") is not None or data.get("type") == "error":
        code = common._body_error_status(data.get("error"))
        kind = common._provider_error_kind(code) if code is not None else "provider_unavailable"
        receipt = common._failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
            retry_after_seconds=common._retry_after_seconds(response),
        )
        retry_permitted = common._capture_error_body_observations(
            response, provider=PROVIDER_ID, receipt=receipt,
        )
        receipt["request_id"] = common._http_error_identifier(
            response.headers.get("x-request-id") or response.headers.get("request-id"),
        )
        raise common.ProviderCallError(
            "MiMo reported an error inside the response body", error_kind=kind,
            status_code=code, provider=PROVIDER_ID, model=agent.model, receipt=receipt,
            retry_permitted=retry_permitted,
            retry_after_seconds=common._retry_after_seconds(response),
        )
    receipt = common._receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), runtime_config=runtime,
        # Catalogue pricing may be historical or broker sourced; it does not
        # establish this account's region, currency, plan or direct-API cost.
        capabilities=replace(agent.capabilities, pricing={}),
    )
    try:
        text = completion_text(data, receipt=receipt, model=agent.model)
    except common.ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def completion_text(data: dict[str, Any], *, receipt: dict[str, Any], model: str) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str, message: str) -> NoReturn:
        raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID, model=model)

    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch", "MiMo returned a malformed completion envelope")
    choice = choices[0]
    message = choice.get("message")
    reason = choice.get("finish_reason")
    known = {"stop", "length", "tool_calls", "content_filter", "repetition_truncation"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch", "MiMo returned a malformed assistant message")
    refusal = message.get("refusal")
    if reason == "content_filter" or isinstance(refusal, str) and bool(refusal):
        receipt["finish_status"] = "refused"
        fail("provider_refused", "MiMo refused or filtered the requested action")
    if reason in ("length", "repetition_truncation"):
        fail("provider_output_truncated", "MiMo truncated the response; no action accepted")
    if reason == "tool_calls" or message.get("tool_calls"):
        fail("provider_request_rejected", "MiMo returned tool calls; no action accepted")
    if (reason != "stop" or choice.get("index") != 0
            or not isinstance(choice.get("index"), int)
            or isinstance(choice.get("index"), bool)
            or refusal is not None and not isinstance(refusal, str)
            or not isinstance(message.get("content"), str) or not message["content"].strip()):
        fail(
            "provider_response_schema_mismatch",
            "MiMo returned malformed or incomplete action text",
        )
    receipt["finish_status"] = "completed"
    return str(message["content"])


def normalize_usage(value: Any) -> dict[str, Any]:
    """Read only documented MiMo fields; absent counts stay unknown, including total."""
    from eslams import agents as common

    normalized = common._empty_usage()
    if not isinstance(value, dict):
        return normalized
    errors: list[str] = []
    for source, target in (
        ("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        normalized[target] = common._usage_int(value.get(source), source, errors)
    for source, field, target in (
        ("prompt_tokens_details", "cached_tokens", "cached_input_tokens"),
        ("completion_tokens_details", "reasoning_tokens", "reasoning_tokens"),
    ):
        details = value.get(source)
        if details is not None and not isinstance(details, dict):
            errors.append(f"{source}_invalid")
        normalized[target] = common._usage_int(
            details.get(field) if isinstance(details, dict) else None, f"{source}.{field}", errors,
        )
    normalized.update(
        cache_read_input_tokens=normalized["cached_input_tokens"],
        cached_input_is_subset=True, reasoning_included_in_output=True,
        total_tokens_source="provider" if normalized["total_tokens"] is not None else "unavailable",
    )
    prompt = normalized["input_tokens"]
    output = normalized["output_tokens"]
    total = normalized["total_tokens"]
    cached = normalized["cached_input_tokens"]
    reasoning = normalized["reasoning_tokens"]
    if prompt is not None and output is not None and total is not None and total != prompt + output:
        errors.append("provider_total_tokens_inconsistent")
    if prompt is not None and cached is not None and cached > prompt:
        errors.append("cached_input_tokens_exceed_input_tokens")
    if output is not None and reasoning is not None and reasoning > output:
        errors.append("reasoning_tokens_exceed_inclusive_output_tokens")
    normalized["usage_validation_errors"] = sorted(set(errors))
    return normalized
