import random

import pytest

from eslams.arena import registry
from eslams.arena_transport import start_session, step_session
from eslams.artifacts import ArtifactValidator
from eslams.catalogue import game_catalogue_rows
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


def test_paddle_target_is_reachable_with_public_tracking_and_valid_artifact(tmp_path):
    class TrackingAgent:
        id = "public-paddle-tracker"
        version = "1"

        def act(self, request):
            observation = request.observation
            difference = observation["ball"]["x"] - observation["paddle_x"]
            action = "right" if difference > 0.06 else "left" if difference < -0.06 else "stay"
            return ActResponse(action=action)

    arena = registry.create("paddle-ball")
    for seed in range(8):
        state = arena.initial_state(seed)
        while not state.terminal:
            observation = arena.observation_for(state, "player_1")
            difference = observation["ball"]["x"] - observation["paddle_x"]
            action = "right" if difference > 0.06 else "left" if difference < -0.06 else "stay"
            state = arena.apply_action(state, "player_1", action)
        assert state.outcome["reason"] == "target_rally"
        assert state.outcome["success"] is True
        assert state.turn <= arena.max_turns
        assert state.public_state["bounces"] == state.public_state["target_bounces"] == 10
        assert state.scores == {"player_1": 1.0}
    result = Runner().run(RunConfig(
        arena_id=arena.id, agent_1=TrackingAgent(), output_dir=tmp_path,
    ))
    assert result.score.outcome["reason"] == "target_rally"
    assert result.score.winner is None
    assert result.score.scores_by_player == {"player_1": 1.0}
    assert result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_ultimate_no_global_line_draws_even_with_unequal_local_board_counts(tmp_path):
    class SeededAgent:
        id = "ultimate-regression-playout"
        version = "1"

        def __init__(self):
            self.rng = random.Random(6)

        def act(self, request):
            return ActResponse(action=self.rng.choice(request.legal_actions))

    agent = SeededAgent()
    result = Runner().run(RunConfig(
        arena_id="ultimate-tic-tac-toe", seed=6, agent_1=agent, agent_2=agent,
        output_dir=tmp_path,
    ))
    assert result.score.outcome == {
        "winner": None, "reason": "draw",
        "local_boards": {"player_1": 4, "player_2": 5},
    }
    assert result.score.scores_by_player == {"player_1": 0.5, "player_2": 0.5}
    assert result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.artifact_path) == []
    # Preserve global-line wins as well as the draw correction.
    winners = set()
    arena = registry.create("ultimate-tic-tac-toe")
    for seed in range(20):
        rng = random.Random(seed)
        state = arena.initial_state(seed)
        while not state.terminal:
            state = arena.apply_action(state, state.active_player,
                                       rng.choice(state.legal_actions_by_player[state.active_player]))
        winners.add(state.outcome["winner"])
        if state.outcome["winner"] is not None:
            assert state.outcome["reason"] == "global_three_in_a_row"
        else:
            assert state.scores == {"player_1": 0.5, "player_2": 0.5}
    assert winners == {None, "player_1", "player_2"}


def test_morris_declares_its_compact_limit_and_draws_a_still_playable_position():
    row = next(r for r in game_catalogue_rows() if r["game_id"] == "nine-mens-morris")
    assert row["fidelity"] == "compact"
    assert "120" in row["help"]["scoringSummary"]
    assert "episode draw" in str(row["help"]["detailSections"])
    arena = registry.create("nine-mens-morris")
    rng = random.Random(8)
    state = arena.initial_state(8)
    while not state.terminal and state.turn < 119:
        state = arena.apply_action(state, state.active_player,
                                   rng.choice(state.legal_actions_by_player[state.active_player]))
    assert not state.terminal
    assert state.legal_actions_by_player[state.active_player]
    terminal = arena.apply_action(state, state.active_player,
                                 state.legal_actions_by_player[state.active_player][0])
    assert terminal.outcome == {"winner": None, "reason": "turn_limit"}
    assert terminal.scores == {"player_1": 0.5, "player_2": 0.5}
    assert all(count >= 3 for count in terminal.public_state["piece_counts"].values())


@pytest.mark.usefixtures("arena_session_env")
def test_all_catalogue_help_examples_are_accepted_in_the_documented_seed_one_position():
    for row in game_catalogue_rows():
        game = row["game_id"]
        arena = registry.create(game)
        started = start_session(game, None, 1, {p: {"kind": "human"} for p in arena.players})
        assert "seed-1" in str(row["help"]["detailSections"])
        for example in row["help"]["exampleActions"]:
            assert example["token"] in started["legal_actions"], (game, example)
            stepped = step_session(started["session_state"], started["active_player"],
                                   example["token"])
            assert stepped["accepted"] is True, (game, example, stepped)
