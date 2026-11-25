from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest

from eslams.arenas import registry
from eslams.native_checkpoint_demo import capture_settled_boundary, restore_settled_boundary
from eslams.native_rounds_demo import NativeProfile, NativeRoundArena, run_native_demo
from eslams.state import ArenaState

ARENA = "first-price-sealed-bid-auction"
AUTH = bytes(range(32))
CUSTODY = bytes(range(32, 64))


def engine(auth: bytes = AUTH) -> NativeRoundArena:
    return NativeRoundArena(NativeProfile(ARENA, 2), "auction-native", auction_authority=auth)


def test_private_valuation_marginals_remain_uniform_and_unlinked_to_other_seat():
    arena = engine()
    assert arena.auction_rules is not None
    pairs = []
    for unit in range(1, 1001):
        state = arena.auction_rules.deal(AUTH, "auction-native", 1, unit)
        pairs.append(tuple(state.private_state_by_player[s]["valuation"] for s in arena.seats))
    assert set(pairs) == {(i, j) for i in range(6, 11) for j in range(6, 11)}
    assert all(sum(pair[seat] == n for pair in pairs) in range(150, 251)
               for seat in range(2) for n in range(6, 11))
    old = registry.create(ARENA)
    assert old.version == "1.1.0" and arena.rules.version == "2.0.0-native"
    assert {old.initial_state(i).private_state_by_player["player_2"]["valuation"]
            for i in range(5)} == set(range(6, 11))


def test_other_valuation_and_pending_bid_do_not_change_active_seat_observation():
    pair: dict[int, tuple[NativeRoundArena, ArenaState]] = {}
    same_own = None
    for i in range(1, 40):
        arena = engine(i.to_bytes(32, "big"))
        state = arena.start()
        own = state.unit.private_state_by_player["player_2"]["valuation"]
        opponent = state.unit.private_state_by_player["player_1"]["valuation"]
        if own in pair:
            left_arena, left_state = pair[own]
            if left_state.unit.private_state_by_player["player_1"]["valuation"] != opponent:
                same_own = (left_arena, left_state, arena, state)
                break
        pair[own] = (arena, state)
    assert same_own is not None
    a, x, b, y = same_own
    left = a.observe(a.transition(x, "player_1", 1), "player_2", history=True)
    right = b.observe(b.transition(y, "player_1", 10), "player_2", history=True)
    assert left == right
    assert left.own_auction_value in range(6, 11)
    assert "own_auction_value" not in str(left)
    assert [e.kind for e in left.journal] == ["round_opened", "sealed_action"]
    assert all(e.action is None and e.utility == () and e.revealed == () for e in left.journal)


def test_public_bytes_and_journal_do_not_disclose_bids_valuations_or_settlement():
    a = engine()
    b = engine(b"q" * 32)
    one = run_native_demo(a, {"player_1": lambda _: 10, "player_2": lambda _: 0})
    two = run_native_demo(b, {"player_1": lambda _: 0, "player_2": lambda _: 10})
    assert one.contents == two.contents
    assert one.score is not None and two.score is not None
    assert one.score[0] < 0 == one.score[1] == two.score[0] > two.score[1]
    assert "score=" not in repr(one)
    assert one.completed == two.completed == 6
    with ZipFile(BytesIO(one.contents)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["score_quanta"] is None
        assert manifest["status"] == "complete"
        ev = [json.loads(raw) for raw in z.read("public/events.jsonl").splitlines()]
        assert all(e["action"] is None and e["utility"] == e["revealed"] == [] for e in ev)
        assert all(k not in str(ev) for k in ("pending_bid", "valuation", "seed", "state_hash"))
    with pytest.raises(ValueError, match="exact integer"):
        a.rules.apply_action(a.start().unit, "player_1", True)


def test_checkpoint_recovers_private_auction_at_boundary_only_with_same_authority():
    a = engine()
    state = a.start()
    initial = state
    while state.completed < 3:
        p = a.active_seat(state)
        state = a.transition(state, p, 5)
    checkpoint = capture_settled_boundary(a, state, CUSTODY)
    assert restore_settled_boundary(engine(), checkpoint, CUSTODY) == state
    with pytest.raises(ValueError, match="attestation"):
        restore_settled_boundary(engine(b"x" * 32), checkpoint, CUSTODY)
    with pytest.raises(ValueError, match="attestation"):
        restore_settled_boundary(engine(), replace(checkpoint, signature=b"x" * 32), CUSTODY)
    with pytest.raises(ValueError, match="settled boundaries"):
        capture_settled_boundary(a, initial, CUSTODY)
    with pytest.raises(ValueError, match="settled boundaries"):
        in_progress = a.transition(state, a.active_seat(state), 5)
        capture_settled_boundary(a, in_progress, CUSTODY)
    assert all(s not in repr(state) for s in ("auction_authority", "audit_actions", "valuation"))
