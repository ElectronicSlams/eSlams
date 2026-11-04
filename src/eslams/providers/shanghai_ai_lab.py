"""Shanghai AI Laboratory's Atria text API; no router or weights substitution.

Contract checked 2026-11-04: https://api.atria-asi.ai/docs
Only documented Chat Completions text and input/output usage paths are consumed.
Reasoning accounting, prices and unreported model identity remain unknown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "shanghai-ai-lab"
API_KEY_ENV = "ATRIA_API_KEY"
MODEL_ID = "Atria-Dawn"
CHAT_COMPLETIONS_ENDPOINT = "https://api.atria-asi.ai/v1/chat/completions"
ENDPOINT_KIND = "shanghai_ai_lab_atria_chat_completions"
PARSER_VERSION = "shanghai-ai-lab-atria-chat-raw-v1"


def validate_configuration(
    model: str,
    runtime: ProviderRuntimeConfig | None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Shanghai AI Lab requires an explicit nonblank model ID")
    if model != MODEL_ID:
        raise ValueError("Shanghai AI Lab's verified Atria endpoint supports only Atria-Dawn")
    if temperature is not None:
        raise ValueError("Shanghai AI Lab temperature control is not verified")
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int)
        or not 1 <= max_output_tokens <= 65_536
    ):
        raise ValueError("Atria output maximum must be an integer from 1 to 65536 or null")
    if runtime is None:
        return
    if runtime.reasoning != "auto" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Shanghai AI Lab reasoning controls are not verified; use native defaults")
    if runtime.history_window_turns is not None:
        raise ValueError("Shanghai AI Lab adapter requires the full public history")
    if runtime.gateway_base_url is not None or runtime.gateway_mode != "direct_provider":
        raise ValueError("Shanghai AI Lab adapter requires its verified direct Atria endpoint")
    if runtime.openrouter_provider_order:
        raise ValueError("Shanghai AI Lab adapter does not support third-party routing controls")


def _scrub(value: Any, secret: str) -> Any:
    """Exact credential custody, including plain echoes that regexes cannot identify."""
    if isinstance(value, str):
        return None if secret in value else value
    if isinstance(value, dict):
        return {_scrub(key, secret): _scrub(item, secret) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, secret) for item in value]
    return value


def _contains_secret(value: Any, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(_contains_secret(key, secret) or _contains_secret(item, secret)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item, secret) for item in value)
    return False


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at call time to reuse transport/receipt custody without a module cycle.
    from eslams import agents

    runtime = agent.runtime_config
    try:
        validate_configuration(
            agent.model, runtime, agent.temperature, agent._effective_max_output_tokens(),
        )
    except ValueError as exc:
        raise agents.ProviderCallError(
            str(exc), error_kind="provider_request_rejected", provider=PROVIDER_ID,
            model=agent.model,
        ) from None
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [{"role": "user", "content": agents._SYSTEM_INSTRUCTIONS + "\n" + prompt}],
        "max_completion_tokens": agent._effective_max_output_tokens(),
    }
    try:
        response = agents._post_json(
            CHAT_COMPLETIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=runtime, control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = agents._response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        # Project documented usage only. No assumed cache/reasoning/total/cost fields.
        raw_usage = data.get("usage")
        usage = {key: raw_usage[key] for key in ("prompt_tokens", "completion_tokens")
                 if key in raw_usage} if isinstance(raw_usage, dict) else None
        receipt = agents._receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"), usage=usage,
            capabilities=agent.capabilities, runtime_config=runtime,
        )
        if receipt["usage"]:
            # The reference does not establish whether reasoning is included in
            # completion_tokens. Even a seemingly obvious sum would invent accounting.
            receipt["usage"].update(total_tokens=None, total_tokens_source="unavailable",
                                    reasoning_included_in_output=None)
        receipt.update(usage_complete=False, reasoning_included_in_output=None)
        receipt = _scrub(receipt, api_key)

        def reject(kind: str, message: str) -> None:
            raise agents.ProviderCallError(
                message, error_kind=kind, provider=PROVIDER_ID, model=agent.model,
                status_code=response.status_code, receipt={**receipt, "outcome": kind},
            )

        if _contains_secret(data, api_key):
            # Reject before action parsing, so explanation/raw_action_text/action
            # cannot publish even an unlabelled or JSON-escaped credential echo.
            reject("provider_response_schema_mismatch", "provider response echoed a credential")
        if response.status_code != 200:
            reject("provider_pending" if response.status_code == 202 else
                   "provider_response_schema_mismatch", "provider response is not complete")
        if data.get("model") is not None and data["model"] != agent.model:
            reject("provider_response_schema_mismatch", "provider returned a different model")
        if data.get("error"):
            reject("provider_unavailable", "provider returned an error envelope")
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = choice.get("message") if isinstance(choice, dict) else None
        reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        receipt["finish_reason"] = reason if reason in (
            "stop", "length", "content_filter", "tool_calls", "function_call",
        ) else "unknown"
        if reason == "length":
            reject("provider_output_truncated", "provider output was truncated")
        if reason == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
            reject("provider_refused", "provider refused the request")
        if isinstance(message, dict) and (
            message.get("tool_calls") or message.get("function_call")
        ):
            reject("provider_interrupted", "provider returned an unsupported tool call")
        metadata = data.get("metadata")
        if isinstance(metadata, dict) and metadata.get("search_used") is True:
            reject("provider_interrupted", "provider reported unrequested search")
        text = message.get("content") if isinstance(message, dict) else None
        if reason != "stop" or not isinstance(text, str) or not text.strip():
            reject("provider_response_schema_mismatch", "provider returned invalid text")
        # Validation above proves this value is text; no SDK convenience fields.
        assert isinstance(text, str)
        return text, receipt
    except agents.ProviderCallError as exc:
        # Shared transport may have already observed partial headers/error bodies.
        # Redact the exact credential before the base agent publishes any receipt.
        failure_receipt = _scrub(exc.receipt, api_key) if exc.receipt is not None else None
        if failure_receipt is not None:
            failure_receipt["usage_complete"] = False
            if failure_receipt.get("usage"):
                failure_receipt["usage"].update(
                    total_tokens=None, total_tokens_source="unavailable",
                    reasoning_included_in_output=None,
                )
        raise agents.ProviderCallError(
            "Shanghai AI Lab request failed", status_code=exc.status_code,
            error_kind=exc.error_kind, retry_after_seconds=exc.retry_after_seconds,
            provider=PROVIDER_ID, model=agent.model,
            receipt=failure_receipt,
            # 429 also means quota exhaustion here. No verified rejection envelope
            # establishes safe replay, even if the caller enables optional retries.
            retry_permitted=False,
        ) from None
    except TimeoutError:
        raise TimeoutError("Shanghai AI Lab request timed out") from None
