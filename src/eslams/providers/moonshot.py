"""Direct Kimi Chat Completions adapter (official REST, no SDK or routing fallback)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from eslams.agents import ModelProviderAgent
    from eslams.contracts.provider import ProviderRuntimeConfig

PROVIDER_ID = "moonshot-ai"
API_KEY_ENV = "MOONSHOT_API_KEY"
DEFAULT_MODEL = "kimi-k3.1-pro"
CHAT_COMPLETIONS_ENDPOINT = "https://api.moonshot.ai/v1/chat/completions"
MODELS_ENDPOINT = "https://api.moonshot.ai/v1/models"
CHINA_CHAT_COMPLETIONS_ENDPOINT = "https://api.moonshot.cn/v1/chat/completions"
CHINA_MODELS_ENDPOINT = "https://api.moonshot.cn/v1/models"
ALIASES = frozenset({PROVIDER_ID, "moonshot", "moonshotai", "moonshotai-cn", "kimi"})


def canonical_provider(provider: str) -> str:
    """Normalize only this adapter's aliases; leave other providers alone."""
    candidate = provider.strip().lower().replace("_", "-")
    return PROVIDER_ID if candidate in ALIASES else provider.lower()


def chat_endpoint(provider: str) -> str:
    return (CHINA_CHAT_COMPLETIONS_ENDPOINT
            if provider.strip().lower().replace("_", "-") == "moonshotai-cn"
            else CHAT_COMPLETIONS_ENDPOINT)


def models_endpoint(provider: str) -> str:
    return (CHINA_MODELS_ENDPOINT
            if provider.strip().lower().replace("_", "-") == "moonshotai-cn"
            else MODELS_ENDPOINT)


def request_controls(model: str, runtime: ProviderRuntimeConfig | None) -> dict[str, Any]:
    from eslams.agents import ProviderCallError

    if runtime is None:
        return {}

    def reject() -> None:
        raise ProviderCallError(
            "unsupported Moonshot reasoning control for the selected model; no request submitted",
            error_kind="provider_request_rejected", provider=PROVIDER_ID, model=model,
        )

    if runtime.reasoning_budget_tokens is not None or runtime.gemini_thinking_budget is not None:
        reject()
    k3 = model in {"kimi-k3", "kimi-k3.1-pro", "kimi-k3.1-pro-highspeed"}
    k27 = model in {"kimi-k2.7-code", "kimi-k2.7-code-highspeed"}
    k26 = model == "kimi-k2.6"
    controls: dict[str, Any] = {}
    if runtime.reasoning_effort is not None:
        if not k3 or runtime.reasoning_effort not in {"low", "high", "max"}:
            reject()
        controls["reasoning_effort"] = runtime.reasoning_effort
    if runtime.reasoning == "disabled":
        if not k26:
            reject()
        controls["thinking"] = {"type": "disabled"}
    elif runtime.reasoning == "enabled":
        if k26:
            controls["thinking"] = {"type": "enabled", "keep": "all"}
        elif not (k3 or k27):
            reject()
    # Auto leaves native model defaults intact, including K3's default effort.
    return controls


def usage_for_receipt(usage: Any) -> Any:
    """Translate documented Kimi fields only; never harvest arbitrary extensions."""
    if not isinstance(usage, dict):
        return usage
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    output_details = usage.get("completion_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "prompt_tokens_details": {
            "cached_tokens": details.get("cached_tokens", usage.get("cached_tokens")),
            "cache_creation_input_tokens": details.get("cache_write_tokens"),
        },
        "completion_tokens_details": {"reasoning_tokens": output_details.get("reasoning_tokens")},
        # Missing reasoning counts remain unknown, never inferred from prose.
        "reasoning_included_in_output": True,
    }


def call(agent: ModelProviderAgent, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
    # Import at call time so the shared agent owns transport/receipt custody
    # without introducing an import cycle or a second transport implementation.
    from eslams.agents import (
        _SYSTEM_INSTRUCTIONS,
        ProviderCallError,
        _check_provider_completion,
        _post_json,
        _provider_endpoint,
        _receipt,
        _response_json_with_receipt,
    )

    runtime = agent.runtime_config
    payload: dict[str, Any] = {
        "model": agent.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": agent._effective_max_output_tokens(),
        **request_controls(agent.model, runtime),
    }
    if agent.temperature is not None:
        payload["temperature"] = agent.temperature
    response = _post_json(
        _provider_endpoint(agent._moonshot_endpoint, runtime),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload, runtime_config=runtime,
        control_key=f"{PROVIDER_ID}:{agent.model}",
    )
    data = _response_json_with_receipt(
        response, provider=PROVIDER_ID, model=agent.model,
        capabilities=agent.capabilities, runtime_config=runtime,
    )
    receipt = _receipt(
        provider=PROVIDER_ID, model=agent.model, response=response,
        provider_response_id=data.get("id"), resolved_model=data.get("model"),
        usage=data.get("usage"), capabilities=agent.capabilities, runtime_config=runtime,
    )
    try:
        error = data.get("error")
        if isinstance(error, dict) and error.get("type") == "content_filter":
            receipt.update(finish_reason="content_filter", finish_status="refused")
            raise ProviderCallError(
                "Moonshot refused or filtered the request", error_kind="provider_refused",
                provider=PROVIDER_ID, model=agent.model,
            )
        _check_provider_completion(
            data, provider=PROVIDER_ID, model=agent.model, response=response, receipt=receipt,
        )
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
        message = first.get("message") if isinstance(first, dict) else None
        if (data.get("object") != "chat.completion" or not isinstance(first, dict)
                or not isinstance(message, dict)
                or message.get("role") != "assistant" or first.get("finish_reason") != "stop"
                or message.get("tool_calls") or not isinstance(message.get("content"), str)
                or not message["content"].strip()):
            raise ProviderCallError(
                "Moonshot response must contain one completed assistant text choice",
                error_kind="provider_response_schema_mismatch", provider=PROVIDER_ID,
                model=agent.model,
            )
        return message["content"], receipt
    except ProviderCallError as exc:
        exc.receipt = {**receipt, "outcome": exc.error_kind}
        raise


def http_error_kind(response: httpx.Response, default: str) -> str:
    """Only a documented safety rejection changes the HTTP classification."""
    from eslams.agents import _strict_provider_json

    if response.status_code != 400:
        return default
    try:
        data = _strict_provider_json(response)
    except (ValueError, UnicodeError, RecursionError):
        return default
    error = data.get("error") if isinstance(data, dict) else None
    return ("provider_refused" if isinstance(error, dict)
            and error.get("type") == "content_filter" else default)
