"""Direct Apodex Core text inference; never the server-side research agent.

Wire contract: https://platform.apodex.ai/docs/models (checked 2026-11-04).
The imports inside call avoid a cycle with the shared agent transport/receipts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "apodex"
API_KEY_ENV = "APODEX_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.apodex.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.apodex.ai/v1/models"
CORE_MODELS = ("apodex-1.1", "apodex-1.1-mini")


def validate_configuration(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Apodex requires an explicit nonblank Core model ID")
    if model not in CORE_MODELS:
        raise ValueError("Apodex supports only apodex-1.1 and apodex-1.1-mini Core model IDs")
    if runtime is None:
        return
    if runtime.reasoning == "disabled" or any(value is not None for value in (
        runtime.reasoning_effort, runtime.reasoning_budget_tokens, runtime.gemini_thinking_budget,
    )):
        raise ValueError("Apodex Core has native reasoning; reasoning controls are unsupported")
    if runtime.gateway_base_url or runtime.openrouter_provider_order:
        raise ValueError("Apodex Core requires its direct operator endpoint without routing")


def _without_credential(value: Any, credential: str) -> Any:
    """Drop echoed credentials, including dictionary keys, before publication.

    An identifier containing a credential becomes unknown, never a redacted
    string that could be mistaken for an attested identity. Numeric telemetry
    remains usable. This also protects receipts made by shared failure paths.
    """
    if isinstance(value, str):
        return None if credential in value else value
    if isinstance(value, dict):
        return {key: _without_credential(item, credential) for key, item in value.items()
                if isinstance(key, str) and credential not in key}
    if isinstance(value, list):
        return [_without_credential(item, credential) for item in value]
    return value


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _extract_json,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    validate_configuration(agent.model, agent.runtime_config)
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
        "temperature": agent.temperature,
    }
    receipt: dict[str, Any] | None = None
    try:
        response = _post_json(
            CHAT_COMPLETIONS_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload=payload, runtime_config=agent.runtime_config,
            control_key=f"{PROVIDER_ID}:{agent.model}",
        )
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=agent.capabilities, runtime_config=agent.runtime_config,
        )
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("id"), resolved_model=data.get("model"),
            usage=data.get("usage"), capabilities=agent.capabilities,
            runtime_config=agent.runtime_config,
        )
        if data.get("model") is not None and data["model"] != agent.model:
            raise ProviderCallError(
                "Apodex returned a different model; no action accepted",
                error_kind="provider_request_rejected",
            )
        text = _completion_text(data, receipt)
        if api_key in text or _contains_credential(_extract_json(text), api_key):
            raise ProviderCallError(
                "Apodex returned credential material; no action accepted",
                error_kind="provider_response_schema_mismatch",
            )
        return text, _without_credential(receipt, api_key)
    except ProviderCallError as exc:
        # No raw provider prose, headers, private reasoning or exception causes
        # escape. Preserve safe observations even for malformed/partial bodies.
        failure = receipt if receipt is not None else exc.receipt
        if failure is not None:
            failure = {**failure, "outcome": exc.error_kind}
        raise ProviderCallError(
            "Apodex request failed; see sanitized receipt outcome",
            status_code=exc.status_code, error_kind=exc.error_kind,
            retry_after_seconds=exc.retry_after_seconds, provider=PROVIDER_ID,
            model=agent.model, receipt=_without_credential(failure, api_key),
            retry_permitted=exc.retry_permitted,
        ) from None


def _contains_credential(value: Any, credential: str) -> bool:
    if isinstance(value, str):
        return credential in value
    if isinstance(value, dict):
        return any(credential in key or _contains_credential(item, credential)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_credential(item, credential) for item in value)
    return False


def _completion_text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str = "provider_response_schema_mismatch") -> NoReturn:
        raise ProviderCallError("Apodex completion was not accepted", error_kind=kind)

    if data.get("error") is not None:
        fail("provider_unavailable")
    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail()
    choice = choices[0]
    if choice.get("error") is not None:
        fail("provider_unavailable")
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if reason in ("stop", "length", "content_filter") else None
    receipt["finish_status"] = "unknown"
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail()
    if reason == "length":
        receipt["finish_status"] = "incomplete"
        fail("provider_output_truncated")
    if reason == "content_filter" or message.get("refusal"):
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if message.get("tool_calls") or message.get("function_call"):
        fail("provider_request_rejected")
    if type(choice.get("index")) is not int or choice["index"] != 0 or reason != "stop":
        fail()
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        fail()
    receipt["finish_status"] = "completed"
    return content
