"""Compact deterministic East Asian board-game arenas."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from eslams.arena import Arena
from eslams.hashing import sha256_json, sha256_text
from eslams.state import ArenaState

Player = str
Point = tuple[int, int]
Board = list[list[Optional[str]]]


class GoArena(Arena):
    """Legal-action-safe 9x9 Go with captures, suicide prevention, ko, and area scoring."""

    id = "go"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "oneOf": [
            {
                "type": "integer",
                "minimum": 0,
                "maximum": 80,
                "description": "Place a stone on a zero-indexed 9x9 point in row-major order.",
            },
            {"type": "string", "enum": ["pass", "resign"]},
        ]
    }
    max_turns = 180

    def initial_state(self, seed: int) -> ArenaState:
        board = _empty_board(9, 9)
        return self._state(
            board=board,
            turn=0,
            active="player_1",
            seed=seed,
            captures={"player_1": 0, "player_2": 0},
            consecutive_passes=0,
            previous_hashes={_board_hash(board)},
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "stone": _go_stone(player_id),
            "captures": state.public_state["captures"],
            "komi": state.public_state["komi"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal go action")
        board = _clone_board(state.public_state["board"])
        captures = {
            player: int(value)
            for player, value in state.public_state["captures"].items()
        }
        previous_hashes = {str(value) for value in state.metadata["previous_hashes"]}
        outcome = None
        consecutive_passes = int(state.metadata["consecutive_passes"])

        if action == "resign":
            outcome = {"winner": _other(player_id), "reason": "resignation"}
        elif action == "pass":
            consecutive_passes += 1
            if consecutive_passes >= 2:
                outcome = _go_area_outcome(board, captures, "two_passes")
        else:
            if not isinstance(action, int):
                raise ValueError("go placement must be an integer, pass, or resign")
            row, col = divmod(action, 9)
            board, captured = _go_play(board, row, col, player_id)
            captures[player_id] += captured
            consecutive_passes = 0
            previous_hashes.add(_board_hash(board))

        if outcome is None and state.turn + 1 >= self.max_turns:
            outcome = _go_area_outcome(board, captures, "max_turns")
        return self._state(
            board=board,
            turn=state.turn + 1,
            active=_other(player_id),
            seed=int(state.metadata["seed"]),
            captures=captures,
            consecutive_passes=consecutive_passes,
            previous_hashes=previous_hashes,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        board: Board,
        turn: int,
        active: str,
        seed: int,
        captures: dict[str, int],
        consecutive_passes: int,
        previous_hashes: set[str],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None
        legal = [] if terminal else _go_legal_actions(board, active, previous_hashes)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "board": board,
                "rows": 9,
                "cols": 9,
                "captures": captures,
                "komi": 6.5,
            },
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_win_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"go:{seed}"),
            render_hints={"renderer": "grid", "symbols": {"player_1": "B", "player_2": "W"}},
            metadata={
                "seed": seed,
                "consecutive_passes": consecutive_passes,
                "previous_hashes": sorted(previous_hashes),
            },
        )


class ShogiArena(Arena):
    """Compact Shogi adapter with legal movement, captures, drops, and promotion choices."""

    id = "shogi"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "description": "Move like 7g7f or 2b3c+; drop like P*5e.",
    }
    max_turns = 320

    def initial_state(self, seed: int) -> ArenaState:
        board = _shogi_initial_board()
        hands: dict[str, dict[str, int]] = {"player_1": {}, "player_2": {}}
        return self._state(
            board=board,
            hands=hands,
            turn=0,
            active="player_1",
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "hands": state.public_state["hands"],
            "you_are": player_id,
            "side": "sente" if player_id == "player_1" else "gote",
            "legal_moves": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal shogi action")
        board = _clone_board(state.public_state["board"])
        hands = _copy_hands(state.public_state["hands"])
        outcome = None

        if "*" in action:
            dropped_piece, row, col = _parse_shogi_drop(action)
            held = hands[player_id].get(dropped_piece, 0)
            if held <= 0:
                raise ValueError("shogi drop uses unavailable piece")
            board[row][col] = _owned_piece(dropped_piece, player_id)
            if held == 1:
                del hands[player_id][dropped_piece]
            else:
                hands[player_id][dropped_piece] = held - 1
        else:
            start, end, promote = _parse_shogi_move(action)
            sr, sc = start
            er, ec = end
            piece = board[sr][sc]
            if piece is None:
                raise ValueError("shogi move has no source piece")
            captured = board[er][ec]
            if captured is not None:
                owner = _piece_owner(captured)
                if owner == player_id:
                    raise ValueError("shogi move captures own piece")
                base = _shogi_base(captured).upper()
                if base == "K":
                    outcome = {"winner": player_id, "reason": "king_captured"}
                else:
                    hands[player_id][base] = hands[player_id].get(base, 0) + 1
            board[sr][sc] = None
            board[er][ec] = _shogi_promote(piece) if promote else piece

        if outcome is None and state.turn + 1 >= self.max_turns:
            outcome = _material_outcome(board, "max_turns", _SHOGI_VALUES)
        return self._state(
            board=board,
            hands=hands,
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
        board: Board,
        hands: dict[str, dict[str, int]],
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        if outcome is None and not _has_piece(board, active, "K"):
            outcome = {"winner": _other(active), "reason": "king_captured"}
        terminal = outcome is not None
        legal = [] if terminal else _shogi_legal_actions(board, hands, active)
        if outcome is None and not legal:
            outcome = {"winner": _other(active), "reason": "no_legal_moves"}
            terminal = True
        public_hands = {player: dict(sorted(hands[player].items())) for player in self.players}
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": 9, "cols": 9, "hands": public_hands},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else [])
                for player in self.players
            },
            scores=_win_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"shogi:{seed}"),
            render_hints={
                "renderer": "grid",
                "symbols": {"player_1": "uppercase", "player_2": "lowercase"},
            },
            metadata={"seed": seed},
        )


class XiangqiArena(Arena):
    """Compact Xiangqi adapter with palace, river, cannon, and flying-general rules."""

    id = "xiangqi"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^[a-i][0-9][a-i][0-9]$",
        "description": "Move from source to destination, e.g. a9a8.",
    }
    max_turns = 240

    def initial_state(self, seed: int) -> ArenaState:
        board = _xiangqi_initial_board()
        return self._state(board=board, turn=0, active="player_1", seed=seed, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "board": state.public_state["board"],
            "you_are": player_id,
            "side": "red" if player_id == "player_1" else "black",
            "legal_moves": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal xiangqi action")
        board = _clone_board(state.public_state["board"])
        sr, sc, er, ec = _parse_xiangqi_move(action)
        piece = board[sr][sc]
        if piece is None:
            raise ValueError("xiangqi move has no source piece")
        captured = board[er][ec]
        outcome = None
        if captured is not None and _xiangqi_base(captured) == "g":
            outcome = {"winner": player_id, "reason": "general_captured"}
        board[sr][sc] = None
        board[er][ec] = piece
        if outcome is None and state.turn + 1 >= self.max_turns:
            outcome = _material_outcome(board, "max_turns", _XIANGQI_VALUES)
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
        board: Board,
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        if outcome is None and not _has_piece(board, active, "G"):
            outcome = {"winner": _other(active), "reason": "general_captured"}
        terminal = outcome is not None
        legal = [] if terminal else _xiangqi_legal_actions(board, active)
        if outcome is None and not legal:
            outcome = {"winner": _other(active), "reason": "no_legal_moves"}
            terminal = True
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"board": board, "rows": 10, "cols": 9},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else [])
                for player in self.players
            },
            scores=_win_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"xiangqi:{seed}"),
            render_hints={
                "renderer": "grid",
                "symbols": {"player_1": "uppercase", "player_2": "lowercase"},
            },
            metadata={"seed": seed},
        )


def _empty_board(rows: int, cols: int) -> Board:
    return [[None for _ in range(cols)] for _ in range(rows)]


def _clone_board(board: Iterable[Iterable[str | None]]) -> Board:
    return [list(row) for row in board]


def _inside(board: Board, row: int, col: int) -> bool:
    return 0 <= row < len(board) and 0 <= col < len(board[0])


def _neighbors(board: Board, row: int, col: int) -> Iterable[Point]:
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        if _inside(board, nr, nc):
            yield nr, nc


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _win_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    return {winner: 1.0, _other(winner): 0.0}


def _material_outcome(board: Board, reason: str, values: dict[str, int]) -> dict[str, Any]:
    material = {"player_1": 0, "player_2": 0}
    for row in board:
        for cell in row:
            if cell is None:
                continue
            owner = _piece_owner(cell)
            material[owner] += values.get(_piece_base(cell).upper(), 0)
    winner = None
    if material["player_1"] > material["player_2"]:
        winner = "player_1"
    elif material["player_2"] > material["player_1"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "material": material}


def _piece_owner(piece: str) -> str:
    core = piece[1:] if piece.startswith("+") else piece
    return "player_1" if core.isupper() else "player_2"


def _piece_base(piece: str) -> str:
    return piece[1:] if piece.startswith("+") else piece


def _owned_piece(piece: str, player_id: str) -> str:
    return piece.upper() if player_id == "player_1" else piece.lower()


def _has_piece(board: Board, player_id: str, piece: str) -> bool:
    target = _owned_piece(piece, player_id)
    return any(cell == target for row in board for cell in row)


# Go helpers


def _go_stone(player_id: str) -> str:
    return "B" if player_id == "player_1" else "W"


def _board_hash(board: Board) -> str:
    return sha256_json(board)


def _go_group(board: Board, row: int, col: int) -> tuple[set[Point], set[Point]]:
    color = board[row][col]
    if color is None:
        return set(), set()
    group = {(row, col)}
    liberties: set[Point] = set()
    frontier = [(row, col)]
    while frontier:
        cr, cc = frontier.pop()
        for nr, nc in _neighbors(board, cr, cc):
            neighbor = board[nr][nc]
            if neighbor is None:
                liberties.add((nr, nc))
            elif neighbor == color and (nr, nc) not in group:
                group.add((nr, nc))
                frontier.append((nr, nc))
    return group, liberties


def _go_play(board: Board, row: int, col: int, player_id: str) -> tuple[Board, int]:
    if not _inside(board, row, col) or board[row][col] is not None:
        raise ValueError("go point is occupied or outside the board")
    next_board = _clone_board(board)
    stone = _go_stone(player_id)
    opponent = _go_stone(_other(player_id))
    next_board[row][col] = stone
    captured = 0
    for nr, nc in list(_neighbors(next_board, row, col)):
        if next_board[nr][nc] != opponent:
            continue
        group, liberties = _go_group(next_board, nr, nc)
        if not liberties:
            captured += len(group)
            for gr, gc in group:
                next_board[gr][gc] = None
    own_group, own_liberties = _go_group(next_board, row, col)
    if not own_liberties and not captured:
        raise ValueError("go suicide is illegal")
    return next_board, captured


def _go_legal_actions(board: Board, player_id: str, previous_hashes: set[str]) -> list[Any]:
    legal: list[Any] = []
    for row in range(9):
        for col in range(9):
            if board[row][col] is not None:
                continue
            action = row * 9 + col
            try:
                next_board, _captured = _go_play(board, row, col, player_id)
            except ValueError:
                continue
            if _board_hash(next_board) not in previous_hashes:
                legal.append(action)
    legal.extend(["pass", "resign"])
    return legal


def _go_area_outcome(board: Board, captures: dict[str, int], reason: str) -> dict[str, Any]:
    area = {"player_1": 0.0, "player_2": 6.5}
    visited: set[Point] = set()
    for row in range(9):
        for col in range(9):
            cell = board[row][col]
            if cell == "B":
                area["player_1"] += 1.0
            elif cell == "W":
                area["player_2"] += 1.0
            elif (row, col) not in visited:
                region, borders = _go_empty_region(board, row, col)
                visited.update(region)
                if borders == {"B"}:
                    area["player_1"] += float(len(region))
                elif borders == {"W"}:
                    area["player_2"] += float(len(region))
    winner = None
    if area["player_1"] > area["player_2"]:
        winner = "player_1"
    elif area["player_2"] > area["player_1"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "area": area, "captures": captures}


def _go_empty_region(board: Board, row: int, col: int) -> tuple[set[Point], set[str]]:
    region = {(row, col)}
    borders: set[str] = set()
    frontier = [(row, col)]
    while frontier:
        cr, cc = frontier.pop()
        for nr, nc in _neighbors(board, cr, cc):
            cell = board[nr][nc]
            if cell is None and (nr, nc) not in region:
                region.add((nr, nc))
                frontier.append((nr, nc))
            elif cell is not None:
                borders.add(cell)
    return region, borders


# Shogi helpers

_SHOGI_VALUES = {"K": 1000, "R": 8, "B": 7, "G": 6, "S": 5, "N": 3, "L": 3, "P": 1}
_PROMOTABLE = {"P", "L", "N", "S", "B", "R"}


def _shogi_initial_board() -> Board:
    return [
        list("lnsgkgsnl"),
        [None, "b", None, None, None, None, None, "r", None],
        list("ppppppppp"),
        [None for _ in range(9)],
        [None for _ in range(9)],
        [None for _ in range(9)],
        list("PPPPPPPPP"),
        [None, "R", None, None, None, None, None, "B", None],
        list("LNSGKGSNL"),
    ]


def _copy_hands(hands: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {
        player: {piece: int(count) for piece, count in hand.items()}
        for player, hand in hands.items()
    }


def _shogi_pos(row: int, col: int) -> str:
    return f"{9 - col}{chr(ord('a') + row)}"


def _parse_shogi_square(square: str) -> Point:
    if len(square) != 2 or square[0] not in "123456789" or square[1] not in "abcdefghi":
        raise ValueError("invalid shogi square")
    return ord(square[1]) - ord("a"), 9 - int(square[0])


def _parse_shogi_move(action: str) -> tuple[Point, Point, bool]:
    promote = action.endswith("+")
    core = action[:-1] if promote else action
    if len(core) != 4:
        raise ValueError("invalid shogi move")
    return _parse_shogi_square(core[:2]), _parse_shogi_square(core[2:]), promote


def _parse_shogi_drop(action: str) -> tuple[str, int, int]:
    if len(action) != 4 or action[1] != "*" or action[0] not in "PLNSGBR":
        raise ValueError("invalid shogi drop")
    row, col = _parse_shogi_square(action[2:])
    return action[0], row, col


def _shogi_base(piece: str) -> str:
    return piece[1:] if piece.startswith("+") else piece


def _shogi_promote(piece: str) -> str:
    if piece.startswith("+"):
        return piece
    return "+" + piece


def _shogi_is_promoted(piece: str) -> bool:
    return piece.startswith("+")


def _shogi_zone(player_id: str, row: int) -> bool:
    return row <= 2 if player_id == "player_1" else row >= 6


def _shogi_legal_actions(
    board: Board,
    hands: dict[str, dict[str, int]],
    player_id: str,
) -> list[str]:
    actions: list[str] = []
    for row in range(9):
        for col in range(9):
            piece = board[row][col]
            if piece is None or _piece_owner(piece) != player_id:
                continue
            for er, ec in _shogi_destinations(board, row, col, piece, player_id):
                base = _shogi_base(piece).upper()
                action = _shogi_pos(row, col) + _shogi_pos(er, ec)
                if base in _PROMOTABLE and not _shogi_is_promoted(piece) and (
                    _shogi_zone(player_id, row) or _shogi_zone(player_id, er)
                ):
                    if _shogi_must_promote(base, player_id, er):
                        actions.append(action + "+")
                    else:
                        actions.append(action)
                        actions.append(action + "+")
                else:
                    actions.append(action)
    actions.extend(_shogi_drop_actions(board, hands.get(player_id, {}), player_id))
    return sorted(actions)


def _shogi_destinations(
    board: Board,
    row: int,
    col: int,
    piece: str,
    player_id: str,
) -> list[Point]:
    base = _shogi_base(piece).upper()
    forward = -1 if player_id == "player_1" else 1
    if _shogi_is_promoted(piece) and base in {"P", "L", "N", "S"}:
        steps = [(forward, -1), (forward, 0), (forward, 1), (0, -1), (0, 1), (-forward, 0)]
        return _step_destinations(board, row, col, steps, player_id)
    if base == "K":
        steps = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        return _step_destinations(board, row, col, steps, player_id)
    if base == "G":
        steps = [(forward, -1), (forward, 0), (forward, 1), (0, -1), (0, 1), (-forward, 0)]
        return _step_destinations(board, row, col, steps, player_id)
    if base == "S":
        steps = [
            (forward, -1),
            (forward, 0),
            (forward, 1),
            (-forward, -1),
            (-forward, 1),
        ]
        return _step_destinations(board, row, col, steps, player_id)
    if base == "N":
        return _step_destinations(board, row, col, [(2 * forward, -1), (2 * forward, 1)], player_id)
    if base == "L":
        return _slide_destinations(board, row, col, [(forward, 0)], player_id)
    if base == "P":
        return _step_destinations(board, row, col, [(forward, 0)], player_id)
    if base == "R":
        moves = _slide_destinations(board, row, col, [(-1, 0), (1, 0), (0, -1), (0, 1)], player_id)
        if _shogi_is_promoted(piece):
            moves.extend(
                _step_destinations(
                    board,
                    row,
                    col,
                    [(-1, -1), (-1, 1), (1, -1), (1, 1)],
                    player_id,
                )
            )
        return moves
    if base == "B":
        moves = _slide_destinations(
            board,
            row,
            col,
            [(-1, -1), (-1, 1), (1, -1), (1, 1)],
            player_id,
        )
        if _shogi_is_promoted(piece):
            moves.extend(
                _step_destinations(
                    board,
                    row,
                    col,
                    [(-1, 0), (1, 0), (0, -1), (0, 1)],
                    player_id,
                )
            )
        return moves
    return []


def _step_destinations(
    board: Board,
    row: int,
    col: int,
    steps: Iterable[Point],
    player_id: str,
) -> list[Point]:
    moves: list[Point] = []
    for dr, dc in steps:
        nr, nc = row + dr, col + dc
        occupant = board[nr][nc] if _inside(board, nr, nc) else None
        if _inside(board, nr, nc) and (occupant is None or _piece_owner(occupant) != player_id):
            moves.append((nr, nc))
    return moves


def _slide_destinations(
    board: Board,
    row: int,
    col: int,
    directions: Iterable[Point],
    player_id: str,
) -> list[Point]:
    moves: list[Point] = []
    for dr, dc in directions:
        nr, nc = row + dr, col + dc
        while _inside(board, nr, nc):
            if board[nr][nc] is None:
                moves.append((nr, nc))
            else:
                if _piece_owner(board[nr][nc] or "") != player_id:
                    moves.append((nr, nc))
                break
            nr += dr
            nc += dc
    return moves


def _shogi_must_promote(base: str, player_id: str, row: int) -> bool:
    if base in {"P", "L"}:
        return row == 0 if player_id == "player_1" else row == 8
    if base == "N":
        return row <= 1 if player_id == "player_1" else row >= 7
    return False


def _shogi_drop_actions(board: Board, hand: dict[str, int], player_id: str) -> list[str]:
    actions: list[str] = []
    for piece, count in sorted(hand.items()):
        if count <= 0:
            continue
        for row in range(9):
            for col in range(9):
                if board[row][col] is not None or not _shogi_drop_allowed(
                    board,
                    piece,
                    row,
                    col,
                    player_id,
                ):
                    continue
                actions.append(f"{piece}*{_shogi_pos(row, col)}")
    return actions


def _shogi_drop_allowed(board: Board, piece: str, row: int, col: int, player_id: str) -> bool:
    if piece in {"P", "L"} and (row == 0 if player_id == "player_1" else row == 8):
        return False
    if piece == "N" and (row <= 1 if player_id == "player_1" else row >= 7):
        return False
    if piece == "P":
        target = _owned_piece("P", player_id)
        for check_row in range(9):
            if board[check_row][col] == target:
                return False
    return True


# Xiangqi helpers

_XIANGQI_VALUES = {"G": 1000, "R": 9, "H": 4, "E": 2, "A": 2, "C": 5, "S": 1}


def _xiangqi_initial_board() -> Board:
    return [
        list("rheagaehr"),
        [None for _ in range(9)],
        [None, "c", None, None, None, None, None, "c", None],
        ["s", None, "s", None, "s", None, "s", None, "s"],
        [None for _ in range(9)],
        [None for _ in range(9)],
        ["S", None, "S", None, "S", None, "S", None, "S"],
        [None, "C", None, None, None, None, None, "C", None],
        [None for _ in range(9)],
        list("RHEAGAEHR"),
    ]


def _xiangqi_square(row: int, col: int) -> str:
    return f"{chr(ord('a') + col)}{row}"


def _parse_xiangqi_move(action: str) -> tuple[int, int, int, int]:
    if len(action) != 4 or action[0] not in "abcdefghi" or action[2] not in "abcdefghi":
        raise ValueError("invalid xiangqi move")
    sr, er = int(action[1]), int(action[3])
    sc, ec = ord(action[0]) - ord("a"), ord(action[2]) - ord("a")
    if not (0 <= sr < 10 and 0 <= er < 10):
        raise ValueError("invalid xiangqi rank")
    return sr, sc, er, ec


def _xiangqi_base(piece: str) -> str:
    return piece.upper()


def _xiangqi_legal_actions(board: Board, player_id: str) -> list[str]:
    actions: list[str] = []
    for row in range(10):
        for col in range(9):
            piece = board[row][col]
            if piece is None or _piece_owner(piece) != player_id:
                continue
            for er, ec in _xiangqi_destinations(board, row, col, piece, player_id):
                trial = _clone_board(board)
                trial[er][ec] = trial[row][col]
                trial[row][col] = None
                if not _xiangqi_generals_face(trial):
                    actions.append(_xiangqi_square(row, col) + _xiangqi_square(er, ec))
    return sorted(actions)


def _xiangqi_destinations(
    board: Board,
    row: int,
    col: int,
    piece: str,
    player_id: str,
) -> list[Point]:
    base = _xiangqi_base(piece)
    forward = -1 if player_id == "player_1" else 1
    if base == "G":
        steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        return [
            point
            for point in _step_destinations(board, row, col, steps, player_id)
            if _xiangqi_in_palace(point[0], point[1], player_id)
        ]
    if base == "A":
        steps = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        return [
            point
            for point in _step_destinations(board, row, col, steps, player_id)
            if _xiangqi_in_palace(point[0], point[1], player_id)
        ]
    if base == "E":
        return _xiangqi_elephant_moves(board, row, col, player_id)
    if base == "H":
        return _xiangqi_horse_moves(board, row, col, player_id)
    if base == "R":
        return _slide_destinations(board, row, col, [(-1, 0), (1, 0), (0, -1), (0, 1)], player_id)
    if base == "C":
        return _xiangqi_cannon_moves(board, row, col, player_id)
    if base == "S":
        steps = [(forward, 0)]
        if _xiangqi_crossed_river(row, player_id):
            steps.extend([(0, -1), (0, 1)])
        return _step_destinations(board, row, col, steps, player_id)
    return []


def _xiangqi_in_palace(row: int, col: int, player_id: str) -> bool:
    if col < 3 or col > 5:
        return False
    return 7 <= row <= 9 if player_id == "player_1" else 0 <= row <= 2


def _xiangqi_crossed_river(row: int, player_id: str) -> bool:
    return row <= 4 if player_id == "player_1" else row >= 5


def _xiangqi_elephant_moves(board: Board, row: int, col: int, player_id: str) -> list[Point]:
    moves: list[Point] = []
    for dr, dc in ((-2, -2), (-2, 2), (2, -2), (2, 2)):
        nr, nc = row + dr, col + dc
        eye = (row + dr // 2, col + dc // 2)
        if not _inside(board, nr, nc) or board[eye[0]][eye[1]] is not None:
            continue
        if player_id == "player_1" and nr < 5:
            continue
        if player_id == "player_2" and nr > 4:
            continue
        if board[nr][nc] is None or _piece_owner(board[nr][nc] or "") != player_id:
            moves.append((nr, nc))
    return moves


def _xiangqi_horse_moves(board: Board, row: int, col: int, player_id: str) -> list[Point]:
    jumps = [
        (-2, -1, -1, 0), (-2, 1, -1, 0), (2, -1, 1, 0), (2, 1, 1, 0),
        (-1, -2, 0, -1), (1, -2, 0, -1), (-1, 2, 0, 1), (1, 2, 0, 1),
    ]
    moves: list[Point] = []
    for dr, dc, lr, lc in jumps:
        nr, nc = row + dr, col + dc
        if not _inside(board, nr, nc) or board[row + lr][col + lc] is not None:
            continue
        if board[nr][nc] is None or _piece_owner(board[nr][nc] or "") != player_id:
            moves.append((nr, nc))
    return moves


def _xiangqi_cannon_moves(board: Board, row: int, col: int, player_id: str) -> list[Point]:
    moves: list[Point] = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = row + dr, col + dc
        jumped = False
        while _inside(board, nr, nc):
            cell = board[nr][nc]
            if not jumped:
                if cell is None:
                    moves.append((nr, nc))
                else:
                    jumped = True
            else:
                if cell is not None:
                    if _piece_owner(cell) != player_id:
                        moves.append((nr, nc))
                    break
            nr += dr
            nc += dc
    return moves


def _xiangqi_generals_face(board: Board) -> bool:
    p1 = _find_piece(board, "G")
    p2 = _find_piece(board, "g")
    if p1 is None or p2 is None or p1[1] != p2[1]:
        return False
    col = p1[1]
    start, end = sorted([p1[0], p2[0]])
    return all(board[row][col] is None for row in range(start + 1, end))


def _find_piece(board: Board, piece: str) -> Point | None:
    for row in range(len(board)):
        for col in range(len(board[0])):
            if board[row][col] == piece:
                return row, col
    return None
