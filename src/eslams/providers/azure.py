"""Direct Azure Foundry v1 chat completions, without an SDK or model routing."""

from __future__ import annotations

import math
import os
import re
from typing import TYPE_CHECKING, Any, NoReturn
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "azure"
API_KEY_ENV = "AZURE_AI_API_KEY"
ALIASES = ("azure", "azure-ai", "azure-foundry", "azure-ai-foundry", "microsoft-azure")
ENDPOINT_KIND = "azure_foundry_v1_chat_completions"
PARSER_VERSION = "azure-foundry-v1-chat-completions-raw-v1"


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in ALIASES else provider.lower()


def credential_environment() -> str:
    mode = os.getenv("AZURE_AI_AUTH_MODE", "api-key")
    if mode not in {"api-key", "entra"}:
        raise ValueError("AZURE_AI_AUTH_MODE must be api-key or entra")
    return "AZURE_AI_AUTH_TOKEN" if mode == "entra" else API_KEY_ENV


def endpoint(runtime_config: ProviderRuntimeConfig | None = None) -> str:
    if runtime_config and runtime_config.gateway_base_url:
        raise ValueError("Azure direct inference does not support gateway_base_url")
    raw = os.getenv("AZURE_AI_ENDPOINT", "")
    # Require a public Azure resource origin or its v1 base; never silently turn
    # a project, legacy deployment, Models API, broker or direct OpenAI URL into it.
    try:
        parsed = urlsplit(raw)
        valid = (
            all(33 <= ord(character) <= 126 for character in raw)
            and parsed.scheme == "https"
            and re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9-]*\.(?:openai\.azure\.com|services\.ai\.azure\.com)",
                parsed.netloc,
            )
            is not None
            and parsed.path in {"", "/", "/openai/v1", "/openai/v1/"}
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(
            "AZURE_AI_ENDPOINT must be an HTTPS public Azure resource endpoint "
            "(*.openai.azure.com or *.services.ai.azure.com), optionally ending in /openai/v1/"
        )
    return f"https://{parsed.netloc}/openai/v1/chat/completions"


def retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after-ms")
    try:
        milliseconds = float(value) if value is not None else math.nan
    except ValueError:
        return None
    return milliseconds / 1000 if math.isfinite(milliseconds) and milliseconds >= 0 else None


def is_content_filter_rejection(response: httpx.Response) -> bool:
    from eslams.agents import _strict_provider_json
    from eslams.protocol import validate_json_payload

    if response.status_code != 400:
        return False
    try:
        data = _strict_provider_json(response)
        validate_json_payload(data)
    except (ValueError, UnicodeError, RecursionError):
        return False
    error = data.get("error") if isinstance(data, dict) else None
    return isinstance(error, dict) and error.get("code") == "content_filter"


def _completion_text(data: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    def fail(kind: str = "provider_response_schema_mismatch") -> NoReturn:
        raise ProviderCallError(
            "Azure returned no complete assistant text action",
            error_kind=kind,
            provider=PROVIDER_ID,
        )

    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        fail()
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        fail()
    if choice.get("finish_reason") == "content_filter" or message.get("refusal"):
        fail("provider_refused")
    if choice.get("finish_reason") == "length":
        fail("provider_output_truncated")
    if choice.get("finish_reason") != "stop":
        fail()
    # Tools and reasoning text cannot become actions, even beside legal-looking text.
    if (
        message.get("role") != "assistant"
        or message.get("tool_calls")
        or message.get("function_call")
    ):
        fail()
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        fail()
    return str(content)


def call(agent: ModelProviderAgent, credential: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Imports are local so the dispatch owner can import provider metadata while
    # this provider reuses the existing bounded transport and sanitized receipts.
    from eslams import agents as core

    try:
        url = endpoint(agent.runtime_config)
        credential_environment()  # Validate the authentication mode, even with a custom key env.
        if not agent.model or not agent.model.strip():
            raise ValueError("Azure requires an explicit deployment name")
    except ValueError as exc:
        raise core.ProviderCallError(
            str(exc),
            error_kind="provider_request_rejected",
            provider=PROVIDER_ID,
            model=agent.model,
        ) from None
    headers = {"Content-Type": "application/json"}
    if os.getenv("AZURE_AI_AUTH_MODE", "api-key") == "entra":
        headers["Authorization"] = f"Bearer {credential}"
    else:
        headers["api-key"] = credential
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": core._SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "store": False,
    }
    limit = agent._effective_max_output_tokens()
    if limit is not None:
        payload["max_completion_tokens"] = limit
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    if agent.runtime_config and agent.runtime_config.reasoning_effort is not None:
        payload["reasoning_effort"] = agent.runtime_config.reasoning_effort
    response = core._post_json(
        url,
        headers=headers,
        payload=payload,
        runtime_config=agent.runtime_config,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    if response.status_code != 200:
        raise core.ProviderCallError(
            "Azure returned an unexpected HTTP status; no action accepted",
            status_code=response.status_code,
            error_kind="provider_transport_error",
            provider=PROVIDER_ID,
            model=agent.model,
        )
    data = core._response_json_with_receipt(
        response,
        provider=PROVIDER_ID,
        model=agent.model,
        capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    )
    receipt = core._receipt(
        provider=PROVIDER_ID,
        model=agent.model,
        response=response,
        provider_response_id=data.get("id"),
        resolved_model=data.get("model"),
        usage=data.get("usage"),
        capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    )
    try:
        core._check_provider_completion(
            data,
            provider=PROVIDER_ID,
            model=agent.model,
            response=response,
            receipt=receipt,
        )
        text = _completion_text(data)
    except core.ProviderCallError as exc:
        exc.model = agent.model
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt
