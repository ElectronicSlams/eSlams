"""Writer direct Chat API; documented raw wire shapes, without an SDK dependency."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "writer"
API_KEY_ENV = "WRITER_API_KEY"
CHAT_ENDPOINT = "https://api.writer.com/v1/chat"
MODELS_ENDPOINT = "https://api.writer.com/v1/models"
ALIASES = {"writer", "writer-ai", "writerai"}


def usage_fields(usage: dict[str, Any]) -> dict[str, Any]:
    """Translate only documented fields; reasoning inclusion remains unverified."""
    prompt = usage.get("prompt_token_details")
    # REST example uses singular completion_token_details; the generated
    # OpenAPI SDK uses completion_tokens_details. Neither is a second charge.
    details = [usage[key] for key in ("completion_tokens_details", "completion_token_details")
               if usage.get(key) is not None]
    reasoning = details[0].get("reasoning_tokens") if details and isinstance(
        details[0], dict
    ) else None
    if len(details) == 2 and details[0] != details[1]:
        reasoning = "conflicting_writer_reasoning_details"
    return {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": prompt.get("cached_tokens") if isinstance(prompt, dict) else None,
        "reasoning_tokens": reasoning,
    }


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Lazy import reuses the existing transport/receipt custody without a cycle.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _failure_receipt,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    if runtime and (runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    ))):
        raise ProviderCallError(
            "Writer Chat API has no documented reasoning control; use native auto defaults",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=agent.model,
        )
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [{"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                     {"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(CHAT_ENDPOINT, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime, control_key=f"writer:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    if "tpe" in data or "errors" in data or "error" in data:
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome="provider_unavailable",
            usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime, status_code=response.status_code,
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["finish_status"] = "failed"
        raise ProviderCallError(
            "Writer reported an error inside the response body", error_kind="provider_unavailable",
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=usage_fields(data["usage"]) if isinstance(data.get("usage"), dict) else None,
        capabilities=agent.capabilities, runtime_config=runtime,
    )

    def fail(kind: str, message: str, *, finish: str | None = None) -> NoReturn:
        receipt.update(outcome=kind, finish_status=finish)
        raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID,
                                model=agent.model, receipt=receipt)

    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch", "Writer response has no unique chat completion")
    choice = choices[0]
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls",
    } else "unknown"
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch", "Writer response has no assistant message")
    refusal = message.get("refusal")
    if refusal is not None and not isinstance(refusal, str):
        fail("provider_response_schema_mismatch", "Writer returned malformed refusal")
    if reason == "content_filter" or refusal:
        fail("provider_refused", "Writer refused or filtered the requested action",
             finish="refused")
    if reason == "length":
        fail("provider_output_truncated", "Writer output was truncated; no action accepted",
             finish="incomplete")
    if reason == "tool_calls" or message.get("tool_calls"):
        fail("provider_request_rejected", "Writer returned unsupported tool calls",
             finish="incomplete")
    content = message.get("content")
    if reason != "stop" or not isinstance(content, str) or not content:
        fail("provider_response_schema_mismatch", "Writer returned incomplete or malformed text")
    receipt["finish_status"] = "completed"
    return content, receipt
