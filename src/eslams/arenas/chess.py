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
    version = "1.1.0"
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
        public = state.public_state
        return {
            "fen": public["fen"],
            "you_are": player_id,
            "color": "white" if player_id == "player_1" else "black",
            "side_to_move": public["side_to_move"],
            "side_to_move_player": public["side_to_move_player"],
            "fullmove_number": public["fullmove_number"],
            "halfmove_clock": public["halfmove_clock"],
            "san_history": public["san_history"],
            "last_move_uci": public["last_move_uci"],
            "last_move_san": public["last_move_san"],
            "legal_uci": state.legal_actions_by_player[player_id],
            "legal_san": public["legal_san"] if player_id == state.active_player else [],
            "legal_moves": public["legal_moves"] if player_id == state.active_player else [],
            "material": public["material"],
            "material_balance": public["material_balance"],
            "king_status": public["king_status"],
            "draw_claims": public["draw_claims"],
            "terminal_reason": public["terminal_reason"],
            "winner": public["winner"],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        self._require_chess()
        if not isinstance(action, str):
            raise ValueError("chess action must be UCI string")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal chess move")
        board = chess.Board(state.public_state["fen"])
        move = chess.Move.from_uci(action)
        move_san = board.san(move)
        board.push(move)
        outcome = _chess_outcome(board)
        if board.fullmove_number > self.max_turns // 2 and outcome is None:
            outcome = {"winner": None, "reason": "max_turns"}
        san_history = [*state.public_state.get("san_history", []), move_san]
        return self._state(
            board=board,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
            san_history=san_history,
            last_move_uci=action,
            last_move_san=move_san,
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
        san_history: list[str] | None = None,
        last_move_uci: str | None = None,
        last_move_san: str | None = None,
    ) -> ArenaState:
        active = "player_1" if board.turn == chess.WHITE else "player_2"
        terminal = outcome is not None
        legal_details = [] if terminal else _legal_move_details(board)
        legal = [item["uci"] for item in legal_details]
        scores = _scores(outcome)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "fen": board.fen(),
                "side_to_move": "white" if board.turn == chess.WHITE else "black",
                "side_to_move_player": active,
                "fullmove_number": board.fullmove_number,
                "halfmove_clock": board.halfmove_clock,
                "san_history": list(san_history or []),
                "last_move_uci": last_move_uci,
                "last_move_san": last_move_san,
                "legal_uci": legal,
                "legal_san": [item["san"] for item in legal_details],
                "legal_moves": legal_details,
                "material": _material_table(board),
                "material_balance": _material_balance(board),
                "king_status": _king_status(board, legal_details),
                "draw_claims": _draw_claims(board),
                "terminal_reason": outcome.get("reason") if outcome else None,
                "winner": outcome.get("winner") if outcome else None,
                "final_validation": {
                    "check": board.is_check(),
                    "checkmate": board.is_checkmate(),
                    "legal_move_count": len(legal),
                    "score": scores,
                },
            },
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=scores,
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"chess:{seed}"),
            render_hints={"renderer": "chessboard"},
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


def _legal_move_details(board: Any) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for move in board.legal_moves:
        after = board.copy(stack=False)
        after.push(move)
        details.append(
            {
                "uci": move.uci(),
                "san": board.san(move),
                "capture": board.is_capture(move),
                "check": after.is_check(),
                "checkmate": after.is_checkmate(),
                "promotion": move.promotion is not None,
                "castle": board.is_castling(move),
                "en_passant": board.is_en_passant(move),
            }
        )
    return sorted(details, key=lambda item: str(item["uci"]))


def _material_table(board: Any) -> dict[str, dict[str, int]]:
    names = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }
    table: dict[str, dict[str, int]] = {"white": {}, "black": {}}
    for piece_type, name in names.items():
        table["white"][name] = len(board.pieces(piece_type, chess.WHITE))
        table["black"][name] = len(board.pieces(piece_type, chess.BLACK))
    return table


def _material_balance(board: Any) -> dict[str, Any]:
    values = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
        chess.KING: 0,
    }
    white = sum(
        len(board.pieces(piece_type, chess.WHITE)) * value
        for piece_type, value in values.items()
    )
    black = sum(
        len(board.pieces(piece_type, chess.BLACK)) * value
        for piece_type, value in values.items()
    )
    return {"white": white, "black": black, "white_minus_black": white - black}


def _king_status(board: Any, legal_details: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "in_check": board.is_check(),
        "checking_pieces": [chess.square_name(square) for square in board.checkers()],
        "legal_evasions": [item["uci"] for item in legal_details] if board.is_check() else [],
    }


def _draw_claims(board: Any) -> dict[str, bool]:
    return {
        "can_claim_threefold_repetition": board.can_claim_threefold_repetition(),
        "can_claim_fifty_move_rule": board.can_claim_fifty_moves(),
        "is_fivefold_repetition": board.is_fivefold_repetition(),
        "is_seventyfive_move_rule": board.is_seventyfive_moves(),
    }


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = "player_2" if winner == "player_1" else "player_1"
    return {winner: 1.0, loser: 0.0}
