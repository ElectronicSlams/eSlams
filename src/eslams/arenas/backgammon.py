"""Deterministic compact Backgammon arena."""

from __future__ import annotations

import random
from typing import Any, Optional

from eslams.arena import Arena, validate_seed
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")
POINTS = 24
CHECKERS = 5
Point = Optional[dict[str, Any]]
Board = list[Point]


class BackgammonArena(Arena):
    id = "backgammon"
    version = "1.1.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "description": "Move as move:<source>-<target>, or pass only when all dice are blocked.",
    }
    max_turns = 160

    def initial_state(self, seed: int) -> ArenaState:
        validate_seed(seed)
        board: Board = [None] * POINTS
        board[0] = {"player": "player_1", "count": 2}
        board[5] = {"player": "player_1", "count": 3}
        board[23] = {"player": "player_2", "count": 2}
        board[18] = {"player": "player_2", "count": 3}
        return self._state(
            board=board,
            bar={"player_1": 0, "player_2": 0},
            borne_off={"player_1": 0, "player_2": 0},
            active="player_1",
            dice=_dice(seed, 0, "player_1"),
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "board": state.public_state["board"],
            "bar": state.public_state["bar"],
            "borne_off": state.public_state["borne_off"],
            "dice": state.public_state["dice"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal backgammon action")
        board = _board_from_public(state.public_state["board"])
        bar = dict(state.public_state["bar"])
        borne_off = dict(state.public_state["borne_off"])
        dice = list(state.public_state["dice"])
        if action == "pass":
            if _legal_backgammon_actions(board, bar, borne_off, player_id, dice):
                raise ValueError("cannot pass while a backgammon die is playable")
            dice = []
        else:
            try:
                _, move_part = action.split(":", 1)
                source_text, target_text = move_part.split("-", 1)
            except (ValueError, IndexError) as exc:
                raise ValueError(f"Invalid backgammon action format: {action!r}") from exc
            die = _die_for_move(board, bar, borne_off, player_id, dice, source_text, target_text)
            dice.remove(die)
            _apply_backgammon_move(board, bar, borne_off, player_id, source_text, target_text)
        remaining_dice = list(dice)
        active = player_id
        outcome = _backgammon_outcome(borne_off)
        if not dice and outcome is None:
            active = _other(player_id)
            dice = _dice(int(state.metadata["seed"]), state.turn + 1, active)
        history = [
            *state.public_state["history"],
            {"player": player_id, "action": action, "remaining_dice": remaining_dice},
        ]
        return self._state(
            board=board,
            bar=bar,
            borne_off=borne_off,
            active=active,
            dice=dice,
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
        board: Board,
        bar: dict[str, int],
        borne_off: dict[str, int],
        active: str,
        dice: list[int],
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _race_outcome(borne_off, reason="turn_limit")
        legal = [] if terminal else _legal_backgammon_actions(board, bar, borne_off, active, dice)
        if not terminal and not legal:
            # A blocked roll is an explicit bounded transition, even if both seats
            # are blocked. No empty-action live state or unrecorded reroll is emitted.
            legal = ["pass"]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "board": _public_board(board),
                "bar": bar,
                "borne_off": borne_off,
                "dice": dice,
                "history": history,
            },
            private_state_by_player={player: {} for player in PLAYERS},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else []) for player in PLAYERS
            },
            scores=_scores(outcome, borne_off),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"backgammon:{seed}"),
            render_hints={"renderer": "backgammon-board"},
            metadata={"seed": seed},
        )


def _dice(seed: int, turn: int, player: str) -> list[int]:
    rng = random.Random(f"{seed}:{turn}:{player}")
    first = rng.randint(1, 6)
    second = rng.randint(1, 6)
    return [first, second] if first != second else [first, first, first, first]


def _legal_backgammon_actions(
    board: Board,
    bar: dict[str, int],
    borne_off: dict[str, int],
    player: str,
    dice: list[int],
) -> list[str]:
    return sorted({f"move:{source}-{target}"
                   for (source, target), _die in _optimal_first_moves(
                       board, bar, borne_off, player, dice)})


def _optimal_first_moves(
    board: Board, bar: dict[str, int], borne_off: dict[str, int],
    player: str, dice: list[int],
) -> list[tuple[tuple[str, str], int]]:
    """First moves of maximum-dice continuations, retaining the consumed die."""
    memo: dict[tuple[Any, ...], int] = {}

    def continuations(b: Board, br: dict[str, int], off: dict[str, int], ds: list[int]) -> int:
        key = (
            tuple(None if point is None else (point["player"], point["count"]) for point in b),
            tuple(br[p] for p in PLAYERS), tuple(off[p] for p in PLAYERS), tuple(sorted(ds)),
        )
        if key not in memo:
            memo[key] = max((length for _move, _die, length in options(b, br, off, ds)), default=0)
        return memo[key]

    def options(
        b: Board, br: dict[str, int], off: dict[str, int], ds: list[int],
    ) -> list[tuple[tuple[str, str], int, int]]:
        choices = []
        for die in sorted(set(ds)):
            for move in _candidate_moves(b, br, off, player, die):
                if not _can_land(b, player, move[1]):
                    continue
                next_board, next_bar, next_off = _public_board(b), dict(br), dict(off)
                _apply_backgammon_move(next_board, next_bar, next_off, player, *move)
                rest = list(ds)
                rest.remove(die)
                length = 1 + continuations(next_board, next_bar, next_off, rest)
                choices.append((move, die, length))
        return choices

    choices = options(board, bar, borne_off, dice)
    longest = max((length for _move, _die, length in choices), default=0)
    best = [(move, die) for move, die, length in choices if length == longest]
    if longest == 1 and len(set(dice)) == 2:
        higher = [(move, die) for move, die in best if die == max(dice)]
        best = higher or best
    return best


def _candidate_moves(
    board: Board,
    bar: dict[str, int],
    borne_off: dict[str, int],
    player: str,
    die: int,
) -> list[tuple[str, str]]:
    if bar[player] > 0:
        entry = die - 1 if player == "player_1" else POINTS - die
        return [("bar", str(entry))]
    candidates: list[tuple[str, str]] = []
    for index, point in enumerate(board):
        if point is None or point["player"] != player:
            continue
        target = index + die if player == "player_1" else index - die
        if 0 <= target < POINTS:
            candidates.append((str(index), str(target)))
        elif _all_in_home(board, player):
            distance = POINTS - index if player == "player_1" else index + 1
            farthest = max(
                POINTS - position if player == "player_1" else position + 1
                for position, checker in enumerate(board)
                if checker is not None and checker["player"] == player
            )
            if die == distance or (die > distance and distance == farthest):
                candidates.append((str(index), "off"))
    return candidates


def _can_land(board: Board, player: str, target_text: str) -> bool:
    if target_text == "off":
        return True
    target = int(target_text)
    point = board[target]
    return point is None or point["player"] == player or int(point["count"]) == 1


def _apply_backgammon_move(
    board: Board,
    bar: dict[str, int],
    borne_off: dict[str, int],
    player: str,
    source_text: str,
    target_text: str,
) -> None:
    if source_text == "bar":
        bar[player] -= 1
    else:
        source = int(source_text)
        source_point = board[source]
        assert source_point is not None
        source_point["count"] = int(source_point["count"]) - 1
        if int(source_point["count"]) == 0:
            board[source] = None
    if target_text == "off":
        borne_off[player] += 1
        return
    target = int(target_text)
    point = board[target]
    if point is not None and point["player"] != player:
        bar[str(point["player"])] += int(point["count"])
        board[target] = None
    target_point = board[target]
    if target_point is None:
        board[target] = {"player": player, "count": 1}
    else:
        target_point["count"] = int(target_point["count"]) + 1


def _die_for_move(
    board: Board,
    bar: dict[str, int],
    borne_off: dict[str, int],
    player: str,
    dice: list[int],
    source_text: str,
    target_text: str,
) -> int:
    move = (source_text, target_text)
    for candidate, die in _optimal_first_moves(board, bar, borne_off, player, dice):
        if move == candidate:
            return die
    raise ValueError("legal backgammon action was not generated by current dice")



def _all_in_home(board: Board, player: str) -> bool:
    home = range(18, 24) if player == "player_1" else range(0, 6)
    for index, point in enumerate(board):
        if point is not None and point["player"] == player and index not in home:
            return False
    return True


def _backgammon_outcome(borne_off: dict[str, int]) -> dict[str, Any] | None:
    for player, count in borne_off.items():
        if count >= CHECKERS:
            return {"winner": player, "reason": "all_checkers_borne_off", "borne_off": borne_off}
    return None


def _race_outcome(borne_off: dict[str, int], *, reason: str) -> dict[str, Any]:
    if borne_off["player_1"] == borne_off["player_2"]:
        winner = None
    else:
        winner = "player_1" if borne_off["player_1"] > borne_off["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "borne_off": borne_off}


def _scores(outcome: dict[str, Any] | None, borne_off: dict[str, int]) -> dict[str, float]:
    if outcome is not None:
        winner = outcome.get("winner")
        if winner is None:
            return {"player_1": 0.5, "player_2": 0.5}
        return {str(winner): 1.0, _other(str(winner)): 0.0}
    return {player: count / CHECKERS for player, count in borne_off.items()}


def _public_board(board: Board) -> Board:
    return [None if point is None else dict(point) for point in board]


def _board_from_public(public_board: Board) -> Board:
    return [None if point is None else dict(point) for point in public_board]


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
