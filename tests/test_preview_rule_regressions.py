"""Deterministic regressions discovered while validating public preview artwork."""

import random

import pytest

from eslams.arenas.advanced_cards import HanabiArena
from eslams.arenas.east_asian_board import ShogiArena, XiangqiArena
from eslams.catalogue import game_catalogue_rows


def board_state(arena, pieces, hands=None):
    board = [[None] * 9 for _ in range(9 if arena.id == "shogi" else 10)]
    for row, col, piece in pieces:
        board[row][col] = piece
    kwargs = {"board": board, "turn": 0, "active": "player_1", "seed": 0, "outcome": None}
    if arena.id == "shogi":
        kwargs["hands"] = hands or {"player_1": {}, "player_2": {}}
    return arena._state(**kwargs)


def test_shogi_standard_rook_bishop_squares():
    board = ShogiArena().initial_state(0).public_state["board"]
    assert (board[7][1], board[7][7]) == ("B", "R")
    assert (board[1][1], board[1][7]) == ("r", "b")


@pytest.mark.parametrize(
    "arena,pieces,action",
    [
        (ShogiArena(), [(8, 4, "K"), (0, 0, "k"), (0, 3, "r")], "5i6i"),
        (XiangqiArena(), [(9, 4, "G"), (0, 5, "g"), (0, 3, "r")], "e9d9"),
        (ShogiArena(), [(8, 4, "K"), (0, 0, "k"), (0, 4, "r"), (7, 4, "G")], "5h6h"),
        (XiangqiArena(), [(9, 4, "G"), (0, 5, "g"), (0, 4, "r"), (8, 4, "R")], "e8d8"),
    ],
)
def test_cannot_move_king_into_attack_or_uncover_it(arena, pieces, action):
    state = board_state(arena, pieces)
    assert not arena.is_legal(state, "player_1", action)
    with pytest.raises(ValueError):
        arena.apply_action(state, "player_1", action)


def test_shogi_drop_must_resolve_check():
    arena = ShogiArena()
    state = board_state(
        arena, [(8, 4, "K"), (0, 0, "k"), (0, 4, "r")], {"player_1": {"G": 1}, "player_2": {}}
    )
    assert "G*5h" in state.legal_actions_by_player["player_1"]
    assert "G*6h" not in state.legal_actions_by_player["player_1"]


def test_xiangqi_cannon_check_respects_screen():
    arena = XiangqiArena()
    state = board_state(arena, [(9, 4, "G"), (0, 5, "g"), (0, 3, "c"), (5, 3, "s")])
    assert "e9d9" not in state.legal_actions_by_player["player_1"]
    state = board_state(arena, [(9, 4, "G"), (0, 5, "g"), (0, 3, "c")])
    assert "e9d9" in state.legal_actions_by_player["player_1"]


def test_hanabi_last_draw_grants_exactly_one_more_turn_each():
    arena = HanabiArena()
    state = arena.initial_state(112)
    while state.public_state["deck_count"]:
        player = state.active_player
        action = (
            "discard:0"
            if state.public_state["clues"] < 8
            else "hint:player_2:R"
            if player == "player_1"
            else "hint:player_1:R"
        )
        state = arena.apply_action(state, player, action)
    assert state.metadata["final_turns_remaining"] == 2
    assert not state.terminal
    for remaining in [1, 0]:
        action = next(
            action
            for action in arena.legal_actions_for(state, state.active_player)
            if action.startswith("hint:")
        )
        state = arena.apply_action(state, state.active_player, action)
        assert state.metadata["final_turns_remaining"] == remaining
        assert state.terminal == (remaining == 0)
    assert state.outcome["reason"] == "final_round_complete"
    assert all(not actions for actions in state.legal_actions_by_player.values())


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 112])
def test_hanabi_never_strands_active_player(seed):
    arena = HanabiArena()
    state = arena.initial_state(seed)
    rng = random.Random(seed)
    for _ in range(arena.max_turns):
        if state.terminal:
            break
        legal = arena.legal_actions_for(state, state.active_player)
        assert legal
        state = arena.apply_action(state, state.active_player, rng.choice(legal))
    assert state.terminal


def test_east_asian_adapters_advertise_remaining_compact_rule_limits():
    rows = {row["game_id"]: row for row in game_catalogue_rows()}
    for game_id in ("shogi", "xiangqi"):
        assert rows[game_id]["fidelity"] == "compact"
        assert rows[game_id]["variant_token"].startswith("core_compact_")
