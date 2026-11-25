from dataclasses import replace

import pytest

from eslams.native_checkpoint_demo import capture_settled_boundary, restore_settled_boundary
from eslams.native_rounds_demo import NativeProfile, NativeRoundArena, run_native_demo
from eslams.native_scope_demo import NATIVE_SCOPE

SCOPED = tuple(name for name, a in NATIVE_SCOPE.items() if a.enabled_for_keyless)
CUSTODY_TEST_KEY = b"fake-test-authority-only-not-live!"


def test_auction_in_scope_requires_private_authority():
    assert len(NATIVE_SCOPE) == len(SCOPED) == 22
    assert {a.seats for a in NATIVE_SCOPE.values()} == {1, 2, 3, 4}
    with pytest.raises(ValueError, match="private authority"):
        NativeRoundArena(NativeProfile("first-price-sealed-bid-auction"), "no-authority")
    with pytest.raises(ValueError, match="not available"):
        NativeProfile("chess")


@pytest.mark.parametrize("game", SCOPED)
@pytest.mark.parametrize("blocks", [1, 2])
def test_scope_complete_native_units(game, blocks):
    auth = CUSTODY_TEST_KEY if game == "first-price-sealed-bid-auction" else None
    arena = NativeRoundArena(NativeProfile(game, blocks), f"all-scope-{blocks}",
                             auction_authority=auth)
    result = run_native_demo(arena, {s: lambda o: o.legal[0] for s in arena.seats})
    assert result.completed == blocks * 3
    assert len(result.score) == len(arena.seats)
    assert [e.event_seq for e in result.events] == list(range(len(result.events)))
    assert [e.round_index for e in result.events if e.kind == "round_settled"] == list(
        range(1, blocks * 3 + 1)
    )
    assert [e.kind for e in result.events].count("match_finalized") == 1
    if game == "hanabi":
        assert result.score[0] == result.score[1]
    if game == "bridge":
        assert result.score[0] == result.score[2] and result.score[1] == result.score[3]
    if game == "prisoners-dilemma":
        assert result.score == (9 * blocks, 9 * blocks)
    openings = {e.round_index: e.actor for e in result.events if e.kind == "round_opened"}
    action_kinds = {"action", "sealed_action", "redacted_unit_action"}
    first_actions = {
        e.round_index: e.actor
        for e in result.events
        if e.round_turn == 1 and e.kind in action_kinds
    }
    assert openings == first_actions
    if game == "dou-dizhu":
        assert [e.actor for e in result.events if e.kind == "round_opened"] == [
            arena.seats[i % 3] for i in range(3 * blocks)
        ]


@pytest.mark.parametrize("game", ["rock-paper-scissors", "limit-texas-holdem", "bridge"])
def test_private_checkpoint_restores_clean_boundary_exactly(game):
    cfg = NativeProfile(game, 2)
    live = NativeRoundArena(cfg, "native-checkpoint")
    state = live.start()
    with pytest.raises(ValueError, match="^only complete settled boundaries can be checkpointed$"):
        capture_settled_boundary(live, state, CUSTODY_TEST_KEY)
    while state.completed < 3:
        actor = live.active_seat(state)
        state = live.transition(state, actor, live.observe(state, actor, history=True).legal[0])
    boundary = capture_settled_boundary(live, state, CUSTODY_TEST_KEY)
    assert "actions" not in repr(boundary) and "signature" not in repr(boundary)
    rebuilt = NativeRoundArena(cfg, "native-checkpoint")
    restored = restore_settled_boundary(rebuilt, boundary, CUSTODY_TEST_KEY)
    assert restored == state and rebuilt.active_seat(restored) == live.active_seat(state)
    taken = rebuilt.active_seat(restored)
    obs = rebuilt.observe(restored, taken, history=True)
    nxt = rebuilt.transition(restored, taken, obs.legal[0])
    with pytest.raises(ValueError, match="^only complete settled boundaries can be checkpointed$"):
        capture_settled_boundary(rebuilt, nxt, CUSTODY_TEST_KEY)
    with pytest.raises(ValueError):
        restore_settled_boundary(rebuilt, replace(boundary, signature=b"not-authentic"),
                                 CUSTODY_TEST_KEY)
    with pytest.raises(ValueError):
        restore_settled_boundary(
            NativeRoundArena(replace(cfg, seed=99), "native-checkpoint"), boundary,
            CUSTODY_TEST_KEY,
        )
    for engine, s in ((live, state), (rebuilt, restored)):
        while not s.finalized:
            player = engine.active_seat(s)
            s = engine.transition(s, player, engine.observe(s, player, history=True).legal[0])
        if engine is live:
            expected = s
        else:
            assert s == expected
