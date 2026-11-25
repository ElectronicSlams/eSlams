"""Explicit native 0.9.1 roster for keyless coverage; not public capability negotiation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeRuleAdapter:
    seats: int
    score_basis: str
    denominator: int
    history_gate: str
    enabled_for_keyless: bool = True


NATIVE_SCOPE = {
    "rock-paper-scissors": NativeRuleAdapter(2, "half_point", 2, "sealed_action_reveal"),
    "prisoners-dilemma": NativeRuleAdapter(2, "raw_payoff", 1, "sealed_action_reveal"),
    "leduc-holdem": NativeRuleAdapter(4, "fractional_first_share", 12, "poker_allowlist"),
    "limit-texas-holdem": NativeRuleAdapter(4, "fractional_first_share", 12, "poker_allowlist"),
    "no-limit-texas-holdem": NativeRuleAdapter(4, "fractional_first_share", 12, "poker_allowlist"),
    "blackjack": NativeRuleAdapter(1, "half_point", 2, "settlement_only"),
    "shedding-card-game": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "crazy-eights": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "gin-rummy": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "hearts": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "spades": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "euchre": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "cribbage": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "hanabi": NativeRuleAdapter(2, "cooperative_score", 6, "settlement_only"),
    "mahjong": NativeRuleAdapter(4, "half_point", 2, "settlement_only"),
    "dou-dizhu": NativeRuleAdapter(3, "landlord_farmers", 2, "settlement_only"),
    "bridge": NativeRuleAdapter(4, "fixed_partnership", 2, "settlement_only"),
    "goofspiel": NativeRuleAdapter(2, "prize_points", 15, "settlement_only"),
    "liars-dice": NativeRuleAdapter(2, "half_point", 2, "settlement_only"),
    "bargaining": NativeRuleAdapter(2, "native_utility", 1, "settlement_only"),
    "negotiation": NativeRuleAdapter(2, "native_utility", 1, "settlement_only"),
    "first-price-sealed-bid-auction": NativeRuleAdapter(
        2, "signed_utility", 1, "independent_private_valuations"
    ),
}
