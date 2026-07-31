"""Provider runtime and receipt contracts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

from eslams.contracts.integrity import ATTEMPT_KINDS
from eslams.contracts.pricing import PriceCardReference, validate_price_card_reference
from eslams.contracts.versions import (
    PROVIDER_ATTEMPT_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
)
from eslams.hashing import sha256_json

PROVIDER_OUTCOMES: tuple[str, ...] = (
    "ok",
    "provider_transport_error",
    "provider_request_rejected",
    "provider_response_schema_mismatch",
    "action_response_unparseable",
    "action_not_legal",
    "arena_apply_error",
    "provider_auth_failed",
    "provider_permission_failed",
    "provider_rate_limited",
    "provider_timeout",
    "provider_unavailable",
    "no_action",
    "gateway_auth_failed",
    "unavailable",
)

_SENSITIVE_PUBLIC_KEYS = {
    "api_key",
    "apikey",
    "access_key",
    "access_key_id",
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
_BEARER_VALUE_RE = re.compile(r"(?i)\bbearer\s+([^\s,;]+)")

# Core 0.6 reads historical 0.5 artifacts but never emits these values.
LEGACY_PROVIDER_OUTCOMES: tuple[str, ...] = (
    "provider_error",
    "provider_network_error",
    "provider_auth_error",
    "provider_invalid_request",
    "parse_error",
)
READ_COMPATIBLE_PROVIDER_OUTCOMES: tuple[str, ...] = (
    *PROVIDER_OUTCOMES,
    *LEGACY_PROVIDER_OUTCOMES,
)

GATEWAY_MODES: tuple[str, ...] = (
    "disabled",
    "generic_base_url",
    "platform_gateway",
    "direct_provider",
)

GATEWAY_AUTH_MODES: tuple[str, ...] = (
    "disabled",
    "provided_header",
    "platform_owned",
    "unknown",
)


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    timeout_ms: int = 60_000
    connect_timeout_ms: int = 10_000
    read_timeout_ms: int = 60_000
    max_retries: int = 0
    retry_backoff_ms: int = 250
    concurrency_limit: int = 1
    rate_limit_per_minute: int | None = None
    gateway_base_url: str | None = None
    gateway_mode: str = "direct_provider"
    gateway_auth_mode: str = "disabled"
    reasoning_budget_tokens: int | None = None
    gemini_thinking_budget: int | None = None
    reasoning: Literal["disabled", "enabled", "auto"] = "auto"
    openrouter_provider_order: tuple[str, ...] = ()
    openrouter_allow_fallbacks: bool = False
    bedrock_region: str = "us-east-1"
    rate_card_id: str | None = None
    rate_card_reference: PriceCardReference | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("timeout_ms", self.timeout_ms),
            ("connect_timeout_ms", self.connect_timeout_ms),
            ("read_timeout_ms", self.read_timeout_ms),
            ("concurrency_limit", self.concurrency_limit),
        ):
            if isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name, value in (
            ("max_retries", self.max_retries),
            ("retry_backoff_ms", self.retry_backoff_ms),
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.rate_limit_per_minute is not None and (
            isinstance(self.rate_limit_per_minute, bool) or self.rate_limit_per_minute < 1
        ):
            raise ValueError("rate_limit_per_minute must be a positive integer or null")
        if self.gateway_mode not in GATEWAY_MODES:
            raise ValueError(f"unsupported gateway_mode {self.gateway_mode!r}")
        if self.gateway_auth_mode not in GATEWAY_AUTH_MODES:
            raise ValueError(f"unsupported gateway_auth_mode {self.gateway_auth_mode!r}")
        if self.reasoning not in {"disabled", "enabled", "auto"}:
            raise ValueError(f"unsupported reasoning mode {self.reasoning!r}")
        if self.reasoning_budget_tokens is not None and (
            isinstance(self.reasoning_budget_tokens, bool) or self.reasoning_budget_tokens < 0
        ):
            raise ValueError("reasoning_budget_tokens must be non-negative or null")
        if self.gemini_thinking_budget is not None and (
            isinstance(self.gemini_thinking_budget, bool) or self.gemini_thinking_budget < -1
        ):
            raise ValueError("gemini_thinking_budget must be -1 or a non-negative integer")
        if any(not item.strip() for item in self.openrouter_provider_order):
            raise ValueError("openrouter_provider_order entries must be non-empty")
        if len(set(self.openrouter_provider_order)) != len(self.openrouter_provider_order):
            raise ValueError("openrouter_provider_order entries must be unique")
        if self.openrouter_allow_fallbacks:
            raise ValueError("OpenRouter provider fallback is unsupported; pin one route order")
        if not re.fullmatch(r"[a-z0-9-]+", self.bedrock_region):
            raise ValueError("bedrock_region must contain lowercase letters, digits, or hyphens")
        if (
            self.rate_card_id is not None
            and self.rate_card_reference is not None
            and self.rate_card_id != self.rate_card_reference.rate_card_id
        ):
            raise ValueError("rate_card_id must match rate_card_reference.rate_card_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout_ms": self.timeout_ms,
            "connect_timeout_ms": self.connect_timeout_ms,
            "read_timeout_ms": self.read_timeout_ms,
            "max_retries": self.max_retries,
            "retry_backoff_ms": self.retry_backoff_ms,
            "concurrency_limit": self.concurrency_limit,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "gateway_base_url": self.gateway_base_url,
            "gateway_mode": self.gateway_mode,
            "gateway_auth_mode": self.gateway_auth_mode,
            "reasoning_budget_tokens": self.reasoning_budget_tokens,
            "gemini_thinking_budget": self.gemini_thinking_budget,
            "reasoning": self.reasoning,
            "openrouter_provider_order": list(self.openrouter_provider_order),
            "openrouter_allow_fallbacks": self.openrouter_allow_fallbacks,
            "bedrock_region": self.bedrock_region,
            "rate_card_id": self.rate_card_id,
            "rate_card_reference": (
                self.rate_card_reference.to_dict() if self.rate_card_reference is not None else None
            ),
        }


@dataclass(frozen=True)
class ProviderReceipt:
    provider: str
    model: str
    agent_id: str
    turn_id: int
    outcome: str
    environment: str
    physical_run_id: str
    official_run_id: str
    model_lane_id: str
    run_job_id: str
    case_id: str | None = None
    case_attempt_index: int = 1
    shard_index: int | None = None
    locked_model_id: str | None = None
    model_identity_source: str | None = None
    endpoint_kind: str | None = None
    parser_version: str | None = None
    agent_version: str | None = None
    attempt: int = 1
    event_id: str | None = None
    logical_action_id: str | None = None
    attempt_kind: str = "primary"
    parent_attempt_id: str | None = None
    status: Literal["started", "completed", "failed"] | None = None
    status_code: int | None = None
    request_id: str | None = None
    gateway_mode: str = "disabled"
    gateway_request_id: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    usage_unavailable_reason: str | None = None
    pricing: dict[str, Any] = field(default_factory=dict)
    estimated_cost: dict[str, Any] = field(default_factory=dict)
    rate_card_reference: dict[str, Any] | None = None
    reasoning_included_in_output: bool | None = None
    usage_source: str | None = None
    usage_complete: bool = False
    cost_source: str | None = None
    cost_complete: bool = False
    wire_parse_status: str | None = None
    action_parse_status: str | None = None
    action_applied: bool = False
    case_valid_for_scoring: bool = False
    redaction_version: str = "provider-receipt-redaction-v1"
    schema_version: str = PROVIDER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        errors = provider_receipt_validation_errors(self.to_dict())
        if errors:
            raise ValueError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "locked_model_id": self.locked_model_id,
            "model_identity_source": self.model_identity_source,
            "endpoint_kind": self.endpoint_kind,
            "parser_version": self.parser_version,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "turn_id": self.turn_id,
            "environment": self.environment,
            "physical_run_id": self.physical_run_id,
            "run_id": self.physical_run_id,
            "official_run_id": self.official_run_id,
            "model_lane_id": self.model_lane_id,
            "run_job_id": self.run_job_id,
            "case_id": self.case_id,
            "case_attempt_index": self.case_attempt_index,
            "shard_index": self.shard_index,
            "attempt": self.attempt,
            "attempt_index": self.attempt,
            "event_id": self.event_id,
            "logical_action_id": self.logical_action_id,
            "attempt_kind": self.attempt_kind,
            "parent_attempt_id": self.parent_attempt_id,
            "status": self.status,
            "outcome": self.outcome,
            "status_code": self.status_code,
            "request_id": self.request_id,
            "gateway_mode": self.gateway_mode,
            "gateway_request_id": self.gateway_request_id,
            "latency_ms": self.latency_ms,
            "usage": dict(self.usage),
            "usage_unavailable_reason": self.usage_unavailable_reason,
            "pricing": dict(self.pricing),
            "estimated_cost": dict(self.estimated_cost),
            "rate_card_reference": (
                dict(self.rate_card_reference) if self.rate_card_reference is not None else None
            ),
            "rate_card_id": (
                self.rate_card_reference.get("rateCardId")
                if isinstance(self.rate_card_reference, dict)
                else None
            ),
            "reasoning_included_in_output": self.reasoning_included_in_output,
            "usage_source": self.usage_source,
            "usage_complete": self.usage_complete,
            "cost_source": self.cost_source,
            "cost_complete": self.cost_complete,
            "wire_parse_status": self.wire_parse_status,
            "action_parse_status": self.action_parse_status,
            "action_applied": self.action_applied,
            "case_valid_for_scoring": self.case_valid_for_scoring,
            "redaction_version": self.redaction_version,
        }


@dataclass(frozen=True)
class ProviderAttemptEvent:
    """Public, secret-free lifecycle event for one physical provider request."""

    event_id: str
    environment: str
    physical_run_id: str
    official_run_id: str
    model_lane_id: str
    run_job_id: str
    shard_index: int
    case_id: str | None
    case_attempt_index: int
    turn_index: int
    seat_id: str
    logical_action_id: str
    attempt_index: int
    attempt_kind: str
    provider: str
    requested_model: str
    resolved_model: str | None
    model_identity_source: str | None
    provider_endpoint: str
    status: Literal["started", "completed", "failed"]
    parent_attempt_id: str | None = None
    endpoint_kind: str | None = None
    parser_version: str | None = None
    wrapper_version: str | None = None
    gateway_request_id: str | None = None
    provider_request_id: str | None = None
    http_status: int | None = None
    error_class: str | None = None
    request_started_at: str | None = None
    request_completed_at: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    usage_complete: bool = False
    reasoning_included_in_output: bool | None = None
    usage_source: str | None = None
    estimated_cost_usd: float | None = None
    cost_source: str | None = None
    cost_complete: bool = False
    rate_card_id: str | None = None
    wire_parse_status: str | None = None
    action_parse_status: str | None = None
    action_applied: bool = False
    case_valid_for_scoring: bool = False
    schema_version: str = PROVIDER_ATTEMPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required_strings = {
            "event_id": self.event_id,
            "environment": self.environment,
            "physical_run_id": self.physical_run_id,
            "official_run_id": self.official_run_id,
            "model_lane_id": self.model_lane_id,
            "run_job_id": self.run_job_id,
            "seat_id": self.seat_id,
            "logical_action_id": self.logical_action_id,
            "provider": self.provider,
            "requested_model": self.requested_model,
            "provider_endpoint": self.provider_endpoint,
        }
        missing = [name for name, value in required_strings.items() if not value]
        if missing:
            raise ValueError(f"required provider-attempt fields are empty: {', '.join(missing)}")
        endpoint_errors = _provider_endpoint_errors(self.provider_endpoint)
        if endpoint_errors:
            raise ValueError("; ".join(endpoint_errors))
        if self.attempt_kind not in ATTEMPT_KINDS:
            raise ValueError(f"unsupported attempt_kind {self.attempt_kind!r}")
        if (
            self.case_attempt_index > 1
            and self.attempt_index == 1
            and self.attempt_kind not in {"case_retry", "action_repair"}
        ):
            raise ValueError("retried cases must begin with a case_retry attempt")
        if self.case_attempt_index == 1 and self.attempt_kind == "case_retry":
            raise ValueError("initial cases cannot use a case_retry attempt")
        if self.status not in {"started", "completed", "failed"}:
            raise ValueError(f"unsupported provider-attempt status {self.status!r}")
        for name, value in (
            ("shard_index", self.shard_index),
            ("turn_index", self.turn_index),
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, value in (
            ("case_attempt_index", self.case_attempt_index),
            ("attempt_index", self.attempt_index),
        ):
            if isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.http_status is not None and (
            isinstance(self.http_status, bool) or not 100 <= self.http_status <= 599
        ):
            raise ValueError("http_status must be an HTTP status code")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool) or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a non-negative integer")
        token_fields: dict[str, Any] = {
            "input_tokens": self.usage.get("input_tokens"),
            "cached_input_tokens": self.usage.get("cached_input_tokens"),
            "output_tokens": self.usage.get("output_tokens"),
            "reasoning_tokens": self.usage.get("reasoning_tokens"),
            "total_tokens": self.usage.get("total_tokens"),
        }
        for name, value in token_fields.items():
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or null")
        if (
            token_fields["cached_input_tokens"] is not None
            and token_fields["input_tokens"] is not None
            and token_fields["cached_input_tokens"] > token_fields["input_tokens"]
        ):
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if (
            self.reasoning_included_in_output is True
            and token_fields["reasoning_tokens"] is not None
            and token_fields["output_tokens"] is not None
            and token_fields["reasoning_tokens"] > token_fields["output_tokens"]
        ):
            raise ValueError("inclusive reasoning_tokens cannot exceed output_tokens")
        if self.usage_complete and (
            token_fields["input_tokens"] is None
            or token_fields["output_tokens"] is None
            or token_fields["total_tokens"] is None
            or not isinstance(self.reasoning_included_in_output, bool)
            or not self.usage_source
        ):
            raise ValueError(
                "complete usage requires coherent tokens, reasoning inclusion, and usage_source"
            )
        if self.usage_complete:
            input_tokens = int(token_fields["input_tokens"])
            output_tokens = int(token_fields["output_tokens"])
            reasoning_tokens = int(token_fields["reasoning_tokens"] or 0)
            expected_total = input_tokens + output_tokens
            if self.reasoning_included_in_output is False:
                expected_total += reasoning_tokens
            if token_fields["total_tokens"] != expected_total:
                raise ValueError("complete usage has incoherent total_tokens")
        if self.estimated_cost_usd is not None and (
            isinstance(self.estimated_cost_usd, bool)
            or not math.isfinite(self.estimated_cost_usd)
            or self.estimated_cost_usd < 0
        ):
            raise ValueError("estimated_cost_usd must be finite and non-negative")
        if self.cost_complete and (
            self.estimated_cost_usd is None or not self.cost_source or not self.rate_card_id
        ):
            raise ValueError(
                "complete cost requires estimated_cost_usd, cost_source, and rate_card_id"
            )
        if not self.request_started_at:
            raise ValueError("request_started_at is required")
        if self.status == "started":
            if self.request_completed_at is not None or self.latency_ms is not None:
                raise ValueError("started events cannot have terminal timing")
            if self.action_applied or self.case_valid_for_scoring:
                raise ValueError("started events cannot be applied or scoring-valid")
            if self.error_class is not None or self.http_status is not None:
                raise ValueError("started events cannot contain terminal status or error")
            if (
                self.usage_complete
                or self.cost_complete
                or any(value is not None for value in token_fields.values())
                or self.reasoning_included_in_output is not None
                or self.usage_source is not None
                or self.estimated_cost_usd is not None
                or self.cost_source is not None
                or self.rate_card_id is not None
            ):
                raise ValueError("started events cannot contain terminal usage or cost")
            if self.resolved_model is not None and (
                self.model_identity_source != "pinned_endpoint"
                or self.resolved_model != self.requested_model
            ):
                raise ValueError("started events may resolve only a matching pinned endpoint")
        elif not self.request_completed_at:
            raise ValueError("terminal events require request_completed_at")
        if self.status == "failed" and not self.error_class:
            raise ValueError("failed events require error_class")
        if self.status == "completed" and self.error_class is not None:
            raise ValueError("completed events cannot have error_class")
        if self.action_applied and self.status != "completed":
            raise ValueError("only completed requests can apply an action")
        if self.case_valid_for_scoring:
            if (
                self.status != "completed"
                or not self.action_applied
                or not self.case_id
                or not self.resolved_model
                or self.model_identity_source not in {"provider_response", "pinned_endpoint"}
                or self.wire_parse_status != "ok"
                or self.action_parse_status != "ok"
            ):
                raise ValueError(
                    "scoring-valid attempts require completed applied action, case/model "
                    "identity, and successful wire/action parsing"
                )
            if (
                self.model_identity_source == "pinned_endpoint"
                and self.resolved_model != self.requested_model
            ):
                raise ValueError("pinned endpoint model identity must match requested_model")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "environment": self.environment,
            "physicalRunId": self.physical_run_id,
            "officialRunId": self.official_run_id,
            "modelLaneId": self.model_lane_id,
            "runJobId": self.run_job_id,
            "shardIndex": self.shard_index,
            "caseId": self.case_id,
            "caseAttemptIndex": self.case_attempt_index,
            "turnIndex": self.turn_index,
            "seatId": self.seat_id,
            "logicalActionId": self.logical_action_id,
            "attemptIndex": self.attempt_index,
            "attemptKind": self.attempt_kind,
            "parentAttemptId": self.parent_attempt_id,
            "provider": self.provider,
            "requestedModel": self.requested_model,
            "resolvedModel": self.resolved_model,
            "modelIdentitySource": self.model_identity_source,
            "providerEndpoint": self.provider_endpoint,
            "endpointKind": self.endpoint_kind,
            "parserVersion": self.parser_version,
            "wrapperVersion": self.wrapper_version,
            "status": self.status,
            "gatewayRequestId": self.gateway_request_id,
            "providerRequestId": self.provider_request_id,
            "httpStatus": self.http_status,
            "errorClass": self.error_class,
            "requestStartedAt": self.request_started_at,
            "requestCompletedAt": self.request_completed_at,
            "latencyMs": self.latency_ms,
            "inputTokens": self.usage.get("input_tokens"),
            "cachedInputTokens": self.usage.get("cached_input_tokens"),
            "outputTokens": self.usage.get("output_tokens"),
            "reasoningTokens": self.usage.get("reasoning_tokens"),
            "totalTokens": self.usage.get("total_tokens"),
            "reasoningIncludedInOutput": self.reasoning_included_in_output,
            "usageSource": self.usage_source,
            "usageComplete": self.usage_complete,
            "estimatedCostUsd": self.estimated_cost_usd,
            "costSource": self.cost_source,
            "costComplete": self.cost_complete,
            "rateCardId": self.rate_card_id,
            "wireParseStatus": self.wire_parse_status,
            "actionParseStatus": self.action_parse_status,
            "actionApplied": self.action_applied,
            "caseValidForScoring": self.case_valid_for_scoring,
        }


def provider_attempt_event_id(
    *,
    physical_run_id: str,
    case_id: str | None,
    case_attempt_index: int,
    logical_action_id: str,
    attempt_index: int,
) -> str:
    """Return the stable idempotency key for one physical provider attempt."""

    if not physical_run_id or not logical_action_id:
        raise ValueError("physical_run_id and logical_action_id are required")
    if isinstance(case_attempt_index, bool) or case_attempt_index < 1:
        raise ValueError("case_attempt_index must be a positive integer")
    if isinstance(attempt_index, bool) or attempt_index < 1:
        raise ValueError("attempt_index must be a positive integer")
    return sha256_json(
        {
            "schemaVersion": PROVIDER_ATTEMPT_SCHEMA_VERSION,
            "physicalRunId": physical_run_id,
            "caseId": case_id,
            "caseAttemptIndex": case_attempt_index,
            "logicalActionId": logical_action_id,
            "attemptIndex": attempt_index,
        }
    )


def provider_receipt_validation_errors(payload: dict[str, Any]) -> list[str]:
    """Validate claims made by an emitted v2 provider receipt.

    Missing accounting may be represented as incomplete.  Contradictory or
    impossible success/scoring claims are rejected.
    """

    errors: list[str] = []
    errors.extend(f"provider receipt {error}" for error in _public_secret_errors(payload))
    provider = payload.get("provider")
    model = payload.get("model")
    if payload.get("schema_version") != PROVIDER_RECEIPT_SCHEMA_VERSION:
        errors.append("provider receipt schema_version is unsupported")
    required_strings = {
        "provider": provider,
        "model": model,
        "environment": payload.get("environment"),
        "physical_run_id": payload.get("physical_run_id"),
        "run_id": payload.get("run_id"),
        "official_run_id": payload.get("official_run_id"),
        "model_lane_id": payload.get("model_lane_id"),
        "run_job_id": payload.get("run_job_id"),
        "agent_id": payload.get("agent_id"),
        "event_id": payload.get("event_id"),
        "logical_action_id": payload.get("logical_action_id"),
    }
    for name, value in required_strings.items():
        if not isinstance(value, str) or not value:
            errors.append(f"provider receipt {name} is required")
    if payload.get("run_id") != payload.get("physical_run_id"):
        errors.append("provider receipt run_id must equal physical_run_id")
    if payload.get("outcome") not in PROVIDER_OUTCOMES:
        errors.append("provider receipt outcome is unsupported")
    for name in ("case_attempt_index", "attempt", "attempt_index"):
        value = payload.get(name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 1
        ):
            errors.append(f"provider receipt {name} must be a positive integer")
    for name in ("turn_id", "shard_index", "latency_ms"):
        value = payload.get(name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            errors.append(f"provider receipt {name} must be a non-negative integer")
    status_code = payload.get("status_code")
    if status_code is not None and (
        not isinstance(status_code, int)
        or isinstance(status_code, bool)
        or not 100 <= status_code <= 599
    ):
        errors.append("provider receipt status_code must be an HTTP status code")
    attempt_kind = payload.get("attempt_kind")
    if attempt_kind not in ATTEMPT_KINDS:
        errors.append("provider receipt attempt_kind is unsupported")
    case_attempt_index = payload.get("case_attempt_index")
    attempt_index = payload.get("attempt_index")
    if (
        isinstance(case_attempt_index, int)
        and not isinstance(case_attempt_index, bool)
        and case_attempt_index > 1
        and attempt_index == 1
        and attempt_kind not in {"case_retry", "action_repair"}
    ):
        errors.append("provider receipt retried case must begin with case_retry")
    if case_attempt_index == 1 and attempt_kind == "case_retry":
        errors.append("provider receipt initial case cannot use case_retry")
    status = payload.get("status")
    if status not in {"started", "completed", "failed"}:
        errors.append("provider receipt status is unsupported")
    outcome = payload.get("outcome")
    if (outcome == "ok" and status != "completed") or (
        outcome != "ok" and status == "completed"
    ):
        errors.append("provider receipt status contradicts outcome")
    if outcome == "ok" and status_code is not None and not 200 <= status_code <= 299:
        errors.append("provider receipt ok outcome contradicts HTTP status")
    for name in ("wire_parse_status", "action_parse_status"):
        if payload.get(name) not in {"ok", "failed", "not_attempted"}:
            errors.append(f"provider receipt {name} is unsupported")

    usage = payload.get("usage")
    usage_claim = payload.get("usage_complete") is True
    usage_errors = _normalized_usage_errors(usage, require_complete=usage_claim)
    if usage_errors:
        errors.extend(f"provider receipt {error}" for error in usage_errors)
    if usage_claim and not payload.get("usage_source"):
        errors.append("provider receipt complete usage requires usage_source")
    if isinstance(usage, dict):
        receipt_reasoning_inclusion = payload.get("reasoning_included_in_output")
        usage_reasoning_inclusion = usage.get("reasoning_included_in_output")
        if (
            (usage_claim or receipt_reasoning_inclusion is not None)
            and receipt_reasoning_inclusion != usage_reasoning_inclusion
        ):
            errors.append("provider receipt reasoning inclusion contradicts normalized usage")
        receipt_usage_source = payload.get("usage_source")
        usage_source = usage.get("usage_source")
        if (
            usage_claim or receipt_usage_source is not None
        ) and receipt_usage_source != usage_source:
            errors.append("provider receipt usage_source contradicts normalized usage")

    estimated_cost = payload.get("estimated_cost")
    cost_value = (
        estimated_cost.get("cost_usd") if isinstance(estimated_cost, dict) else None
    )
    if cost_value is not None and (
        isinstance(cost_value, bool)
        or not isinstance(cost_value, (int, float))
        or not math.isfinite(float(cost_value))
        or float(cost_value) < 0
    ):
        errors.append("provider receipt cost_usd must be finite and non-negative")
    cost_claim = payload.get("cost_complete") is True
    reference = payload.get("rate_card_reference")
    estimated_cost_source = (
        estimated_cost.get("source") if isinstance(estimated_cost, dict) else None
    )
    if (
        payload.get("cost_source") is not None
        and estimated_cost_source is not None
        and payload.get("cost_source") != estimated_cost_source
    ):
        errors.append("provider receipt cost_source contradicts estimated cost")
    if (
        isinstance(reference, dict)
        and payload.get("rate_card_id") is not None
        and payload.get("rate_card_id") != reference.get("rateCardId")
    ):
        errors.append("provider receipt rate_card_id contradicts price-card reference")
    if cost_claim and (
        cost_value is None
        or not payload.get("cost_source")
        or not validate_price_card_reference(reference)
        or not isinstance(reference, dict)
        or reference.get("provider") != provider
        or reference.get("model") != model
    ):
        errors.append(
            "provider receipt complete cost requires value/source and matching price-card reference"
        )

    resolved_model = payload.get("locked_model_id")
    identity_source = payload.get("model_identity_source")
    trusted_identity_sources = {"provider_response", "pinned_endpoint"}
    if provider == "mock":
        trusted_identity_sources.add("mock_attested")
    if (resolved_model is None) != (identity_source is None) or identity_source is not None and (
        not isinstance(resolved_model, str)
        or not resolved_model
        or identity_source not in trusted_identity_sources
    ):
        errors.append("provider receipt model identity is incomplete")
    if (
        identity_source == "pinned_endpoint"
        and isinstance(resolved_model, str)
        and resolved_model != model
    ):
        errors.append("provider receipt pinned model identity does not match requested model")

    action_applied = payload.get("action_applied") is True
    if action_applied and (
        payload.get("outcome") != "ok"
        or status != "completed"
        or payload.get("wire_parse_status") != "ok"
        or payload.get("action_parse_status") != "ok"
    ):
        errors.append("provider receipt applied action requires completed parsed ok status")
    if payload.get("case_valid_for_scoring") is True and (
        not action_applied
        or not payload.get("case_id")
        or identity_source not in trusted_identity_sources
        or payload.get("wire_parse_status") != "ok"
        or payload.get("action_parse_status") != "ok"
    ):
        errors.append(
            "provider receipt scoring validity requires case/action/model/parse completeness"
        )
    return list(dict.fromkeys(errors))


def _provider_endpoint_errors(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, str):
        return ["provider_endpoint must be a string"]
    if any(ord(character) < 32 or character.isspace() for character in value):
        errors.append("provider_endpoint cannot contain whitespace or control characters")
        return errors
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ["provider_endpoint must be a valid absolute URI"]
    if parsed.scheme not in {"https", "mock"} or not parsed.netloc:
        errors.append("provider_endpoint must use an absolute https or mock URI")
    try:
        has_userinfo = parsed.username is not None or parsed.password is not None
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return ["provider_endpoint must be a valid absolute URI"]
    if has_userinfo:
        errors.append("provider_endpoint cannot contain userinfo credentials")
    if parsed.scheme == "https" and not hostname:
        errors.append("provider_endpoint https URI requires a hostname")
    if parsed.fragment or "#" in value:
        errors.append("provider_endpoint cannot contain a fragment")
    for key, _value in _query_pairs(parsed.query):
        if _sensitive_public_key(key):
            errors.append("provider_endpoint cannot contain sensitive query parameters")
            break
    errors.extend(_secret_string_errors(value, path="provider_endpoint"))
    return list(dict.fromkeys(errors))


def _public_secret_errors(value: Any, *, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            item_path = f"{path}.{key_text}"
            if _sensitive_public_key(key_text):
                errors.append(f"contains sensitive field at {item_path}")
                continue
            errors.extend(_public_secret_errors(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_public_secret_errors(item, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        errors.extend(_secret_string_errors(value, path=path))
    return errors


def _secret_string_errors(value: str, *, path: str) -> list[str]:
    errors: list[str] = []
    for match in _BEARER_VALUE_RE.finditer(value):
        if match.group(1) != "[REDACTED]":
            errors.append(f"contains bearer credential at {path}")
            break
    if "://" not in value:
        return errors
    try:
        parsed = urlsplit(value)
        has_userinfo = parsed.username is not None or parsed.password is not None
    except ValueError:
        return errors
    if has_userinfo:
        errors.append(f"contains URL userinfo credentials at {path}")
    for key, query_value in _query_pairs(parsed.query):
        if _sensitive_public_key(key) and query_value != "[REDACTED]":
            errors.append(f"contains sensitive URL query at {path}")
            break
    for key, fragment_value in _query_pairs(parsed.fragment):
        if _sensitive_public_key(key) and fragment_value != "[REDACTED]":
            errors.append(f"contains sensitive URL fragment at {path}")
            break
    return errors


def _query_pairs(value: str) -> list[tuple[str, str]]:
    return parse_qsl(value.replace(";", "&"), keep_blank_values=True)


def _sensitive_public_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    if normalized in _SENSITIVE_PUBLIC_KEYS:
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


def _normalized_usage_errors(value: Any, *, require_complete: bool) -> list[str]:
    if not isinstance(value, dict):
        return ["usage must be an object"]
    errors = [str(item) for item in value.get("usage_validation_errors", []) if item]
    tokens: dict[str, int | None] = {}
    for name in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        raw = value.get(name)
        if raw is not None and (
            not isinstance(raw, int) or isinstance(raw, bool) or raw < 0
        ):
            errors.append(f"{name} must be a non-negative integer")
            tokens[name] = None
        else:
            tokens[name] = raw
    required = (tokens["input_tokens"], tokens["output_tokens"], tokens["total_tokens"])
    inclusion = value.get("reasoning_included_in_output")
    if any(item is None for item in required) or not isinstance(inclusion, bool):
        if require_complete:
            errors.append("complete usage requires input/output/total and reasoning inclusion")
        input_tokens = tokens["input_tokens"]
        cached_tokens = tokens["cached_input_tokens"]
        if (
            input_tokens is not None
            and cached_tokens is not None
            and cached_tokens > input_tokens
        ):
            errors.append("cached_input_tokens exceeds input_tokens")
        return list(dict.fromkeys(errors))
    input_tokens = tokens["input_tokens"]
    output_tokens = tokens["output_tokens"]
    total_tokens = tokens["total_tokens"]
    assert input_tokens is not None and output_tokens is not None and total_tokens is not None
    if (
        tokens["cached_input_tokens"] is not None
        and tokens["cached_input_tokens"] > input_tokens
    ):
        errors.append("cached_input_tokens exceeds input_tokens")
    reasoning = tokens["reasoning_tokens"] or 0
    if inclusion and reasoning > output_tokens:
        errors.append("inclusive reasoning_tokens exceeds output_tokens")
    expected = input_tokens + output_tokens
    if not inclusion:
        expected += reasoning
    if total_tokens != expected:
        errors.append("total_tokens is incoherent")
    return list(dict.fromkeys(errors))


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        PROVIDER_RECEIPT_SCHEMA_VERSION: ProviderReceipt(
            provider="mock",
            model="mock-legal-action",
            agent_id="mock-agent",
            turn_id=0,
            outcome="ok",
            environment="example",
            physical_run_id="run_physical_example",
            official_run_id="run_example",
            model_lane_id="lane_example",
            run_job_id="job_example",
            case_id="case_001",
            event_id="sha256:example",
            logical_action_id="run_example:case_001:player_1:000000",
            status="completed",
            usage={
                "input_tokens": 12,
                "output_tokens": 3,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 15,
            },
            pricing={"status": "cost_unavailable", "source": "mock"},
            estimated_cost={"status": "cost_unavailable"},
            wire_parse_status="ok",
            action_parse_status="ok",
        ).to_dict(),
        PROVIDER_ATTEMPT_SCHEMA_VERSION: ProviderAttemptEvent(
            event_id="sha256:example",
            environment="example",
            physical_run_id="run_physical_example",
            official_run_id="run_example",
            model_lane_id="lane_example",
            run_job_id="job_example",
            shard_index=0,
            case_id="case_001",
            case_attempt_index=1,
            turn_index=0,
            seat_id="player_1",
            logical_action_id="run_example:episode_001:player_1:000000",
            attempt_index=1,
            attempt_kind="primary",
            provider="mock",
            requested_model="mock-legal-action",
            resolved_model="mock-legal-action",
            model_identity_source="pinned_endpoint",
            provider_endpoint="mock://legal-action",
            status="completed",
            request_started_at="2026-07-31T12:00:00Z",
            request_completed_at="2026-07-31T12:00:00Z",
            latency_ms=0,
            usage={
                "input_tokens": 12,
                "output_tokens": 3,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 15,
            },
            usage_complete=True,
            reasoning_included_in_output=True,
            usage_source="provider",
            estimated_cost_usd=None,
            cost_source=None,
            cost_complete=False,
            wire_parse_status="ok",
            action_parse_status="ok",
            action_applied=True,
            case_valid_for_scoring=False,
        ).to_dict(),
    }
