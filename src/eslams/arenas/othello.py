"""Deterministic Othello/Reversi arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

SIZE = 8
DIRECTIONS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


class OthelloArena(Arena):
    id = "othello"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "oneOf": [
            {
                "type": "array",
                "prefixItems": [
                    {"type": "integer", "minimum": 0, "maximum": SIZE - 1},
                    {"type": "integer", "minimum": 0, "maximum": SIZE - 1},
                ],
                "minItems": 2,
                "maxItems": 2,
                "description": "Place a disc at [row, col].",
            },
            {"const": "pass", "description": "Pass only when no placement is legal."},
        ]
    }
    max_turns = SIZE * SIZE

    def initial_state(self, seed: int) -> ArenaState:
        board: list[list[str | None]] = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        board[3][3] = "W"
        board[3][4] = "B"
        board[4][3] = "B"
        board[4][4] = "W"
        return self._state(board=board, turn=0, active="player_1", seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "disc": _disc(player_id),
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal othello action")
        board = [list(row) for row in state.public_state["board"]]
        if action != "pass":
            row, col = _action_pair(action)
            flips = _flips(board, row, col, _disc(player_id))
            if not flips:
                raise ValueError("othello placement flips no discs")
            board[row][col] = _disc(player_id)
            for flip_row, flip_col in flips:
                board[flip_row][flip_col] = _disc(player_id)
        next_player = _other(player_id)
        outcome = _outcome(board)
        return self._state(
            board=board,
            turn=state.turn + 1,
            active=next_player,
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
        if outcome is None and (_board_full(board) or not _has_any_legal_move(board)):
            outcome = _final_outcome(board, "finished")
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _final_outcome(board, "max_turns")
        legal: list[Any] = [] if terminal else _legal_actions(board, _disc(active))
        if not legal and not terminal:
            legal = ["pass"]
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
            rng_commitment=sha256_text(f"othello:{seed}"),
            render_hints={"renderer": "grid", "symbols": {"player_1": "B", "player_2": "W"}},
            metadata={"seed": seed},
        )


def _disc(player_id: str) -> str:
    return "B" if player_id == "player_1" else "W"


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _opponent(disc: str) -> str:
    return "W" if disc == "B" else "B"


def _legal_actions(board: list[list[str | None]], disc: str) -> list[list[int]]:
    actions: list[list[int]] = []
    for row in range(SIZE):
        for col in range(SIZE):
            if _flips(board, row, col, disc):
                actions.append([row, col])
    return actions


def _flips(board: list[list[str | None]], row: int, col: int, disc: str) -> list[tuple[int, int]]:
    if not _inside(row, col) or board[row][col] is not None:
        return []
    all_flips: list[tuple[int, int]] = []
    opponent = _opponent(disc)
    for dr, dc in DIRECTIONS:
        path: list[tuple[int, int]] = []
        current_row = row + dr
        current_col = col + dc
        while _inside(current_row, current_col) and board[current_row][current_col] == opponent:
            path.append((current_row, current_col))
            current_row += dr
            current_col += dc
        if path and _inside(current_row, current_col) and board[current_row][current_col] == disc:
            all_flips.extend(path)
    return all_flips


def _inside(row: int, col: int) -> bool:
    return 0 <= row < SIZE and 0 <= col < SIZE


def _action_pair(action: Any) -> tuple[int, int]:
    if (
        isinstance(action, (list, tuple))
        and len(action) == 2
        and all(isinstance(value, int) for value in action)
    ):
        return int(action[0]), int(action[1])
    raise ValueError("othello action must be [row, col]")


def _board_full(board: list[list[str | None]]) -> bool:
    return all(cell is not None for row in board for cell in row)


def _has_any_legal_move(board: list[list[str | None]]) -> bool:
    return bool(_legal_actions(board, "B") or _legal_actions(board, "W"))


def _outcome(board: list[list[str | None]]) -> dict[str, Any] | None:
    if _board_full(board) or not _has_any_legal_move(board):
        return _final_outcome(board, "finished")
    return None


def _final_outcome(board: list[list[str | None]], reason: str) -> dict[str, Any]:
    counts = _counts(board)
    winner = None
    if counts["B"] > counts["W"]:
        winner = "player_1"
    elif counts["W"] > counts["B"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "disc_counts": counts}


def _counts(board: list[list[str | None]]) -> dict[str, int]:
    return {
        "B": sum(cell == "B" for row in board for cell in row),
        "W": sum(cell == "W" for row in board for cell in row),
    }


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}
