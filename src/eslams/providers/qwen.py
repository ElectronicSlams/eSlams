"""Native DashScope synchronous text generation; no SDK or broker translation.

Wire provenance and deliberately unsupported routes are in docs/providers/QWEN.md.
Shared transport/accounting imports are deferred to avoid an agents import cycle.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import validate_json_payload
from eslams.providers.registry import PROVIDER_ALIASES

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.protocol import ActRequest, ActResponse

PROVIDER_ID = "qwen"
API_KEY_ENV = "DASHSCOPE_API_KEY"
ENDPOINT_KIND = "dashscope_text_generation"
PARSER_VERSION = "dashscope-text-generation-raw-v1"
_PATH = "/api/v1/services/aigc/text-generation/generation"
_REGIONS = {
    "ap-southeast-1", "cn-beijing", "cn-hongkong", "us-east-1",
    "eu-central-1", "ap-northeast-1",
}
_LEGACY_HOSTS = {
    "ap-southeast-1": "dashscope-intl.aliyuncs.com",
    "cn-beijing": "dashscope.aliyuncs.com",
    "cn-hongkong": "cn-hongkong.dashscope.aliyuncs.com",
}
_CREDENTIALS: ContextVar[tuple[str, ...]] = ContextVar("qwen_receipt_credentials", default=())


def validate_model(model: Any) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Qwen requires an explicit nonblank model ID")


def validate_controls(runtime: ProviderRuntimeConfig | None) -> None:
    if runtime is None:
        return
    if runtime.gemini_thinking_budget is not None:
        raise ValueError("Qwen does not support gemini_thinking_budget")
    if runtime.reasoning_effort is not None and runtime.reasoning_budget_tokens is not None:
        raise ValueError("Qwen accepts one of reasoning_effort and reasoning_budget_tokens")
    if runtime.reasoning_budget_tokens == 0:
        raise ValueError("Qwen thinking_budget must be positive")


@contextmanager
def credential_scope(environment_name: str) -> Iterator[None]:
    # Capture values privately before transport; no environment values enter a
    # receipt. Include configured secondary credentials, even without sk- syntax.
    credentials = set(_CREDENTIALS.get())
    for name, value in os.environ.items():
        if (name == environment_name or re.search(
            r"API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ACCESS_KEY|PRIVATE_KEY", name.upper(),
        )) and value.strip():
            credentials.add(value.strip())
    token = _CREDENTIALS.set(tuple(sorted(credentials, key=len, reverse=True)))
    try:
        yield
    finally:
        _CREDENTIALS.reset(token)


def contains_credential(value: str) -> bool:
    return any(secret in value for secret in _CREDENTIALS.get())


def redact(value: Any) -> Any:
    if isinstance(value, str):
        for secret in _CREDENTIALS.get():
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()
                if not isinstance(key, str) or not contains_credential(key)}
    return value


def act(agent: ModelProviderAgent, request: ActRequest) -> ActResponse:
    from eslams.agents import ProviderCallError

    with credential_scope(agent.api_key_env):
        try:
            response = agent._act(request)
        except ProviderCallError as exc:
            if exc.receipt is not None:
                exc.receipt = redact(exc.receipt)
            exc.args = (redact(str(exc)),)
            raise exc from None
        return replace(response, public_explanation=redact(response.public_explanation),
                       metadata=redact(response.metadata))

def canonicalize_provider(value: str) -> str:
    """Normalize Qwen aliases without changing other adapters' legacy naming."""
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ID if PROVIDER_ALIASES.get(normalized) == PROVIDER_ID else value.lower()


def generation_endpoint() -> str:
    """Allow only documented regional hosts; never echo environment values."""
    region = os.environ.get("DASHSCOPE_REGION", "ap-southeast-1")
    workspace = os.environ.get("DASHSCOPE_WORKSPACE_ID")
    if region not in _REGIONS:
        raise ValueError("DASHSCOPE_REGION must name a documented Model Studio region")
    if workspace is not None:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", workspace):
            raise ValueError("DASHSCOPE_WORKSPACE_ID must be a nonempty DNS label")
        host = f"{workspace}.{region}.maas.aliyuncs.com"
    else:
        if region not in _LEGACY_HOSTS:
            raise ValueError("DASHSCOPE_WORKSPACE_ID is required for this Model Studio region")
        host = _LEGACY_HOSTS[region]
    return f"https://{host}{_PATH}"


def usage_fields(usage: dict[str, Any]) -> dict[str, Any]:
    """Map documented native usage into Core's common token validator.

    Output includes reasoning. Cache tokens are subsets of input. Missing fields
    remain unknown; do not accept OpenAI names or a private extension's cost.
    """
    details = usage.get("prompt_tokens_details")
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "input_tokens_details": {
            "cached_tokens": details.get("cached_tokens") if isinstance(details, dict) else None,
            "cache_creation_input_tokens": (
                details.get("cache_creation_input_tokens") if isinstance(details, dict) else None
            ),
        },
        "output_tokens_details": usage.get("output_tokens_details"),
        "reasoning_included_in_output": True,
    }


def error_kind(code: Any, fallback: str = "provider_unavailable") -> str:
    if not isinstance(code, str):
        return fallback
    return {
        "InvalidApiKey": "provider_auth_failed",
        "invalid_api_key": "provider_auth_failed",
        "AccessDenied": "provider_permission_failed",
        "access_denied": "provider_permission_failed",
        "ModelNotFound": "provider_unavailable",
        "NotFound": "provider_unavailable",
        "InvalidParameter": "provider_request_rejected",
        "DataInspectionFailed": "provider_refused",
        "data_inspection_failed": "provider_refused",
        "Throttling": "provider_rate_limited",
        "Throttling.RateQuota": "provider_rate_limited",
        "Throttling.AllocationQuota": "provider_rate_limited",
        "InternalError": "provider_unavailable",
        "ServiceUnavailable": "provider_unavailable",
    }.get(code, fallback)


def annotate_http_error(response: httpx.Response, receipt: dict[str, Any], fallback: str) -> str:
    from eslams import agents as core

    try:
        data = core._strict_provider_json(response)
        validate_json_payload(data)
    except (ValueError, UnicodeError, RecursionError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    receipt["request_id"] = core._http_error_identifier(data.get("request_id"))
    # Only the documented moderation code changes HTTP classification. Other
    # codes cannot contradict the physical HTTP status (e.g. a gateway 5xx).
    if error_kind(data.get("code")) == "provider_refused":
        receipt["finish_status"] = "refused"
        return "provider_refused"
    return fallback


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    from eslams import agents as core

    runtime = agent.runtime_config
    try:
        validate_model(agent.model)
        validate_controls(runtime)
        endpoint = generation_endpoint()
    except ValueError as exc:
        raise core.ProviderCallError(
            str(exc), error_kind="provider_request_rejected", provider=PROVIDER_ID,
            model=agent.model,
        ) from None
    parameters: dict[str, Any] = {"result_format": "message"}
    if agent._effective_max_output_tokens() is not None:
        # This legacy native control caps answer tokens, excluding thinking.
        parameters["max_tokens"] = agent._effective_max_output_tokens()
    if agent.temperature is not None:
        parameters["temperature"] = agent.temperature
    if runtime is not None:
        if runtime.reasoning != "auto":
            parameters["enable_thinking"] = runtime.reasoning == "enabled"
        if runtime.reasoning_budget_tokens is not None:
            parameters["thinking_budget"] = runtime.reasoning_budget_tokens
        if runtime.reasoning_effort is not None:
            parameters["reasoning_effort"] = runtime.reasoning_effort
    response = core._post_json(
        core._provider_endpoint(endpoint, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload={
            "model": agent.model,
            "input": {"messages": [
                {"role": "system", "content": core._SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ]},
            "parameters": parameters,
        },
        runtime_config=runtime,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    # Catalogue prices are neither region-specific nor a complete native rate
    # card (tier/cache/thinking). Never label a broker price as DashScope cost.
    capabilities = replace(agent.capabilities, pricing={})
    data = core._response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model, capabilities=capabilities,
        runtime_config=runtime,
    )
    receipt = core._receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("request_id"), resolved_model=None,
        usage=data.get("usage"), capabilities=capabilities, runtime_config=runtime,
    )
    receipt["request_id"] = (
        core._http_error_identifier(data.get("request_id")) or receipt["request_id"]
    )
    try:
        return _completed_text(data, receipt, agent.model), receipt
    except core.ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise


def _completed_text(data: dict[str, Any], receipt: dict[str, Any], model: str) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str, message: str) -> NoReturn:
        raise ProviderCallError(message, error_kind=kind, provider=PROVIDER_ID, model=model)

    # Native errors are flat {code, message, request_id}; do not parse error
    # prose or trust work/cost extensions, and never auto-replay body errors.
    if data.get("code") is not None or data.get("error") is not None:
        kind = error_kind(data.get("code"))
        receipt["finish_status"] = "refused" if kind == "provider_refused" else "failed"
        fail(kind, "DashScope reported an error; no action accepted")
    output = data.get("output")
    choices = output.get("choices") if isinstance(output, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch", "DashScope requires one message choice")
    choice = choices[0]
    reason = choice.get("finish_reason")
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in {
        "stop", "length", "tool_calls", "content_filter",
    } else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason == "length":
        fail("provider_output_truncated", "DashScope output was truncated; no action accepted")
    if reason == "content_filter":
        receipt["finish_status"] = "refused"
        fail("provider_refused", "DashScope filtered the response; no action accepted")
    if reason == "tool_calls":
        fail("provider_request_rejected", "DashScope requested tools; tools are unsupported")
    if reason != "stop":
        fail("provider_response_schema_mismatch", "DashScope response has no completed stop")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch", "DashScope assistant message is missing")
    if message.get("refusal"):
        receipt["finish_status"] = "refused"
        fail("provider_refused", "DashScope refused the response; no action accepted")
    if message.get("tool_calls") or message.get("function_call"):
        fail("provider_request_rejected", "DashScope requested tools; tools are unsupported")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        fail("provider_response_schema_mismatch", "DashScope text content is missing")
    receipt["finish_status"] = "completed"
    return text
