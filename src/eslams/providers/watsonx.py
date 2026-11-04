"""IBM watsonx.ai direct, non-streaming text chat (not the model gateway).

Wire references and deliberately unsupported surfaces: docs/PROVIDER_WATSONX.md.
Environment configuration stays out of the shared runtime/receipt contracts.
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.deadlines import ExecutionCancelled
from eslams.http_io import bounded_post
from eslams.protocol import ProtocolError

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

API_KEY_ENV = "WATSONX_API_KEY"
IAM_ENDPOINT = "https://iam.cloud.ibm.com/identity/token"
API_VERSION = "2025-10-25"
REGIONS = {
    region: f"https://{region}.ml.cloud.ibm.com"
    for region in ("us-south", "eu-de", "eu-gb", "jp-tok", "au-syd", "ca-tor")
}
ALIASES = {"watsonx", "watsonx-ai", "ibm-watsonx", "ibm-watsonx-ai"}


def normalize_alias(provider: str) -> str:
    value = provider.strip().lower().replace("_", "-")
    return "watsonx" if value in ALIASES else provider


def configuration(runtime: ProviderRuntimeConfig | None) -> tuple[str, dict[str, str]]:
    """Validate before either authentication or inference; never guess a region/model."""
    if runtime and (runtime.gateway_base_url or runtime.gateway_mode not in {
        "direct_provider", "disabled",
    }):
        raise ValueError("watsonx supports direct IBM Cloud endpoints only")
    region = os.environ.get("WATSONX_REGION", "")
    if region not in REGIONS:
        raise ValueError("WATSONX_REGION must select a documented IBM Cloud region")
    version = os.environ.get("WATSONX_API_VERSION", API_VERSION)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
            raise ValueError
        date.fromisoformat(version)
    except ValueError:
        raise ValueError("WATSONX_API_VERSION must be a YYYY-MM-DD date") from None
    project = os.environ.get("WATSONX_PROJECT_ID", "")
    space = os.environ.get("WATSONX_SPACE_ID", "")
    deployment = os.environ.get("WATSONX_DEPLOYMENT_ID", "")
    if deployment:
        # Prompt-template deployments can replace messages and model parameters.
        # Do not claim to preserve the direct chat policy through that surface.
        raise ValueError("watsonx deployment inference is unsupported; select a base model")
    if bool(project) == bool(space):
        raise ValueError("configure exactly one of WATSONX_PROJECT_ID or WATSONX_SPACE_ID")
    context = project or space
    if not re.fullmatch(r"[A-Za-z0-9-]+", context):
        raise ValueError("watsonx project/space ID must contain letters, digits or hyphens")
    if runtime and (runtime.reasoning_budget_tokens is not None
                    or runtime.gemini_thinking_budget is not None):
        raise ValueError("watsonx does not support these token reasoning budget controls")
    if runtime and runtime.reasoning_effort not in {None, "low", "medium", "high"}:
        raise ValueError("watsonx reasoning_effort must be low, medium or high")
    return (f"{REGIONS[region]}/ml/v1/text/chat?version={version}",
            {"project_id" if project else "space_id": context})


def configuration_error(runtime: ProviderRuntimeConfig | None) -> str | None:
    try:
        configuration(runtime)
    except ValueError as exc:
        return str(exc)
    return None


def _iam_token(api_key: str, runtime: ProviderRuntimeConfig | None) -> str:
    from eslams.agents import (
        ProviderCallError,
        _httpx_timeout,
        _provider_error_kind,
        _response_json,
    )

    # No token persistence, SDK retries, auth refresh/replay or arbitrary read cap.
    try:
        response = bounded_post(
            IAM_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"},
            json=None,
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
            timeout=_httpx_timeout(runtime),
        )
    except ExecutionCancelled:
        raise
    except httpx.TimeoutException:
        raise ProviderCallError("watsonx IAM authentication timed out; inference not submitted",
                                error_kind="provider_timeout", provider="watsonx") from None
    except (httpx.HTTPError, ProtocolError):
        raise ProviderCallError("watsonx IAM transport failed; inference not submitted",
                                error_kind="provider_transport_error",
                                provider="watsonx") from None
    if response.status_code != 200:
        raise ProviderCallError(
            f"watsonx IAM returned HTTP {response.status_code}; inference not submitted",
            status_code=response.status_code, error_kind=_provider_error_kind(response.status_code),
            provider="watsonx",
        )
    try:
        data = _response_json(response, provider="watsonx", model="")
        token = data.get("access_token")
        token_type = data.get("token_type")
        if (not isinstance(token, str) or not token or len(token) > 65536
                or any(ord(c) < 33 or ord(c) > 126 for c in token)
                or not isinstance(token_type, str) or token_type.lower() != "bearer"):
            raise ValueError
    except (ProviderCallError, ValueError):
        raise ProviderCallError("watsonx IAM returned invalid token data; inference not submitted",
                                error_kind="provider_auth_failed", provider="watsonx") from None
    return token


def call(agent: ModelProviderAgent, api_key: str, prompt: str,
         system: str) -> tuple[str, dict[str, Any]]:
    from eslams.agents import (
        ProviderCallError,
        _http_error_identifier,
        _post_json,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    try:
        endpoint, context = configuration(runtime)
        if not agent.model or agent.model != agent.model.strip():
            raise ValueError("watsonx requires an exact nonempty model ID")
    except ValueError as exc:
        raise ProviderCallError(str(exc), error_kind="provider_request_rejected",
                                provider="watsonx", model=agent.model) from None
    payload: dict[str, Any] = {
        **context, "model_id": agent.model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
    }
    maximum = agent._effective_max_output_tokens()
    if maximum is not None:
        payload["max_completion_tokens"] = maximum
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if runtime:
        if runtime.reasoning != "auto":
            payload["chat_template_kwargs"] = {"thinking": runtime.reasoning == "enabled"}
        if runtime.reasoning_effort is not None:
            payload["reasoning_effort"] = runtime.reasoning_effort
    token = _iam_token(api_key, runtime)
    try:
        response = _post_json(endpoint,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json",
                                       "Accept": "application/json"},
                              payload=payload, runtime_config=runtime,
                              control_key=f"watsonx:{agent.model}")
        data = _response_json_with_receipt(response, provider="watsonx", model=agent.model,
                                         capabilities=agent.capabilities, runtime_config=runtime)
    except ProviderCallError as exc:
        if exc.receipt is not None:
            _exclude_credentials(exc.receipt, api_key, token)
        raise
    # Only IBM's model_id attests identity; never use an OpenAI-shaped model field
    # or substitute the request/deployment ID. Missing accounting remains unknown.
    receipt = _receipt(provider="watsonx", model=agent.model, response=response,
                       provider_response_id=data.get("id"), resolved_model=data.get("model_id"),
                       usage=data.get("usage"), capabilities=agent.capabilities,
                       runtime_config=runtime)
    receipt["request_id"] = _http_error_identifier(response.headers.get("x-global-transaction-id"))
    _exclude_credentials(receipt, api_key, token)
    try:
        text = _text(data, receipt)
        reported = _http_error_identifier(data.get("model_id"))
        if reported is not None and reported != agent.model:
            raise ProviderCallError("watsonx returned a different model identity",
                                    error_kind="provider_request_rejected", provider="watsonx")
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def _text(data: dict[str, Any], receipt: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str) -> NoReturn:
        raise ProviderCallError("watsonx response did not contain a completed text action",
                                error_kind=kind, provider="watsonx")

    if data.get("errors") or data.get("error"):
        receipt["finish_status"] = "failed"
        fail("provider_unavailable")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail("provider_response_schema_mismatch")
    choice = choices[0]
    message = choice.get("message")
    reason = choice.get("finish_reason")
    known = {"stop", "length", "content_filter", "tool_calls", "function_call", "time_limit",
             "cancelled", "error"}
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known else "unknown"
    receipt["finish_status"] = "incomplete"
    if reason == "content_filter" or isinstance(message, dict) and message.get("refusal"):
        receipt["finish_status"] = "refused"
        fail("provider_refused")
    if "finish_reason" in choice and reason is None:
        fail("provider_pending")
    if reason == "cancelled":
        receipt["finish_status"] = "cancelled"
        fail("provider_cancelled")
    if reason == "error":
        receipt["finish_status"] = "failed"
        fail("provider_unavailable")
    if reason == "length":
        fail("provider_output_truncated")
    if reason in ("time_limit", "TIME_LIMIT"):
        fail("provider_interrupted")
    if reason in ("tool_calls", "function_call"):
        fail("provider_request_rejected")
    if reason != "stop" or not isinstance(message, dict) or message.get("role") != "assistant":
        fail("provider_response_schema_mismatch")
    if message.get("tool_calls") or message.get("function_call"):
        fail("provider_request_rejected")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        fail("provider_response_schema_mismatch")
    receipt["finish_status"] = "completed"
    # reasoning_content is private. It is never parsed as an action or retained.
    assert isinstance(content, str)
    return content


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    from eslams.agents import _normalize_usage

    # IBM documents these counters; neither response extensions nor requested
    # controls attest cached/reasoning counts or their billing inclusion.
    documented = {key: usage[key] for key in (
        "prompt_tokens", "completion_tokens", "total_tokens",
    ) if key in usage}
    normalized = _normalize_usage("generic", documented)
    raw_total = documented.get("total_tokens")
    if isinstance(raw_total, bool) or not isinstance(raw_total, int) or raw_total < 0:
        normalized["total_tokens"] = None
        normalized["total_tokens_source"] = "unavailable"
    return normalized


def _exclude_credentials(receipt: dict[str, Any], *secrets: str) -> None:
    """A provider can echo credentials even in otherwise safe identifier syntax."""
    for key in ("locked_model_id", "provider_response_id", "request_id", "gateway_request_id"):
        value = receipt.get(key)
        if isinstance(value, str) and any(secret in value for secret in secrets):
            receipt[key] = None
    if receipt.get("locked_model_id") is None:
        receipt["model_identity_source"] = None
