"""Provider runtime and receipt contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import PROVIDER_RECEIPT_SCHEMA_VERSION

PROVIDER_OUTCOMES: tuple[str, ...] = (
    "ok",
    "provider_error",
    "provider_network_error",
    "provider_auth_error",
    "provider_rate_limited",
    "provider_invalid_request",
    "provider_timeout",
    "parse_error",
    "no_action",
    "gateway_auth_failed",
    "unavailable",
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
        }


@dataclass(frozen=True)
class ProviderReceipt:
    provider: str
    model: str
    agent_id: str
    turn_id: int
    outcome: str
    locked_model_id: str | None = None
    agent_version: str | None = None
    attempt: int = 1
    status_code: int | None = None
    request_id: str | None = None
    gateway_mode: str = "disabled"
    gateway_request_id: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    usage_unavailable_reason: str | None = None
    pricing: dict[str, Any] = field(default_factory=dict)
    estimated_cost: dict[str, Any] = field(default_factory=dict)
    redaction_version: str = "provider-receipt-redaction-v1"
    schema_version: str = PROVIDER_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "locked_model_id": self.locked_model_id,
            "agent_id": self.agent_id,
            "agent_version": self.agent_version,
            "turn_id": self.turn_id,
            "attempt": self.attempt,
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
            "redaction_version": self.redaction_version,
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        PROVIDER_RECEIPT_SCHEMA_VERSION: ProviderReceipt(
            provider="mock",
            model="mock-legal-action",
            agent_id="mock-agent",
            turn_id=0,
            outcome="ok",
            usage={
                "input_tokens": 12,
                "output_tokens": 3,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 15,
            },
            pricing={"status": "cost_unavailable", "source": "mock"},
            estimated_cost={"status": "cost_unavailable"},
        ).to_dict()
    }
