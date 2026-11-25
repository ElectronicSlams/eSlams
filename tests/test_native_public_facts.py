from __future__ import annotations

import json
from dataclasses import replace

import pytest

from eslams.native_artifact import verify_native_replay
from eslams.native_public_facts import shared_facts, valid_shared_facts
from eslams.native_rounds_demo import NativeProfile, NativeRoundArena, run_native_match

EXPECTED_MOVES = {
    "blackjack": "hit", "shedding-card-game": "play", "crazy-eights": "play",
    "gin-rummy": "draw", "hearts": "play", "spades": "play", "euchre": "play",
    "cribbage": "private_discard", "hanabi": "play", "mahjong": "discard",
    "dou-dizhu": "play", "bridge": "play", "goofspiel": "sealed_bid",
    "liars-dice": "challenge", "bargaining": "offer", "negotiation": "offer",
}
_PRIVATE_KEYS = {"hand", "hands", "hole", "deck", "seed", "legal_actions", "valuation",
                 "authorities", "private", "pending_bid", "reserves", "unmet_reserves",
                 "revealed_dice", "discards", "hints", "visible_partner_hand", "rng_commitment"}


def _all_keys(obj):
    if isinstance(obj, dict):
        yield from obj
        for e in obj.values():
            yield from _all_keys(e)
    elif isinstance(obj, list):
        for e in obj:
            yield from _all_keys(e)


@pytest.mark.parametrize("game", EXPECTED_MOVES)
@pytest.mark.parametrize("last", [False, True])
def test_allowlisted_facts_are_resolved_at_action_authority(game, last):
    arena = NativeRoundArena(NativeProfile(game), "visible-policy")

    moves = []

    def policy(view):
        # Same closed shape in the agent journal, not inferred from private fields.
        for event in view.journal:
            safe = event.public_document()["game_facts"]
            assert valid_shared_facts(game, event.kind, safe)
        choice = view.legal[-1] if last else view.legal[0]
        moves.append("sealed_bid" if game == "goofspiel" else
                     "private_discard" if game == "cribbage" else choice)
        return choice

    result = run_native_match(arena, dict.fromkeys(arena.seats, policy))
    replay = verify_native_replay(result.contents)
    assert replay.manifest["completed_rounds"] == 3
    assert moves == [e["game_facts"]["move"] for e in replay.events
                     if e["kind"] == "redacted_unit_action"]
    for event in replay.events:
        facts = event["game_facts"]
        assert not (_PRIVATE_KEYS & set(_all_keys(facts)))
        if event["kind"] == "redacted_unit_action":
            assert facts["move"] is not None
            assert event["action"] is None
        if game == "blackjack":
            assert ("dealer_hand" in facts) == (event["kind"] == "round_settled")


@pytest.mark.parametrize("game,field", [
    ("goofspiel", "round_history"), ("cribbage", "discard_counts"),
])
def test_first_sealed_move_does_not_leak_action(game, field):
    arena = NativeRoundArena(NativeProfile(game), "sealed-public-snapshot")
    state = arena.start()
    seat = arena.active_seat(state)
    obs = arena.observe(state, seat, history=True)
    assert len(obs.legal) > 1
    first, second = (arena.transition(state, seat, move)
                     for move in (obs.legal[0], obs.legal[-1]))
    e1, e2 = first.events[-1], second.events[-1]
    assert e1 == e2
    assert field in e1.public_document()["game_facts"]
    recipient = arena.active_seat(first)
    assert arena.observe(first, recipient, history=True) == (
        arena.observe(second, recipient, history=True)
    )


def test_goofspiel_paired_reveal_and_chronological_public_action():
    arena = NativeRoundArena(NativeProfile("goofspiel"), "goof-order")
    state = arena.start()
    p = arena.active_seat(state)
    first = arena.transition(state, p, 1)
    assert first.events[-1].public_document()["game_facts"]["round_history"] == []
    p = arena.active_seat(first)
    second = arena.transition(first, p, 2)
    facts = second.events[-1].public_document()["game_facts"]
    assert len(facts["round_history"]) == 1
    assert facts["round_history"][0]["bids"] == {"player_1": 1, "player_2": 2}


@pytest.mark.parametrize("game,secret", [
    ("hanabi", "hints"), ("cribbage", "discards"), ("liars-dice", "revealed_dice"),
])
def test_even_raw_native_public_state_is_not_an_approved_envelope(game, secret):
    arena = NativeRoundArena(NativeProfile(game), "unknown-field")
    u = arena.start().unit
    original = shared_facts(game, "round_opened", u)
    injected = replace(u, state_hash="",
                       public_state={**u.public_state, secret: "synthetic-private-marker"})
    updated = shared_facts(game, "round_opened", injected)
    assert updated == original
    assert not valid_shared_facts(game, "round_opened", {**original, secret: None})
    assert "synthetic-private-marker" not in json.dumps(updated)
