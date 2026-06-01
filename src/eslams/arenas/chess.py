"""Chess arena powered by python-chess."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

try:
    import chess
except Exception:  # pragma: no cover - import failure is surfaced on use
    chess = None  # type: ignore[assignment]


class ChessArena(Arena):
    id = "chess"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^[a-h][1-8][a-h][1-8][qrbn]?$",
        "description": "UCI move such as e2e4 or e7e8q.",
    }
    max_turns = 240

    def initial_state(self, seed: int) -> ArenaState:
        self._require_chess()
        board = chess.Board()
        return self._state(board=board, turn=0, seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "fen": state.public_state["fen"],
            "you_are": player_id,
            "color": "white" if player_id == "player_1" else "black",
            "legal_uci": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        self._require_chess()
        if not isinstance(action, str):
            raise ValueError("chess action must be UCI string")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal chess move")
        board = chess.Board(state.public_state["fen"])
        board.push(chess.Move.from_uci(action))
        outcome = _chess_outcome(board)
        if board.fullmove_number > self.max_turns // 2 and outcome is None:
            outcome = {"winner": None, "reason": "max_turns"}
        return self._state(
            board=board,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        board: Any,
        turn: int,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        active = "player_1" if board.turn == chess.WHITE else "player_2"
        terminal = outcome is not None
        legal = [] if terminal else [move.uci() for move in board.legal_moves]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"fen": board.fen(), "san_history": []},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"chess:{seed}"),
            render_hints={"renderer": "chessboard", "orientation": active},
            metadata={"seed": seed},
        )

    @staticmethod
    def _require_chess() -> None:
        if chess is None:
            raise RuntimeError("ChessArena requires the python-chess dependency")


def _chess_outcome(board: Any) -> dict[str, Any] | None:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    winner = None
    if outcome.winner is True:
        winner = "player_1"
    elif outcome.winner is False:
        winner = "player_2"
    return {"winner": winner, "reason": outcome.termination.name.lower()}


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = "player_2" if winner == "player_1" else "player_1"
    return {winner: 1.0, loser: 0.0}
