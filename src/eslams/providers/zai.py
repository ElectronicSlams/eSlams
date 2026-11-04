"""Direct Z.ai (international) and Zhipu (China) Chat Completions.

Transport, attempt custody, deadlines and sanitization remain owned by agents.
Only standard API endpoints are supported; Coding Plan names never alias here.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

ENDPOINTS = {
    "zai": "https://api.z.ai/api/paas/v4/chat/completions",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
}
API_KEY_ENVS = {"zai": "ZAI_API_KEY", "zhipu": "ZHIPU_API_KEY"}
ALIASES = {"z.ai": "zai", "z-ai": "zai", "zhipuai": "zhipu"}


def canonical_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    if normalized in ENDPOINTS or normalized in ALIASES:
        return ALIASES.get(normalized, normalized)
    return provider


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import lazily: agents owns the shared receipt/transport implementation.
    from eslams import agents as shared

    runtime = agent.runtime_config
    if runtime and any(
        value is not None
        for value in (
            runtime.reasoning_budget_tokens,
            runtime.gemini_thinking_budget,
        )
    ):
        raise shared.ProviderCallError(
            "Z.ai/Zhipu has no token-budget reasoning control; no request submitted",
            error_kind="provider_request_rejected",
            provider=agent.provider,
            model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": shared._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime and runtime.reasoning != "auto":
        payload["thinking"] = {"type": runtime.reasoning}
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning_effort"] = runtime.reasoning_effort
    response = shared._post_json(
        shared._provider_endpoint(ENDPOINTS[agent.provider], runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
        runtime_config=runtime,
        control_key=f"{agent.provider}:{agent.model}",
    )
    data = shared._response_json_with_receipt(
        response,
        provider=agent.provider,
        model=agent.model,
        capabilities=agent.capabilities,
        runtime_config=runtime,
    )
    # Business errors may be returned inside HTTP 200. Quarantine observations;
    # error-body model/cost claims cannot attest identity or canonical cost.
    if "error" in data or "code" in data:
        receipt = shared._failure_receipt(
            provider=agent.provider,
            model=agent.model,
            agent_id="",
            agent_version="",
            turn_id=0,
            outcome="provider_request_rejected",
            usage_unavailable_reason="provider_error",
            runtime_config=runtime,
            status_code=response.status_code,
        )
        shared._capture_error_body_observations(response, provider=agent.provider, receipt=receipt)
        receipt["request_id"] = shared._http_error_identifier(
            response.headers.get("x-request-id")
            or response.headers.get("request-id")
            or data.get("request_id")
        )
        raw_error = data.get("error")
        error = raw_error if isinstance(raw_error, dict) else data
        kind = _business_error_kind(error.get("code"))
        receipt["outcome"] = kind
        raise shared.ProviderCallError(
            "provider reported a business error",
            error_kind=kind,
            status_code=response.status_code,
            provider=agent.provider,
            model=agent.model,
            receipt=receipt,
        )
    receipt = shared._receipt(
        provider=agent.provider,
        model=agent.model,
        response=response,
        provider_response_id=data.get("id"),
        resolved_model=data.get("model"),
        usage=data.get("usage"),
        capabilities=replace(agent.capabilities, pricing={}),
        runtime_config=runtime,
    )
    if receipt["request_id"] is None:
        receipt["request_id"] = shared._http_error_identifier(data.get("request_id"))
    try:
        text = _text(data, receipt)
    except shared.ProviderCallError as exc:
        exc.provider, exc.model = agent.provider, agent.model
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    message = first.get("message") if isinstance(first, dict) else None
    reason = first.get("finish_reason") if isinstance(first, dict) else None
    known = {
        "stop",
        "length",
        "sensitive",
        "tool_calls",
        "model_context_window_exceeded",
        "network_error",
    }
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason == "sensitive" or (isinstance(message, dict) and message.get("refusal")):
        receipt["finish_status"] = "refused"
        kind = "provider_refused"
    elif isinstance(reason, str) and reason in {"length", "model_context_window_exceeded"}:
        kind = "provider_output_truncated"
    elif reason == "network_error":
        kind = "provider_interrupted"
    elif reason == "tool_calls" or (isinstance(message, dict) and message.get("tool_calls")):
        kind = "provider_request_rejected"
    elif (
        reason != "stop"
        or not isinstance(message, dict)
        or message.get("role") != "assistant"
        or (isinstance(first, dict) and "error" in first)
        or not isinstance(message.get("content"), str)
        or not message["content"].strip()
    ):
        kind = "provider_response_schema_mismatch"
    else:
        receipt["finish_status"] = "completed"
        return str(message["content"])
    raise ProviderCallError(
        "provider did not return a complete text action",
        error_kind=kind,
    )


def _business_error_kind(code: Any) -> str:
    # Codes are allowlisted; raw messages and arbitrary classifiers stay private.
    value = str(code) if isinstance(code, (str, int)) and not isinstance(code, bool) else ""
    if value in {"1000", "1001", "1003", "1005"}:
        return "provider_auth_failed"
    if value == "1220":
        return "provider_permission_failed"
    if value == "1301":
        return "provider_refused"
    if value in {"1113", "1302", "1305"}:
        return "provider_rate_limited"
    if value in {"1200", "1230", "1234"}:
        return "provider_unavailable"
    return "provider_request_rejected"


def safe_rate_rejection(data: Any, status: int) -> bool:
    """Only documented request-rate/overload rejections can be safely retried.

    Balance, plan limits, unknown codes, or any evidence of work fail closed.
    The shared transport additionally quarantines usage/identity observations.
    """
    if status != 429 or not isinstance(data, dict) or set(data) != {"error"}:
        return False
    error = data["error"]
    return (
        isinstance(error, dict)
        and set(error) <= {"code", "message"}
        and isinstance(error.get("code"), str)
        and error["code"] in {"1302", "1305"}
        and ("message" not in error or isinstance(error["message"], str))
    )


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Read documented fields only; missing categories/inclusion remain unknown."""
    from eslams import agents as shared

    result = shared._empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for target, source in (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        result[target] = shared._usage_int(usage.get(source), source, errors)
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = shared._usage_int(details.get("cached_tokens"), "cached_tokens", errors)
        result.update(cached_input_tokens=cached, cache_read_input_tokens=cached)
        if (
            cached is not None
            and result["input_tokens"] is not None
            and cached > result["input_tokens"]
        ):
            errors.append("cached_input_tokens_exceed_input_tokens")
    result.update(
        cached_input_is_subset=True,
        total_tokens_source="provider" if result["total_tokens"] is not None else "unavailable",
        usage_validation_errors=errors,
    )
    return result
