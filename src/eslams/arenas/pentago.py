"""Deterministic Pentago arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

SIZE = 6
TARGET = 5
QUADRANTS = (0, 1, 2, 3)
DIRECTIONS = ("cw", "ccw")
LINES = ((1, 0), (0, 1), (1, 1), (1, -1))


class PentagoArena(Arena):
    id = "pentago"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^[0-9]+:[0-3]:(cw|ccw)$",
        "description": "Place at cell then rotate a quadrant, e.g. '14:2:cw'.",
    }
    max_turns = SIZE * SIZE

    def initial_state(self, seed: int) -> ArenaState:
        board: list[list[str | None]] = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        return self._state(board=board, turn=0, active="player_1", seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "marble": _marble(player_id),
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal pentago action")
        cell, quadrant, direction = _parse_action(action)
        row, col = divmod(cell, SIZE)
        board = [list(existing_row) for existing_row in state.public_state["board"]]
        board[row][col] = _marble(player_id)
        _rotate(board, quadrant, direction)
        winners = [player for player in self.players if _has_line(board, _marble(player))]
        outcome: dict[str, Any] | None = None
        if len(winners) == 1:
            outcome = {"winner": winners[0], "reason": "five_in_a_row"}
        elif len(winners) > 1:
            outcome = {"winner": None, "reason": "simultaneous_five_in_a_row"}
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
        legal = [] if terminal else _legal_actions(board)
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
            rng_commitment=sha256_text(f"pentago:{seed}"),
            render_hints={
                "renderer": "grid",
                "symbols": {"player_1": "B", "player_2": "W"},
                "quadrants": 4,
            },
            metadata={"seed": seed},
        )


def _legal_actions(board: list[list[str | None]]) -> list[str]:
    actions: list[str] = []
    for row in range(SIZE):
        for col in range(SIZE):
            if board[row][col] is not None:
                continue
            cell = row * SIZE + col
            for quadrant in QUADRANTS:
                for direction in DIRECTIONS:
                    actions.append(f"{cell}:{quadrant}:{direction}")
    return actions


def _parse_action(action: str) -> tuple[int, int, str]:
    raw_cell, raw_quadrant, direction = action.split(":")
    cell = int(raw_cell)
    quadrant = int(raw_quadrant)
    if not 0 <= cell < SIZE * SIZE or quadrant not in QUADRANTS or direction not in DIRECTIONS:
        raise ValueError("invalid pentago action")
    return cell, quadrant, direction


def _rotate(board: list[list[str | None]], quadrant: int, direction: str) -> None:
    row_offset = 0 if quadrant in {0, 1} else 3
    col_offset = 0 if quadrant in {0, 2} else 3
    block = [
        [board[row_offset + row][col_offset + col] for col in range(3)]
        for row in range(3)
    ]
    if direction == "cw":
        rotated = [[block[2 - col][row] for col in range(3)] for row in range(3)]
    else:
        rotated = [[block[col][2 - row] for col in range(3)] for row in range(3)]
    for row in range(3):
        for col in range(3):
            board[row_offset + row][col_offset + col] = rotated[row][col]


def _has_line(board: list[list[str | None]], marble: str) -> bool:
    for row in range(SIZE):
        for col in range(SIZE):
            if board[row][col] != marble:
                continue
            for dr, dc in LINES:
                if all(
                    0 <= row + dr * index < SIZE
                    and 0 <= col + dc * index < SIZE
                    and board[row + dr * index][col + dc * index] == marble
                    for index in range(TARGET)
                ):
                    return True
    return False


def _board_full(board: list[list[str | None]]) -> bool:
    return all(cell is not None for row in board for cell in row)


def _marble(player_id: str) -> str:
    return "B" if player_id == "player_1" else "W"


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
