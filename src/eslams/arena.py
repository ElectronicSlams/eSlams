"""Arena interfaces and local registry."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Protocol

from eslams.state import ArenaState


class AgentLike(Protocol):
    id: str
    version: str

    def act(self, request: Any) -> Any:
        ...


class Arena(ABC):
    id: str
    version: str
    players: tuple[str, ...]
    action_schema: dict[str, Any]
    max_turns: int
    pending_action_key: str | None = None

    def action_reveal_turn(self, state_after: ArenaState) -> int:
        """First turn at which an applied action may enter public history.

        Sealed two-seat arenas declare the private commitment field. The
        following response completes their reveal phase; other arenas reveal
        immediately. Auditor evidence always retains the original action.
        """
        if self.pending_action_key is not None and any(
            private.get(self.pending_action_key) is not None
            for private in state_after.private_state_by_player.values()
        ):
            return state_after.turn + 1
        return state_after.turn

    def public_action(self, state_after: ArenaState, action: Any) -> Any:
        return action if self.action_reveal_turn(state_after) <= state_after.turn else None

    @abstractmethod
    def initial_state(self, seed: int) -> ArenaState:
        raise NotImplementedError

    @abstractmethod
    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        raise NotImplementedError

    @abstractmethod
    def score(self, state: ArenaState) -> dict[str, float]:
        raise NotImplementedError

    def legal_actions_for(self, state: ArenaState, player_id: str) -> list[Any]:
        return list(state.legal_actions_by_player.get(player_id, []))

    def is_legal(self, state: ArenaState, player_id: str, action: Any) -> bool:
        return any(
            _same_json_action(action, candidate)
            for candidate in self.legal_actions_for(state, player_id)
        )

    def failure_action(self, state: ArenaState, player_id: str, reason: str) -> Any | None:
        legal = self.legal_actions_for(state, player_id)
        if "resign" in legal:
            return "resign"
        return legal[0] if legal else None


class ArenaRegistry:
    def __init__(self) -> None:
        self._arenas: dict[str, type[Arena]] = {}

    def register(self, arena_type: type[Arena]) -> None:
        self._arenas[arena_type.id] = arena_type

    def create(self, arena_id: str) -> Arena:
        if arena_id not in self._arenas:
            available = ", ".join(sorted(self._arenas))
            raise KeyError(f"unknown arena {arena_id!r}; available: {available}")
        return self._arenas[arena_id]()

    def list(self) -> list[str]:
        return sorted(self._arenas)


registry = ArenaRegistry()


def _same_json_action(left: Any, right: Any) -> bool:
    """Compare JSON action values without Python's bool/int/float equivalence."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            isinstance(key, str) and _same_json_action(value, right[key])
            for key, value in left.items()
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_json_action(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, float):
        return math.isfinite(left) and left == right
    return type(left) in (str, int, bool, type(None)) and left == right
