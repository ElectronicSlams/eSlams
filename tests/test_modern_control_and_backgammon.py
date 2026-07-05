from dataclasses import replace
from pathlib import Path

import pytest

from eslams.arenas import registry
from eslams.arenas.backgammon import BackgammonArena
from eslams.arenas.modern_control import (
    BipedalWalkerArena,
    CarRacingArena,
    LunarLanderArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

MODERN_CONTROL_AND_BACKGAMMON = {
    "backgammon",
    "bipedal-walker",
    "car-racing",
    "lunar-lander",
}


def test_modern_control_and_backgammon_arenas_are_registered():
    assert MODERN_CONTROL_AND_BACKGAMMON.issubset(set(registry.list()))


def test_lunar_lander_soft_landing_scores_success():
    arena = LunarLanderArena()
    state = arena._state(
        x=0.02,
        y=0.01,
        vx=0.0,
        vy=-0.04,
        angle=0.02,
        angular_velocity=0.0,
        fuel=70.0,
        turn=10,
        seed=1,
        history=[],
        outcome=None,
    )

    terminal = arena.apply_action(state, "player_1", "idle")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "soft_landing"
    assert terminal.scores["player_1"] == 1.0


def test_car_racing_completes_lap_from_near_finish():
    arena = CarRacingArena()
    state = arena._state(
        progress=0.98,
        speed=0.12,
        lane=0.0,
        heading=0.0,
        offtrack_ticks=0,
        track=[0.0] * 20,
        turn=20,
        seed=1,
        history=[],
        outcome=None,
    )

    terminal = arena.apply_action(state, "player_1", "coast")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "lap_complete"
    assert terminal.scores["player_1"] == 1.0


def test_bipedal_walker_alternating_step_advances_without_falling():
    arena = BipedalWalkerArena()
    state = arena.initial_state(2)

    next_state = arena.apply_action(state, "player_1", "left-step")

    assert next_state.terminal is False
    assert next_state.public_state["walker"]["distance"] > state.public_state["walker"]["distance"]
    assert next_state.public_state["walker"]["next_foot"] == "right"


def test_backgammon_hit_sends_single_opponent_checker_to_bar():
    arena = BackgammonArena()
    board = [None] * 24
    board[0] = {"player": "player_1", "count": 1}
    board[3] = {"player": "player_2", "count": 1}
    state = arena._state(
        board=board,
        bar={"player_1": 0, "player_2": 0},
        borne_off={"player_1": 0, "player_2": 0},
        active="player_1",
        dice=[3],
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    next_state = arena.apply_action(state, "player_1", "move:0-3")

    assert next_state.public_state["bar"]["player_2"] == 1
    assert next_state.public_state["board"][3] == {"player": "player_1", "count": 1}


def test_backgammon_bear_off_finishes_race():
    arena = BackgammonArena()
    board = [None] * 24
    board[23] = {"player": "player_1", "count": 1}
    state = arena._state(
        board=board,
        bar={"player_1": 0, "player_2": 0},
        borne_off={"player_1": 4, "player_2": 0},
        active="player_1",
        dice=[1],
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    terminal = arena.apply_action(state, "player_1", "move:23-off")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "all_checkers_borne_off"
    assert terminal.scores["player_1"] == 1.0


def test_backgammon_bear_off_uses_overshoot_die_that_made_move_legal():
    arena = BackgammonArena()
    board = [None] * 24
    board[22] = {"player": "player_1", "count": 1}
    state = arena._state(
        board=board,
        bar={"player_1": 0, "player_2": 0},
        borne_off={"player_1": 4, "player_2": 0},
        active="player_1",
        dice=[6],
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    assert state.legal_actions_by_player["player_1"] == ["move:22-off"]
    terminal = arena.apply_action(state, "player_1", "move:22-off")

    assert terminal.terminal is True
    assert terminal.outcome["winner"] == "player_1"


def test_backgammon_dedupes_legal_actions_from_multiple_dice():
    arena = BackgammonArena()
    board = [None] * 24
    board[22] = {"player": "player_1", "count": 1}
    state = arena._state(
        board=board,
        bar={"player_1": 0, "player_2": 0},
        borne_off={"player_1": 3, "player_2": 0},
        active="player_1",
        dice=[2, 6],
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    assert state.legal_actions_by_player["player_1"].count("move:22-off") == 1


def test_backgammon_malformed_legal_action_raises_controlled_error():
    arena = BackgammonArena()
    state = arena.initial_state(1)
    malformed = replace(
        state,
        legal_actions_by_player={"player_1": ["not-a-move"], "player_2": []},
        state_hash=None,
    )

    with pytest.raises(ValueError, match="Invalid backgammon action format"):
        arena.apply_action(malformed, "player_1", "not-a-move")


def test_runner_generates_valid_artifacts_for_modern_control_and_backgammon(tmp_path: Path):
    for arena_id in sorted(MODERN_CONTROL_AND_BACKGAMMON):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=79, max_turns=18, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
