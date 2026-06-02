from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.hex import HexArena
from eslams.arenas.othello import OthelloArena
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


def test_new_board_arenas_are_registered():
    assert {"othello", "gomoku", "hex"}.issubset(set(registry.list()))


def test_othello_initial_move_flips_disc():
    arena = OthelloArena()
    state = arena.initial_state(7)

    assert sorted(state.legal_actions_by_player["player_1"]) == [[2, 3], [3, 2], [4, 5], [5, 4]]

    next_state = arena.apply_action(state, "player_1", [2, 3])

    assert next_state.public_state["board"][2][3] == "B"
    assert next_state.public_state["board"][3][3] == "B"
    assert next_state.active_player == "player_2"


def test_gomoku_detects_five_in_a_row():
    arena = GomokuArena()
    state = arena.initial_state(1)
    for action in [0, 15, 1, 16, 2, 17, 3, 18, 4]:
        state = arena.apply_action(state, state.active_player, action)

    assert state.terminal is True
    assert state.outcome == {"winner": "player_1", "reason": "five_in_a_row"}
    assert state.scores["player_1"] == 1.0


def test_hex_detects_top_bottom_connection():
    arena = HexArena()
    state = arena.initial_state(1)
    player_2_fillers = [10, 21, 32, 43, 54, 65, 76, 87, 98, 109]
    player_1_path = [row * 11 for row in range(11)]
    actions: list[int] = []
    for index, action in enumerate(player_1_path):
        actions.append(action)
        if index < len(player_2_fillers):
            actions.append(player_2_fillers[index])

    for action in actions:
        state = arena.apply_action(state, state.active_player, action)
        if state.terminal:
            break

    assert state.terminal is True
    assert state.outcome == {"winner": "player_1", "reason": "connected_sides"}
    assert state.scores["player_1"] == 1.0


def test_runner_generates_valid_artifacts_for_new_board_arenas(tmp_path: Path):
    for arena_id in ("othello", "gomoku", "hex"):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=5, max_turns=4, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
