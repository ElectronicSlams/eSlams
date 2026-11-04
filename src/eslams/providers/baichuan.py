"""Baichuan's direct, non-streaming Chat Completions adapter.

Sources and verification limits: docs/providers/BAICHUAN.md. Keep private
reasoning, grounding, provider error prose and unknown extensions out of receipts.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any, NoReturn

from eslams.contracts.provider import ProviderRuntimeConfig

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "baichuan-ai"
API_KEY_ENV = "BAICHUAN_API_KEY"
CHAT_COMPLETIONS_ENDPOINT = "https://api.baichuan-ai.com/v1/chat/completions"
ALIASES = {"baichuan", "baichuan-ai", "baichuan_ai"}
ENDPOINT_KIND = "baichuan_chat_completions"
PARSER_VERSION = "baichuan-chat-completions-raw-v1"


def request_payload(
    model: str, prompt: str, *, instructions: str, temperature: float | None,
    max_tokens: int | None, runtime: ProviderRuntimeConfig | None,
) -> dict[str, Any]:
    validate_controls(model, runtime)
    runtime = runtime or ProviderRuntimeConfig()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if runtime.reasoning_budget_tokens is not None:
        payload["thinking"] = {"budget_tokens": runtime.reasoning_budget_tokens}
    return payload


def validate_controls(model: str, runtime: ProviderRuntimeConfig | None) -> None:
    """Shared preflight/transport admission for explicit native controls."""
    from eslams.agents import ProviderCallError

    runtime = runtime or ProviderRuntimeConfig()
    budget = runtime.reasoning_budget_tokens
    # The docs only establish this control for M2/M3. Do not invent switches,
    # effort mappings, budgets, Plus-model support, or silent ignored controls.
    unsupported = (
        runtime.reasoning_effort is not None or runtime.gemini_thinking_budget is not None
        or runtime.reasoning == "disabled"
        or (runtime.reasoning == "enabled" and budget is None)
        or (budget is not None and model not in {"Baichuan-M2", "Baichuan-M3"})
    )
    if unsupported or not isinstance(model, str) or not model.strip():
        raise ProviderCallError(
            "Baichuan requires an exact model and supported native reasoning controls; "
            "use auto defaults, or an explicit thinking budget for Baichuan-M2/M3",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=model,
        )


def normalize_usage(usage: Any) -> dict[str, Any]:
    """Preserve documented counters; absent accounting remains unknown."""
    errors: list[str] = []
    source = usage if isinstance(usage, dict) else {}

    def counter(name: str) -> int | None:
        value = source.get(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{name}_invalid")
            return None
        return int(value)

    prompt, completion, total = (counter(name) for name in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ))
    if (prompt is not None and completion is not None and total is not None
            and total != prompt + completion):
        errors.append("provider_total_tokens_inconsistent")
    return {
        "input_tokens": prompt, "output_tokens": completion, "total_tokens": total,
        "cached_input_tokens": None, "cache_read_input_tokens": None,
        "cache_write_input_tokens": None, "reasoning_tokens": None,
        # Neither the general nor medical wire docs establish token inclusion.
        "reasoning_included_in_output": None, "cached_input_is_subset": None,
        "total_tokens_source": "provider" if total is not None else "unavailable",
        "usage_source": "provider", "usage_validation_errors": sorted(errors),
    }


def call(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    from eslams.agents import ProviderCallError

    # Scrub the actual transmitted credential, including opaque keys that do
    # not match generic secret patterns. This boundary also covers shared
    # transport's error/malformed/partially observed response receipts.
    try:
        text, receipt = _call(agent, api_key, prompt)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _redact_credential(exc.receipt, api_key)
        # Shared transport may chain an exception containing an echoed secret.
        # Keep its sanitized observations, not its raw exception traceback.
        raise exc from None
    except TimeoutError:
        raise TimeoutError("Baichuan provider timed out") from None
    try:
        private_answer = _has_private_answer(text, api_key)
    except (ValueError, RecursionError):
        raise ProviderCallError(
            "Baichuan answer could not be inspected safely",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model, receipt=_redact_credential(receipt, api_key),
        ) from None
    if private_answer:
        raise ProviderCallError(
            "Baichuan returned credential material in answer text",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model, receipt=_redact_credential(receipt, api_key),
        )
    return text, _redact_credential(receipt, api_key)


_JSON_ESCAPE = re.compile(r'\\(?:u([0-9a-fA-F]{4})|(["\\/bfnrt]))')
_CREDENTIAL_LABEL = re.compile(
    r"(?i)\b(?:credential|password|client[_-]?secret|access[_-]?token)\s*[:=]\s*\S+"
)


def _has_private_answer(text: str, credential: str) -> bool:
    """Inspect raw and JSON-escaped answer text before parsing or recording it.

    Decoding is for inspection only; it never changes the model's action. A
    stack reduces escapes as characters arrive, without repeated full scans.
    Unrelated opaque values cannot be recognized without their value or a
    credential marker; no unused environment credentials are read here.
    """
    from eslams.agents import _SECRET_TEXT_PATTERNS
    from eslams.contracts.provider import _BEARER_VALUE_RE, _sensitive_public_key
    from eslams.model_actions import extract_json

    def private_string(value: str) -> bool:
        escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
                   "n": "\n", "r": "\r", "t": "\t"}

        def decode(match: re.Match[str]) -> str:
            return chr(int(match[1], 16)) if match[1] is not None else escapes[match[2]]

        def marked(candidate: str) -> bool:
            return bool(
                credential in candidate or _CREDENTIAL_LABEL.search(candidate)
                or any(match[1] != "[REDACTED]" for match in _BEARER_VALUE_RE.finditer(candidate))
                or any(pattern.search(candidate) for pattern in _SECRET_TEXT_PATTERNS)
            )

        if marked(value):
            return True
        decoded: list[str] = []
        for char in value:
            decoded.append(char)
            while True:
                match = (_JSON_ESCAPE.fullmatch("".join(decoded[-6:]))
                         if len(decoded) >= 6 and decoded[-6] == "\\" else None)
                if match is None and len(decoded) >= 2 and decoded[-2] == "\\":
                    match = _JSON_ESCAPE.fullmatch("".join(decoded[-2:]))
                if match is None:
                    break
                del decoded[-len(match[0]):]
                decoded.append(decode(match))
        return marked("".join(decoded))

    pending: list[Any] = [text, extract_json(text)]
    while pending:
        value = pending.pop()
        if isinstance(value, str) and private_string(value):
            return True
        if isinstance(value, dict):
            if any(_sensitive_public_key(str(key)) for key in value):
                return True
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def _redact_credential(receipt: dict[str, Any], credential: str) -> dict[str, Any]:
    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(credential, "[REDACTED]")
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    result: dict[str, Any] = scrub(receipt)
    usage = result.get("usage")
    if isinstance(usage, dict) and usage.get("usage_validation_errors"):
        # Incoherent counters cannot enter the canonical aggregate or make the
        # Runner reject its own ledger. Retain only static validation evidence.
        result["pricing_provenance"] = {
            **(result.get("pricing_provenance") or {}),
            "source": "unverified_provider_usage", "accounting_status": "quarantined",
            "usage_observation_status": "malformed",
            "usage_validation_errors": usage["usage_validation_errors"],
        }
        result["usage"] = {}
        result["usage_unavailable_reason"] = "provider_usage_malformed"
    provenance = result.get("pricing_provenance")
    if isinstance(provenance, dict) and "observed_cost_usd" in provenance:
        # Shared error custody is untrusted. Baichuan has no verified USD cost
        # field: even a numeric extension cannot establish its currency.
        provenance.pop("observed_cost_usd")
        provenance["cost_observation_status"] = "present_currency_unverified"
    for field in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id"):
        if isinstance(receipt.get(field), str) and credential in receipt[field]:
            result[field] = None
    # Opaque remote IDs can echo unrelated credentials the adapter never read.
    # Keep stable correlation fingerprints instead of publishing those strings.
    for field in ("request_id", "gateway_request_id", "provider_response_id"):
        if isinstance(result.get(field), str):
            result[field] = "sha256:" + hashlib.sha256(result[field].encode()).hexdigest()
    if result.get("locked_model_id") is None:
        result["model_identity_source"] = None
    return result


def _call(
    agent: ModelProviderAgent, api_key: str, prompt: str,
) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _body_error_status,
        _capture_error_body_observations,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_endpoint,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
        _retry_after_seconds,
    )

    payload = request_payload(
        agent.model, prompt, instructions=_SYSTEM_INSTRUCTIONS,
        temperature=agent.temperature, max_tokens=agent._effective_max_output_tokens(),
        runtime=agent.runtime_config,
    )
    response = _post_json(
        _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, agent.runtime_config),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=agent.runtime_config,
    )
    if data.get("error") is not None:
        code = _body_error_status(data["error"])
        kind = _provider_error_kind(code) if code is not None else "provider_unavailable"
        receipt = _failure_receipt(
            provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=agent.runtime_config, status_code=response.status_code,
        )
        _capture_error_body_observations(response, provider=PROVIDER_ID, receipt=receipt)
        receipt["request_id"] = _http_error_identifier(response.headers.get("x-bc-request-id"))
        raise ProviderCallError(
            "Baichuan reported an error inside the response body", error_kind=kind,
            status_code=code, provider=PROVIDER_ID, model=agent.model, receipt=receipt,
            # A body code alone does not establish a documented Baichuan
            # rejection after HTTP 200. Do not replay accepted/ambiguous work.
            retry_permitted=False, retry_after_seconds=_retry_after_seconds(response),
        )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    )

    def fail(kind: str, message: str) -> NoReturn:
        raise ProviderCallError(
            message, error_kind=kind, status_code=response.status_code,
            provider=PROVIDER_ID, model=agent.model, receipt={**receipt, "outcome": kind},
        )

    if response.status_code != 200:
        fail("provider_response_schema_mismatch", "Baichuan returned an unexpected HTTP status")
    if data.get("model") is not None and data["model"] != agent.model:
        # Unrecognized identities may be arbitrary echoed private data. Record
        # the mismatch outcome without copying that string into the ledger.
        receipt["locked_model_id"] = None
        receipt["model_identity_source"] = None
        fail("provider_response_schema_mismatch", "Baichuan returned a different model identity")
    choices = data.get("choices")
    if (data.get("object") != "chat.completion" or not isinstance(choices, list)
            or len(choices) != 1 or not isinstance(choices[0], dict)):
        fail("provider_response_schema_mismatch", "Baichuan returned an invalid completion")
    choice = choices[0]
    reason = choice.get("finish_reason")
    message = choice.get("message")
    receipt["finish_reason"] = reason if reason in (
        "stop", "length", "content_filter", "refuse_answer", "tool_calls",
    ) else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason in ("content_filter", "refuse_answer") or (
        isinstance(message, dict) and message.get("refusal")
    ):
        receipt["finish_status"] = "refused"
        fail("provider_refused", "Baichuan refused or filtered the requested action")
    if reason == "length":
        fail("provider_output_truncated", "Baichuan truncated the response; no action accepted")
    if (reason != "stop" or choice.get("error") is not None
            or type(choice.get("index")) is not int or choice["index"] != 0
            or not isinstance(message, dict) or message.get("role") != "assistant"
            or message.get("tool_calls") or not isinstance(message.get("content"), str)
            or not message["content"].strip()):
        fail("provider_response_schema_mismatch", "Baichuan returned no completed assistant text")
    receipt["finish_status"] = "completed"
    return str(message["content"]), receipt
