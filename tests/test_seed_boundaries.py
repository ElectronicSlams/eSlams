from pathlib import Path

import pytest

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.arena_transport import initial_state, start_session
from eslams.runner import RunConfig, Runner
from eslams.runner_session import RunnerSessionStore


def test_all_registered_arenas_reject_coerced_seeds_and_keep_commitments():
    for game_id in registry.list():
        arena = registry.create(game_id)
        for invalid in (True, False, 1.5, 1.0, "1", None):
            with pytest.raises(ValueError, match="seed must be an integer"):
                arena.initial_state(invalid)
        for seed in (0, -1, 2**40):
            state = arena.initial_state(seed)
            assert state.metadata["seed"] == seed
            action = arena.legal_actions_for(state, state.active_player)[0]
            next_state = arena.apply_action(state, state.active_player, action)
            assert next_state.rng_commitment == state.rng_commitment, (game_id, seed)
            assert next_state.metadata["seed"] == seed


def test_invalid_seed_is_rejected_before_runner_outputs_and_session_storage(tmp_path: Path):
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="seed must be an integer"):
        Runner().run(RunConfig(arena_id="tic-tac-toe", seed=1.5, output_dir=output))
    assert not output.exists()
    with pytest.raises(ValueError, match="seed must be an integer"):
        initial_state("tic-tac-toe", seed=True)
    with pytest.raises(ValueError, match="seed must be an integer"):
        start_session(
            "tic-tac-toe",
            variant=None,
            seed=1.5,
            players={"player_1": {"kind": "human"}, "player_2": {"kind": "human"}},
        )
    store = RunnerSessionStore()
    with pytest.raises(ValueError, match="seed must be an integer"):
        store.create(game_id="tic-tac-toe", initial_seed="1")
