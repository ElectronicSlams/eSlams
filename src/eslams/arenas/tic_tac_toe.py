"""Tiny public arena used for protocol tests."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState


class TicTacToeArena(Arena):
    id = "tic-tac-toe"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 8,
        "description": "Claim a zero-indexed square in row-major order.",
    }
    max_turns = 9

    def initial_state(self, seed: int) -> ArenaState:
        return self._state([None] * 9, 0, "player_1", seed, None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "mark": "X" if player_id == "player_1" else "O",
            "legal_squares": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("tic-tac-toe action must be an integer square")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal tic-tac-toe square")
        board = list(state.public_state["board"])
        board[action] = "X" if player_id == "player_1" else "O"
        winner = _winner(board)
        outcome = {"winner": player_id, "reason": "three_in_a_row"} if winner else None
        active = "player_2" if player_id == "player_1" else "player_1"
        return self._state(board, state.turn + 1, active, int(state.metadata["seed"]), outcome)

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        board: list[str | None],
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= 9 or all(cell is not None for cell in board)
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "draw"}
        scores = {"player_1": 0.0, "player_2": 0.0}
        if outcome:
            if outcome["winner"] is None:
                scores = {"player_1": 0.5, "player_2": 0.5}
            else:
                scores[str(outcome["winner"])] = 1.0
        legal = [] if terminal else [index for index, cell in enumerate(board) if cell is None]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": 3, "cols": 3},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=scores,
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"tic-tac-toe:{seed}"),
            render_hints={"renderer": "grid", "symbols": {"player_1": "X", "player_2": "O"}},
            metadata={"seed": seed},
        )


def _winner(board: list[str | None]) -> str | None:
    lines = (
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    )
    for a, b, c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return str(board[a])
    return None
