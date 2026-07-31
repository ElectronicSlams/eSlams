"""Usage and cost accounting contracts for Core 0.6."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

from eslams.contracts.pricing import validate_price_card_reference
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
    by_provider: dict[str, Any] | None = None
    by_attempt_kind: dict[str, Any] | None = None
    by_status: dict[str, Any] | None = None
    receipt_count: int = 0
    attempt_count: int = 0
    logical_action_count: int = 0
    unavailable_reason_codes: list[str] | None = None
    rate_card_references: list[str] | None = None
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
            "byProvider": dict(self.by_provider or {}),
            "byAttemptKind": dict(self.by_attempt_kind or {}),
            "byStatus": dict(self.by_status or {}),
            "receiptCount": self.receipt_count,
            "attemptCount": self.attempt_count,
            "logicalActionCount": self.logical_action_count,
            "unavailableReasonCodes": list(self.unavailable_reason_codes or []),
            "rateCardReferences": list(self.rate_card_references or []),
        }


def aggregate_provider_receipts(
    receipts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Aggregate sanitized physical-attempt receipts without inventing zeroes.

    Partial observed totals remain available for diagnostics.  Canonical totals
    are null unless every physical attempt has complete provider usage and a
    complete named price calculation.
    """

    token_keys = (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    observed = dict.fromkeys(token_keys, 0)
    usage_reasons: set[str] = set()
    cost_reasons: set[str] = set()
    rate_cards: set[str] = set()
    cost_total = 0.0
    usage_complete = bool(receipts)
    cost_complete = bool(receipts)
    breakdowns: dict[str, dict[str, dict[str, Any]]] = {
        "bySeat": {},
        "byProvider": {},
        "byModel": {},
        "byAttemptKind": {},
        "byStatus": {},
    }

    for receipt in receipts:
        usage = receipt.get("usage")
        required_usage_present = isinstance(usage, dict) and _usage_is_complete(usage)
        if not required_usage_present:
            usage_complete = False
            malformed = isinstance(usage, dict) and bool(usage.get("usage_validation_errors"))
            usage_reasons.add(
                "provider_usage_malformed"
                if malformed
                else _string(receipt.get("usage_unavailable_reason")) or "provider_usage_missing"
            )
        if isinstance(usage, dict):
            for key in token_keys:
                value = usage.get(key)
                if _is_int(value):
                    observed[key] += cast(int, value)

        estimated_cost = receipt.get("estimated_cost")
        cost_value = estimated_cost.get("cost_usd") if isinstance(estimated_cost, dict) else None
        pricing = receipt.get("pricing")
        rate_card_reference = receipt.get("rate_card_reference")
        if rate_card_reference is None and isinstance(pricing, dict):
            rate_card_reference = pricing.get("rate_card_reference")
        reference = rate_card_reference if isinstance(rate_card_reference, dict) else {}
        reference_matches_receipt = (
            validate_price_card_reference(reference)
            and reference.get("provider") == receipt.get("provider")
            and reference.get("model") == receipt.get("model")
        )
        rate_card = _string(reference.get("rateCardId")) if reference_matches_receipt else None
        if not _is_finite_nonnegative_number(cost_value) or not rate_card:
            cost_complete = False
            cost_reasons.add(
                _string(
                    estimated_cost.get("unavailable_reason")
                    if isinstance(estimated_cost, dict)
                    else None
                )
                or (
                    "rate_card_reference_invalid"
                    if cost_value is not None and not rate_card
                    else "pricing_not_configured"
                )
            )
        else:
            if not isinstance(cost_value, (int, float)) or isinstance(cost_value, bool):
                raise AssertionError("validated cost must be numeric")
            cost_total += float(cost_value)
            rate_cards.add(rate_card)

        for dimension, raw in (
            ("bySeat", receipt.get("active_player") or receipt.get("seat_id")),
            ("byProvider", receipt.get("provider")),
            ("byModel", receipt.get("model")),
            ("byAttemptKind", receipt.get("attempt_kind")),
            ("byStatus", receipt.get("status") or receipt.get("outcome")),
        ):
            name = _string(raw) or "unknown"
            _add_breakdown(breakdowns[dimension], name, usage, cost_value)

    logical_action_ids = {
        value
        for receipt in receipts
        if (value := _string(receipt.get("logical_action_id"))) is not None
    }
    attempt_indexes_valid = _attempt_indexes_are_valid(receipts)
    if not attempt_indexes_valid:
        usage_reasons.add("attempt_ledger_incomplete")

    canonical_tokens = {
        _camel_token_key(key): observed[key] if usage_complete else None for key in token_keys
    }
    usage_summary = {
        "schemaVersion": USAGE_SUMMARY_SCHEMA_VERSION,
        **canonical_tokens,
        "observedPartialTotals": {_camel_token_key(key): value for key, value in observed.items()},
        "totalCostUsd": round(cost_total, 12) if cost_complete else None,
        "usageComplete": usage_complete,
        "costComplete": cost_complete,
        "receiptCount": len(receipts),
        "attemptCount": len(receipts),
        "logicalActionCount": len(logical_action_ids),
        "attemptLedgerComplete": attempt_indexes_valid,
        "unavailableReasonCodes": sorted(usage_reasons | cost_reasons),
        "rateCardReferences": sorted(rate_cards),
        **breakdowns,
    }
    cost_summary = {
        "status": "ok" if cost_complete else "cost_unavailable",
        "costUsd": round(cost_total, 12) if cost_complete else None,
        "costComplete": cost_complete,
        "rateCardReferences": sorted(rate_cards),
        "unavailableReasonCodes": sorted(cost_reasons),
    }
    return usage_summary, cost_summary


def _attempt_indexes_are_valid(receipts: list[dict[str, Any]]) -> bool:
    if not receipts:
        return False
    seen_events: set[str] = set()
    by_logical_action: dict[str, list[int]] = {}
    for receipt in receipts:
        event_id = _string(receipt.get("event_id"))
        logical_action_id = _string(receipt.get("logical_action_id"))
        attempt_index_value = receipt.get("attempt_index", receipt.get("attempt"))
        if (
            event_id is None
            or event_id in seen_events
            or logical_action_id is None
            or not _is_int(attempt_index_value)
        ):
            return False
        attempt_index = cast(int, attempt_index_value)
        if attempt_index < 1:
            return False
        seen_events.add(event_id)
        by_logical_action.setdefault(logical_action_id, []).append(attempt_index)
    return all(
        indexes == list(range(1, len(indexes) + 1)) for indexes in by_logical_action.values()
    )


def _add_breakdown(
    rows: dict[str, dict[str, Any]],
    name: str,
    usage: Any,
    cost_value: Any,
) -> None:
    row = rows.setdefault(
        name,
        {
            "attemptCount": 0,
            "observedInputTokens": 0,
            "observedOutputTokens": 0,
            "observedCachedInputTokens": 0,
            "observedReasoningTokens": 0,
            "observedTotalTokens": 0,
            "observedCostUsd": 0.0,
        },
    )
    row["attemptCount"] += 1
    if isinstance(usage, dict):
        for source, target in (
            ("input_tokens", "observedInputTokens"),
            ("output_tokens", "observedOutputTokens"),
            ("cached_input_tokens", "observedCachedInputTokens"),
            ("reasoning_tokens", "observedReasoningTokens"),
            ("total_tokens", "observedTotalTokens"),
        ):
            if _is_int(usage.get(source)):
                row[target] += usage[source]
    if _is_finite_nonnegative_number(cost_value):
        row["observedCostUsd"] = round(row["observedCostUsd"] + float(cost_value), 12)


def _camel_token_key(value: str) -> str:
    return {
        "input_tokens": "totalInputTokens",
        "output_tokens": "totalOutputTokens",
        "cached_input_tokens": "totalCachedInputTokens",
        "reasoning_tokens": "totalReasoningTokens",
        "total_tokens": "totalTokens",
    }[value]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _usage_is_complete(usage: dict[str, Any]) -> bool:
    if usage.get("usage_validation_errors") not in (None, []):
        return False
    if not all(
        _is_int(usage.get(key)) for key in ("input_tokens", "output_tokens", "total_tokens")
    ):
        return False
    reasoning_included = usage.get("reasoning_included_in_output")
    if not isinstance(reasoning_included, bool):
        return False
    cached = usage.get("cached_input_tokens")
    input_tokens = cast(int, usage["input_tokens"])
    if cached is not None:
        if not _is_int(cached):
            return False
        if usage.get("cached_input_is_subset") is True and cast(int, cached) > input_tokens:
            return False
    reasoning = usage.get("reasoning_tokens")
    if reasoning is not None and not _is_int(reasoning):
        return False
    output_tokens = cast(int, usage["output_tokens"])
    reasoning_tokens = cast(int, reasoning) if reasoning is not None else 0
    if reasoning_included and reasoning_tokens > output_tokens:
        return False
    expected_total = input_tokens + output_tokens
    if not reasoning_included:
        expected_total += reasoning_tokens
    return cast(int, usage["total_tokens"]) == expected_total


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


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
