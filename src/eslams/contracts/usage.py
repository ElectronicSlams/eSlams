"""Usage and cost accounting contracts for Core 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import USAGE_MODEL_CALL_SCHEMA_VERSION, USAGE_SUMMARY_SCHEMA_VERSION


@dataclass(frozen=True)
class ModelUsageRecord:
    run_id: str
    game_id: str
    seat_id: str
    agent_id: str
    model_id: str
    provider: str
    turn_index: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    timestamp: str
    request_id: str | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    cost_usd: float | None = None
    usage_unavailable_reason: str | None = None
    cost_unavailable_reason: str | None = None
    schema_version: str = USAGE_MODEL_CALL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "gameId": self.game_id,
            "seatId": self.seat_id,
            "agentId": self.agent_id,
            "modelId": self.model_id,
            "provider": self.provider,
            "turnIndex": self.turn_index,
            "requestId": self.request_id,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "totalTokens": self.total_tokens,
            "latencyMs": self.latency_ms,
            "costUsd": self.cost_usd,
            "usageUnavailableReason": self.usage_unavailable_reason,
            "costUnavailableReason": self.cost_unavailable_reason,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RunUsageSummary:
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_tokens: int | None
    usage_complete: bool
    cost_complete: bool
    total_reasoning_tokens: int | None = None
    total_cached_input_tokens: int | None = None
    total_cost_usd: float | None = None
    by_seat: dict[str, Any] | None = None
    by_agent: dict[str, Any] | None = None
    by_model: dict[str, Any] | None = None
    schema_version: str = USAGE_SUMMARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "totalInputTokens": self.total_input_tokens,
            "totalOutputTokens": self.total_output_tokens,
            "totalReasoningTokens": self.total_reasoning_tokens,
            "totalCachedInputTokens": self.total_cached_input_tokens,
            "totalTokens": self.total_tokens,
            "totalCostUsd": self.total_cost_usd,
            "usageComplete": self.usage_complete,
            "costComplete": self.cost_complete,
            "bySeat": dict(self.by_seat or {}),
            "byAgent": dict(self.by_agent or {}),
            "byModel": dict(self.by_model or {}),
        }


def validate_usage_summary(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schemaVersion") != USAGE_SUMMARY_SCHEMA_VERSION:
        errors.append("usage.summary schemaVersion is unsupported")
    if payload.get("totalCostUsd") == 0 and payload.get("costComplete") is not True:
        errors.append("usage.summary must not report unknown cost as zero")
    for key in ("usageComplete", "costComplete"):
        if not isinstance(payload.get(key), bool):
            errors.append(f"usage.summary {key} must be boolean")
    return errors


def no_secret_example() -> dict[str, Any]:
    return RunUsageSummary(
        total_input_tokens=10,
        total_output_tokens=5,
        total_tokens=15,
        total_cost_usd=None,
        usage_complete=True,
        cost_complete=False,
        by_seat={"player_1": {"totalTokens": 15, "costUsd": None}},
    ).to_dict()
