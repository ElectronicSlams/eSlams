"""Deterministic Hex arena."""

from __future__ import annotations

from collections import deque
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

SIZE = 11
NEIGHBORS = ((-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0))


class HexArena(Arena):
    id = "hex"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": SIZE * SIZE - 1,
        "description": "Claim a zero-indexed hex cell in row-major order.",
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
            "goal": "connect top to bottom" if player_id == "player_1" else "connect left to right",
            "legal_cells": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("hex action must be an integer cell")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal hex cell")
        row, col = divmod(action, SIZE)
        board = [list(existing_row) for existing_row in state.public_state["board"]]
        board[row][col] = _stone(player_id)
        outcome = (
            {"winner": player_id, "reason": "connected_sides"}
            if _connected(board, _stone(player_id))
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
            outcome = {"winner": None, "reason": "max_turns"}
        legal = [] if terminal else _legal_cells(board)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": SIZE, "cols": SIZE, "geometry": "hex"},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"hex:{seed}"),
            render_hints={
                "renderer": "hex-grid",
                "symbols": {"player_1": "B", "player_2": "W"},
                "goals": {"player_1": "top-bottom", "player_2": "left-right"},
            },
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


def _connected(board: list[list[str | None]], stone: str) -> bool:
    queue: deque[tuple[int, int]] = deque()
    seen: set[tuple[int, int]] = set()
    if stone == "B":
        for col in range(SIZE):
            if board[0][col] == stone:
                queue.append((0, col))
                seen.add((0, col))
    else:
        for row in range(SIZE):
            if board[row][0] == stone:
                queue.append((row, 0))
                seen.add((row, 0))
    while queue:
        row, col = queue.popleft()
        if _reaches_target(row, col, stone):
            return True
        for dr, dc in NEIGHBORS:
            neighbor = (row + dr, col + dc)
            if neighbor in seen:
                continue
            next_row, next_col = neighbor
            if 0 <= next_row < SIZE and 0 <= next_col < SIZE and board[next_row][next_col] == stone:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def _reaches_target(row: int, col: int, stone: str) -> bool:
    if stone == "B":
        return row == SIZE - 1
    return col == SIZE - 1


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}
