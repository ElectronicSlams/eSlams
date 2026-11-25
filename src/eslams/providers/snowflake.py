"""Snowflake Cortex Chat Completions wire contract (no SDK or SQL execution)."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent

PROVIDER_ID = "snowflake"
API_KEY_ENV = "SNOWFLAKE_TOKEN"
ACCOUNT_URL_ENV = "SNOWFLAKE_ACCOUNT_URL"
TOKEN_TYPE_ENV = "SNOWFLAKE_TOKEN_TYPE"
ALIASES = {"snowflake", "snowflake-cortex", "cortex"}
CHAT_PATH = "/api/v2/cortex/v1/chat/completions"


def canonical_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    return PROVIDER_ID if normalized in ALIASES else provider.lower()


def connection_settings() -> tuple[str, dict[str, str]]:
    """Validate an explicit account origin without leaking its value on failure.

    Region/cloud/PrivateLink selection belongs to the supplied account URL and
    Snowflake account policy. Never infer an account or change routing policy.
    """
    origin = os.getenv(ACCOUNT_URL_ENV, "").strip()
    message = (
        "SNOWFLAKE_ACCOUNT_URL must be an HTTPS Snowflake account origin "
        "without credentials, port, query, fragment, or API path"
    )
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https" or parsed.netloc != host
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or not host.endswith(".snowflakecomputing.com")
            or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part)
                       for part in host.split("."))
            or any(character.isspace() for character in origin)
            or "?" in origin or "#" in origin
        ):
            raise ValueError(message)
    except ValueError:
        raise ValueError(message) from None
    token_type = os.getenv(TOKEN_TYPE_ENV, "").strip()
    if token_type not in {"", "OAUTH", "KEYPAIR_JWT", "PROGRAMMATIC_ACCESS_TOKEN"}:
        raise ValueError(
            "SNOWFLAKE_TOKEN_TYPE must be OAUTH, KEYPAIR_JWT, "
            "PROGRAMMATIC_ACCESS_TOKEN, or unset for Snowflake token detection"
        )
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token_type:
        headers["X-Snowflake-Authorization-Token-Type"] = token_type
    return f"https://{host}{CHAT_PATH}", headers


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at call time to reuse Core's transport/receipts without a cycle or
    # placing the provider's request/parser implementation in shared dispatch.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    try:
        endpoint, headers = connection_settings()
        payload = request_payload(agent, prompt, _SYSTEM_INSTRUCTIONS)
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_request_rejected", provider=PROVIDER_ID,
            model=agent.model,
        ) from None
    headers["Authorization"] = f"Bearer {api_key}"
    response = _post_json(
        _provider_endpoint(endpoint, agent.runtime_config), headers=headers, payload=payload,
        runtime_config=agent.runtime_config, control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model, capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities,
        runtime_config=agent.runtime_config,
    )
    if agent.model.startswith("claude-") and receipt["usage"]:
        # Snowflake's cached_tokens combines cache reads and writes for Claude;
        # the aggregate is known but neither individual category is attested.
        receipt["usage"]["cache_read_input_tokens"] = None
        receipt["usage"]["cache_write_input_tokens"] = None
    try:
        # Session tokens are unsupported; still reject their documented HTTP-200
        # expiration envelope rather than accepting any attached action text.
        if str(data.get("code")) == "390112":
            raise ProviderCallError(
                "Snowflake session token expired; supply a PAT, OAuth token, or key-pair JWT",
                error_kind="provider_auth_failed", provider=PROVIDER_ID, model=agent.model,
            )
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        text = response_text(data)
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise
    return text, receipt


def request_payload(
    agent: ModelProviderAgent, prompt: str, instructions: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if agent._effective_max_output_tokens() is not None:
        payload["max_completion_tokens"] = agent._effective_max_output_tokens()
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    runtime = agent.runtime_config
    if runtime is None:
        return payload
    effort, budget = runtime.reasoning_effort, runtime.reasoning_budget_tokens
    if runtime.gemini_thinking_budget is not None:
        raise ValueError("Snowflake does not support gemini_thinking_budget")
    if runtime.reasoning == "enabled" and effort is None and budget is None:
        raise ValueError("Snowflake reasoning=enabled requires an explicit effort or budget")
    if runtime.reasoning == "disabled":
        if not agent.model.startswith("openai-"):
            raise ValueError("Snowflake only documents reasoning_effort=none for OpenAI models")
        effort = "none"
    if agent.model.startswith("openai-"):
        if budget is not None:
            raise ValueError("Snowflake OpenAI models do not support a reasoning token budget")
        if effort is not None:
            payload["reasoning_effort"] = effort
    elif agent.model.startswith("claude-"):
        if effort is not None and budget is not None:
            raise ValueError("Choose either Snowflake Claude reasoning effort or token budget")
        if effort is not None:
            payload["reasoning"] = {"effort": effort}
        elif budget is not None:
            payload["reasoning"] = {"max_tokens": budget}
    elif effort is not None or budget is not None:
        raise ValueError("Snowflake documents reasoning controls only for OpenAI and Claude models")
    return payload


def response_text(data: dict[str, Any]) -> str:
    from eslams.agents import ProviderCallError

    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
        choice = choices[0]
        message = choice.get("message")
        # Some Snowflake model families omit finish_reason. Absence cannot
        # establish complete output; never accept legal-looking partial text.
        if (
            choice.get("finish_reason") == "stop" and isinstance(message, dict)
            and message.get("role") == "assistant"
            and not message.get("tool_calls") and not message.get("function_call")
            and isinstance(message.get("content"), str) and message["content"].strip()
        ):
            return str(message["content"])
    raise ProviderCallError(
        "Snowflake response requires one completed assistant text choice with finish_reason=stop",
        error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
    )
