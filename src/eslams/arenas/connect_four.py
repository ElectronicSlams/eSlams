"""Deterministic Connect Four arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

ROWS = 6
COLS = 7


class ConnectFourArena(Arena):
    id = "connect-four"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": COLS - 1,
        "description": "Drop a disc into a zero-indexed column.",
    }
    max_turns = ROWS * COLS

    def initial_state(self, seed: int) -> ArenaState:
        board: list[list[str | None]] = [[None for _ in range(COLS)] for _ in range(ROWS)]
        return self._state(board=board, turn=0, active="player_1", seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "disc": "R" if player_id == "player_1" else "Y",
            "legal_columns": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("connect-four action must be an integer column")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal connect-four column")
        board = [list(row) for row in state.public_state["board"]]
        disc = "R" if player_id == "player_1" else "Y"
        for row in range(ROWS - 1, -1, -1):
            if board[row][action] is None:
                board[row][action] = disc
                break
        outcome = _outcome(board, player_id, disc)
        next_player = "player_2" if player_id == "player_1" else "player_1"
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
        terminal = outcome is not None or turn >= self.max_turns or _board_full(board)
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "draw"}
        scores = _scores(outcome)
        legal = [] if terminal else [col for col in range(COLS) if board[0][col] is None]
        legal_by_player = {player: (legal if player == active else []) for player in self.players}
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": ROWS, "cols": COLS},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player=legal_by_player,
            scores=scores,
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"connect-four:{seed}"),
            render_hints={"renderer": "grid", "symbols": {"player_1": "R", "player_2": "Y"}},
            metadata={"seed": seed},
        )


def _board_full(board: list[list[str | None]]) -> bool:
    return all(cell is not None for cell in board[0])


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if not outcome or outcome.get("winner") is None:
        return {"player_1": 0.5 if outcome else 0.0, "player_2": 0.5 if outcome else 0.0}
    winner = str(outcome["winner"])
    loser = "player_2" if winner == "player_1" else "player_1"
    return {winner: 1.0, loser: 0.0}


def _outcome(board: list[list[str | None]], player_id: str, disc: str) -> dict[str, Any] | None:
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    for row in range(ROWS):
        for col in range(COLS):
            if board[row][col] != disc:
                continue
            for dr, dc in directions:
                if all(
                    0 <= row + dr * i < ROWS
                    and 0 <= col + dc * i < COLS
                    and board[row + dr * i][col + dc * i] == disc
                    for i in range(4)
                ):
                    return {"winner": player_id, "reason": "four_in_a_row"}
    return None
