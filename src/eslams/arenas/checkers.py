"""Deterministic American checkers arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

SIZE = 8
MEN = {"player_1": "r", "player_2": "b"}
KINGS = {"player_1": "R", "player_2": "B"}


class CheckersArena(Arena):
    id = "checkers"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^[0-7],[0-7]-[0-7],[0-7]$",
        "description": "Move one piece, e.g. '5,0-4,1'. Captures are mandatory.",
    }
    max_turns = 200

    def initial_state(self, seed: int) -> ArenaState:
        board: list[list[str | None]] = [[None for _ in range(SIZE)] for _ in range(SIZE)]
        for row in range(3):
            for col in range(SIZE):
                if (row + col) % 2 == 1:
                    board[row][col] = "b"
        for row in range(5, SIZE):
            for col in range(SIZE):
                if (row + col) % 2 == 1:
                    board[row][col] = "r"
        return self._state(
            board=board,
            turn=0,
            active="player_1",
            seed=seed,
            outcome=None,
            forced_piece=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "pieces": {"man": MEN[player_id], "king": KINGS[player_id]},
            "forced_piece": state.public_state.get("forced_piece"),
            "legal_moves": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal checkers move")
        start, end = _parse_move(action)
        board = [list(row) for row in state.public_state["board"]]
        sr, sc = start
        er, ec = end
        piece = board[sr][sc]
        if piece is None:
            raise ValueError("checkers move has no source piece")
        board[sr][sc] = None
        captured = abs(er - sr) == 2
        if abs(er - sr) == 2:
            board[(sr + er) // 2][(sc + ec) // 2] = None
        promoted_piece = _promote(piece, er)
        board[er][ec] = promoted_piece
        further_jumps = (
            captured
            and promoted_piece == piece
            and bool(_capture_moves_from(board, player_id, er, ec))
        )
        next_player = player_id if further_jumps else _other(player_id)
        forced_piece = (er, ec) if further_jumps else None
        outcome = _terminal_outcome_after_move(board, next_player, forced_piece)
        return self._state(
            board=board,
            turn=state.turn + 1,
            active=next_player,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
            forced_piece=forced_piece,
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
        forced_piece: tuple[int, int] | None,
    ) -> ArenaState:
        if outcome is None and turn >= self.max_turns:
            outcome = _material_outcome(board, "max_turns")
        terminal = outcome is not None
        legal = [] if terminal else _legal_moves(board, active, forced_piece)
        if outcome is None and not legal:
            outcome = {"winner": _other(active), "reason": "no_legal_moves"}
            terminal = True
            forced_piece = None
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "board": board,
                "rows": SIZE,
                "cols": SIZE,
                "forced_piece": list(forced_piece) if forced_piece else None,
            },
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else [])
                for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"checkers:{seed}"),
            render_hints={"renderer": "grid", "symbols": {**MEN, **KINGS}},
            metadata={"seed": seed},
        )


def _legal_moves(
    board: list[list[str | None]],
    player_id: str,
    forced_piece: tuple[int, int] | None = None,
) -> list[str]:
    captures: list[str] = []
    moves: list[str] = []
    owned = {MEN[player_id], KINGS[player_id]}
    positions = [forced_piece] if forced_piece else [
        (row, col)
        for row in range(SIZE)
        for col in range(SIZE)
    ]
    for row, col in positions:
        piece = board[row][col]
        if piece not in owned:
            continue
        for dr, dc in _directions(piece):
            nr, nc = row + dr, col + dc
            if forced_piece is None and _inside(nr, nc) and board[nr][nc] is None:
                moves.append(_move(row, col, nr, nc))
            jr, jc = row + dr * 2, col + dc * 2
            if (
                _inside(jr, jc)
                and _inside(nr, nc)
                and board[jr][jc] is None
                and board[nr][nc] in _opponent_pieces(player_id)
            ):
                captures.append(_move(row, col, jr, jc))
    return sorted(captures or moves)


def _capture_moves_from(
    board: list[list[str | None]],
    player_id: str,
    row: int,
    col: int,
) -> list[str]:
    return _legal_moves(board, player_id, (row, col))


def _directions(piece: str) -> tuple[tuple[int, int], ...]:
    if piece in {"R", "B"}:
        return ((-1, -1), (-1, 1), (1, -1), (1, 1))
    if piece == "r":
        return ((-1, -1), (-1, 1))
    return ((1, -1), (1, 1))


def _opponent_pieces(player_id: str) -> set[str]:
    opponent = _other(player_id)
    return {MEN[opponent], KINGS[opponent]}


def _promote(piece: str, row: int) -> str:
    if piece == "r" and row == 0:
        return "R"
    if piece == "b" and row == SIZE - 1:
        return "B"
    return piece


def _terminal_outcome_after_move(
    board: list[list[str | None]],
    next_player: str,
    forced_piece: tuple[int, int] | None,
) -> dict[str, Any] | None:
    counts = _counts(board)
    if counts["player_1"] == 0:
        return {"winner": "player_2", "reason": "all_pieces_captured"}
    if counts["player_2"] == 0:
        return {"winner": "player_1", "reason": "all_pieces_captured"}
    if forced_piece is not None:
        return None
    if not _legal_moves(board, next_player):
        return {"winner": _other(next_player), "reason": "no_legal_moves"}
    return None


def _material_outcome(board: list[list[str | None]], reason: str) -> dict[str, Any]:
    material = _material(board)
    winner = None
    if material["player_1"] > material["player_2"]:
        winner = "player_1"
    elif material["player_2"] > material["player_1"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "material": material}


def _counts(board: list[list[str | None]]) -> dict[str, int]:
    return {
        "player_1": sum(cell in {"r", "R"} for row in board for cell in row),
        "player_2": sum(cell in {"b", "B"} for row in board for cell in row),
    }


def _material(board: list[list[str | None]]) -> dict[str, int]:
    values = {"r": 1, "R": 2, "b": 1, "B": 2}
    return {
        "player_1": sum(
            values.get(cell or "", 0) for row in board for cell in row if cell in {"r", "R"}
        ),
        "player_2": sum(
            values.get(cell or "", 0) for row in board for cell in row if cell in {"b", "B"}
        ),
    }


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}


def _parse_move(action: str) -> tuple[tuple[int, int], tuple[int, int]]:
    start, end = action.split("-")
    sr, sc = (int(value) for value in start.split(","))
    er, ec = (int(value) for value in end.split(","))
    if not (_inside(sr, sc) and _inside(er, ec)):
        raise ValueError("checkers move is outside the board")
    return (sr, sc), (er, ec)


def _move(sr: int, sc: int, er: int, ec: int) -> str:
    return f"{sr},{sc}-{er},{ec}"


def _inside(row: int, col: int) -> bool:
    return 0 <= row < SIZE and 0 <= col < SIZE


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
