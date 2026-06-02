from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.control_arcade import (
    AlienShooterArena,
    BoxingStyleArena,
    CartPoleArena,
    IceHockeyStyleArena,
    MountainCarArena,
    PaddleBallArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

CONTROL_ARCADE_ARENAS = {
    "alien-shooter",
    "boxing-style-arena",
    "cartpole",
    "ice-hockey-style-arena",
    "mountain-car",
    "paddle-ball",
}


def test_control_arcade_arenas_are_registered():
    assert CONTROL_ARCADE_ARENAS.issubset(set(registry.list()))


def test_cartpole_applies_physics_and_keeps_observation_public():
    arena = CartPoleArena()
    state = arena.initial_state(11)

    next_state = arena.apply_action(state, "player_1", "right")
    observation = arena.observation_for(next_state, "player_1")

    assert next_state.turn == 1
    assert next_state.public_state["reward"] == 1.0
    assert observation["legal_actions"] == ["left", "right"]
    assert "role" not in str(observation)


def test_mountain_car_reaches_goal_from_near_success_state():
    arena = MountainCarArena()
    state = arena._state(
        position=0.499,
        velocity=0.01,
        reward=-12.0,
        turn=12,
        seed=1,
        history=[],
        outcome=None,
    )

    terminal = arena.apply_action(state, "player_1", "right")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "reached_goal"
    assert terminal.scores["player_1"] == 1.0


def test_paddle_ball_bounces_when_paddle_is_aligned():
    arena = PaddleBallArena()
    state = arena._state(
        paddle_x=0.5,
        ball={"x": 0.5, "y": 0.09, "vx": 0.0, "vy": -0.04},
        bounces=0,
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    next_state = arena.apply_action(state, "player_1", "stay")

    assert next_state.terminal is False
    assert next_state.public_state["bounces"] == 1
    assert next_state.public_state["ball"]["vy"] > 0


def test_alien_shooter_fire_action_destroys_aligned_alien():
    arena = AlienShooterArena()
    state = arena._state(
        player_x=3,
        aliens=[(3, 2)],
        bullets=[],
        destroyed=0,
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    terminal = arena.apply_action(state, "player_1", "fire")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "wave_cleared"
    assert terminal.public_state["destroyed"] == 1


def test_boxing_jab_damages_opponent_at_range():
    arena = BoxingStyleArena()
    state = arena._state(
        health={"player_1": 100.0, "player_2": 100.0},
        stamina={"player_1": 100.0, "player_2": 100.0},
        stances={"player_1": "neutral", "player_2": "neutral"},
        distance=1,
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    next_state = arena.apply_action(state, "player_1", "jab")

    assert next_state.public_state["health"]["player_2"] == 92.0
    assert next_state.active_player == "player_2"


def test_ice_hockey_shot_scores_from_scoring_lane():
    arena = IceHockeyStyleArena()
    state = arena._state(
        positions={"player_1": {"x": 3, "lane": 1}, "player_2": {"x": 1, "lane": 0}},
        puck_owner="player_1",
        goals={"player_1": 0, "player_2": 0},
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    next_state = arena.apply_action(state, "player_1", "shoot")

    assert next_state.public_state["goals"]["player_1"] == 1
    assert next_state.public_state["puck_owner"] == "player_2"


def test_runner_generates_valid_artifacts_for_control_arcade_arenas(tmp_path: Path):
    for arena_id in sorted(CONTROL_ARCADE_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=67, max_turns=16, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
