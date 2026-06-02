"""Deterministic Nine Men's Morris arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")
PIECES_PER_PLAYER = 9
POINTS = 24
ADJACENCY = {
    0: (1, 9),
    1: (0, 2, 4),
    2: (1, 14),
    3: (4, 10),
    4: (1, 3, 5, 7),
    5: (4, 13),
    6: (7, 11),
    7: (4, 6, 8),
    8: (7, 12),
    9: (0, 10, 21),
    10: (3, 9, 11, 18),
    11: (6, 10, 15),
    12: (8, 13, 17),
    13: (5, 12, 14, 20),
    14: (2, 13, 23),
    15: (11, 16),
    16: (15, 17, 19),
    17: (12, 16),
    18: (10, 19),
    19: (16, 18, 20, 22),
    20: (13, 19),
    21: (9, 22),
    22: (19, 21, 23),
    23: (14, 22),
}
MILLS = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (9, 10, 11),
    (12, 13, 14),
    (15, 16, 17),
    (18, 19, 20),
    (21, 22, 23),
    (0, 9, 21),
    (3, 10, 18),
    (6, 11, 15),
    (1, 4, 7),
    (16, 19, 22),
    (8, 12, 17),
    (5, 13, 20),
    (2, 14, 23),
)


class NineMensMorrisArena(Arena):
    id = "nine-mens-morris"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "description": (
            "place:<point> or move:<from>-<to>, with :capture:<point> "
            "when a mill forms."
        ),
    }
    max_turns = 120

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            board=[None] * POINTS,
            reserves={"player_1": PIECES_PER_PLAYER, "player_2": PIECES_PER_PLAYER},
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "board": state.public_state["board"],
            "reserves": state.public_state["reserves"],
            "phase": state.public_state["phase"],
            "mills": [list(mill) for mill in MILLS],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal nine-mens-morris action")
        board = list(state.public_state["board"])
        reserves = dict(state.public_state["reserves"])
        history = list(state.public_state["history"])
        base, capture = _split_capture(action)
        if base.startswith("place:"):
            point = int(base.split(":", 1)[1])
            board[point] = player_id
            reserves[player_id] -= 1
        else:
            source, target = base.split(":", 1)[1].split("-", 1)
            board[int(source)] = None
            board[int(target)] = player_id
        if capture is not None:
            board[capture] = None
        history.append({"player": player_id, "action": action})
        outcome = _outcome(board, reserves, _other(player_id))
        return self._state(
            board=board,
            reserves=reserves,
            active=_other(player_id),
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        board: list[str | None],
        reserves: dict[str, int],
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "turn_limit"}
        phase = "placement" if any(reserves[player] > 0 for player in PLAYERS) else "movement"
        legal = [] if terminal else _legal_actions(board, reserves, active)
        if not terminal and phase == "movement" and not legal:
            outcome = {"winner": _other(active), "reason": "no_legal_moves"}
            terminal = True
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "board": board,
                "reserves": reserves,
                "phase": phase,
                "piece_counts": _piece_counts(board, reserves),
                "history": history,
            },
            private_state_by_player={player: {} for player in PLAYERS},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else []) for player in PLAYERS
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"nine-mens-morris:{seed}"),
            render_hints={"renderer": "morris-board"},
            metadata={"seed": seed},
        )


def _legal_actions(board: list[str | None], reserves: dict[str, int], player: str) -> list[str]:
    if reserves[player] > 0:
        bases = [f"place:{point}" for point, owner in enumerate(board) if owner is None]
    else:
        bases = _movement_actions(board, player)
    actions: list[str] = []
    for base in bases:
        projected = _project(board, player, base)
        if _formed_mill(projected, player, base):
            captures = _capturable_points(projected, _other(player))
            if captures:
                actions.extend(f"{base}:capture:{point}" for point in captures)
            else:
                actions.append(base)
        else:
            actions.append(base)
    return actions


def _movement_actions(board: list[str | None], player: str) -> list[str]:
    owned = [point for point, owner in enumerate(board) if owner == player]
    can_fly = len(owned) <= 3
    empty = [point for point, owner in enumerate(board) if owner is None]
    actions: list[str] = []
    for source in owned:
        targets = (
            empty
            if can_fly
            else [point for point in ADJACENCY[source] if board[point] is None]
        )
        actions.extend(f"move:{source}-{target}" for target in targets)
    return actions


def _project(board: list[str | None], player: str, base: str) -> list[str | None]:
    projected = list(board)
    if base.startswith("place:"):
        projected[int(base.split(":", 1)[1])] = player
    else:
        source, target = base.split(":", 1)[1].split("-", 1)
        projected[int(source)] = None
        projected[int(target)] = player
    return projected


def _formed_mill(board: list[str | None], player: str, base: str) -> bool:
    point = int(base.split(":", 1)[1]) if base.startswith("place:") else int(base.rsplit("-", 1)[1])
    return any(point in mill and all(board[item] == player for item in mill) for mill in MILLS)


def _capturable_points(board: list[str | None], opponent: str) -> list[int]:
    pieces = [point for point, owner in enumerate(board) if owner == opponent]
    outside_mills = [point for point in pieces if not _point_in_mill(board, opponent, point)]
    return outside_mills or pieces


def _point_in_mill(board: list[str | None], player: str, point: int) -> bool:
    return any(point in mill and all(board[item] == player for item in mill) for mill in MILLS)


def _split_capture(action: str) -> tuple[str, int | None]:
    if ":capture:" not in action:
        return action, None
    base, capture = action.rsplit(":capture:", 1)
    return base, int(capture)


def _outcome(
    board: list[str | None],
    reserves: dict[str, int],
    next_player: str,
) -> dict[str, Any] | None:
    if any(reserves[player] > 0 for player in PLAYERS):
        return None
    counts = _piece_counts(board, reserves)
    for player in PLAYERS:
        if counts[player] < 3:
            return {"winner": _other(player), "reason": "fewer_than_three_pieces"}
    if not _legal_actions(board, reserves, next_player):
        return {"winner": _other(next_player), "reason": "no_legal_moves"}
    return None


def _piece_counts(board: list[str | None], reserves: dict[str, int]) -> dict[str, int]:
    return {
        player: reserves[player] + sum(1 for owner in board if owner == player)
        for player in PLAYERS
    }


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
