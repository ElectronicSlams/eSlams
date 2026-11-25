"""Version-pinned fields for the active seat, separate from the public journal."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import canonical_json
from eslams.state import ArenaState

# Seat-relative fields unique to each trusted rule implementation.
_SEAT_FIELDS = {
    "rock-paper-scissors": ("1.0.0", "round revealed_actions"),
    "prisoners-dilemma": ("1.0.1", "payoff_matrix revealed_actions"),
    "blackjack": ("1.0.1", "player_hand dealer_upcard player_total"),
    "shedding-card-game": ("1.0.1", "hand discard deck_count hand_counts"),
    "crazy-eights": ("1.0.1", "hand discard deck_count hand_counts"),
    "gin-rummy": ("1.0.1", "hand phase discard_top deck_count hand_counts own_deadwood"),
    "hearts": ("1.0.1", "hand hand_counts current_trick trick_history"),
    "spades": ("1.0.1", "hand hand_counts current_trick trick_history"),
    "euchre": ("1.0.1", "hand hand_counts phase trump upcard current_trick tricks"),
    "cribbage": ("1.1.0", "hand starter dealer discard_counts"),
    "hanabi": ("1.1.0", "own_hand_size own_hints visible_partner_hand partner "
               "fireworks discard clues lives"),
    "mahjong": ("1.0.0", "hand wall_count discard_pile hand_counts"),
    "dou-dizhu": ("1.0.0", "role hand hand_counts last_play passes"),
    "bridge": ("1.0.0", "partnership hand contract declarer current_trick trick_history "
               "tricks hand_counts"),
    "goofspiel": ("1.0.0", "current_prize remaining_hand round_history"),
    "liars-dice": ("1.0.0", "your_dice dice_per_player current_bid bid_history"),
    "bargaining": ("1.0.1", "private_reserve_share last_offer transcript"),
    "negotiation": ("1.1.0", "private_reserve_share last_offer transcript"),
    "first-price-sealed-bid-auction": ("2.0.0-native", "item private_value"),
}
POKER = frozenset(("leduc-holdem", "limit-texas-holdem", "no-limit-texas-holdem"))
PUBLIC_ENTROPY_ARENAS = frozenset(("rock-paper-scissors", "prisoners-dilemma"))


def seat_facts(rules: Arena, state: ArenaState, position: str) -> str:
    """Copy reviewed fields from the verified active seat's pinned observation only."""
    if state.terminal or position != state.active_player:
        raise ValueError("only the active seat receives game facts")
    if rules.id in POKER:
        version, fields = "1.0.1", "street board pot hole"
    else:
        version, fields = _SEAT_FIELDS[rules.id]
    if rules.version != version:
        raise ValueError("unreviewed native seat observation rules version")
    facts = rules.observation_for(state, position)
    projected = {name: facts[name] for name in fields.split()}
    if any(key.endswith("_token") for key in projected):
        raise ValueError("unexpected native seat secret token field")
    return closed_fact_bytes(projected)


def closed_fact_bytes(facts: Any) -> str:
    result = canonical_json(facts)
    if len(result.encode()) > 72 * 1024:
        raise ValueError("native seat facts exceed supported adapter bound")
    return result
