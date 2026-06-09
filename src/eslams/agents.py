"""Built-in agent adapters."""

from __future__ import annotations

import json
import os
import random
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.contracts.versions import PROVIDER_RECEIPT_SCHEMA_VERSION
from eslams.protocol import ActRequest, ActResponse, ProtocolError
from eslams.providers import ModelCapabilities, load_provider_registry
from eslams.providers.anthropic import MESSAGES_ENDPOINT
from eslams.providers.google import GENERATE_CONTENT_ENDPOINT
from eslams.providers.openai import RESPONSES_ENDPOINT


class AgentError(RuntimeError):
    pass


class ProviderCallError(AgentError):
    pass


_PROVIDER_CONTROL_LOCK = threading.Lock()
_PROVIDER_SEMAPHORES: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_PROVIDER_RATE_RESERVATIONS: dict[str, float] = {}


@dataclass
class FirstLegalAgent:
    id: str = "first-legal"
    version: str = "1.0.0"

    def act(self, request: ActRequest) -> ActResponse:
        if not request.legal_actions:
            raise AgentError("no legal actions")
        return ActResponse(
            action=request.legal_actions[0],
            confidence=1.0,
            public_explanation="Selected the first legal action.",
        )


@dataclass
class RandomAgent:
    id: str = "random"
    version: str = "1.0.0"
    seed: int = 0

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def act(self, request: ActRequest) -> ActResponse:
        if not request.legal_actions:
            raise AgentError("no legal actions")
        return ActResponse(
            action=self._rng.choice(request.legal_actions),
            confidence=0.5,
            public_explanation="Sampled uniformly from legal actions.",
        )


@dataclass
class FunctionAgent:
    callback: Callable[[ActRequest], Any]
    id: str = "function-agent"
    version: str = "1.0.0"

    def act(self, request: ActRequest) -> ActResponse:
        value = self.callback(request)
        if isinstance(value, ActResponse):
            return value
        if isinstance(value, dict):
            return ActResponse.from_mapping(value)
        return ActResponse(action=value)


@dataclass
class HttpAgent:
    url: str
    id: str = "http-agent"
    version: str = "1.0.0"
    bearer_token: str | None = None
    last_receipt: dict[str, Any] | None = field(default=None, init=False)
    attempt_receipts: list[dict[str, Any]] = field(default_factory=list, init=False)

    def act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        self.attempt_receipts = []
        headers = {"content-type": "application/json"}
        if self.bearer_token:
            headers["authorization"] = f"Bearer {self.bearer_token}"
        try:
            response = httpx.post(
                self.url,
                json=request.to_dict(),
                headers=headers,
                timeout=max(1.0, request.time_budget_ms / 1000),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("agent timed out") from exc
        except Exception as exc:
            raise AgentError(f"agent request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProtocolError("agent response must be a JSON object")
        act_response = ActResponse.from_mapping(payload)
        receipt = act_response.metadata.get("provider_receipt")
        if isinstance(receipt, dict):
            self.last_receipt = receipt
            self.attempt_receipts.append(receipt)
        return act_response


@dataclass
class ModelProviderAgent:
    """Model-backed eSlams agent using official provider HTTP APIs.

    The model receives only the public / agent-visible ActRequest fields and must
    return one legal action. API keys are read from environment variables and are
    never stored in artifacts.
    """

    provider: str
    model: str
    api_key_env: str
    id: str | None = None
    version: str = "1.0.0"
    temperature: float = 0.0
    max_output_tokens: int = 1024
    runtime_config: ProviderRuntimeConfig | None = None

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()
        if self.id is None:
            self.id = f"{self.provider}-{self.model}"
        if self.runtime_config is None:
            self.runtime_config = ProviderRuntimeConfig()
        self.last_receipt: dict[str, Any] | None = None
        self.attempt_receipts: list[dict[str, Any]] = []
        self.capabilities = load_provider_registry().resolve(self.provider, self.model)

    def act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        self.attempt_receipts = []
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=str(self.id),
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="unavailable",
                    usage_unavailable_reason="provider_not_called_missing_api_key",
                    runtime_config=self.runtime_config,
                )
            )
            raise ProviderCallError(f"missing API key environment variable {self.api_key_env}")
        prompt = _provider_prompt(request)
        parse_error: ProtocolError | None = None
        provider_attempt = 0
        for parse_attempt in range(2):
            if parse_attempt:
                prompt = _retry_prompt(prompt, request.legal_actions, parse_error)
            retry_index = 0
            while True:
                provider_attempt += 1
                try:
                    text, receipt = self._call_provider(api_key, prompt)
                except TimeoutError:
                    self._remember_receipt(
                        _failure_receipt(
                            provider=self.provider,
                            model=self.model,
                            agent_id=str(self.id),
                            agent_version=self.version,
                            turn_id=request.turn_id,
                            outcome="provider_timeout",
                            usage_unavailable_reason="provider_timeout",
                            runtime_config=self.runtime_config,
                            attempt=provider_attempt,
                        )
                    )
                    if retry_index < _max_retries(self.runtime_config):
                        retry_index += 1
                        _sleep_before_retry(self.runtime_config)
                        continue
                    raise
                except ProviderCallError:
                    self._remember_receipt(
                        _failure_receipt(
                            provider=self.provider,
                            model=self.model,
                            agent_id=str(self.id),
                            agent_version=self.version,
                            turn_id=request.turn_id,
                            outcome="provider_error",
                            usage_unavailable_reason="provider_error",
                            runtime_config=self.runtime_config,
                            attempt=provider_attempt,
                        )
                    )
                    if retry_index < _max_retries(self.runtime_config):
                        retry_index += 1
                        _sleep_before_retry(self.runtime_config)
                        continue
                    raise
                self._remember_receipt(
                    _attempt_receipt(
                        receipt,
                        agent_id=str(self.id),
                        agent_version=self.version,
                        turn_id=request.turn_id,
                        attempt=provider_attempt,
                    )
                )
                break
            try:
                action, confidence, explanation = _parse_model_action(text, request.legal_actions)
            except ProtocolError as exc:
                parse_error = exc
                receipt = self.last_receipt or {}
                self._replace_last_receipt(
                    {
                        **receipt,
                        "outcome": "parse_error",
                        "usage_unavailable_reason": receipt.get("usage_unavailable_reason"),
                        "parse_error": str(exc),
                    }
                )
                continue
            return ActResponse(
                action=action,
                confidence=confidence,
                public_explanation=explanation,
                metadata={
                    "provider": self.provider,
                    "model": self.model,
                    "raw_action_text": text[:500],
                    "provider_receipt": self.last_receipt,
                },
            )
        raise parse_error or ProtocolError("model response could not be parsed")

    def _remember_receipt(self, receipt: dict[str, Any]) -> None:
        self.last_receipt = receipt
        self.attempt_receipts.append(receipt)

    def _replace_last_receipt(self, receipt: dict[str, Any]) -> None:
        self.last_receipt = receipt
        if self.attempt_receipts:
            self.attempt_receipts[-1] = receipt
        else:
            self.attempt_receipts.append(receipt)

    def _call_provider(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        if self.provider == "openai":
            return self._call_openai(api_key, prompt)
        if self.provider == "anthropic":
            return self._call_anthropic(api_key, prompt)
        if self.provider == "gemini":
            return self._call_gemini(api_key, prompt)
        raise ProviderCallError(f"unsupported provider {self.provider!r}")

    def _call_openai(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": self.max_output_tokens,
        }
        reasoning = self.capabilities.reasoning_payload()
        if reasoning:
            payload["reasoning"] = reasoning
        response = _post_json(
            _provider_endpoint(RESPONSES_ENDPOINT, self.runtime_config),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            runtime_config=self.runtime_config,
            control_key=f"{self.provider}:{self.model}",
        )
        data = response.json()
        text = _openai_text(data)
        return text, _receipt(
            provider="openai",
            model=self.model,
            response=response,
            provider_id=data.get("id"),
            usage=data.get("usage"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )

    def _call_anthropic(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "system": _SYSTEM_INSTRUCTIONS,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.capabilities.supports_temperature:
            payload["temperature"] = self.temperature
        response = _post_json(
            _provider_endpoint(MESSAGES_ENDPOINT, self.runtime_config),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload=payload,
            runtime_config=self.runtime_config,
            control_key=f"{self.provider}:{self.model}",
        )
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return text, _receipt(
            provider="anthropic",
            model=self.model,
            response=response,
            provider_id=data.get("id"),
            usage=data.get("usage"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )

    def _call_gemini(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        generation_config: dict[str, Any] = {"maxOutputTokens": self.max_output_tokens}
        if self.capabilities.supports_temperature:
            generation_config["temperature"] = self.temperature
        if self.capabilities.supports_google_thinking_config:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{_SYSTEM_INSTRUCTIONS}\n\n{prompt}"}],
                }
            ],
            "generationConfig": generation_config,
        }
        response = _post_json(
            _provider_endpoint(
                GENERATE_CONTENT_ENDPOINT.format(model=self.model),
                self.runtime_config,
            ),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            payload=payload,
            runtime_config=self.runtime_config,
            control_key=f"{self.provider}:{self.model}",
        )
        data = response.json()
        text = "".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            if isinstance(candidate, dict)
            for part in candidate.get("content", {}).get("parts", [])
            if isinstance(part, dict)
        )
        return text, _receipt(
            provider="gemini",
            model=self.model,
            response=response,
            provider_id=data.get("responseId"),
            usage=data.get("usageMetadata"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )


@dataclass
class MockProviderAgent:
    """Local provider-runtime test double with normalized receipts."""

    scenario: str = "success"
    provider: str = "mock"
    model: str = "mock-legal-action"
    id: str = "mock-provider-agent"
    version: str = "1.0.0"
    runtime_config: ProviderRuntimeConfig | None = None

    def __post_init__(self) -> None:
        if self.runtime_config is None:
            self.runtime_config = ProviderRuntimeConfig(gateway_mode="disabled")
        self.last_receipt: dict[str, Any] | None = None
        self.attempt_receipts: list[dict[str, Any]] = []

    def act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        self.attempt_receipts = []
        if self.scenario == "timeout":
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=self.id,
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="provider_timeout",
                    usage_unavailable_reason="provider_timeout",
                    runtime_config=self.runtime_config,
                )
            )
            raise TimeoutError("mock provider timed out")
        if self.scenario == "provider_error":
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=self.id,
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="provider_error",
                    usage_unavailable_reason="provider_error",
                    runtime_config=self.runtime_config,
                )
            )
            raise ProviderCallError("mock provider error")
        if self.scenario == "gateway_auth_failed":
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=self.id,
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="gateway_auth_failed",
                    usage_unavailable_reason="gateway_auth_failed",
                    runtime_config=self.runtime_config,
                )
            )
            raise ProviderCallError("mock gateway auth failed")
        if self.scenario == "parse_error":
            self._remember_receipt(
                _mock_receipt(
                    request=request,
                    agent=self,
                    outcome="parse_error",
                    usage={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
                    runtime_config=self.runtime_config,
                )
            )
            raise ProtocolError("mock parse error")
        if not request.legal_actions:
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=self.id,
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="no_action",
                    usage_unavailable_reason="no_legal_actions",
                    runtime_config=self.runtime_config,
                )
            )
            raise AgentError("no legal actions")

        usage = (
            {}
            if self.scenario == "missing_usage"
            else {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}
        )
        self._remember_receipt(
            _mock_receipt(
                request=request,
                agent=self,
                outcome="ok",
                usage=usage,
                runtime_config=self.runtime_config,
            )
        )
        return ActResponse(
            action=request.legal_actions[0],
            confidence=1.0,
            public_explanation="Mock provider selected the first legal action.",
        )

    def _remember_receipt(self, receipt: dict[str, Any]) -> None:
        self.last_receipt = receipt
        self.attempt_receipts.append(receipt)


_SYSTEM_INSTRUCTIONS = (
    "You are an eSlams game-playing model wrapper. Choose exactly one action from "
    "the provided legal_actions list. Do not use tools, external engines, web, or "
    "hidden information. Return only JSON with keys action, confidence, and "
    "public_explanation."
)


def _provider_prompt(request: ActRequest) -> str:
    payload = {
        "arena": request.arena.to_dict(),
        "active_player": request.active_player,
        "observation": request.observation,
        "legal_actions": request.legal_actions,
        "action_schema": request.action_schema,
        "history": request.history[-12:],
        "memory_policy": request.memory_policy,
    }
    return (
        "Select a legal action for this eSlams /act request.\n"
        f"The only legal_actions are: {json.dumps(request.legal_actions, ensure_ascii=False)}.\n"
        "Return JSON only, for example: "
        '{"action": 0, "confidence": 0.72, "public_explanation": "Blocks an immediate threat."}\n'
        f"{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
    )


def _retry_prompt(prompt: str, legal_actions: list[Any], parse_error: ProtocolError | None) -> str:
    return (
        f"{prompt}\n\nYour previous answer was invalid: {parse_error}.\n"
        f"Return exactly one JSON object. The action must equal one of these values: "
        f"{json.dumps(legal_actions, ensure_ascii=False)}. No markdown. No prose."
    )


def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    runtime_config: ProviderRuntimeConfig | None,
    control_key: str,
) -> httpx.Response:
    with _provider_runtime_guard(runtime_config, control_key):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=_httpx_timeout(runtime_config),
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("provider timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderCallError(f"provider request failed: {exc}") from exc
    if response.status_code >= 400:
        body = response.text[:500].replace("\n", " ")
        raise ProviderCallError(f"provider returned {response.status_code}: {body}")
    return response


@contextmanager
def _provider_runtime_guard(
    runtime_config: ProviderRuntimeConfig | None,
    control_key: str,
) -> Iterator[None]:
    _reserve_rate_slot(runtime_config, control_key)
    semaphore = _provider_semaphore(runtime_config, control_key)
    semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


def _provider_semaphore(
    runtime_config: ProviderRuntimeConfig | None,
    control_key: str,
) -> threading.BoundedSemaphore:
    limit = max(1, runtime_config.concurrency_limit if runtime_config else 1)
    key = (control_key, limit)
    with _PROVIDER_CONTROL_LOCK:
        semaphore = _PROVIDER_SEMAPHORES.get(key)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(limit)
            _PROVIDER_SEMAPHORES[key] = semaphore
        return semaphore


def _reserve_rate_slot(
    runtime_config: ProviderRuntimeConfig | None,
    control_key: str,
) -> None:
    rate_limit = runtime_config.rate_limit_per_minute if runtime_config else None
    if rate_limit is None or rate_limit <= 0:
        return
    interval_seconds = 60.0 / rate_limit
    with _PROVIDER_CONTROL_LOCK:
        now = time.monotonic()
        reserved_at = max(now, _PROVIDER_RATE_RESERVATIONS.get(control_key, 0.0))
        _PROVIDER_RATE_RESERVATIONS[control_key] = reserved_at + interval_seconds
    delay = reserved_at - now
    if delay > 0:
        time.sleep(delay)


def _httpx_timeout(runtime_config: ProviderRuntimeConfig | None) -> httpx.Timeout:
    if runtime_config is None:
        return httpx.Timeout(timeout=60.0)
    total = max(1.0, runtime_config.timeout_ms / 1000)
    connect = max(0.001, runtime_config.connect_timeout_ms / 1000)
    read = max(0.001, runtime_config.read_timeout_ms / 1000)
    return httpx.Timeout(timeout=total, connect=connect, read=read, write=read, pool=connect)


def _max_retries(runtime_config: ProviderRuntimeConfig | None) -> int:
    if runtime_config is None:
        return 0
    return max(0, runtime_config.max_retries)


def _sleep_before_retry(runtime_config: ProviderRuntimeConfig | None) -> None:
    if runtime_config is None or runtime_config.retry_backoff_ms <= 0:
        return
    time.sleep(runtime_config.retry_backoff_ms / 1000)


def _receipt(
    *,
    provider: str,
    model: str,
    response: httpx.Response,
    provider_id: Any,
    usage: Any,
    capabilities: ModelCapabilities,
    runtime_config: ProviderRuntimeConfig | None,
) -> dict[str, Any]:
    normalized_usage = _normalize_usage(provider, usage)
    has_usage = any(value is not None for value in normalized_usage.values())
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "locked_model_id": provider_id if isinstance(provider_id, str) else None,
        "outcome": "ok",
        "model_capability_known": capabilities.known,
        "game_agent_supported": capabilities.game_agent_supported,
        "capability_sources": list(capabilities.sources),
        "provider_response_id": provider_id,
        "status_code": response.status_code,
        "request_id": response.headers.get("x-request-id")
        or response.headers.get("request-id")
        or response.headers.get("x-cloud-trace-context"),
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": response.headers.get("cf-aig-request-id")
        or response.headers.get("x-gateway-request-id"),
        "usage": normalized_usage if has_usage else {},
        "usage_unavailable_reason": None if has_usage else "provider_usage_absent",
        "pricing": {
            "status": "cost_unavailable",
            "pricing_table_version": None,
            "currency": "USD",
            "billable_token_categories": [],
            "source": "not_configured",
            "unavailable_reason": "pricing_not_configured",
        },
        "estimated_cost": {
            "status": "cost_unavailable",
            "unavailable_reason": "pricing_not_configured",
        },
        "redaction_version": "provider-receipt-redaction-v1",
    }


def _attempt_receipt(
    receipt: dict[str, Any],
    *,
    agent_id: str,
    agent_version: str,
    turn_id: int,
    attempt: int,
) -> dict[str, Any]:
    return {
        **receipt,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "turn_id": turn_id,
        "attempt": attempt,
    }


def _failure_receipt(
    *,
    provider: str,
    model: str,
    agent_id: str,
    agent_version: str,
    turn_id: int,
    outcome: str,
    usage_unavailable_reason: str,
    runtime_config: ProviderRuntimeConfig | None,
    attempt: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "locked_model_id": None,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "turn_id": turn_id,
        "attempt": attempt,
        "outcome": outcome,
        "status_code": None,
        "request_id": None,
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": None,
        "usage": {},
        "usage_unavailable_reason": usage_unavailable_reason,
        "pricing": {
            "status": "cost_unavailable",
            "source": "not_configured",
            "unavailable_reason": "pricing_not_configured",
        },
        "estimated_cost": {
            "status": "cost_unavailable",
            "unavailable_reason": "pricing_not_configured",
        },
        "redaction_version": "provider-receipt-redaction-v1",
    }


def _mock_receipt(
    *,
    request: ActRequest,
    agent: MockProviderAgent,
    outcome: str,
    usage: dict[str, int],
    runtime_config: ProviderRuntimeConfig | None,
) -> dict[str, Any]:
    normalized_usage = _normalize_usage(agent.provider, usage)
    has_usage = any(value is not None for value in normalized_usage.values())
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": agent.provider,
        "model": agent.model,
        "locked_model_id": agent.model,
        "agent_id": agent.id,
        "agent_version": agent.version,
        "turn_id": request.turn_id,
        "attempt": 1,
        "outcome": outcome,
        "status_code": 200 if outcome in {"ok", "parse_error"} else None,
        "request_id": "mock-request",
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": None,
        "usage": normalized_usage if has_usage else {},
        "usage_unavailable_reason": None if has_usage else "provider_usage_absent",
        "pricing": {
            "status": "cost_unavailable",
            "source": "mock",
            "unavailable_reason": "pricing_not_configured",
        },
        "estimated_cost": {
            "status": "cost_unavailable",
            "unavailable_reason": "pricing_not_configured",
        },
        "redaction_version": "provider-receipt-redaction-v1",
    }


def _provider_endpoint(
    default_url: str,
    runtime_config: ProviderRuntimeConfig | None,
) -> str:
    if runtime_config is None or not runtime_config.gateway_base_url:
        return default_url
    parsed = urlparse(default_url)
    path = parsed.path.lstrip("/")
    return f"{runtime_config.gateway_base_url.rstrip('/')}/{path}"


def _normalize_usage(provider: str, usage: Any) -> dict[str, int | None]:
    if not isinstance(usage, dict):
        return _empty_usage()
    if provider == "gemini":
        input_tokens = _optional_int(usage.get("promptTokenCount"))
        output_tokens = _optional_int(usage.get("candidatesTokenCount"))
        total_tokens = _optional_int(usage.get("totalTokenCount"))
    else:
        input_tokens = _optional_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
        output_tokens = _optional_int(
            usage.get("output_tokens") or usage.get("completion_tokens")
        )
        total_tokens = _optional_int(usage.get("total_tokens"))
    cached_input_tokens = _optional_int(usage.get("cached_input_tokens"))
    reasoning_tokens = _optional_int(usage.get("reasoning_tokens"))
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
    }


def _empty_usage() -> dict[str, int | None]:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _openai_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    chunks: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks)


def _parse_model_action(
    text: str,
    legal_actions: list[Any],
) -> tuple[Any, float | None, str | None]:
    payload = _extract_json(text)
    if not isinstance(payload, dict) or "action" not in payload:
        action = _find_legal_action(text, legal_actions)
        return action, None, "Selected a legal action from the model response."
    action = _coerce_action(payload["action"], legal_actions)
    confidence = payload.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_value: float | None = max(0.0, min(1.0, float(confidence)))
    else:
        confidence_value = None
    explanation = payload.get("public_explanation")
    return action, confidence_value, explanation if isinstance(explanation, str) else None


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            with_json = stripped[start : end + 1]
            try:
                return json.loads(with_json)
            except json.JSONDecodeError:
                return None
    return None


def _coerce_action(value: Any, legal_actions: list[Any]) -> Any:
    for action in legal_actions:
        if value == action or str(value) == str(action):
            return action
    raise ProtocolError(f"model returned illegal action {value!r}")


def _find_legal_action(text: str, legal_actions: list[Any]) -> Any:
    for action in legal_actions:
        if str(action) in text:
            return action
    raise ProtocolError("model response did not contain a legal action")


def create_builtin_agent(name: str, *, seed: int = 0) -> FirstLegalAgent | RandomAgent:
    if name == "first-legal":
        return FirstLegalAgent()
    if name == "random":
        return RandomAgent(seed=seed)
    raise KeyError(f"unknown built-in agent {name!r}")
