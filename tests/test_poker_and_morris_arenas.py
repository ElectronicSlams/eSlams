from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.nine_mens_morris import NineMensMorrisArena
from eslams.arenas.poker import (
    LeducHoldemArena,
    LimitTexasHoldemArena,
    NoLimitTexasHoldemArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

POKER_AND_MORRIS_ARENAS = {
    "leduc-holdem",
    "limit-texas-holdem",
    "nine-mens-morris",
    "no-limit-texas-holdem",
}


def test_poker_and_morris_arenas_are_registered():
    assert POKER_AND_MORRIS_ARENAS.issubset(set(registry.list()))


def test_leduc_hides_private_hole_cards_and_keeps_board_betting_round():
    arena = LeducHoldemArena()
    state = arena.initial_state(7)
    player_2_hole = state.private_state_by_player["player_2"]["hole"][0]

    observation = arena.observation_for(state, "player_1")

    assert observation["hole"] == state.private_state_by_player["player_1"]["hole"]
    assert player_2_hole not in str(observation)

    state = arena.apply_action(state, "player_1", "check")
    board_state = arena.apply_action(state, "player_2", "check")

    assert board_state.terminal is False
    assert board_state.public_state["street"] == "board"
    assert len(board_state.public_state["board"]) == 1
    assert board_state.legal_actions_by_player["player_1"] == ["check", "bet"]

    state = arena.apply_action(board_state, "player_1", "check")
    terminal = arena.apply_action(state, "player_2", "check")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "showdown"


def test_limit_holdem_betting_advances_to_flop_without_terminal_showdown():
    arena = LimitTexasHoldemArena()
    state = arena.initial_state(3)

    raised = arena.apply_action(state, "player_1", "bet")

    assert raised.legal_actions_by_player["player_2"] == ["call", "fold", "raise"]

    flop = arena.apply_action(raised, "player_2", "call")

    assert flop.terminal is False
    assert flop.public_state["street"] == "flop"
    assert len(flop.public_state["board"]) == 3
    assert flop.legal_actions_by_player["player_1"] == ["check", "bet"]


def test_no_limit_holdem_exposes_profiled_bet_sizes_and_all_in():
    arena = NoLimitTexasHoldemArena()
    state = arena.initial_state(3)

    assert state.legal_actions_by_player["player_1"] == [
        "check",
        "bet:2",
        "bet:4",
        "all-in",
    ]

    all_in = arena.apply_action(state, "player_1", "all-in")

    assert all_in.legal_actions_by_player["player_2"] == ["call", "fold"]


def test_nine_mens_morris_forms_mill_and_captures_piece():
    arena = NineMensMorrisArena()
    board = [None] * 24
    board[0] = "player_1"
    board[1] = "player_1"
    board[3] = "player_2"
    state = arena._state(
        board=board,
        reserves={"player_1": 7, "player_2": 8},
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    assert "place:2:capture:3" in state.legal_actions_by_player["player_1"]

    next_state = arena.apply_action(state, "player_1", "place:2:capture:3")

    assert next_state.public_state["board"][2] == "player_1"
    assert next_state.public_state["board"][3] is None
    assert next_state.public_state["reserves"]["player_1"] == 6


def test_runner_generates_valid_artifacts_for_poker_and_morris_arenas(tmp_path: Path):
    for arena_id in sorted(POKER_AND_MORRIS_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=53, max_turns=16, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
