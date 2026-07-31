from __future__ import annotations

import math

import pytest

from eslams.agents import _estimated_cost, _normalize_usage
from eslams.contracts.pricing import PriceCardReference
from eslams.contracts.usage import aggregate_provider_receipts

PRICING = {
    "status": "ok",
    "currency": "USD",
    "input_cost_per_token": 0.001,
    "output_cost_per_token": 0.002,
    "cache_read_input_token_cost": 0.00025,
    "output_cost_per_reasoning_token": 0.003,
}


def test_openai_inclusive_reasoning_is_not_double_billed():
    usage = _normalize_usage(
        "openai",
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 25},
            "output_tokens_details": {"reasoning_tokens": 5},
            "total_tokens": 120,
        },
    )

    cost = _estimated_cost(usage, PRICING)

    assert usage["reasoning_included_in_output"] is True
    assert usage["total_tokens"] == 120
    assert cost["status"] == "ok"
    assert cost["reasoning_cost_usd"] == 0
    assert cost["cost_usd"] == 0.12125


def test_gemini_separate_reasoning_is_included_in_total_and_cost_once():
    usage = _normalize_usage(
        "gemini",
        {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "thoughtsTokenCount": 5,
            "totalTokenCount": 125,
        },
    )

    cost = _estimated_cost(usage, PRICING)

    assert usage["reasoning_included_in_output"] is False
    assert usage["total_tokens"] == 125
    assert cost["reasoning_cost_usd"] == 0.015
    assert cost["cost_usd"] == 0.155


def test_unknown_reasoning_inclusion_fails_closed():
    usage = _normalize_usage(
        "custom-provider",
        {
            "input_tokens": 10,
            "output_tokens": 4,
            "reasoning_tokens": 2,
        },
    )

    assert usage["total_tokens"] is None
    assert "reasoning_inclusion_unknown" in usage["usage_validation_errors"]
    assert _estimated_cost(usage, PRICING) == {
        "status": "cost_unavailable",
        "unavailable_reason": "provider_usage_malformed",
    }


@pytest.mark.parametrize("bad_value", [-1, math.nan, math.inf, -math.inf])
def test_nonnegative_finite_accounting_values_are_required(bad_value: float):
    usage = _normalize_usage(
        "openai",
        {"input_tokens": bad_value, "output_tokens": 2, "total_tokens": 2},
    )

    assert usage["input_tokens"] is None
    assert usage["usage_validation_errors"]
    assert _estimated_cost(usage, PRICING)["status"] == "cost_unavailable"


@pytest.mark.parametrize(
    ("usage", "expected_error"),
    [
        (
            {
                "input_tokens": 2,
                "output_tokens": 1,
                "cached_input_tokens": 3,
                "total_tokens": 3,
            },
            "cached_input_tokens_exceed_input_tokens",
        ),
        (
            {"input_tokens": 2, "output_tokens": 1, "total_tokens": 99},
            "provider_total_tokens_inconsistent",
        ),
    ],
)
def test_incoherent_provider_usage_is_malformed(
    usage: dict[str, int],
    expected_error: str,
):
    normalized = _normalize_usage("openai", usage)

    assert expected_error in normalized["usage_validation_errors"]
    summary, _ = aggregate_provider_receipts([_receipt(normalized)])
    assert summary["usageComplete"] is False
    assert "provider_usage_malformed" in summary["unavailableReasonCodes"]


def test_arbitrary_rate_card_id_cannot_make_cost_complete():
    usage = _normalize_usage(
        "openai",
        {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    )
    receipt = _receipt(usage)
    receipt["estimated_cost"] = {"status": "ok", "cost_usd": 0.01}
    receipt["rate_card_id"] = "unreviewed-string"

    summary, cost = aggregate_provider_receipts([receipt])

    assert summary["costComplete"] is False
    assert cost["costComplete"] is False
    assert "rate_card_reference_invalid" in summary["unavailableReasonCodes"]


def test_complete_matching_price_card_reference_closes_cost_accounting():
    usage = _normalize_usage(
        "openai",
        {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    )
    reference = PriceCardReference(
        rate_card_id="openai-reviewed-2026-07-31",
        rate_card_hash="sha256:" + "1" * 64,
        provider="openai",
        model="gpt-fixture",
        currency="USD",
        source_uri="https://example.invalid/reviewed-rate-card.json",
        complete=True,
    ).to_dict()
    receipt = _receipt(usage)
    receipt["estimated_cost"] = {"status": "ok", "cost_usd": 0.01}
    receipt["rate_card_reference"] = reference

    summary, cost = aggregate_provider_receipts([receipt])

    assert summary["costComplete"] is True
    assert summary["totalCostUsd"] == 0.01
    assert summary["rateCardReferences"] == ["openai-reviewed-2026-07-31"]
    assert cost["costComplete"] is True


def _receipt(usage: dict[str, object]) -> dict[str, object]:
    return {
        "provider": "openai",
        "model": "gpt-fixture",
        "active_player": "player_1",
        "logical_action_id": "logical_001",
        "attempt_index": 1,
        "attempt_kind": "primary",
        "status": "completed",
        "usage": usage,
        "estimated_cost": {
            "status": "cost_unavailable",
            "unavailable_reason": "pricing_not_configured",
        },
    }
