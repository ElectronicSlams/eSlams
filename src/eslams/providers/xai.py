"""Native xAI Responses transport and conservative raw-wire parsing.

No SDK, model substitution, server-side history, or tool execution.
See docs/PROVIDER_XAI.md for source provenance and accounting limits.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "xai"
API_KEY_ENV = "XAI_API_KEY"
RESPONSES_ENDPOINT = "https://api.x.ai/v1/responses"
MODELS_ENDPOINT = "https://api.x.ai/v1/models"
COST_SOURCE = "https://docs.x.ai/developers/cost-tracking"


def canonical_provider(provider: str) -> str:
    """Normalize only xAI spellings without changing other adapter conventions."""
    return "xai" if provider.strip().lower().replace("_", "-") in {"xai", "x-ai"} else provider


def usage_fields(usage: dict[str, Any]) -> dict[str, Any]:
    # The REST reference also contains an older prompt/completion envelope whose
    # total explicitly adds reasoning separately (32 + 9 + 110 = 151).
    # Current input/output examples have zero reasoning: do not infer inclusion
    # for nonzero reasoning, or accept a nonstandard caller-supplied inclusion flag.
    legacy = "input_tokens" not in usage and "output_tokens" not in usage and (
        "prompt_tokens" in usage or "completion_tokens" in usage
    )
    return {**usage, "reasoning_included_in_output": False if legacy else None}


def cost_usd(usage: Any) -> float | None:
    ticks = usage.get("cost_in_usd_ticks") if isinstance(usage, dict) else None
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
        return None
    try:
        value = ticks / 10_000_000_000
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Imported at execution time: Core owns shared attempt, transport and receipt
    # machinery; the provider-specific module owns wire behavior.
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
    if runtime and (
        runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None
    ):
        raise ProviderCallError(
            "xAI does not support Core's token-based thinking budget controls",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "input": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "store": False,
        "truncation": "disabled",
        "max_output_tokens": agent._effective_max_output_tokens(),
    }
    if runtime and runtime.reasoning_effort is not None:
        payload["reasoning"] = {"effort": runtime.reasoning_effort}
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(RESPONSES_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), native_cost=cost_usd(data.get("usage")),
        # A stale catalogue price cannot express tier/long-context/region costs.
        capabilities=replace(agent.capabilities, pricing={}), runtime_config=runtime,
    )
    try:
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = response_text(data, model=agent.model)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def response_text(data: dict[str, Any], *, model: str) -> str:
    from eslams.agents import ProviderCallError

    def malformed() -> ProviderCallError:
        return ProviderCallError(
            "xAI returned an unsupported or malformed Responses envelope",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID, model=model,
        )

    if (data.get("object") != "response" or data.get("status") != "completed"
            or data.get("incomplete_details") is not None or data.get("error") is not None):
        raise malformed()
    output = data.get("output")
    if not isinstance(output, list) or not output:
        raise malformed()
    text: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            raise malformed()
        if item.get("status", "completed") != "completed":
            raise malformed()
        if item.get("type") == "reasoning":
            continue  # Never publish summaries/ciphertext or treat them as actions.
        if (item.get("type") != "message" or item.get("role") != "assistant"
                or item.get("status") != "completed"):
            raise malformed()  # Includes unsolicited function/server-side tool calls.
        content = item.get("content")
        if not isinstance(content, list) or not content:
            raise malformed()
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                raise malformed()
            if not isinstance(part.get("text"), str):
                raise malformed()
            text.append(part["text"])
    if not text or not "".join(text).strip():
        raise malformed()
    return "".join(text)
