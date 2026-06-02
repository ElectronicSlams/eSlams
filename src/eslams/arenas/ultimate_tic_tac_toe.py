"""Deterministic Ultimate Tic-Tac-Toe arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

LOCAL_CELLS = 9
TOTAL_CELLS = 81
WIN_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class UltimateTicTacToeArena(Arena):
    id = "ultimate-tic-tac-toe"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": TOTAL_CELLS - 1,
        "description": "Claim a global cell 0-80. Board is action//9, local cell is action%9.",
    }
    max_turns = TOTAL_CELLS

    def initial_state(self, seed: int) -> ArenaState:
        boards: list[list[str | None]] = [[None for _ in range(LOCAL_CELLS)] for _ in range(9)]
        local_status: list[str | None] = [None] * 9
        return self._state(
            boards=boards,
            local_status=local_status,
            next_board=None,
            turn=0,
            active="player_1",
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "boards": state.public_state["boards"],
            "local_status": state.public_state["local_status"],
            "next_board": state.public_state["next_board"],
            "you_are": player_id,
            "mark": _mark(player_id),
            "legal_cells": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("ultimate tic-tac-toe action must be an integer cell")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal ultimate tic-tac-toe cell")
        board_index, cell_index = divmod(action, LOCAL_CELLS)
        boards = [list(board) for board in state.public_state["boards"]]
        local_status = list(state.public_state["local_status"])
        boards[board_index][cell_index] = _mark(player_id)
        local_status[board_index] = _local_status(boards[board_index])
        next_board = cell_index if local_status[cell_index] is None else None
        winner_mark = _winner(local_status)
        outcome = None
        if winner_mark:
            outcome = {"winner": _player(winner_mark), "reason": "global_three_in_a_row"}
        elif all(status is not None for status in local_status):
            outcome = _points_outcome(local_status)
        return self._state(
            boards=boards,
            local_status=local_status,
            next_board=next_board,
            turn=state.turn + 1,
            active=_other(player_id),
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        boards: list[list[str | None]],
        local_status: list[str | None],
        next_board: int | None,
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _points_outcome(local_status)
        legal = [] if terminal else _legal_actions(boards, local_status, next_board)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "boards": boards,
                "local_status": local_status,
                "next_board": next_board,
                "rows": 9,
                "cols": 9,
            },
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"ultimate-tic-tac-toe:{seed}"),
            render_hints={
                "renderer": "ultimate-grid",
                "symbols": {"player_1": "X", "player_2": "O"},
            },
            metadata={"seed": seed},
        )


def _legal_actions(
    boards: list[list[str | None]],
    local_status: list[str | None],
    next_board: int | None,
) -> list[int]:
    board_indices = (
        [next_board]
        if next_board is not None and local_status[next_board] is None
        else [index for index, status in enumerate(local_status) if status is None]
    )
    return [
        board_index * LOCAL_CELLS + cell_index
        for board_index in board_indices
        for cell_index, cell in enumerate(boards[board_index])
        if cell is None
    ]


def _local_status(board: list[str | None]) -> str | None:
    winner = _winner(board)
    if winner:
        return winner
    if all(cell is not None for cell in board):
        return "D"
    return None


def _winner(cells: list[str | None]) -> str | None:
    for a, b, c in WIN_LINES:
        if cells[a] in {"X", "O"} and cells[a] == cells[b] == cells[c]:
            return cells[a]
    return None


def _points_outcome(local_status: list[str | None]) -> dict[str, Any]:
    x_boards = sum(status == "X" for status in local_status)
    o_boards = sum(status == "O" for status in local_status)
    winner = None
    if x_boards > o_boards:
        winner = "player_1"
    elif o_boards > x_boards:
        winner = "player_2"
    return {
        "winner": winner,
        "reason": "local_board_points",
        "local_boards": {"player_1": x_boards, "player_2": o_boards},
    }


def _mark(player_id: str) -> str:
    return "X" if player_id == "player_1" else "O"


def _player(mark: str) -> str:
    return "player_1" if mark == "X" else "player_2"


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}
