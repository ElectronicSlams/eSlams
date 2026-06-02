"""Deterministic Gomoku arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

SIZE = 15
TARGET = 5
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


class GomokuArena(Arena):
    id = "gomoku"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": SIZE * SIZE - 1,
        "description": "Claim a zero-indexed board cell in row-major order.",
    }
    max_turns = SIZE * SIZE

    def initial_state(self, seed: int) -> ArenaState:
        board: list[list[str | None]] = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        return self._state(board=board, turn=0, active="player_1", seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "stone": _stone(player_id),
            "legal_cells": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("gomoku action must be an integer cell")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal gomoku cell")
        row, col = divmod(action, SIZE)
        board = [list(existing_row) for existing_row in state.public_state["board"]]
        board[row][col] = _stone(player_id)
        outcome = (
            {"winner": player_id, "reason": "five_in_a_row"}
            if _has_line(board, row, col, _stone(player_id))
            else None
        )
        return self._state(
            board=board,
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
        board: list[list[str | None]],
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns or _board_full(board)
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "draw"}
        legal = [] if terminal else _legal_cells(board)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": SIZE, "cols": SIZE},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"gomoku:{seed}"),
            render_hints={"renderer": "grid", "symbols": {"player_1": "B", "player_2": "W"}},
            metadata={"seed": seed},
        )


def _stone(player_id: str) -> str:
    return "B" if player_id == "player_1" else "W"


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _legal_cells(board: list[list[str | None]]) -> list[int]:
    return [
        row * SIZE + col
        for row in range(SIZE)
        for col in range(SIZE)
        if board[row][col] is None
    ]


def _board_full(board: list[list[str | None]]) -> bool:
    return all(cell is not None for row in board for cell in row)


def _has_line(board: list[list[str | None]], row: int, col: int, stone: str) -> bool:
    for dr, dc in DIRECTIONS:
        forward = _count(board, row, col, dr, dc, stone)
        backward = _count(board, row, col, -dr, -dc, stone)
        length = 1 + forward + backward
        if length >= TARGET:
            return True
    return False


def _count(
    board: list[list[str | None]],
    row: int,
    col: int,
    dr: int,
    dc: int,
    stone: str,
) -> int:
    total = 0
    current_row = row + dr
    current_col = col + dc
    while 0 <= current_row < SIZE and 0 <= current_col < SIZE:
        if board[current_row][current_col] != stone:
            break
        total += 1
        current_row += dr
        current_col += dc
    return total


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}
