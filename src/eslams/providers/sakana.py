"""Direct Sakana Namazu text inference; Fugu's routed products are excluded."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import extract_json

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "sakana"
API_KEY_ENV = "SAKANA_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.sakana.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.sakana.ai/v1/models"
MODELS = frozenset({"sakana-namazu", "sakana-namazu-v1.0"})


def validate_config(model: str, config: ProviderRuntimeConfig) -> None:
    """Fail before authentication/network; never substitute a model or control."""
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Sakana requires an explicit nonblank model ID")
    if model not in MODELS:
        raise ValueError("Sakana adapter supports only the documented Namazu model IDs")
    if any(value is not None for value in (
        config.reasoning_effort, config.reasoning_budget_tokens, config.gemini_thinking_budget,
    )):
        raise ValueError("Namazu supports reasoning auto/enabled/disabled without effort or budget")
    if config.gateway_base_url or config.gateway_mode != "direct_provider":
        raise ValueError("Sakana requires its direct provider endpoint")
    if config.openrouter_provider_order:
        raise ValueError("Sakana does not support third-party provider routing controls")
    if config.history_window_turns is not None:
        raise ValueError("Sakana requires full supplied history")


def _contains_secret(value: Any, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(_contains_secret(key, secret) or _contains_secret(item, secret)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item, secret) for item in value)
    return False


def _safe_receipt(value: Any, secret: str) -> Any:
    """Exact credential suppression also covers otherwise valid public IDs."""
    if isinstance(value, str):
        return None if secret in value else value
    if isinstance(value, dict):
        result = {key: _safe_receipt(item, secret) for key, item in value.items()
                  if secret not in key}
        if result.get("locked_model_id") is None and "model_identity_source" in result:
            result["model_identity_source"] = None
        return result
    if isinstance(value, list):
        return [_safe_receipt(item, secret) for item in value]
    return value


def call_sakana(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    # Lazy imports keep provider code isolated while reusing Core's bounded
    # transport, cancellation, error custody, and invocation-scoped receipts.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    config = agent.runtime_config or ProviderRuntimeConfig()
    validate_config(agent.model, config)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "tools": [],
        "tool_choice": "none",
    }
    if agent._request_max_output_tokens is not None:
        payload["max_completion_tokens"] = agent._request_max_output_tokens
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if config.reasoning != "auto":
        payload["chat_template_kwargs"] = {"thinking": config.reasoning == "enabled"}

    receipt = None
    try:
        response = _post_json(
            CHAT_COMPLETIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=config, control_key=f"sakana:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=config,
        )
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=_usage(data.get("usage")), capabilities=agent.capabilities,
            runtime_config=config,
        )
        receipt = _safe_receipt(receipt, api_key)
        text = _text(data, receipt, agent.model)
        # Reject secret-bearing output before action parsing; replacing text
        # could change a legal action. Internal thinking is never returned.
        try:
            decoded = extract_json(text)
        except (ValueError, RecursionError):
            raise ProviderCallError(
                "Sakana action text cannot be decoded safely",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            ) from None
        if _contains_secret(text, api_key) or _contains_secret(decoded, api_key):
            raise ProviderCallError(
                "Sakana response contains credential material; no action accepted",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        return text, receipt
    except ProviderCallError as exc:
        # Shared HTTP and partial-body paths can carry echoed header/body IDs.
        # Scrub before ModelProviderAgent publishes an immutable receipt batch.
        observed = exc.receipt if exc.receipt is not None else receipt
        if observed is not None:
            exc.receipt = _safe_receipt({**observed, "outcome": exc.error_kind}, api_key)
        if _contains_secret(str(exc), api_key):
            exc.args = ("Sakana provider request failed",)
        # Sakana has no published replay-safety guarantee for rate-limit errors.
        exc.retry_permitted = False
        raise exc from None


def _usage(raw: Any) -> Any:
    """Only documented OpenAI-compatible counters enter trusted accounting."""
    if not isinstance(raw, dict):
        return None
    result = {key: raw[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
              if key in raw}
    for field, allowed in (
        ("prompt_tokens_details", ("cached_tokens",)),
        ("completion_tokens_details", ("reasoning_tokens",)),
    ):
        details = raw.get(field)
        if isinstance(details, dict):
            result[field] = {key: details[key] for key in allowed if key in details}
    return result


def _text(data: dict[str, Any], receipt: dict[str, Any], model: str) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str) -> NoReturn:
        raise ProviderCallError(
            "Sakana did not return one complete assistant text response",
            error_kind=kind, provider=PROVIDER_ID, model=model,
        )

    if data.get("error") is not None:
        fail("provider_unavailable")
    reported = data.get("model")
    if reported is not None and (
        not isinstance(reported, str) or reported not in MODELS
        or model == "sakana-namazu-v1.0" and reported != model
    ):
        fail("provider_response_schema_mismatch")
    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch")
    choice = choices[0]
    message = choice.get("message")
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "content_filter", "tool_calls", "function_call",
    } else "unknown"
    receipt["finish_status"] = "incomplete"
    if (reason == "content_filter"
            or isinstance(message, dict) and message.get("refusal") is not None):
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if reason == "length":
        fail("provider_output_truncated")
    if isinstance(reason, str) and reason in {"tool_calls", "function_call"}:
        fail("provider_request_rejected")
    if (reason != "stop" or choice.get("error") is not None
            or not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or message.get("function_call")
            or not isinstance(message.get("content"), str) or not message["content"].strip()):
        fail("provider_response_schema_mismatch")
    receipt["finish_status"] = "completed"
    return str(message["content"])
