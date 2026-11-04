"""Built-in agent adapters."""

from __future__ import annotations

import copy
import json
import math
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
from eslams.deadlines import (
    ExecutionCancelled,
    action_deadline,
    check_cancelled,
    current_deadline,
    current_receipt_invocation,
    remaining_seconds,
    sleep_with_cancellation,
)
from eslams.hashing import sha256_json
from eslams.http_io import TotalTimeout, bounded_post, response_observation
from eslams.model_actions import (
    coerce_action,
    extract_json,
    find_legal_action,
    invalid_action_retry_prompt,
    parse_model_action,
)
from eslams.protocol import ActRequest, ActResponse, ProtocolError, validate_json_payload
from eslams.provider_credentials import provider_key
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
        retry_permitted: bool = False,
    ) -> None:
        self.retry_permitted = retry_permitted
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
    _receipt_batch: tuple[object, tuple[dict[str, Any], ...]] | None = field(
        default=None, init=False, repr=False,
    )

    def act(self, request: ActRequest) -> ActResponse:
        request = ActRequest.from_mapping(request.to_dict())
        # Token and batch change together; a timeout before this assignment
        # cannot attribute an old invocation's receipt to the new request.
        self._receipt_batch = (current_receipt_invocation() or object(), ())
        with action_deadline(request.time_budget_ms):
            return self._act(request)

    def _receipt_snapshot(self, invocation: object) -> list[dict[str, Any]]:
        batch = self._receipt_batch
        if batch is None or batch[0] is not invocation:
            return []
        return copy.deepcopy(list(batch[1]))

    def _publish_receipts(self, receipts: list[dict[str, Any]]) -> None:
        batch = self._receipt_batch
        invocation = current_receipt_invocation()
        if batch is None or (invocation is not None and batch[0] is not invocation):
            return
        # Private copies are never mutated/exposed. One reference assignment
        # transfers the complete observed batch before convenience fields.
        published = (batch[0], tuple(copy.deepcopy(receipts)))
        self._receipt_batch = published

    def _act(self, request: ActRequest) -> ActResponse:
        self.attempt_receipts = []
        self.last_receipt = None
        headers = {"content-type": "application/json"}
        if self.bearer_token:
            headers["authorization"] = f"Bearer {self.bearer_token}"
        try:
            response = bounded_post(
                self.url,
                json=request.to_dict(),
                headers=headers,
                timeout=(request.time_budget_ms / 1000 if request.time_budget_ms is not None
                         else httpx.Timeout(None, connect=10, write=10, pool=None)),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            # Body bytes are already bounded by bounded_post. Receipt custody
            # is independent of whether this failed callback returns an action.
            try:
                failure = exc.response.json()
            except (ValueError, UnicodeError, RecursionError):
                failure = None
            kind = _http_failure_kind(exc.response.status_code, failure)
            self._remember_failure_receipt(failure, kind, error_envelope=True)
            raise ProviderCallError(
                f"agent HTTP request failed with status {exc.response.status_code}",
                status_code=exc.response.status_code,
                error_kind=kind,
                provider=self.provider,
                model=self.model,
                receipt=self.last_receipt,
            ) from exc
        except ProtocolError:
            raise
        except (ValueError, UnicodeError) as exc:
            raise ProtocolError("agent response must be valid JSON") from exc
        except ExecutionCancelled:
            raise
        except httpx.TimeoutException as exc:
            raise TimeoutError("agent timed out") from exc
        except Exception as exc:
            raise ProviderCallError(
                "agent HTTP transport failed", error_kind="provider_transport_error",
                provider=self.provider, model=self.model,
            ) from exc
        if not isinstance(payload, dict):
            raise ProtocolError("agent response must be a JSON object")
        try:
            act_response = ActResponse.from_mapping(payload)
        except ProtocolError:
            self._remember_failure_receipt(
                payload, "action_response_unparseable", error_envelope=False,
            )
            raise
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
            self._publish_receipts([*self.attempt_receipts, normalized_receipt])
            self.attempt_receipts.append(normalized_receipt)
            self.last_receipt = normalized_receipt
        if self.last_receipt is not None:
            act_response.metadata["provider_receipt"] = self.last_receipt
            act_response.metadata["attempt_receipts"] = [
                dict(item) for item in self.attempt_receipts
            ]
        return act_response

    def _remember_failure_receipt(
        self, payload: Any, failure_kind: str, *, error_envelope: bool,
    ) -> None:
        # This first contract supports one structured callback receipt. Multi-
        # attempt carriers need an explicit complete/gap-free ledger contract.
        if not isinstance(payload, dict):
            return
        try:
            validate_json_payload(payload)
            if error_envelope:
                error = payload.get("error")
                details = error.get("details") if isinstance(error, dict) else None
                carrier = details if isinstance(details, dict) else {}
                candidate = carrier.get("providerReceipt")
            else:
                metadata = payload.get("metadata")
                carrier = metadata if isinstance(metadata, dict) else {}
                candidate = carrier.get("provider_receipt")
            if any(key in carrier for key in ("attempt_receipts", "attemptReceipts")):
                return
            if not isinstance(candidate, dict) or candidate.get("schema_version") not in {
                "eslams.provider.receipt.v1", PROVIDER_RECEIPT_SCHEMA_VERSION,
            }:
                return
            if any(
                key in candidate and (
                    isinstance(candidate[key], bool)
                    or not isinstance(candidate[key], int) or candidate[key] != 1
                ) for key in ("attempt", "attempt_index")
            ) or candidate.get("attempt_kind") not in (None, "primary"):
                return
            code = candidate.get("status_code")
            if code is not None and (
                isinstance(code, bool) or not isinstance(code, int) or not 100 <= code <= 599
            ):
                return
            latency = candidate.get("latency_ms")
            if latency is not None and (
                isinstance(latency, bool) or not isinstance(latency, int) or latency < 0
            ):
                return
            # This carrier admits observations, never remote price-card or
            # model attestation claims. Project before the legacy normalizer.
            projected = _http_error_receipt_projection(candidate, failure_kind)
            normalized = _http_provider_receipt(
                projected,
                provider=_http_error_identifier(self.provider),
                model=_http_error_identifier(self.model),
                endpoint_metadata={
                    key: value for key in ("region", "route", "gateway_mode")
                    if (value := _http_error_identifier(self.endpoint_metadata.get(key)))
                },
            )
            usage = normalized.get("usage")
            if isinstance(usage, dict) and usage.get("usage_validation_errors"):
                normalized["usage"] = {}
                normalized["usage_unavailable_reason"] = "provider_usage_malformed"
            elif normalized.get("usage"):
                normalized["usage_unavailable_reason"] = None
            else:
                normalized["usage_unavailable_reason"] = "provider_outcome_unknown"
            normalized.update(attempt=1, attempt_index=1, attempt_kind="primary")
            validate_json_payload(normalized)
        except (ProtocolError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
            return
        self._publish_receipts([normalized])
        self.attempt_receipts = [normalized]
        self.last_receipt = normalized



def _http_error_identifier(value: Any) -> str | None:
    # Bounded identifier syntax, not a content-redaction or authenticity proof.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./:@+-]{1,256}", value):
        return None
    sanitized = _sanitize_receipt_value(value)
    return sanitized if isinstance(sanitized, str) else None


def _http_error_receipt_projection(receipt: dict[str, Any], outcome: str) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "schema_version": PROVIDER_RECEIPT_SCHEMA_VERSION,
        "outcome": outcome,
        # Normalization reads only defined numeric/boolean usage fields. Raw
        # nested fields are never copied into normalized usage.
        "usage": receipt.get("usage"),
        "status_code": receipt.get("status_code"),
        "latency_ms": receipt.get("latency_ms"),
        "pricing": {
            "status": "cost_unavailable", "source": "http_error_receipt",
            "unavailable_reason": "unverified_error_receipt_pricing",
        },
        "estimated_cost": {
            "status": "cost_unavailable",
            "unavailable_reason": "unverified_error_receipt_pricing",
        },
        # Fixed-shape local provenance: no remote free-form dictionaries,
        # raw output, price references, rates, URLs, or model attestations.
        "pricing_provenance": {
            "schema_version": "eslams.http-error-provenance.v1",
            "source": "unverified_http_error_receipt",
            "accounting_status": "quarantined",
            "model_identity_status": "unverified",
        },
    }
    for key in ("provider", "model", "request_id", "gateway_request_id", "provider_response_id"):
        value = _http_error_identifier(receipt.get(key))
        if value is not None:
            projected[key] = value
    return projected


def _http_failure_kind(status_code: int, payload: Any) -> str:
    # HTTP status does not prove whether the provider accepted/charged work.
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if status_code == 502 and isinstance(code, str):
        kind = {
            "runner_agent_invalid_action": "action_response_unparseable",
            "action_response_unparseable": "action_response_unparseable",
            "action_not_legal": "action_not_legal",
            "provider_response_schema_mismatch": "provider_response_schema_mismatch",
        }.get(code)
        if kind is not None:
            return kind
    return {
        401: "provider_auth_failed", 403: "provider_permission_failed",
        429: "provider_rate_limited", 504: "provider_timeout",
    }.get(status_code, "provider_unavailable")


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
    temperature: float | None = None
    max_output_tokens: int | None = None
    runtime_config: ProviderRuntimeConfig | None = None

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()
        if self.provider.replace("_", "-") in {"arcee", "arcee-ai"}:
            self.provider = "arcee-ai"
        if self.id is None:
            self.id = f"{self.provider}-{self.model}"
        if self.runtime_config is None:
            self.runtime_config = ProviderRuntimeConfig()
        self._receipt_batch: tuple[object, tuple[dict[str, Any], ...]] | None = None
        self.last_receipt: dict[str, Any] | None = None
        self.attempt_receipts: list[dict[str, Any]] = []
        self._reasoning_enabled = False
        self._request_max_output_tokens: int | None = self.max_output_tokens
        self.capabilities = load_provider_registry().resolve(self.provider, self.model)
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int) or self.max_output_tokens < 1
        ):
            raise ValueError("max_output_tokens must be a positive operator limit or null")

    def act(self, request: ActRequest) -> ActResponse:
        request = ActRequest.from_mapping(request.to_dict())
        self._receipt_batch = (current_receipt_invocation() or object(), ())
        with action_deadline(request.time_budget_ms):
            return self._act(request)

    def _act(self, request: ActRequest) -> ActResponse:
        self.last_receipt = None
        self.attempt_receipts = []
        request = ActRequest.from_mapping(request.to_dict())
        policy = request.metadata.get("model_execution_policy")
        output = policy.get("output", {}) if isinstance(policy, dict) else {}
        requested = output.get("max_tokens") if output.get("mode") == "bounded" else None
        if (requested is not None and self.max_output_tokens is not None
                and requested != self.max_output_tokens):
            raise ProviderCallError(
                "request and adapter operator output policies conflict; no request submitted",
                error_kind="provider_request_rejected", provider=self.provider, model=self.model,
            )
        self._request_max_output_tokens = (
            requested if requested is not None else self.max_output_tokens
        )
        self._reasoning_enabled = _reasoning_enabled_for_request(
            self.runtime_config,
            self.capabilities,
            request,
        )
        key_error = None
        try:
            api_key = provider_key(self.api_key_env)
        except ValueError as exc:
            api_key = None
            key_error = str(exc)
        if not api_key:
            self._remember_receipt(
                _failure_receipt(
                    provider=self.provider,
                    model=self.model,
                    agent_id=str(self.id),
                    agent_version=self.version,
                    turn_id=request.turn_id,
                    outcome="provider_auth_failed",
                    usage_unavailable_reason=(
                        "provider_not_called_invalid_api_key"
                        if key_error
                        else "provider_not_called_missing_api_key"
                    ),
                    runtime_config=self.runtime_config,
                )
            )
            raise ProviderCallError(
                key_error or f"missing API key environment variable {self.api_key_env}",
                error_kind="provider_auth_failed",
                provider=self.provider,
                model=self.model,
            )
        prompt = _provider_prompt(
            request, history_window_turns=(
                self.runtime_config.history_window_turns if self.runtime_config else None
            ),
        )
        parse_error: ProtocolError | None = None
        provider_attempt = 0
        for parse_attempt in range(1 + (self.runtime_config.action_repair_attempts
                                        if self.runtime_config else 0)):
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
                    # A timeout does not prove remote work stopped or was rejected.
                    # Never replay it automatically, even with optional safe retries.
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
                failed_receipt: dict[str, Any] = self.last_receipt or {}
                self._replace_last_receipt(
                    {
                        **failed_receipt,
                        "outcome": "action_response_unparseable",
                        "usage_unavailable_reason": failed_receipt.get("usage_unavailable_reason"),
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

    def _receipt_snapshot(self, invocation: object) -> list[dict[str, Any]]:
        batch = self._receipt_batch
        if batch is None or batch[0] is not invocation:
            return []
        return copy.deepcopy(list(batch[1]))

    def _publish_receipts(self, receipts: list[dict[str, Any]]) -> None:
        batch = self._receipt_batch
        invocation = current_receipt_invocation()
        if batch is None or (invocation is not None and batch[0] is not invocation):
            return
        # One immutable-reference transfer precedes convenience-field updates.
        self._receipt_batch = (batch[0], tuple(copy.deepcopy(receipts)))

    def _remember_receipt(self, receipt: dict[str, Any]) -> None:
        receipts = [*self.attempt_receipts, receipt]
        self._publish_receipts(receipts)
        self.attempt_receipts = receipts
        self.last_receipt = receipt

    def _replace_last_receipt(self, receipt: dict[str, Any]) -> None:
        receipts = [*self.attempt_receipts[:-1], receipt]
        self._publish_receipts(receipts)
        self.attempt_receipts = receipts
        self.last_receipt = receipt

    def _call_provider(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        if self.provider == "arcee-ai":
            from eslams.providers.arcee import call

            return call(self, api_key, prompt)
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
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {"role": "developer", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            "max_output_tokens": self._effective_max_output_tokens(),
        }
        effort = self.runtime_config.reasoning_effort if self.runtime_config else None
        reasoning = {"effort": effort} if effort is not None else None
        # An explicit endpoint control is not a claim about catalogue membership.
        # Forward it unchanged; authoritative endpoint rejection retains its receipt.
        if self.temperature is not None and self.capabilities.supports_temperature:
            payload["temperature"] = self.temperature
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
            _check_provider_completion(
                data, provider="openai", model=self.model,
                response=response, receipt=receipt,
            )
            text = _openai_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_anthropic(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        max_output_tokens = self._effective_max_output_tokens()
        if max_output_tokens is None:
            max_output_tokens = self.capabilities.max_output_tokens
            if max_output_tokens is None or not self.capabilities.sources:
                raise ProviderCallError(
                    "Anthropic requires max_tokens; no verified maximum is available. "
                    "Supply an operator limit or a verified capability record.",
                    error_kind="provider_request_rejected",
                    provider=self.provider, model=self.model,
                )
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
        elif (self.temperature is not None and self.capabilities.supports_temperature
              and thinking_mode != "adaptive"):
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
            _check_provider_completion(
                data, provider="anthropic", model=self.model,
                response=response, receipt=receipt,
            )
            text = _anthropic_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _call_gemini(self, api_key: str, prompt: str) -> tuple[str, dict[str, Any]]:
        generation_config: dict[str, Any] = {"maxOutputTokens": self._effective_max_output_tokens()}
        if self.temperature is not None and self.capabilities.supports_temperature:
            generation_config["temperature"] = self.temperature
        if self._reasoning_enabled:
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
            _check_provider_completion(
                data, provider=self.provider, model=self.model,
                response=response, receipt=receipt,
            )
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
        if self.temperature is not None and self.capabilities.supports_temperature:
            payload["temperature"] = self.temperature
        runtime = self.runtime_config
        # Emit even without an order: upstream defaults must not silently turn
        # forbidden fallback on. An absent route order is not a verified pin.
        payload["provider"] = {"allow_fallbacks": False}
        if runtime and runtime.openrouter_provider_order:
            payload["provider"]["order"] = list(runtime.openrouter_provider_order)
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
            _check_provider_completion(
                data, provider="openrouter", model=self.model,
                response=response, receipt=receipt,
            )
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
        if self.temperature is not None and self.capabilities.supports_temperature:
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
            _check_provider_completion(
                data, provider="bedrock", model=self.model,
                response=response, receipt=receipt,
            )
            text = _bedrock_text(data)
        except ProviderCallError as exc:
            exc.receipt = {**receipt, "outcome": exc.error_kind}
            raise
        return text, receipt

    def _effective_max_output_tokens(self) -> int | None:
        return self._request_max_output_tokens

    def _reasoning_budget_tokens(self, *, max_tokens: int) -> int:
        configured = self.runtime_config.reasoning_budget_tokens if self.runtime_config else None
        if configured is None:
            raise ProviderCallError(
                "This provider manual-thinking mode requires an explicit finite budget; "
                "select a supported provider-native/adaptive mode or caller policy",
                error_kind="provider_request_rejected", provider=self.provider, model=self.model,
            )
        budget = configured
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
        with action_deadline(request.time_budget_ms):
            return self._act(request)

    def _act(self, request: ActRequest) -> ActResponse:
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


def _reasoning_enabled_for_request(
    runtime_config: ProviderRuntimeConfig | None,
    capabilities: ModelCapabilities,
    request: ActRequest,
) -> bool:
    mode = runtime_config.reasoning if runtime_config is not None else "auto"
    if mode == "disabled":
        return False
    if mode == "enabled" and capabilities.supports_reasoning:
        return True
    # Native defaults belong to the provider; neither arena labels nor a
    # catalogue's recommended effort should silently select reasoning policy.
    return bool(runtime_config and (
        runtime_config.reasoning_effort is not None
        or runtime_config.reasoning_budget_tokens is not None
        or runtime_config.gemini_thinking_budget is not None
    ))


def _provider_prompt(
    request: ActRequest, *, history_window_turns: int | None = None,
) -> str:
    payload = {
        "arena": request.arena.to_dict(),
        "active_player": request.active_player,
        "observation": request.observation,
        "legal_actions": request.legal_actions,
        "action_schema": request.action_schema,
        "history": (request.history if history_window_turns is None
                    else request.history[-history_window_turns:]),
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
    check_cancelled()
    # None removes only framework limits; omitted wire parameters retain
    # genuine provider defaults/constraints, whose actual ceiling may be unknown.
    payload = {key: value for key, value in payload.items() if value is not None}
    for group in ("generationConfig", "inferenceConfig"):
        if isinstance(payload.get(group), dict):
            payload[group] = {
                key: value for key, value in payload[group].items() if value is not None
            }
    timeout_ms = runtime_config.timeout_ms if runtime_config else None
    deadline = time.monotonic() + timeout_ms / 1000 if timeout_ms is not None else None
    action = current_deadline()
    if action is not None:
        deadline = min(deadline, action) if deadline is not None else action
    with _provider_runtime_guard(runtime_config, control_key, deadline=deadline):
        try:
            response = bounded_post(
                url,
                headers=headers,
                json=payload,
                timeout=_httpx_timeout(runtime_config, deadline=deadline),
            )
        except ExecutionCancelled:
            raise
        except ProtocolError as exc:
            _raise_observed_transport_failure(
                exc, "provider_response_schema_mismatch", provider, model, runtime_config,
            )
            raise ProviderCallError(
                str(exc),
                error_kind="provider_response_schema_mismatch",
                provider=provider,
                model=model,
            ) from exc
        except httpx.TimeoutException as exc:
            _raise_observed_transport_failure(
                exc, "provider_timeout", provider, model, runtime_config,
            )
            raise TimeoutError("provider timed out") from exc
        except httpx.HTTPError as exc:
            _raise_observed_transport_failure(
                exc, "provider_transport_error", provider, model, runtime_config,
            )
            raise ProviderCallError(
                "provider transport request failed",
                error_kind="provider_transport_error",
                provider=provider,
                model=model,
            ) from exc
    if response.status_code >= 400:
        kind = _provider_error_kind(response.status_code)
        retry_after = _retry_after_seconds(response)
        receipt = _failure_receipt(
            provider=provider, model=model, agent_id="", agent_version="", turn_id=0,
            outcome=kind, usage_unavailable_reason="provider_error_usage_unverified",
            runtime_config=runtime_config, status_code=response.status_code,
            retry_after_seconds=retry_after,
        )
        body_retry_permitted = _capture_error_body_observations(
            response, provider=provider, receipt=receipt,
        )
        receipt["request_id"] = _http_error_identifier(
            response.headers.get("x-request-id") or response.headers.get("request-id")
            or response.headers.get("x-amzn-requestid"),
        )
        receipt["gateway_request_id"] = _http_error_identifier(
            response.headers.get("cf-aig-request-id")
            or response.headers.get("x-gateway-request-id"),
        )
        raise ProviderCallError(
            f"provider returned HTTP {response.status_code}",
            status_code=response.status_code, error_kind=kind,
            retry_after_seconds=retry_after, provider=provider, model=model, receipt=receipt,
            retry_permitted=body_retry_permitted,
        )
    return response


def _strict_provider_json(response: httpx.Response) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate provider JSON field")
            result[key] = value
        return result
    return json.loads(response.content, object_pairs_hook=unique_pairs)


def _safe_rate_rejection(data: Any, status: int) -> bool:
    # Deliberately narrow: unknown extensions, malformed observations and an
    # incomplete/unparseable body cannot establish a safe rejection to replay.
    if status not in {200, 429} or not isinstance(data, dict):
        return False
    error = data.get("error")
    if not isinstance(error, dict):
        return False
    supplied = [
        _body_error_status({key: error[key]}) for key in ("code", "type") if key in error
    ]
    # Display classification may have precedence; safe replay requires every
    # supplied classifier to independently establish the same rejection.
    return bool(supplied) and all(value == 429 for value in supplied) and not (
        set(data) - {"error", "type", "status"}
        or data.get("status") not in (None, "failed")
        or data.get("type") not in (None, "error")
        or set(error) - {"code", "type", "message", "param"}
        or any(error.get(key) is not None and not isinstance(error[key], str)
               for key in ("type", "message", "param"))
    )


def _capture_error_body_observations(
    response: httpx.Response, *, provider: str, receipt: dict[str, Any],
) -> bool:
    provenance: dict[str, Any] = {
        "schema_version": "eslams.native-error-provenance.v1",
        "source": "unverified_provider_error_body", "accounting_status": "quarantined",
        "model_identity_status": "unverified", "body_status": "unparseable",
    }
    receipt["pricing_provenance"] = provenance
    try:
        data = _strict_provider_json(response)
        validate_json_payload(data)
        if not isinstance(data, dict):
            return False
    except (ValueError, UnicodeError, RecursionError):
        return False
    provenance["body_status"] = "bounded_json_object"
    usages: list[Any] = []
    identities: list[Any] = []
    costs: list[Any] = []
    # Only documented envelope positions are custody sources. Never descend
    # through prompt/response/content/message payloads to harvest telemetry.
    nodes: list[dict[str, Any]] = [data]
    error = data.get("error")
    if isinstance(error, dict):
        nodes.append(error)
        if isinstance(error.get("metadata"), dict):
            nodes.append(error["metadata"])
    choices = data.get("choices")
    if isinstance(choices, list):
        nodes.extend(choice["error"] for choice in choices
                     if isinstance(choice, dict) and isinstance(choice.get("error"), dict))
    for node in nodes:
        for key in ("id", "responseId", "provider_response_id", "generation_id"):
            if key in node:
                identities.append(node[key])
        for key in ("usage", "usageMetadata"):
            if key in node:
                usages.append(node[key])
        for key in ("cost", "cost_usd", "total_cost", "total_cost_usd"):
            if key in node:
                costs.append(node[key])
    for usage in usages:
        if isinstance(usage, dict):
            for key in ("cost", "cost_usd", "total_cost", "total_cost_usd"):
                if key in usage:
                    costs.append(usage[key])
    provenance["work_observation_present"] = bool(identities or usages or costs)
    safe_ids = [_http_error_identifier(value) for value in identities]
    if safe_ids and all(value is not None and value == safe_ids[0] for value in safe_ids):
        receipt["provider_response_id"] = safe_ids[0]
    if usages:
        provenance["usage_observation_status"] = "conflicting_or_malformed"
        if len(usages) == 1 and isinstance(usages[0], dict):
            usage = _normalize_usage(provider, usages[0])
            if not usage.get("usage_validation_errors") and _normalized_usage_has_tokens(usage):
                receipt["usage"] = usage
                receipt["usage_unavailable_reason"] = None
                provenance["usage_observation_status"] = "normalized_unverified"
    if costs:
        provenance["cost_observation_status"] = "conflicting_or_malformed"
        values = [_optional_float(value) for value in costs]
        if values and all(value is not None and value == values[0] for value in values):
            provenance["observed_cost_usd"] = values[0]
            provenance["cost_observation_status"] = "reported_unverified"
    # Error-body pricing never supplies a trusted rate card or a measured cost.
    # Quoted observations remain diagnostic; canonical cost stays unknown.
    return (_safe_rate_rejection(data, response.status_code)
            and not provenance["work_observation_present"])


def _raise_observed_transport_failure(
    exc: BaseException, kind: str, provider: str, model: str,
    runtime_config: ProviderRuntimeConfig | None,
) -> None:
    observed = response_observation(exc)
    if observed is None:
        return
    headers = dict(observed.headers)
    receipt = _failure_receipt(
        provider=provider, model=model, agent_id="", agent_version="", turn_id=0,
        outcome=kind, usage_unavailable_reason="response_body_not_verified",
        runtime_config=runtime_config, status_code=observed.status_code,
    )
    receipt["request_id"] = _http_error_identifier(
        headers.get("x-request-id") or headers.get("request-id")
        or headers.get("x-amzn-requestid"),
    )
    receipt["gateway_request_id"] = _http_error_identifier(
        headers.get("cf-aig-request-id") or headers.get("x-gateway-request-id"),
    )
    # An observed error status does not make an incomplete response safely
    # retryable. No body, generation, token or cost claim is inferred here.
    raise ProviderCallError(
        "provider response body could not be verified", error_kind=kind,
        status_code=observed.status_code, provider=provider, model=model, receipt=receipt,
    ) from exc


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
    # max_retries is a maximum for definitive rejection, not permission to
    # replay an ambiguous timeout, gateway5xx or accepted generation.
    if (not exc.retry_permitted or exc.status_code != 429
            or exc.error_kind != "provider_rate_limited"):
        return False
    receipt = exc.receipt or {}
    if receipt.get("provider_response_id") or receipt.get("usage"):
        return False
    cost = receipt.get("estimated_cost")
    return not (isinstance(cost, dict) and cost.get("status") == "ok")


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
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
    *, deadline: float | None = None,
) -> Iterator[None]:
    _reserve_rate_slot(runtime_config, control_key, deadline=deadline)
    semaphore = _provider_semaphore(runtime_config, control_key)
    while True:
        check_cancelled()
        remaining = remaining_seconds(deadline)
        if semaphore.acquire(timeout=0.1 if remaining is None else min(0.1, remaining)):
            break
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
    *, deadline: float | None = None,
) -> None:
    rate_limit = runtime_config.rate_limit_per_minute if runtime_config else None
    if rate_limit is None or rate_limit <= 0:
        return
    interval_seconds = 60.0 / rate_limit
    with _PROVIDER_CONTROL_LOCK:
        now = time.monotonic()
        reserved_at = max(now, _PROVIDER_RATE_RESERVATIONS.get(control_key, 0.0))
        if deadline is not None and reserved_at >= deadline:
            raise TimeoutError("provider rate-limit wait exceeds the action deadline")
        _PROVIDER_RATE_RESERVATIONS[control_key] = reserved_at + interval_seconds
    delay = reserved_at - now
    if delay > 0:
        sleep_with_cancellation(delay)


def _httpx_timeout(
    runtime_config: ProviderRuntimeConfig | None, *, deadline: float | None = None,
) -> httpx.Timeout:
    total_ms = runtime_config.timeout_ms if runtime_config else None
    limit = deadline
    if limit is None and total_ms is not None:
        limit = time.monotonic() + total_ms / 1000
    connect = runtime_config.connect_timeout_ms / 1000 if runtime_config else 10.0
    read_ms = runtime_config.read_timeout_ms if runtime_config else None
    read = read_ms / 1000 if read_ms is not None else None
    if limit is None:
        return httpx.Timeout(None, connect=connect, read=read, write=connect, pool=None)
    seconds = remaining_seconds(limit)
    return TotalTimeout(seconds, connect=connect, read=read if read is not None else seconds,
                        deadline=limit)


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
        if not math.isfinite(retry_after_seconds) or retry_after_seconds < 0:
            raise ValueError("Retry-After must be finite and non-negative")
        deadline = current_deadline()
        if deadline is not None and retry_after_seconds >= remaining_seconds(deadline):
            raise TimeoutError("provider retry delay exceeds the action deadline")
        sleep_with_cancellation(retry_after_seconds)
        return
    if runtime_config is None or runtime_config.retry_backoff_ms <= 0:
        return
    delay = runtime_config.retry_backoff_ms / 1000
    if runtime_config.retry_jitter:
        delay *= random.uniform(0.5, 1.5)
    deadline = current_deadline()
    if deadline is not None and delay >= remaining_seconds(deadline):
        raise TimeoutError("configured retry delay exceeds the action deadline")
    sleep_with_cancellation(delay)


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
        "locked_model_id": _http_error_identifier(resolved_model),
        "model_identity_source": (
            model_identity_source
            if (_http_error_identifier(resolved_model) is not None
                and model_identity_source is not None)
            else "provider_response"
            if _http_error_identifier(resolved_model) is not None
            else None
        ),
        "endpoint_kind": _endpoint_kind(provider),
        "parser_version": _parser_version(provider),
        "outcome": "ok",
        "model_capability_known": capabilities.known,
        "game_agent_supported": capabilities.game_agent_supported,
        "capability_sources": list(capabilities.sources),
        "provider_response_id": _http_error_identifier(provider_response_id),
        "status_code": response.status_code,
        "request_id": _http_error_identifier(response.headers.get("x-request-id")
        or response.headers.get("request-id")
        or response.headers.get("x-cloud-trace-context")),
        "gateway_mode": runtime_config.gateway_mode if runtime_config else "disabled",
        "gateway_request_id": _http_error_identifier(response.headers.get("cf-aig-request-id")
        or response.headers.get("x-gateway-request-id")),
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
            round(min(retry_after_seconds, 86_400.0) * 1000)
            if retry_after_seconds is not None
            else None
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
        "arcee-ai": "arcee_chat_completions",
    }.get(provider, "unknown")


def _parser_version(provider: str) -> str:
    return {
        "openai": "openai-responses-raw-v2",
        "anthropic": "anthropic-messages-raw-v2",
        "gemini": "gemini-generate-content-raw-v2",
        "google": "gemini-generate-content-raw-v2",
        "openrouter": "openrouter-chat-completions-raw-v1",
        "bedrock": "bedrock-converse-raw-v1",
        "arcee-ai": "arcee-chat-completions-raw-v1",
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
        try:
            numeric = float(value)
        except OverflowError:
            return None
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


def _check_provider_completion(
    data: dict[str, Any], *, provider: str, model: str,
    response: httpx.Response, receipt: dict[str, Any],
) -> None:
    """Classify semantic failures before text parsing, retaining billable usage.

    Refusal, truncation, pending work and cancellation have distinct outcomes.
    No legal-looking partial text is accepted after a non-complete envelope.
    Never copy refusal prose or arbitrary provider error strings into receipts.
    """
    reason: Any = None
    status: Any = None
    error = data.get("error")
    refused = False
    if provider == "openai":
        status = data.get("status")
        details = data.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        output = data.get("output")
        refused = reason == "content_filter"
        if isinstance(output, list):
            for item in output:
                content = item.get("content") if isinstance(item, dict) else None
                if isinstance(content, list):
                    refused = refused or any(
                        isinstance(part, dict) and part.get("type") == "refusal"
                        for part in content
                    )
    elif provider == "anthropic":
        reason = data.get("stop_reason")
        details = data.get("stop_details")
        refused = reason == "refusal" or (
            isinstance(details, dict) and details.get("type") == "refusal"
        )
    elif provider in {"google", "gemini"}:
        feedback = data.get("promptFeedback")
        blocked = feedback.get("blockReason") if isinstance(feedback, dict) else None
        candidates = data.get("candidates")
        first = candidates[0] if isinstance(candidates, list) and candidates else None
        reason = first.get("finishReason") if isinstance(first, dict) else None
        if blocked is not None and blocked != "BLOCK_REASON_UNSPECIFIED":
            refused = True
            reason = blocked
        refused = refused or (isinstance(reason, str) and reason in {
            "SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
            "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION", "ESCALATION",
            "PUP_LIMITED_DISABLED",
        })
    elif provider == "openrouter":
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        if isinstance(first, dict):
            error = error or first.get("error")
            reason = first.get("finish_reason")
            message = first.get("message")
            refused = reason == "content_filter" or (
                isinstance(message, dict) and bool(message.get("refusal"))
            )
    elif provider == "bedrock":
        reason = data.get("stopReason")
        refused = isinstance(reason, str) and reason in {"guardrail_intervened", "content_filtered"}

    if (reason is not None and not isinstance(reason, str)) or (
        status is not None and not isinstance(status, str)
    ):
        receipt.update(finish_reason="unknown", finish_status="unknown")
        raise ProviderCallError(
            "provider returned malformed completion fields",
            error_kind="provider_response_schema_mismatch", provider=provider, model=model,
        )

    known_reasons = {
        "max_output_tokens", "content_filter", "steered", "refusal", "max_tokens",
        "end_turn", "stop_sequence", "tool_use", "pause_turn", "model_context_window_exceeded",
        "STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "LANGUAGE", "OTHER", "BLOCKLIST",
        "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT",
        "IMAGE_RECITATION", "ESCALATION", "PUP_LIMITED_DISABLED", "MALFORMED_FUNCTION_CALL",
        "MALFORMED_RESPONSE", "FINISH_REASON_UNSPECIFIED", "BLOCK_REASON_UNSPECIFIED",
        "stop", "length", "error", "tool_calls", "guardrail_intervened", "content_filtered",
        "malformed_model_output", "malformed_tool_use",
    }
    receipt["finish_reason"] = reason if isinstance(reason, str) and reason in known_reasons else (
        "unknown" if reason is not None else None
    )
    receipt["finish_status"] = status if isinstance(status, str) and status in {
        "completed", "failed", "incomplete", "cancelled", "queued", "in_progress"
    } else ("unknown" if status is not None else "completed" if reason is not None else None)

    if error or status == "failed" or reason == "error" or data.get("type") == "error":
        receipt["finish_status"] = "failed"
        code = _body_error_status(error)
        kind = _provider_error_kind(code) if code is not None else "provider_unavailable"
        raise ProviderCallError(
            "provider reported an error inside the response body",
            status_code=code, error_kind=kind, provider=provider, model=model,
            retry_after_seconds=_retry_after_seconds(response),
            retry_permitted=_safe_rate_rejection(data, response.status_code),
        )
    if refused:
        receipt["finish_status"] = "refused"
        raise ProviderCallError(
            "provider refused or filtered the requested action",
            error_kind="provider_refused", provider=provider, model=model,
        )
    if reason in {
        "max_output_tokens", "max_tokens", "MAX_TOKENS", "length", "model_context_window_exceeded",
    }:
        receipt["finish_status"] = "incomplete"
        raise ProviderCallError(
            "provider token/context constraint interrupted the response; no action accepted",
            error_kind="provider_output_truncated", provider=provider, model=model,
        )
    deferred_kind = (
        "provider_cancelled" if status == "cancelled" else
        "provider_pending" if status in {"queued", "in_progress"} or reason == "pause_turn" else
        "provider_interrupted" if status == "incomplete" else None
    )
    if deferred_kind is not None:
        raise ProviderCallError(
            "provider response requires cancellation/pending/interruption handling; "
            "no action accepted",
            error_kind=deferred_kind, provider=provider, model=model,
        )
    if status in {"incomplete", "cancelled", "queued", "in_progress"} or reason in {
        "max_output_tokens", "max_tokens", "MAX_TOKENS", "length",
        "model_context_window_exceeded", "steered", "tool_use", "tool_calls", "pause_turn",
        "MALFORMED_FUNCTION_CALL", "MALFORMED_RESPONSE",
        "malformed_model_output", "malformed_tool_use",
    }:
        receipt["finish_status"] = "incomplete"
        detail = receipt["finish_reason"] or receipt["finish_status"]
        raise ProviderCallError(
            f"provider response is incomplete ({detail}); no action accepted",
            error_kind="provider_request_rejected", provider=provider, model=model,
        )


def _body_error_status(error: Any) -> int | None:
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    if isinstance(code, int) and not isinstance(code, bool) and 400 <= code <= 599:
        return code
    metadata = error.get("metadata")
    kind = error.get("type") or error.get("code") or (
        metadata.get("error_type") if isinstance(metadata, dict) else None
    )
    codes = {
        "authentication_error": 401, "invalid_api_key": 401, "permission_error": 403,
        "rate_limit_error": 429, "rate_limit_exceeded": 429,
        "overloaded_error": 529, "api_error": 500, "server_error": 500, "server": 500,
        "internal_error": 500, "timeout_error": 504, "timeout": 504,
        "not_found_error": 404, "invalid_request_error": 400,
    }
    return codes.get(kind) if isinstance(kind, str) else None


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
                "request_id": _http_error_identifier(response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or response.headers.get("x-cloud-trace-context")
                or response.headers.get("x-amzn-requestid")),
                "gateway_request_id": _http_error_identifier(
                    response.headers.get("cf-aig-request-id")
                    or response.headers.get("x-gateway-request-id")),
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
        payload = _strict_provider_json(response)
        validate_json_payload(payload)
    except (json.JSONDecodeError, ValueError, UnicodeError, RecursionError) as exc:
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
