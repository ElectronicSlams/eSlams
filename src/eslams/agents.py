"""Built-in agent adapters."""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import unquote_plus, urlparse, urlsplit

import httpx

from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.contracts.versions import PROVIDER_RECEIPT_SCHEMA_VERSION
from eslams.hashing import sha256_json
from eslams.model_actions import (
    coerce_action,
    extract_json,
    find_legal_action,
    invalid_action_retry_prompt,
    parse_model_action,
)
from eslams.protocol import ActRequest, ActResponse, ProtocolError
from eslams.providers import ModelCapabilities, load_provider_registry
from eslams.providers.anthropic import MESSAGES_ENDPOINT
from eslams.providers.bedrock import converse_endpoint
from eslams.providers.google import GENERATE_CONTENT_ENDPOINT
from eslams.providers.openai import RESPONSES_ENDPOINT
from eslams.providers.openrouter import CHAT_COMPLETIONS_ENDPOINT


class AgentError(RuntimeError):
    pass


class ProviderCallError(AgentError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_kind: str = "provider_unavailable",
        retry_after_seconds: float | None = None,
        provider: str | None = None,
        model: str | None = None,
        receipt: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_kind = error_kind
        self.retry_after_seconds = retry_after_seconds
        self.provider = provider
        self.model = model
        self.receipt = dict(receipt) if receipt is not None else None
        super().__init__(_redact_sensitive_text(message))


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
    provider: str | None = None
    model: str | None = None
    endpoint_metadata: dict[str, Any] = field(default_factory=dict)
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
        raw_attempts = act_response.metadata.get("attempt_receipts")
        candidates = (
            [item for item in raw_attempts if isinstance(item, dict)]
            if isinstance(raw_attempts, list)
            else ([receipt] if isinstance(receipt, dict) else [])
        )
        for attempt_index, candidate in enumerate(candidates, start=1):
            normalized_receipt = _http_provider_receipt(
                candidate,
                provider=self.provider,
                model=self.model,
                endpoint_metadata=self.endpoint_metadata,
            )
            normalized_receipt.setdefault("attempt", attempt_index)
            normalized_receipt.setdefault("attempt_index", attempt_index)
            normalized_receipt.setdefault("attempt_kind", "primary")
            self.last_receipt = normalized_receipt
            self.attempt_receipts.append(normalized_receipt)
        if self.last_receipt is not None:
            act_response.metadata["provider_receipt"] = self.last_receipt
            act_response.metadata["attempt_receipts"] = [
                dict(item) for item in self.attempt_receipts
            ]
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
        self._reasoning_enabled = False
        self.capabilities = load_provider_registry().resolve(self.provider, self.model)

    def act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        self.attempt_receipts = []
        self._reasoning_enabled = _reasoning_enabled_for_request(
            self.runtime_config,
            self.capabilities,
            request,
        )
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=str(self.id),
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="provider_auth_failed",
                    usage_unavailable_reason="provider_not_called_missing_api_key",
                    runtime_config=self.runtime_config,
                )
            )
            raise ProviderCallError(
                f"missing API key environment variable {self.api_key_env}",
                error_kind="provider_auth_failed",
                provider=self.provider,
                model=self.model,
            )
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
                            attempt_kind=("action_repair" if parse_attempt else "primary"),
                        )
                    )
                    if retry_index < _max_retries(self.runtime_config):
                        retry_index += 1
                        _sleep_before_retry(self.runtime_config)
                        continue
                    raise
                except ProviderCallError as exc:
                    failure_receipt = (
                        {
                            **exc.receipt,
                            "outcome": exc.error_kind,
                            "usage_unavailable_reason": (
                                exc.receipt.get("usage_unavailable_reason")
                                if exc.receipt.get("usage")
                                else exc.error_kind
                            ),
                        }
                        if exc.receipt is not None
                        else _failure_receipt(
                            provider=self.provider,
                            model=self.model,
                            agent_id=str(self.id),
                            agent_version=self.version,
                            turn_id=request.turn_id,
                            outcome=exc.error_kind,
                            usage_unavailable_reason=exc.error_kind,
                            runtime_config=self.runtime_config,
                            attempt=provider_attempt,
                            status_code=exc.status_code,
                            retry_after_seconds=exc.retry_after_seconds,
                            attempt_kind=("action_repair" if parse_attempt else "primary"),
                        )
                    )
                    self._remember_receipt(
                        _attempt_receipt(
                            failure_receipt,
                            agent_id=str(self.id),
                            agent_version=self.version,
                            turn_id=request.turn_id,
                            attempt=provider_attempt,
                            attempt_kind=("action_repair" if parse_attempt else "primary"),
                        )
                    )
                    if retry_index < _max_retries(
                        self.runtime_config
                    ) and _provider_error_is_retryable(exc):
                        retry_index += 1
                        _sleep_before_retry(
                            self.runtime_config,
                            retry_after_seconds=exc.retry_after_seconds,
                        )
                        continue
                    raise
                self._remember_receipt(
                    _attempt_receipt(
                        receipt,
                        agent_id=str(self.id),
                        agent_version=self.version,
                        turn_id=request.turn_id,
                        attempt=provider_attempt,
                        attempt_kind="action_repair" if parse_attempt else "primary",
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
                        "outcome": "action_response_unparseable",
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
                    "attempt_receipts": [dict(item) for item in self.attempt_receipts],
                },
            )
        raise ProviderCallError(
            str(parse_error or "model response could not be parsed"),
            error_kind="action_response_unparseable",
            provider=self.provider,
            model=self.model,
        )

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
        if self.provider in {"gemini", "google"}:
            return self._call_gemini(api_key, prompt)
        if self.provider == "openrouter":
            return self._call_openrouter(api_key, prompt)
        if self.provider == "bedrock":
            return self._call_bedrock(api_key, prompt)
        raise ProviderCallError(
            f"unsupported provider {self.provider!r}",
            error_kind="provider_unavailable",
            provider=self.provider,
            model=self.model,
        )

    def _call_openai(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": self._effective_max_output_tokens(),
        }
        reasoning = self.capabilities.reasoning_payload() if self._reasoning_enabled else None
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
        data = _response_json_with_receipt(
            response,
            provider="openai",
            model=self.model,
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        receipt = _receipt(
            provider="openai",
            model=self.model,
            response=response,
            provider_response_id=data.get("id"),
            resolved_model=data.get("model"),
            usage=data.get("usage"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        try:
            text = _openai_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_anthropic(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        max_output_tokens = self._effective_max_output_tokens()
        payload = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "system": _SYSTEM_INSTRUCTIONS,
            "messages": [{"role": "user", "content": prompt}],
        }
        reasoning_enabled = self._reasoning_enabled
        thinking_mode = self.capabilities.anthropic_reasoning_mode()
        if reasoning_enabled:
            if thinking_mode == "manual":
                # Anthropic's manual extended-thinking contract fixes temperature at 1
                # and requires budget_tokens < max_tokens:
                # https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
                payload["temperature"] = 1.0
                payload["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": self._reasoning_budget_tokens(max_tokens=max_output_tokens),
                }
            elif thinking_mode == "adaptive":
                # Adaptive thinking owns its budget and rejects manual temperature controls:
                # https://docs.anthropic.com/en/docs/build-with-claude/adaptive-thinking
                payload["thinking"] = {"type": "adaptive"}
            # ``default`` deliberately sends neither thinking nor temperature;
            # the provider owns the current model's default reasoning policy.
        elif self.capabilities.supports_temperature and thinking_mode != "adaptive":
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
        data = _response_json_with_receipt(
            response,
            provider="anthropic",
            model=self.model,
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        receipt = _receipt(
            provider="anthropic",
            model=self.model,
            response=response,
            provider_response_id=data.get("id"),
            resolved_model=data.get("model"),
            usage=data.get("usage"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        try:
            text = _anthropic_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_gemini(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        generation_config: dict[str, Any] = {"maxOutputTokens": self._effective_max_output_tokens()}
        if self.capabilities.supports_temperature:
            generation_config["temperature"] = self.temperature
        if self._reasoning_enabled and self.capabilities.supports_google_thinking_config:
            thinking_budget = self._gemini_thinking_budget()
            if thinking_budget is not None:
                generation_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}
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
        data = _response_json_with_receipt(
            response,
            provider=self.provider,
            model=self.model,
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        receipt = _receipt(
            provider=self.provider,
            model=self.model,
            response=response,
            provider_response_id=data.get("responseId"),
            resolved_model=data.get("modelVersion"),
            usage=data.get("usageMetadata"),
            capabilities=self.capabilities,
            runtime_config=self.runtime_config,
        )
        try:
            text = _gemini_text(data, provider=self.provider)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_openrouter(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._effective_max_output_tokens(),
        }
        if self.capabilities.supports_temperature:
            payload["temperature"] = self.temperature
        runtime = self.runtime_config
        if runtime and runtime.openrouter_provider_order:
            payload["provider"] = {
                "order": list(runtime.openrouter_provider_order),
                "allow_fallbacks": runtime.openrouter_allow_fallbacks,
            }
        response = _post_json(
            _provider_endpoint(CHAT_COMPLETIONS_ENDPOINT, runtime),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            runtime_config=runtime,
            control_key=f"{self.provider}:{self.model}",
        )
        data = _response_json_with_receipt(
            response,
            provider="openrouter",
            model=self.model,
            capabilities=self.capabilities,
            runtime_config=runtime,
        )
        usage = data.get("usage")
        native_cost = usage.get("cost") if isinstance(usage, dict) else None
        receipt = _receipt(
            provider="openrouter",
            model=self.model,
            response=response,
            provider_response_id=data.get("id"),
            resolved_model=data.get("model"),
            usage=usage,
            capabilities=self.capabilities,
            runtime_config=runtime,
            native_cost=native_cost,
        )
        try:
            text = _openrouter_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_bedrock(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        runtime = self.runtime_config or ProviderRuntimeConfig()
        inference_config: dict[str, Any] = {
            "maxTokens": self._effective_max_output_tokens(),
        }
        if self.capabilities.supports_temperature:
            inference_config["temperature"] = self.temperature
        payload = {
            "system": [{"text": _SYSTEM_INSTRUCTIONS}],
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": inference_config,
        }
        response = _post_json(
            _provider_endpoint(
                converse_endpoint(self.model, runtime.bedrock_region),
                runtime,
            ),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            runtime_config=runtime,
            control_key=f"{self.provider}:{self.model}",
        )
        data = _response_json_with_receipt(
            response,
            provider="bedrock",
            model=self.model,
            capabilities=self.capabilities,
            runtime_config=runtime,
        )
        receipt = _receipt(
            provider="bedrock",
            model=self.model,
            response=response,
            provider_response_id=response.headers.get("x-amzn-requestid"),
            resolved_model=(self.model if runtime.gateway_base_url is None else None),
            model_identity_source=("pinned_endpoint" if runtime.gateway_base_url is None else None),
            usage=data.get("usage"),
            capabilities=self.capabilities,
            runtime_config=runtime,
        )
        try:
            text = _bedrock_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _effective_max_output_tokens(self) -> int:
        if not self._reasoning_enabled or self.max_output_tokens > 1024:
            return self.max_output_tokens
        capability_limit = self.capabilities.max_output_tokens or 4096
        return max(self.max_output_tokens, min(capability_limit, 4096))

    def _reasoning_budget_tokens(self, *, max_tokens: int) -> int:
        configured = self.runtime_config.reasoning_budget_tokens if self.runtime_config else None
        budget = configured if configured is not None else 1024
        if budget < 1024:
            raise ProviderCallError(
                "Anthropic manual thinking budget must be at least 1024 tokens",
                error_kind="provider_request_rejected",
                provider=self.provider,
                model=self.model,
            )
        if budget >= max_tokens:
            raise ProviderCallError(
                "Anthropic max_tokens must be greater than the manual thinking budget",
                error_kind="provider_request_rejected",
                provider=self.provider,
                model=self.model,
            )
        return budget

    def _gemini_thinking_budget(self) -> int | None:
        if self.runtime_config is None:
            return None
        return self.runtime_config.gemini_thinking_budget


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
                    outcome="provider_unavailable",
                    usage_unavailable_reason="provider_unavailable",
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
                    outcome="action_response_unparseable",
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

# Auto mode avoids paid extended thinking for arenas whose public state and
# legal-action sets are intentionally small.  Callers can force it with
# ``reasoning="enabled"`` or disable it for every arena.
_SIMPLE_REASONING_OPTIONAL_ARENAS = frozenset({"tic-tac-toe", "connect-four"})


def _reasoning_enabled_for_request(
    runtime_config: ProviderRuntimeConfig | None,
    capabilities: ModelCapabilities,
    request: ActRequest,
) -> bool:
    if not capabilities.supports_reasoning:
        return False
    mode = runtime_config.reasoning if runtime_config is not None else "auto"
    if mode == "disabled":
        return False
    if mode == "enabled":
        return True
    return request.arena.id not in _SIMPLE_REASONING_OPTIONAL_ARENAS


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
    return invalid_action_retry_prompt(prompt, legal_actions, parse_error)


def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    runtime_config: ProviderRuntimeConfig | None,
    control_key: str,
) -> httpx.Response:
    provider, _, model = control_key.partition(":")
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
            raise ProviderCallError(
                f"provider request failed: {exc}",
                error_kind="provider_transport_error",
                provider=provider,
                model=model,
            ) from exc
    if response.status_code >= 400:
        body = response.text[:500].replace("\n", " ")
        raise ProviderCallError(
            f"provider returned {response.status_code}: {body}",
            status_code=response.status_code,
            error_kind=_provider_error_kind(response.status_code),
            retry_after_seconds=_retry_after_seconds(response),
            provider=provider,
            model=model,
        )
    return response


def _provider_error_kind(status_code: int | None) -> str:
    if status_code == 401:
        return "provider_auth_failed"
    if status_code == 403:
        return "provider_permission_failed"
    if status_code == 429:
        return "provider_rate_limited"
    if status_code == 404 or (status_code is not None and status_code >= 500):
        return "provider_unavailable"
    if status_code is not None and 400 <= status_code < 500:
        return "provider_request_rejected"
    return "provider_transport_error"


def _provider_error_is_retryable(exc: ProviderCallError) -> bool:
    if exc.status_code == 429:
        return True
    if exc.status_code is not None:
        return exc.status_code >= 500
    return exc.error_kind in {"provider_transport_error", "provider_unavailable"}


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed: datetime = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return float(max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds()))


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


def _sleep_before_retry(
    runtime_config: ProviderRuntimeConfig | None,
    *,
    retry_after_seconds: float | None = None,
) -> None:
    if retry_after_seconds is not None:
        time.sleep(retry_after_seconds)
        return
    if runtime_config is None or runtime_config.retry_backoff_ms <= 0:
        return
    time.sleep(runtime_config.retry_backoff_ms / 1000)


def _provider_native_cost_reference(provider: str, model: str) -> dict[str, Any]:
    identity = {
        "contract": "provider-native-reported-cost-v1",
        "provider": provider,
        "model": model,
        "currency": "USD",
        "sourceUri": "https://openrouter.ai/docs/cookbook/administration/usage-accounting",
    }
    return {
        "schemaVersion": "eslams.price-card-reference.v1",
        "rateCardId": f"{provider}:provider-native-reported-cost:v1",
        "rateCardHash": sha256_json(identity),
        "provider": provider,
        "model": model,
        "currency": "USD",
        "sourceUri": identity["sourceUri"],
        "effectiveAt": None,
        "retrievedAt": None,
        "complete": provider == "openrouter",
    }


def _receipt(
    *,
    provider: str,
    model: str,
    response: httpx.Response,
    provider_response_id: Any,
    resolved_model: Any,
    model_identity_source: str | None = None,
    usage: Any,
    capabilities: ModelCapabilities,
    runtime_config: ProviderRuntimeConfig | None,
    native_cost: Any = None,
) -> dict[str, Any]:
    normalized_usage = _normalize_usage(provider, usage)
    has_usage = _normalized_usage_has_tokens(normalized_usage)
    pricing = _pricing_summary(capabilities)
    normalized_native_cost = _optional_float(native_cost)
    runtime_rate_card_reference = (
        runtime_config.rate_card_reference.to_dict()
        if runtime_config and runtime_config.rate_card_reference is not None
        else None
    )
    if normalized_native_cost is not None:
        estimated_cost = {
            "status": "ok",
            "currency": "USD",
            "cost_usd": normalized_native_cost,
            "source": "provider_native",
        }
        if pricing.get("status") != "ok":
            native_reference = _provider_native_cost_reference(provider, model)
            pricing = {
                "status": "ok",
                "pricing_table_version": native_reference["rateCardId"],
                "rate_card_id": native_reference["rateCardId"],
                "rate_card_reference": native_reference,
                "currency": "USD",
                "billable_token_categories": [],
                "source": "provider_native",
                "unit": "request-reported",
            }
    else:
        estimated_cost = (
            _estimated_cost(normalized_usage, pricing)
            if has_usage
            else {
                "status": "cost_unavailable",
                "unavailable_reason": "provider_usage_absent",
            }
        )
    rate_card_reference = runtime_rate_card_reference or pricing.get("rate_card_reference")
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "locked_model_id": resolved_model if isinstance(resolved_model, str) else None,
        "model_identity_source": (
            model_identity_source
            if isinstance(resolved_model, str) and model_identity_source is not None
            else "provider_response"
            if isinstance(resolved_model, str)
            else None
        ),
        "endpoint_kind": _endpoint_kind(provider),
        "parser_version": _parser_version(provider),
        "outcome": "ok",
        "model_capability_known": capabilities.known,
        "game_agent_supported": capabilities.game_agent_supported,
        "capability_sources": list(capabilities.sources),
        "provider_response_id": provider_response_id,
        "status_code": response.status_code,
        "request_id": response.headers.get("x-request-id")
        or response.headers.get("request-id")
        or response.headers.get("x-cloud-trace-context"),
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": response.headers.get("cf-aig-request-id")
        or response.headers.get("x-gateway-request-id"),
        "usage": normalized_usage if has_usage else {},
        "usage_unavailable_reason": None if has_usage else "provider_usage_absent",
        "pricing": pricing,
        "estimated_cost": estimated_cost,
        "rate_card_reference": rate_card_reference,
        "rate_card_id": (
            rate_card_reference.get("rateCardId") if isinstance(rate_card_reference, dict) else None
        ),
        "redaction_version": "provider-receipt-redaction-v1",
    }


def _attempt_receipt(
    receipt: dict[str, Any],
    *,
    agent_id: str,
    agent_version: str,
    turn_id: int,
    attempt: int,
    attempt_kind: str,
) -> dict[str, Any]:
    return {
        **receipt,
        "agent_id": agent_id,
        "agent_version": agent_version,
        "turn_id": turn_id,
        "attempt": attempt,
        "attempt_index": attempt,
        "attempt_kind": attempt_kind,
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
    attempt_kind: str = "primary",
    status_code: int | None = None,
    retry_after_seconds: float | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": provider,
        "model": model,
        "locked_model_id": None,
        "model_identity_source": None,
        "endpoint_kind": _endpoint_kind(provider),
        "parser_version": _parser_version(provider),
        "agent_id": agent_id,
        "agent_version": agent_version,
        "turn_id": turn_id,
        "attempt": attempt,
        "attempt_index": attempt,
        "attempt_kind": attempt_kind,
        "outcome": outcome,
        "status_code": status_code,
        "request_id": None,
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": None,
        "retry_after_ms": (
            round(retry_after_seconds * 1000) if retry_after_seconds is not None else None
        ),
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
    normalized_usage = _normalize_usage(
        agent.provider,
        {**usage, "reasoning_included_in_output": True},
    )
    has_usage = _normalized_usage_has_tokens(normalized_usage)
    return {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "provider": agent.provider,
        "model": agent.model,
        "locked_model_id": agent.model,
        "model_identity_source": "mock_attested",
        "endpoint_kind": "mock",
        "parser_version": "mock-action-v1",
        "agent_id": agent.id,
        "agent_version": agent.version,
        "turn_id": request.turn_id,
        "attempt": 1,
        "attempt_index": 1,
        "attempt_kind": "primary",
        "outcome": outcome,
        "status_code": (200 if outcome in {"ok", "action_response_unparseable"} else None),
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


def _http_provider_receipt(
    receipt: dict[str, Any],
    *,
    provider: str | None,
    model: str | None,
    endpoint_metadata: dict[str, Any],
) -> dict[str, Any]:
    receipt_provider = _optional_str_value(receipt.get("provider")) or provider or "unknown"
    receipt_model = _optional_str_value(receipt.get("model")) or model or "unknown"
    usage = receipt.get("usage")
    normalized_usage = _normalize_usage(receipt_provider, usage)
    has_usage = _normalized_usage_has_tokens(normalized_usage)
    usage_unavailable_reason = _optional_str_value(receipt.get("usage_unavailable_reason"))
    if not has_usage and usage_unavailable_reason is None:
        usage_unavailable_reason = "provider_usage_absent"
    allowed = {
        "schema_version",
        "provider",
        "model",
        "locked_model_id",
        "model_identity_source",
        "endpoint_kind",
        "parser_version",
        "provider_response_id",
        "request_id",
        "gateway_request_id",
        "status_code",
        "outcome",
        "finish_reason",
        "finish_status",
        "latency_ms",
        "attempt",
        "attempt_index",
        "attempt_kind",
        "event_id",
        "logical_action_id",
        "parent_attempt_id",
        "pricing",
        "estimated_cost",
        "rate_card_reference",
        "rate_card_id",
        "pricing_provenance",
    }
    normalized: dict[str, Any] = {}
    for key, value in receipt.items():
        if key not in allowed:
            continue
        sanitized = _sanitize_receipt_value(value)
        if sanitized is not _DROP_RECEIPT_VALUE:
            normalized[key] = sanitized
    normalized.update(
        {
            "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
            "provider": receipt_provider,
            "model": receipt_model,
            "locked_model_id": _optional_str_value(receipt.get("locked_model_id")),
            "model_identity_source": _optional_str_value(receipt.get("model_identity_source")),
            "endpoint_kind": _optional_str_value(receipt.get("endpoint_kind")),
            "parser_version": _optional_str_value(receipt.get("parser_version")),
            "outcome": _optional_str_value(receipt.get("outcome")) or "ok",
            "usage": normalized_usage if has_usage else {},
            "usage_unavailable_reason": usage_unavailable_reason,
            "pricing": _receipt_dict(
                receipt.get("pricing"),
                fallback={
                    "status": "cost_unavailable",
                    "source": "http_agent_metadata",
                    "unavailable_reason": "pricing_not_configured",
                },
            ),
            "estimated_cost": _receipt_dict(
                receipt.get("estimated_cost"),
                fallback={
                    "status": "cost_unavailable",
                    "unavailable_reason": "pricing_not_configured",
                },
            ),
            "endpoint_metadata": _receipt_dict(endpoint_metadata, fallback={}),
            "redaction_version": "provider-receipt-redaction-v1",
        }
    )
    return normalized


def _receipt_dict(value: Any, *, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return dict(fallback)
    sanitized = _sanitize_receipt_value(value)
    return sanitized if isinstance(sanitized, dict) else dict(fallback)


_DROP_RECEIPT_VALUE = object()
_SENSITIVE_RECEIPT_KEYS = {
    "access_key",
    "access_key_id",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "key",
    "password",
    "private_key",
    "proxy_authorization",
    "refresh_token",
    "secret",
    "secret_access_key",
    "secret_key",
    "set_cookie",
    "signature",
    "token",
    "x_api_key",
}


def _sanitize_receipt_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP_RECEIPT_VALUE
    if isinstance(value, str):
        redacted = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer [REDACTED]", value)
        return _sanitize_url_secrets(redacted)
    if isinstance(value, list):
        sanitized_items = [_sanitize_receipt_value(item) for item in value]
        return [item for item in sanitized_items if item is not _DROP_RECEIPT_VALUE]
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or _sensitive_receipt_key(key):
                continue
            sanitized_item = _sanitize_receipt_value(item)
            if sanitized_item is not _DROP_RECEIPT_VALUE:
                sanitized_dict[key] = sanitized_item
        return sanitized_dict
    return _DROP_RECEIPT_VALUE


def _sensitive_receipt_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    if normalized in _SENSITIVE_RECEIPT_KEYS:
        return True
    if normalized.endswith(
        (
            "_api_key",
            "_authorization",
            "_credential",
            "_password",
            "_secret",
            "_signature",
        )
    ):
        return True
    return normalized.endswith("_token") and not normalized.endswith("_per_token")


def _sanitize_url_secrets(value: str) -> str:
    if "://" not in value:
        return value
    try:
        parsed = urlsplit(value)
        has_userinfo = parsed.username is not None or parsed.password is not None
        hostname = parsed.hostname
    except ValueError:
        return value
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = parsed.netloc
    if has_userinfo:
        if hostname is None:
            return "[REDACTED]"
        netloc = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None:
            netloc = f"{netloc}:{port}"
    return parsed._replace(
        netloc=netloc,
        query=_redact_sensitive_url_parameters(parsed.query),
        fragment=_redact_sensitive_url_parameters(parsed.fragment),
    ).geturl()


def _redact_sensitive_url_parameters(value: str) -> str:
    parts = re.split(r"([&;])", value)
    for index in range(0, len(parts), 2):
        raw_key, separator, _raw_value = parts[index].partition("=")
        if raw_key and _sensitive_receipt_key(unquote_plus(raw_key)):
            parts[index] = f"{raw_key}=[REDACTED]"
        elif not separator:
            parts[index] = raw_key
    return "".join(parts)


def _optional_str_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _provider_endpoint(
    default_url: str,
    runtime_config: ProviderRuntimeConfig | None,
) -> str:
    if runtime_config is None or not runtime_config.gateway_base_url:
        return default_url
    parsed = urlparse(default_url)
    path = parsed.path.lstrip("/")
    return f"{runtime_config.gateway_base_url.rstrip('/')}/{path}"


def _endpoint_kind(provider: str) -> str:
    return {
        "openai": "openai_responses",
        "anthropic": "anthropic_messages",
        "gemini": "gemini_generate_content",
        "google": "gemini_generate_content",
        "openrouter": "openrouter_chat_completions",
        "bedrock": "bedrock_converse",
    }.get(provider, "unknown")


def _parser_version(provider: str) -> str:
    return {
        "openai": "openai-responses-raw-v2",
        "anthropic": "anthropic-messages-raw-v2",
        "gemini": "gemini-generate-content-raw-v2",
        "google": "gemini-generate-content-raw-v2",
        "openrouter": "openrouter-chat-completions-raw-v1",
        "bedrock": "bedrock-converse-raw-v1",
    }.get(provider, "unknown")


def _normalize_usage(provider: str, usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return _empty_usage()
    validation_errors: list[str] = []
    if provider in {"gemini", "google"}:
        prompt_tokens = _usage_int(
            usage.get("promptTokenCount"), "promptTokenCount", validation_errors
        )
        tool_input_tokens = _usage_int(
            usage.get("toolUsePromptTokenCount"),
            "toolUsePromptTokenCount",
            validation_errors,
        )
        input_tokens = _sum_optional(prompt_tokens, tool_input_tokens)
        output_tokens = _usage_int(
            usage.get("candidatesTokenCount"),
            "candidatesTokenCount",
            validation_errors,
        )
        provider_total_tokens = _usage_int(
            usage.get("totalTokenCount"), "totalTokenCount", validation_errors
        )
        cached_input_tokens = _usage_int(
            usage.get("cachedContentTokenCount"),
            "cachedContentTokenCount",
            validation_errors,
        )
        cache_read_input_tokens = cached_input_tokens
        cache_write_input_tokens = None
        reasoning_tokens = _usage_int(
            _first_present(usage, "thoughtsTokenCount", "thinkingTokenCount"),
            "thoughtsTokenCount",
            validation_errors,
        )
        reasoning_included_in_output: bool | None = False
        cached_input_is_subset: bool | None = True
    elif provider == "anthropic":
        uncached_input_tokens = _usage_int(
            usage.get("input_tokens"), "input_tokens", validation_errors
        )
        cache_write_input_tokens = _usage_int(
            usage.get("cache_creation_input_tokens"),
            "cache_creation_input_tokens",
            validation_errors,
        )
        cache_read_input_tokens = _usage_int(
            usage.get("cache_read_input_tokens"),
            "cache_read_input_tokens",
            validation_errors,
        )
        cached_input_tokens = _sum_optional(
            cache_write_input_tokens,
            cache_read_input_tokens,
        )
        input_tokens = _sum_optional(
            uncached_input_tokens,
            cache_write_input_tokens,
            cache_read_input_tokens,
        )
        output_tokens = _usage_int(usage.get("output_tokens"), "output_tokens", validation_errors)
        provider_total_tokens = _usage_int(
            usage.get("total_tokens"), "total_tokens", validation_errors
        )
        output_details = _dict(usage.get("output_tokens_details"))
        reasoning_tokens = _usage_int(
            _first_present(
                usage,
                "reasoning_tokens",
                fallback=output_details.get("thinking_tokens"),
            ),
            "output_tokens_details.thinking_tokens",
            validation_errors,
        )
        reasoning_included_in_output = True
        cached_input_is_subset = True
    elif provider == "bedrock":
        uncached_input_tokens = _usage_int(
            usage.get("inputTokens"), "inputTokens", validation_errors
        )
        cache_read_input_tokens = _usage_int(
            usage.get("cacheReadInputTokens"),
            "cacheReadInputTokens",
            validation_errors,
        )
        cache_write_input_tokens = _usage_int(
            usage.get("cacheWriteInputTokens"),
            "cacheWriteInputTokens",
            validation_errors,
        )
        cached_input_tokens = _sum_optional(
            cache_read_input_tokens,
            cache_write_input_tokens,
        )
        input_tokens = _sum_optional(
            uncached_input_tokens,
            cache_read_input_tokens,
            cache_write_input_tokens,
        )
        output_tokens = _usage_int(usage.get("outputTokens"), "outputTokens", validation_errors)
        provider_total_tokens = _usage_int(
            usage.get("totalTokens"), "totalTokens", validation_errors
        )
        reasoning_tokens = _usage_int(
            usage.get("reasoningTokens"), "reasoningTokens", validation_errors
        )
        reasoning_included_in_output = True
        cached_input_is_subset = True
    else:
        input_tokens = _usage_int(
            _first_present(usage, "input_tokens", "prompt_tokens"),
            "input_tokens",
            validation_errors,
        )
        output_tokens = _usage_int(
            _first_present(usage, "output_tokens", "completion_tokens"),
            "output_tokens",
            validation_errors,
        )
        provider_total_tokens = _usage_int(
            usage.get("total_tokens"), "total_tokens", validation_errors
        )
        input_details = _dict(usage.get("input_tokens_details")) or _dict(
            usage.get("prompt_tokens_details")
        )
        output_details = _dict(usage.get("output_tokens_details")) or _dict(
            usage.get("completion_tokens_details")
        )
        cache_read_input_tokens = _usage_int(
            _first_present(
                usage,
                "cached_input_tokens",
                fallback=_first_present(
                    input_details,
                    "cached_tokens",
                    "cache_read_input_tokens",
                ),
            ),
            "cached_input_tokens",
            validation_errors,
        )
        cache_write_input_tokens = _usage_int(
            input_details.get("cache_creation_input_tokens"),
            "cache_creation_input_tokens",
            validation_errors,
        )
        cached_input_tokens = _sum_optional(
            cache_read_input_tokens,
            cache_write_input_tokens,
        )
        reasoning_tokens = _usage_int(
            _first_present(
                usage,
                "reasoning_tokens",
                fallback=output_details.get("reasoning_tokens"),
            ),
            "reasoning_tokens",
            validation_errors,
        )
        raw_inclusion = usage.get("reasoning_included_in_output")
        reasoning_included_in_output = (
            True if provider in {"openai", "openrouter"} else _optional_bool(raw_inclusion)
        )
        cached_input_is_subset = True

    total_tokens, total_tokens_source = _normalized_total_tokens(
        provider_total_tokens=provider_total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        reasoning_included_in_output=reasoning_included_in_output,
        validation_errors=validation_errors,
    )
    if (
        cached_input_is_subset is True
        and cached_input_tokens is not None
        and input_tokens is not None
        and cached_input_tokens > input_tokens
    ):
        validation_errors.append("cached_input_tokens_exceed_input_tokens")
    if (
        reasoning_included_in_output is True
        and reasoning_tokens is not None
        and output_tokens is not None
        and reasoning_tokens > output_tokens
    ):
        validation_errors.append("reasoning_tokens_exceed_inclusive_output_tokens")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_write_input_tokens": cache_write_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "reasoning_included_in_output": reasoning_included_in_output,
        "cached_input_is_subset": cached_input_is_subset,
        "total_tokens_source": total_tokens_source,
        "usage_source": "provider",
        "usage_validation_errors": sorted(set(validation_errors)),
    }


def _normalized_usage_has_tokens(usage: dict[str, Any]) -> bool:
    return any(
        usage.get(key) is not None for key in ("input_tokens", "output_tokens", "total_tokens")
    )


def _empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "cache_read_input_tokens": None,
        "cache_write_input_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
        "reasoning_included_in_output": None,
        "cached_input_is_subset": None,
        "total_tokens_source": "unavailable",
        "usage_source": "provider",
        "usage_validation_errors": [],
    }


def _first_present(
    mapping: dict[str, Any],
    *keys: str,
    fallback: Any = None,
) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return fallback


def _sum_optional(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _usage_int(value: Any, field: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    parsed = _optional_int(value)
    if parsed is None:
        errors.append(f"{field}_invalid")
    return parsed


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _normalized_total_tokens(
    *,
    provider_total_tokens: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None,
    reasoning_included_in_output: bool | None,
    validation_errors: list[str],
) -> tuple[int | None, str]:
    expected: int | None = None
    source = "provider" if provider_total_tokens is not None else "unavailable"
    if input_tokens is not None and output_tokens is not None:
        expected = input_tokens + output_tokens
        source = "derived_input_plus_output"
        if reasoning_tokens is not None and reasoning_tokens > 0:
            if reasoning_included_in_output is False:
                expected += reasoning_tokens
                source = "derived_input_plus_output_plus_reasoning"
            elif reasoning_included_in_output is None:
                validation_errors.append("reasoning_inclusion_unknown")
                expected = None
                source = "unavailable"
    if provider_total_tokens is not None:
        if expected is not None and provider_total_tokens != expected:
            validation_errors.append("provider_total_tokens_inconsistent")
        return provider_total_tokens, "provider"
    return expected, source


def _pricing_summary(capabilities: ModelCapabilities) -> dict[str, Any]:
    pricing = capabilities.pricing
    if not pricing:
        return _cost_unavailable(source="not_configured")
    categories = [
        key
        for key in (
            "input_cost_per_token",
            "output_cost_per_token",
            "cache_creation_input_token_cost",
            "cache_read_input_token_cost",
            "output_cost_per_reasoning_token",
        )
        if _optional_float(pricing.get(key)) is not None
    ]
    if not categories:
        return _cost_unavailable(source="not_configured")
    return {
        "status": "ok",
        "pricing_table_version": capabilities.last_verified_at,
        "rate_card_id": (
            str(pricing.get("rate_card_id"))
            if pricing.get("rate_card_id")
            else capabilities.last_verified_at
        ),
        "currency": str(pricing.get("currency") or "USD"),
        "billable_token_categories": categories,
        "source": str(pricing.get("source") or "provider_registry"),
        "unit": str(pricing.get("unit") or "token"),
        **{
            key: value
            for key in categories
            if (value := _optional_float(pricing.get(key))) is not None
        },
    }


def _estimated_cost(
    usage: dict[str, Any],
    pricing_summary: dict[str, Any],
) -> dict[str, Any]:
    if pricing_summary.get("status") != "ok":
        return {
            "status": "cost_unavailable",
            "unavailable_reason": "pricing_not_configured",
        }
    if usage.get("usage_validation_errors"):
        return {
            "status": "cost_unavailable",
            "unavailable_reason": "provider_usage_malformed",
        }
    rates = _pricing_rates(pricing_summary)
    input_tokens = _optional_int(usage.get("input_tokens"))
    output_tokens = _optional_int(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return {
            "status": "cost_unavailable",
            "unavailable_reason": "provider_usage_missing",
        }
    cache_read_tokens = _optional_int(usage.get("cache_read_input_tokens")) or 0
    cache_write_tokens = _optional_int(usage.get("cache_write_input_tokens")) or 0
    reasoning_tokens = _optional_int(usage.get("reasoning_tokens")) or 0
    reasoning_included = usage.get("reasoning_included_in_output")
    if reasoning_tokens and not isinstance(reasoning_included, bool):
        return {
            "status": "cost_unavailable",
            "unavailable_reason": "reasoning_inclusion_unknown",
        }
    billable_uncached_input = max(
        0,
        input_tokens - cache_read_tokens - cache_write_tokens,
    )
    cache_read_rate = rates.get("cache_read_input_token_cost") or rates.get(
        "input_cost_per_token",
        0.0,
    )
    cache_write_rate = rates.get("cache_creation_input_token_cost") or rates.get(
        "input_cost_per_token",
        0.0,
    )
    reasoning_rate = rates.get("output_cost_per_reasoning_token") or rates.get(
        "output_cost_per_token",
        0.0,
    )
    separately_billed_reasoning = reasoning_tokens if reasoning_included is False else 0
    total = (
        billable_uncached_input * rates.get("input_cost_per_token", 0.0)
        + output_tokens * rates.get("output_cost_per_token", 0.0)
        + cache_read_tokens * cache_read_rate
        + cache_write_tokens * cache_write_rate
        + separately_billed_reasoning * reasoning_rate
    )
    return {
        "status": "ok",
        "source": "registry_rate_card_estimate",
        "currency": pricing_summary.get("currency", "USD"),
        "cost_usd": round(total, 12),
        "input_cost_usd": round(
            billable_uncached_input * rates.get("input_cost_per_token", 0.0),
            12,
        ),
        "cache_read_input_cost_usd": round(
            cache_read_tokens * cache_read_rate,
            12,
        ),
        "cache_write_input_cost_usd": round(
            cache_write_tokens * cache_write_rate,
            12,
        ),
        "output_cost_usd": round(
            output_tokens * rates.get("output_cost_per_token", 0.0),
            12,
        ),
        "reasoning_cost_usd": round(
            separately_billed_reasoning * reasoning_rate,
            12,
        ),
        "reasoning_included_in_output": reasoning_included,
    }


def _pricing_rates(pricing_summary: dict[str, Any]) -> dict[str, float]:
    return {
        key: _optional_float(pricing_summary.get(key)) or 0.0
        for key in (
            "input_cost_per_token",
            "output_cost_per_token",
            "cache_creation_input_token_cost",
            "cache_read_input_token_cost",
            "output_cost_per_reasoning_token",
        )
    }


def _cost_unavailable(*, source: str) -> dict[str, Any]:
    return {
        "status": "cost_unavailable",
        "pricing_table_version": None,
        "currency": "USD",
        "billable_token_categories": [],
        "source": source,
        "unavailable_reason": "pricing_not_configured",
    }


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) and numeric >= 0 else None
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _openai_text(data: dict[str, Any]) -> str:
    """Extract text from the raw Responses REST envelope.

    Direct REST calls require typed ``output[]`` items and ``output_text``
    content parts.  The SDK-only top-level convenience field is deliberately not
    accepted in this live adapter.
    """

    chunks: list[str] = []
    output = data.get("output")
    if not isinstance(output, list):
        raise ProviderCallError(
            "OpenAI Responses body is missing the output array",
            error_kind="provider_response_schema_mismatch",
            provider="openai",
        )
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise ProviderCallError(
            "OpenAI Responses body has no output_text content parts",
            error_kind="provider_response_schema_mismatch",
            provider="openai",
        )
    return "".join(chunks)


def _openrouter_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderCallError(
            "OpenRouter response is missing choices[0]",
            error_kind="provider_response_schema_mismatch",
            provider="openrouter",
        )
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        chunks = [
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") in {None, "text"}
            and isinstance(part.get("text"), str)
        ]
        if chunks:
            return "".join(chunks)
    raise ProviderCallError(
        "OpenRouter response message has no text content",
        error_kind="provider_response_schema_mismatch",
        provider="openrouter",
    )


def _anthropic_text(data: dict[str, Any]) -> str:
    content = data.get("content")
    if not isinstance(content, list):
        raise ProviderCallError(
            "Anthropic Messages response is missing content",
            error_kind="provider_response_schema_mismatch",
            provider="anthropic",
        )
    chunks = [
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    if not chunks:
        raise ProviderCallError(
            "Anthropic Messages response contains no text block",
            error_kind="provider_response_schema_mismatch",
            provider="anthropic",
        )
    return "".join(chunks)


def _gemini_text(data: dict[str, Any], *, provider: str) -> str:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise ProviderCallError(
            "Gemini response is missing candidates",
            error_kind="provider_response_schema_mismatch",
            provider=provider,
        )
    chunks: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        chunks.extend(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    if not chunks:
        raise ProviderCallError(
            "Gemini response contains no text part",
            error_kind="provider_response_schema_mismatch",
            provider=provider,
        )
    return "".join(chunks)


def _bedrock_text(data: dict[str, Any]) -> str:
    output = data.get("output")
    message = output.get("message") if isinstance(output, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        raise ProviderCallError(
            "Bedrock Converse response is missing output.message.content",
            error_kind="provider_response_schema_mismatch",
            provider="bedrock",
        )
    chunks = [
        part["text"]
        for part in content
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not chunks:
        raise ProviderCallError(
            "Bedrock Converse response contains no text block",
            error_kind="provider_response_schema_mismatch",
            provider="bedrock",
        )
    return "".join(chunks)


def _response_json_with_receipt(
    response: httpx.Response,
    *,
    provider: str,
    model: str,
    capabilities: ModelCapabilities,
    runtime_config: ProviderRuntimeConfig | None,
) -> dict[str, Any]:
    try:
        return _response_json(response, provider=provider, model=model)
    except ProviderCallError as exc:
        receipt = _failure_receipt(
            provider=provider,
            model=model,
            agent_id="",
            agent_version="",
            turn_id=0,
            outcome=exc.error_kind,
            usage_unavailable_reason=exc.error_kind,
            runtime_config=runtime_config,
            status_code=response.status_code,
        )
        receipt.update(
            {
                "request_id": response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or response.headers.get("x-cloud-trace-context")
                or response.headers.get("x-amzn-requestid"),
                "gateway_request_id": response.headers.get("cf-aig-request-id")
                or response.headers.get("x-gateway-request-id"),
                "model_capability_known": capabilities.known,
                "capability_sources": list(capabilities.sources),
            }
        )
        exc.receipt = receipt
        raise


def _response_json(
    response: httpx.Response,
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProviderCallError(
            "provider response body is not valid JSON",
            status_code=response.status_code,
            error_kind="provider_response_schema_mismatch",
            provider=provider,
            model=model,
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderCallError(
            "provider response body must be a JSON object",
            status_code=response.status_code,
            error_kind="provider_response_schema_mismatch",
            provider=provider,
            model=model,
        )
    return payload


_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;\"']+"),
    re.compile(r"(?i)((?:x-api-key|api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;\"']+"),
    re.compile(r"\b(?:sk|key|token)-[A-Za-z0-9_-]{8,}\b"),
)


def _redact_sensitive_text(value: str) -> str:
    redacted = value.replace("\r", " ").replace("\n", " ")
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
            redacted,
        )
    return redacted[:500]


def _parse_model_action(
    text: str,
    legal_actions: list[Any],
) -> tuple[Any, float | None, str | None]:
    parsed = parse_model_action(text, legal_actions)
    return parsed.action, parsed.confidence, parsed.public_explanation


def _extract_json(text: str) -> Any:
    return extract_json(text)


def _coerce_action(value: Any, legal_actions: list[Any]) -> Any:
    return coerce_action(value, legal_actions)


def _find_legal_action(text: str, legal_actions: list[Any]) -> Any:
    return find_legal_action(text, legal_actions)


def create_builtin_agent(name: str, *, seed: int = 0) -> FirstLegalAgent | RandomAgent:
    if name == "first-legal":
        return FirstLegalAgent()
    if name == "random":
        return RandomAgent(seed=seed)
    raise KeyError(f"unknown built-in agent {name!r}")
