import random
from dataclasses import replace

import pytest

from eslams.arenas.backgammon import BackgammonArena
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


def position(arena, own, opponent, dice, *, player="player_1", bar=0, turn=0, seed=0):
    board = [None] * 24
    other = "player_2" if player == "player_1" else "player_1"
    for owner, points in ((player, own), (other, opponent)):
        for point, count in points.items():
            index = point if player == "player_1" else 23 - point
            board[index] = {"player": owner, "count": count}
    return arena._state(
        board=board, bar={player: bar, other: 0},
        borne_off={player: 5 - sum(own.values()) - bar, other: 5 - sum(opponent.values())},
        active=player, dice=dice, turn=turn, seed=seed, history=[], outcome=None,
    )


def test_bearing_off_and_dice_use_rules_hold_for_both_directions():
    arena = BackgammonArena()
    for player, far, near in (("player_1", 18, 23), ("player_2", 5, 0)):
        state = position(arena, {18: 1, 23: 1}, {0: 5}, [6, 5], player=player)
        legal = state.legal_actions_by_player[player]
        assert f"move:{near}-off" not in legal
        assert f"move:{far}-off" in legal
        with pytest.raises(ValueError, match="illegal backgammon"):
            arena.apply_action(state, player, f"move:{near}-off")
        next_state = arena.apply_action(state, player, f"move:{far}-off")
        assert next_state.public_state["dice"] == [5]
        terminal = arena.apply_action(next_state, player, f"move:{near}-off")
        assert terminal.outcome["winner"] == player
        assert terminal.outcome["reason"] == "all_checkers_borne_off"
        assert terminal.scores[player] == 1.0

    # A locally legal move may block the other die. It cannot start a turn
    # when another first move permits both dice to be used.
    state = position(arena, {0: 1, 1: 1}, {3: 2, 23: 3}, [1, 2])
    assert state.legal_actions_by_player["player_1"] == ["move:0-2", "move:1-2"]
    with pytest.raises(ValueError, match="illegal backgammon"):
        arena.apply_action(state, "player_1", "move:0-1")
    # If neither ordering can use both numbers, the larger playable die wins.
    state = position(arena, {0: 1}, {3: 2, 23: 3}, [1, 2])
    assert state.legal_actions_by_player["player_1"] == ["move:0-2"]
    next_state = arena.apply_action(state, "player_1", "move:0-2")
    assert next_state.public_state["dice"] == [1]
    assert next_state.legal_actions_by_player["player_1"] == ["pass"]
    # The shared bear-off token retains which die survived the larger-die rule.
    state = position(arena, {22: 1}, {0: 5}, [2, 6])
    terminal = arena.apply_action(state, "player_1", "move:22-off")
    assert terminal.public_state["dice"] == [2]
    assert terminal.public_state["history"][-1]["remaining_dice"] == [2]


def test_blocked_rolls_are_explicit_progressing_passes_not_agent_failures(tmp_path):
    arena = BackgammonArena()
    board = [None] * 24
    for index in (0, 1):
        board[index] = {"player": "player_2", "count": 2}
    for index in (22, 23):
        board[index] = {"player": "player_1", "count": 2}
    state = arena._state(
        board=board, bar={"player_1": 1, "player_2": 1},
        borne_off={"player_1": 0, "player_2": 0}, active="player_1", dice=[1, 2],
        turn=0, seed=10, history=[], outcome=None,
    )
    assert state.legal_actions_by_player["player_1"] == ["pass"]
    state = arena.apply_action(state, "player_1", "pass")
    assert state.turn == 1 and state.active_player == "player_2"
    assert state.public_state["dice"] == [2, 2, 2, 2]
    assert state.legal_actions_by_player["player_2"] == ["pass"]
    state = arena.apply_action(state, "player_2", "pass")
    assert state.turn == 2 and state.active_player == "player_1"
    assert state.legal_actions_by_player[state.active_player]
    assert [row["action"] for row in state.public_state["history"]] == ["pass", "pass"]
    fresh = arena.initial_state(1)
    forged = replace(fresh, legal_actions_by_player={"player_1": ["pass"], "player_2": []},
                     state_hash=None)
    with pytest.raises(ValueError, match="cannot pass"):
        arena.apply_action(forged, "player_1", "pass")
    # Include the reported dead-end seeds and ensure every live state can advance.
    for seed in [*range(100), 411, 472, 1053]:
        rng = random.Random(seed * 7919 + 1)
        state = arena.initial_state(seed)
        while not state.terminal:
            legal = state.legal_actions_by_player[state.active_player]
            assert legal, (seed, state.turn)
            previous_turn = state.turn
            state = arena.apply_action(state, state.active_player, rng.choice(legal))
            assert state.turn == previous_turn + 1
            for player in arena.players:
                pieces = sum(p["count"] for p in state.public_state["board"]
                             if p is not None and p["player"] == player)
                assert pieces + state.public_state["bar"][player] + (
                    state.public_state["borne_off"][player]
                ) == 5
        assert state.outcome
    for seed in (411, 472):
        result = Runner().run(RunConfig(
            arena_id=arena.id, seed=seed, agent_1="random", agent_2="random", output_dir=tmp_path,
        ))
        assert result.score.match_valid_for_scoring
        assert result.score.outcome
        assert sum(result.score.agent_error_count_by_player.values()) == 0
        assert sum(result.score.illegal_action_count_by_player.values()) == 0
        assert ArtifactValidator().validate(result.artifact_path) == []
