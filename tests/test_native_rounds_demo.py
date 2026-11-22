import json
from dataclasses import asdict, replace
from io import BytesIO
from zipfile import ZipFile

import pytest

from eslams.arenas import registry
from eslams.hashing import sha256_text
from eslams.native_rounds_demo import NativeProfile, NativeRoundArena, run_native_demo

POKER = ("leduc-holdem", "limit-texas-holdem", "no-limit-texas-holdem")


class CountedArena(NativeRoundArena):
    starts = 0
    final_calls = 0

    def start(self):
        self.starts += 1
        return super().start()

    def final_score(self, state):
        self.final_calls += 1
        return super().final_score(state)


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, 1.5, "2", 21])
def test_invalid_block(value):
    with pytest.raises(ValueError):
        NativeProfile("rock-paper-scissors", value)


@pytest.mark.parametrize("blocks", [1, 2, 3])
def test_one_match_all_blocks_and_continuous_history(blocks):
    views = []

    def rock(view):
        views.append(view)
        return "rock"

    def scissors(view):
        views.append(view)
        return "scissors"

    arena = CountedArena(NativeProfile("rock-paper-scissors", blocks), "rps-native")
    result = run_native_demo(arena, {"player_1": rock, "player_2": scissors})
    assert arena.starts == arena.final_calls == 1
    assert result.completed == 3 * blocks and result.score == (6 * blocks, 0)
    assert len(views) == 6 * blocks and {v.run_id for v in views} == {"rps-native"}
    assert [v.global_action_index for v in views] == list(range(6 * blocks))
    assert [e.event_seq for e in result.events] == list(range(len(result.events)))
    assert [e.kind for e in result.events].count("match_finalized") == 1
    for view in views:
        assert view.journal == result.events[:len(view.journal)]
        assert len([x for x in view.journal if x.kind == "round_settled"]) == view.round_index - 1
    assert all(e.action is None for e in result.events if e.kind == "sealed_action")
    assert registry.create("rock-paper-scissors").max_turns == 2


def test_sealed_noninterference_in_entire_receiving_payload():
    arena = NativeRoundArena(NativeProfile("rock-paper-scissors"), "sealed-test")
    initial = arena.start()
    views = [
        asdict(arena.observe(arena.transition(initial, "player_1", action),
                             "player_2", history=True))
        for action in ("rock", "paper", "scissors")
    ]
    assert views[0] == views[1] == views[2]


@pytest.mark.parametrize("game", POKER)
def test_three_native_poker_hands_and_memory_vs_control(game):
    def setup(adaptation):
        by_seat = {}
        arena = CountedArena(NativeProfile(game, seed=401, rotate_positions=True),
                             "poker-native-control")
        for seat in arena.seats:
            by_seat[seat] = []

        def policy(identity):
            def choose(view):
                assert view.seat_id == identity
                by_seat[identity].append(view)
                if adaptation and view.own_completed_hands and view.round_turn == 0:
                    assert view.round_index in (2, 3)
                    assert any(e.kind == "round_settled" for e in view.journal)
                    for action in ("bet", "bet:2"):
                        if action in view.legal:
                            return action
                return "check" if "check" in view.legal else "call"
            return choose

        result = run_native_demo(arena, {s: policy(s) for s in arena.seats}, history=adaptation)
        assert arena.starts == arena.final_calls == 1 and result.completed == 3
        assert sum(result.score) == 36
        return result, by_seat

    adaptive, trace = setup(True)
    control, _ = setup(False)
    assert [e.actor for e in adaptive.events if e.kind == "round_opened"] == [
        "player_1", "player_2", "player_3",
    ]
    with ZipFile(BytesIO(adaptive.contents)) as z:
        assert z.namelist() == ["manifest.json", "public/events.jsonl"]
        manifest = json.loads(z.read("manifest.json"))
        stream = z.read("public/events.jsonl").decode()
        assert manifest["event_stream_sha256"] == sha256_text(stream)
        assert manifest["blocks"] == 1 and manifest["completed_rounds"] == 3
        assert all(key not in stream for key in ("own_cards", "own_completed", "deck", "seed"))
        assert len(stream.splitlines()) == len(adaptive.events)
    for identity, views in trace.items():
        own = {}
        for view in views:
            own.setdefault(view.round_index, view.own_cards)
            assert view.own_cards == own[view.round_index]
            assert tuple(p.own_cards for p in view.own_completed_hands) == tuple(
                own[i] for i in range(1, view.round_index)
            )
            assert view.journal == adaptive.events[:len(view.journal)]
            assert view.seat_id == identity
    assert [e for e in adaptive.events if e.round_index == 1] == [
        e for e in control.events if e.round_index == 1
    ]
    later = [e for e in adaptive.events if e.kind == "action" and e.round_index > 1]
    assert {e.round_index for e in later if e.action in ("bet", "bet:2")} == {2, 3}
    assert all(e.action == "check" for e in control.events if e.kind == "action")
    for i in (1, 2, 3):
        expected_streets = {"preflop", "board"} if game == "leduc-holdem" else {
            "preflop", "flop", "turn", "river",
        }
        for artifact in (adaptive, control):
            relevant = [e for e in artifact.events if e.round_index == i and e.kind == "action"]
            assert {e.street for e in relevant} == expected_streets
            assert [e.round_turn for e in relevant] == list(range(1, len(relevant) + 1))


def test_poker_unrevealed_other_hand_state_does_not_enter_receiving_view():
    arena = NativeRoundArena(NativeProfile("limit-texas-holdem"), "opponents-excluded")
    state = arena.start()
    guarded = state.unit.private_state_by_player
    permuted = dict(guarded)
    permuted["player_3"], permuted["player_4"] = guarded["player_4"], guarded["player_3"]
    alternate = replace(state, unit=replace(state.unit, private_state_by_player=permuted,
                                             state_hash=None))
    assert arena.observe(state, "player_1", history=True) == arena.observe(
        alternate, "player_1", history=True
    )


def test_undelivered_hand_is_never_scored_or_finalized():
    arena = CountedArena(NativeProfile("leduc-holdem"), "native-abort")

    def policy(view):
        if view.round_index == 2:
            raise RuntimeError("unapproved provider content")
        return "check"

    result = run_native_demo(arena, dict.fromkeys(arena.seats, policy))
    assert result.completed == 1 and result.score is None
    assert arena.starts == arena.final_calls == 1
    assert result.events[-1].kind == "match_invalid"
    assert all(e.kind != "match_finalized" for e in result.events)
    assert b"unapproved provider content" not in result.contents
