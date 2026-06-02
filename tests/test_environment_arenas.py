from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.battleship import BattleshipArena
from eslams.arenas.gridworld import CliffWalkingArena, FrozenLakeArena, TaxiArena
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

ENVIRONMENT_ARENAS = {
    "battleship",
    "cliff-walking",
    "frozen-lake",
    "taxi",
}


def test_environment_arenas_are_registered():
    assert ENVIRONMENT_ARENAS.issubset(set(registry.list()))


def test_frozen_lake_reaches_goal_on_safe_path():
    arena = FrozenLakeArena()
    state = arena.initial_state(1)
    for action in ["down", "down", "down", "right", "right", "right"]:
        state = arena.apply_action(state, "player_1", action)

    assert state.terminal is True
    assert state.outcome["reason"] == "reached_goal"
    assert state.scores["player_1"] == 1.0


def test_cliff_walking_penalizes_cliff_entry():
    arena = CliffWalkingArena()
    state = arena.initial_state(1)
    terminal = arena.apply_action(state, "player_1", "right")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "fell_from_cliff"
    assert terminal.public_state["cumulative_reward"] == -100.0


def test_taxi_pickup_and_dropoff_complete_delivery():
    arena = TaxiArena()
    state = arena._state(
        taxi=(0, 0),
        passenger=(0, 0),
        destination=(0, 1),
        onboard=False,
        turn=0,
        seed=1,
        outcome=None,
        history=[],
    )

    picked_up = arena.apply_action(state, "player_1", "pickup")
    delivered_ready = arena.apply_action(picked_up, "player_1", "right")
    terminal = arena.apply_action(delivered_ready, "player_1", "dropoff")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "passenger_delivered"
    assert terminal.scores["player_1"] == 1.0


def test_battleship_hides_ship_layout_and_scores_hits():
    arena = BattleshipArena()
    state = arena._state(
        ships={"player_1": ["0,0"], "player_2": ["1,1"]},
        shots={"player_1": [], "player_2": []},
        turn=0,
        active="player_1",
        seed=1,
        outcome=None,
    )

    observation = arena.observation_for(state, "player_1")
    assert observation["own_ships"] == ["0,0"]
    assert observation["shots"] == {"player_1": [], "player_2": []}

    terminal = arena.apply_action(state, "player_1", "1,1")

    assert terminal.terminal is True
    assert terminal.outcome["winner"] == "player_1"
    assert terminal.public_state["hits"]["player_1"] == 1


def test_runner_generates_valid_artifacts_for_environment_arenas(tmp_path: Path):
    for arena_id in sorted(ENVIRONMENT_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=31, max_turns=12, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
