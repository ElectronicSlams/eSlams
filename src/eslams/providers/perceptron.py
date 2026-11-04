"""Direct Perceptron text chat completions; no SDK routing or tool execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "perceptron"
API_KEY_ENV = "PERCEPTRON_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.perceptron.inc/v1/chat/completions"
MODELS_ENDPOINT = "https://api.perceptron.inc/v1/models"
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")


def validate_settings(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Perceptron requires an explicit nonblank model ID")
    if runtime is None:
        return
    if runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None:
        raise ValueError("Perceptron does not support a reasoning token budget")
    effort = runtime.reasoning_effort
    if effort is not None and (model != "perceptron-mk1.5" or effort not in REASONING_EFFORTS):
        raise ValueError("Perceptron reasoning effort requires Mk1.5 and a documented tier")
    if runtime.reasoning == "enabled" and effort == "none":
        raise ValueError("Perceptron reasoning is enabled but effort is none")
    if runtime.reasoning == "enabled" and model != "perceptron-mk1" and effort is None:
        raise ValueError("Perceptron reasoning enabled requires an explicit Mk1.5 effort")
    if model not in {"perceptron-mk1", "perceptron-mk1.5"} and runtime.reasoning != "auto":
        raise ValueError("Perceptron reasoning controls are unverified for this model ID")


def _contains_credential(value: Any, api_key: str) -> bool:
    if isinstance(value, str):
        return api_key in value
    if isinstance(value, dict):
        return any(_contains_credential(key, api_key) or _contains_credential(item, api_key)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_credential(item, api_key) for item in value)
    return False


def scrub_receipt(value: Any, api_key: str) -> Any:
    """Drop credential-bearing observations; redacted text cannot attest identity."""
    if isinstance(value, str):
        return None if api_key in value else value
    if isinstance(value, dict):
        clean = {key: scrub_receipt(item, api_key) for key, item in value.items()
                 if not _contains_credential(key, api_key)}
        if "locked_model_id" in clean and clean["locked_model_id"] is None:
            clean["model_identity_source"] = None
        return clean
    if isinstance(value, list):
        return [scrub_receipt(item, api_key) for item in value]
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Local import keeps the shared dispatcher independent of provider implementation details.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _capture_error_body_observations,
        _check_provider_completion,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    validate_settings(agent.model, runtime)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
    }
    if agent._request_max_output_tokens is not None:
        payload["max_completion_tokens"] = agent._request_max_output_tokens
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime:
        if agent.model == "perceptron-mk1" and runtime.reasoning != "auto":
            payload["vision_config"] = {"enable_thinking": runtime.reasoning == "enabled"}
        elif runtime.reasoning == "disabled":
            payload["reasoning_effort"] = "none"
        elif runtime.reasoning_effort is not None:
            payload["reasoning_effort"] = runtime.reasoning_effort
    receipt = None
    try:
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"perceptron:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        raw_usage = data.get("usage")
        # Only documented native token fields feed the shared accounting parser.
        usage = ({key: raw_usage[key] for key in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_tokens_details", "completion_tokens_details",
        ) if key in raw_usage} if isinstance(raw_usage, dict) else None)
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=usage, capabilities=agent.capabilities, runtime_config=runtime,
        )
        receipt["request_id"] = _http_error_identifier(response.headers.get("x-trace-id"))
        if data.get("error") or data.get("type") == "error":
            receipt = _failure_receipt(
                provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
                outcome="provider_unavailable",
                usage_unavailable_reason="provider_error_usage_unverified",
                runtime_config=runtime, status_code=response.status_code,
            )
            receipt["request_id"] = _http_error_identifier(response.headers.get("x-trace-id"))
            _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        if (data.get("object") != "chat.completion" or not isinstance(choices, list)
                or len(choices) != 1 or not isinstance(choices[0], dict)
                or type(choices[0].get("index")) is not int or choices[0]["index"] != 0):
            raise ProviderCallError("invalid Perceptron completion envelope",
                                    error_kind="provider_response_schema_mismatch")
        choice = choices[0]
        message = choice.get("message")
        reason = choice.get("finish_reason")
        receipt["finish_reason"] = reason if reason in (
            "stop", "length", "content_filter", "tool_calls", "interrupted",
        ) else "unknown"
        receipt["finish_status"] = "completed" if reason == "stop" else "incomplete"
        if reason == "length":
            raise ProviderCallError("Perceptron output was truncated",
                                    error_kind="provider_output_truncated")
        if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
            raise ProviderCallError("Perceptron refused the action", error_kind="provider_refused")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ProviderCallError("invalid Perceptron assistant message",
                                    error_kind="provider_response_schema_mismatch")
        if reason == "tool_calls" or message.get("tool_calls") or message.get("function_call"):
            raise ProviderCallError("Perceptron requested unsupported tools",
                                    error_kind="provider_request_rejected")
        if reason != "stop":
            raise ProviderCallError("Perceptron did not return a completed answer",
                                    error_kind="provider_response_schema_mismatch")
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise ProviderCallError("Perceptron returned no final answer",
                                    error_kind="provider_response_schema_mismatch")
        try:
            parsed_text = extract_json(text)
        except (ValueError, RecursionError):
            raise ProviderCallError("Perceptron returned malformed action text",
                                    error_kind="provider_response_schema_mismatch") from None
        if _contains_credential(text, api_key) or _contains_credential(parsed_text, api_key):
            raise ProviderCallError("Perceptron answer contained credentials",
                                    error_kind="provider_response_schema_mismatch")
        return text, scrub_receipt(receipt, api_key)
    except ProviderCallError as exc:
        safe_receipt = scrub_receipt(exc.receipt or receipt, api_key)
        raise ProviderCallError(
            "Perceptron request failed: " + exc.error_kind,
            error_kind=exc.error_kind, status_code=exc.status_code,
            retry_after_seconds=exc.retry_after_seconds, retry_permitted=exc.retry_permitted,
            provider=PROVIDER_ID, model=agent.model, receipt=safe_receipt,
        ) from None
