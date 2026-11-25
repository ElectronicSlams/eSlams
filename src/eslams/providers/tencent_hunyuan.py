"""Tencent Hunyuan's native, signed 2023-09-01 ChatCompletions API.

This legacy product is distinct from TokenHub and Coding Plan. See
docs/providers/TENCENT_HUNYUAN.md for lifecycle and raw-wire provenance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus

import httpx

from eslams.provider_credentials import provider_key

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "tencent-hunyuan"
ALIASES = {"hunyuan", PROVIDER_ID}
API_KEY_ENV = "TENCENTCLOUD_SECRET_ID"
ENDPOINT = "https://hunyuan.ai.tencentcloudapi.com/"
HOST = "hunyuan.ai.tencentcloudapi.com"
RETIREMENT_WARNING = (
    "Tencent native Hunyuan ChatCompletions is scheduled for retirement on "
    "2026-12-21; TokenHub is a separate product and is never selected automatically."
)


def credentials() -> tuple[str, str | None, str | None]:
    """Validate the complete credential set and optional explicit region privately."""
    secret = provider_key("TENCENTCLOUD_SECRET_KEY")
    if secret is None:
        raise ValueError("missing environment variable TENCENTCLOUD_SECRET_KEY")
    token = provider_key("TENCENTCLOUD_TOKEN")
    region = os.getenv("TENCENTCLOUD_REGION", "").strip() or None
    if region is not None and not re.fullmatch(r"[a-z0-9-]+", region):
        raise ValueError("TENCENTCLOUD_REGION must contain lowercase letters, digits or hyphens")
    return secret, token, region


def require_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("native Hunyuan requires an explicit nonblank model ID")


def validate_controls(
    model: str, runtime: ProviderRuntimeConfig, max_output_tokens: int | None,
) -> None:
    require_model(model)
    # Neither the native request documentation nor the official SDK defines
    # MaxTokens. Never silently ignore an operator policy or invent a wire field.
    if (runtime.gateway_base_url is not None or max_output_tokens is not None
            or runtime.reasoning_effort is not None
            or runtime.reasoning_budget_tokens is not None
            or runtime.gemini_thinking_budget is not None):
        raise ValueError(
            "native Hunyuan does not support gateway, output-token or reasoning-budget controls"
        )
    if runtime.reasoning != "auto" and model != "hunyuan-a13b":
        raise ValueError("native EnableThinking is documented only for exact model hunyuan-a13b")


def signed_headers(
    payload: dict[str, Any], secret_id: str, secret_key: str, *,
    timestamp: int | None = None, token: str | None = None, region: str | None = None,
) -> dict[str, str]:
    """Sign the same UTF-8 bytes HTTPX sends through the shared JSON transport."""
    stamp = int(time.time()) if timestamp is None else timestamp
    date = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d")
    body = httpx.Request("POST", ENDPOINT, json=payload).content
    digest = hashlib.sha256
    canonical = (
        "POST\n/\n\ncontent-type:application/json\n"
        f"host:{HOST}\nx-tc-action:chatcompletions\n\n"
        "content-type;host;x-tc-action\n" + digest(body).hexdigest()
    )
    scope = f"{date}/hunyuan/tc3_request"
    to_sign = f"TC3-HMAC-SHA256\n{stamp}\n{scope}\n{digest(canonical.encode()).hexdigest()}"
    date_key = hmac.new(("TC3" + secret_key).encode(), date.encode(), digest).digest()
    service_key = hmac.new(date_key, b"hunyuan", digest).digest()
    signing_key = hmac.new(service_key, b"tc3_request", digest).digest()
    signature = hmac.new(signing_key, to_sign.encode(), digest).hexdigest()
    headers = {
        "Content-Type": "application/json", "Host": HOST,
        "X-TC-Action": "ChatCompletions", "X-TC-Version": "2023-09-01",
        "X-TC-Timestamp": str(stamp),
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
            f"SignedHeaders=content-type;host;x-tc-action, Signature={signature}"
        ),
    }
    if token is not None:
        headers["X-TC-Token"] = token
    if region is not None:
        headers["X-TC-Region"] = region
    return headers


def normalize_usage(usage: Any) -> dict[str, Any]:
    from eslams.agents import _empty_usage, _usage_int

    result = _empty_usage()
    if not isinstance(usage, dict):
        return result
    errors: list[str] = []
    for source, target in (
        ("PromptTokens", "input_tokens"), ("CompletionTokens", "output_tokens"),
        ("TotalTokens", "total_tokens"),
    ):
        result[target] = _usage_int(usage.get(source), source, errors)
    result["total_tokens_source"] = (
        "provider" if result["total_tokens"] is not None else "unavailable"
    )
    details = usage.get("PromptTokensDetails")
    cached = details.get("CachedTokens") if isinstance(details, dict) else None
    if isinstance(cached, str) and re.fullmatch(r"[0-9]{1,20}", cached):
        cached = int(cached)
    result["cached_input_tokens"] = _usage_int(cached, "PromptTokensDetails.CachedTokens", errors)
    # Native docs do not attest a reasoning count, inclusion rule or USD cost.
    # Missing totals and cache/reasoning categories remain unknown.
    if (all(result[key] is not None for key in ("input_tokens", "output_tokens", "total_tokens"))
            and result["total_tokens"] != result["input_tokens"] + result["output_tokens"]):
        errors.append("provider_total_tokens_inconsistent")
    result["usage_validation_errors"] = errors
    return result


def _error_kind(code: Any) -> str:
    if not isinstance(code, str):
        return "provider_response_schema_mismatch"
    if code == "AuthFailure.UnauthorizedOperation" or code.startswith("UnauthorizedOperation"):
        return "provider_permission_failed"
    if code.startswith("AuthFailure"):
        return "provider_auth_failed"
    if (code.startswith("RequestLimitExceeded")
            or code == "FailedOperation.EngineServerLimitExceeded"):
        return "provider_rate_limited"
    if code == "OperationDenied.TextIllegalDetected":
        return "provider_refused"
    if code == "FailedOperation.EngineRequestTimeout":
        return "provider_timeout"
    if code == "ActionOffline" or code.startswith(
        ("InternalError", "ResourceUnavailable", "ResourceNotFound", "FailedOperation",
         "ServiceUnavailable")
    ):
        return "provider_unavailable"
    return "provider_request_rejected"


def _exclude_credential_identifiers(
    receipt: dict[str, Any], credentials: tuple[str, ...],
) -> dict[str, Any]:
    from eslams.agents import _redact_sensitive_text

    # Identifier syntax alone cannot distinguish a request ID from an echoed
    # credential. Apply this before publishing either success or failure receipts,
    # including receipts constructed by the shared malformed/partial-body paths.
    safe = dict(receipt)
    for field in ("request_id", "provider_response_id", "gateway_request_id", "locked_model_id"):
        value = safe.get(field)
        if isinstance(value, str) and (
            any(credential in value for credential in credentials if credential)
            or _redact_sensitive_text(value) != value
            or re.search(r"(?i)\b(?:AKID|AKIA|ASIA)[A-Za-z0-9]{12,}\b", value)
        ):
            safe[field] = None
    return safe


def _action_contains_credentials(text: str, credentials: tuple[str, ...]) -> bool:
    from eslams.model_actions import extract_json

    credentials = tuple({variant for credential in credentials if credential
                         for variant in (credential, quote(credential, safe=""),
                                         quote_plus(credential, safe=""))})

    def contains(value: str) -> bool:
        if any(credential in value for credential in credentials if credential):
            return True
        # Inspect JSON escapes even in frontmatter or malformed text that the
        # action extractor could discard. Never modify the returned action text.
        decoded = re.sub(
            r'\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt])',
            lambda match: json.loads('"' + match.group() + '"'), value,
        )
        return any(credential in decoded for credential in credentials if credential)

    if contains(text):
        return True
    try:
        pending = [extract_json(text)]
    except RecursionError:
        return True  # A failed exclusion scan cannot authorize public action text.
    while pending:
        value = pending.pop()
        if isinstance(value, str) and contains(value):
            return True
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def call(
    agent: ModelProviderAgent, secret_id: str, prompt: str, system: str,
) -> tuple[str, dict[str, Any]]:
    """Keep unobserved transport diagnostics and private exception chains private."""
    from eslams.agents import ProviderCallError

    excluded = tuple(value for value in (
        secret_id, *(os.getenv(name, "").strip() for name in (
            API_KEY_ENV, "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_TOKEN",
        )),
    ) if value)
    failure: ProviderCallError | TimeoutError
    try:
        return _call(agent, secret_id, prompt, system)
    except ProviderCallError as exc:
        message = str(exc)
        if (exc.error_kind in {"provider_response_schema_mismatch", "provider_transport_error",
                               "provider_timeout"}
                or _action_contains_credentials(message, excluded)):
            message = "native Hunyuan request or response failed; inspect the sanitized receipt"
        failure = ProviderCallError(
            message, status_code=exc.status_code, error_kind=exc.error_kind,
            retry_after_seconds=exc.retry_after_seconds, provider=PROVIDER_ID, model=agent.model,
            receipt=(_exclude_credential_identifiers(exc.receipt, excluded)
                     if exc.receipt is not None else None),
        )
    except TimeoutError:
        failure = TimeoutError("native Hunyuan request timed out")
    # Raising after the handler also discards the original private context.
    raise failure from None


def _call(
    agent: ModelProviderAgent, secret_id: str, prompt: str, system: str,
) -> tuple[str, dict[str, Any]]:
    # Local imports avoid a module cycle while retaining the existing physical
    # attempt, safe transport, cancellation, receipt and action parsing machinery.
    from eslams.agents import (
        ProviderCallError,
        _failure_receipt,
        _http_error_identifier,
        _post_json,
        _provider_error_kind,
        _receipt,
        _response_json_with_receipt,
        _retry_after_seconds,
    )
    from eslams.contracts.provider import ProviderRuntimeConfig
    from eslams.providers.capabilities import ModelCapabilities

    runtime = agent.runtime_config or ProviderRuntimeConfig()
    try:
        validate_controls(agent.model, runtime, agent._effective_max_output_tokens())
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_request_rejected",
            provider=PROVIDER_ID, model=agent.model,
        ) from None
    try:
        secret, token, region = credentials()
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_auth_failed", provider=PROVIDER_ID, model=agent.model,
        ) from None
    excluded = tuple(value for value in (
        secret_id, secret, token, os.getenv(API_KEY_ENV, "").strip(),
    ) if value)
    payload: dict[str, Any] = {
        "Model": agent.model, "Stream": False, "EnableEnhancement": False,
        "Messages": [{"Role": "system", "Content": system}, {"Role": "user", "Content": prompt}],
    }
    if agent.temperature is not None:
        payload["Temperature"] = agent.temperature
    if runtime.reasoning != "auto":
        payload["EnableThinking"] = runtime.reasoning == "enabled"

    # Catalogue prices describe other Tencent products too. Never price this
    # native route from a TokenHub/OpenRouter listing.
    capabilities = ModelCapabilities.unknown(PROVIDER_ID, agent.model)

    def read(response: httpx.Response) -> tuple[dict[str, Any], dict[str, Any]]:
        data = _response_json_with_receipt(
            response, provider=PROVIDER_ID, model=agent.model,
            capabilities=capabilities, runtime_config=runtime,
        )
        if "Response" in data:
            if not isinstance(data["Response"], dict) or len(data) != 1:
                failed = _failure_receipt(
                    provider=PROVIDER_ID, model=agent.model, agent_id="", agent_version="",
                    turn_id=0, outcome="provider_response_schema_mismatch",
                    usage_unavailable_reason="provider_response_schema_mismatch",
                    runtime_config=runtime, status_code=response.status_code,
                )
                failed["request_id"] = _http_error_identifier(
                    response.headers.get("X-TC-RequestId"),
                )
                raise ProviderCallError(
                    "malformed native Hunyuan envelope",
                    error_kind="provider_response_schema_mismatch",
                    provider=PROVIDER_ID, model=agent.model, receipt=failed,
                )
            data = data["Response"]
        receipt = _receipt(
            provider=PROVIDER_ID, model=agent.model, response=response,
            provider_response_id=data.get("Id"), resolved_model=None,
            usage=data.get("Usage"), capabilities=capabilities, runtime_config=runtime,
        )
        receipt["request_id"] = _http_error_identifier(
            response.headers.get("X-TC-RequestId") or data.get("RequestId"),
        )
        return data, _exclude_credential_identifiers(receipt, excluded)

    def check_error(response: httpx.Response) -> None:
        try:
            data, receipt = read(response)
        except ProviderCallError:
            if response.status_code >= 400:
                return  # Shared non-2xx custody handles an unparseable error body.
            raise
        if "Error" not in data and data.get("ErrorMsg") is None and response.status_code < 400:
            return
        error = data.get("Error") or data.get("ErrorMsg")
        if "Error" not in data and isinstance(error, dict) and type(error.get("Code")) is int:
            kind = {4000: "provider_unavailable", 4001: "provider_timeout"}.get(
                error["Code"], "provider_response_schema_mismatch",
            )
        else:
            kind = (_error_kind(error.get("Code")) if isinstance(error, dict)
                    else _provider_error_kind(response.status_code))
        # No automatic replay: engine/rate errors and RequestId do not prove
        # rejection before generation. Even an explicit retry budget cannot replay.
        receipt["outcome"] = kind
        raise ProviderCallError(
            "native Hunyuan returned an error", error_kind=kind,
            status_code=response.status_code, provider=PROVIDER_ID, model=agent.model,
            receipt=receipt, retry_after_seconds=_retry_after_seconds(response),
        )

    try:
        response = _post_json(
            ENDPOINT, headers={}, payload=payload, runtime_config=runtime,
            control_key=f"{PROVIDER_ID}:{agent.model}",
            header_factory=lambda body: signed_headers(
                body, secret_id, secret, token=token, region=region,
            ),
            response_handler=check_error,
        )
    except ProviderCallError as exc:
        if exc.receipt is not None:
            exc.receipt = _exclude_credential_identifiers(exc.receipt, excluded)
        raise
    data, receipt = read(response)
    choices = data.get("Choices")
    first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
    reason = first.get("FinishReason") if isinstance(first, dict) else None
    message = first.get("Message") if isinstance(first, dict) else None
    kind = None
    if reason == "sensitive" or data.get("ModerationLevel") == "1" or (
        isinstance(first, dict) and first.get("ModerationLevel") == "1"
    ):
        kind = "provider_refused"
    elif isinstance(reason, str) and reason in {"length", "max_tokens"}:
        kind = "provider_output_truncated"
    elif reason != "stop" or not isinstance(message, dict) or (
        message.get("Role") != "assistant" or not isinstance(message.get("Content"), str)
        or not message.get("Content") or message.get("ToolCalls")
    ):
        kind = "provider_response_schema_mismatch"
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "sensitive", "length", "max_tokens", "tool_calls",
    } else "unknown"
    if kind is not None:
        receipt["outcome"] = kind
        raise ProviderCallError(
            "native Hunyuan did not return a complete text action", error_kind=kind,
            provider=PROVIDER_ID, model=agent.model, receipt=receipt,
        )
    assert isinstance(message, dict)
    text = str(message["Content"])
    if _action_contains_credentials(text, excluded):
        receipt["outcome"] = "provider_response_schema_mismatch"
        raise ProviderCallError(
            "native Hunyuan action content failed credential exclusion",
            error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
            model=agent.model, receipt=receipt,
        )
    return text, receipt
