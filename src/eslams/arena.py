"""Arena interfaces and local registry."""

from __future__ import annotations

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
        return action in self.legal_actions_for(state, player_id)

    def failure_action(self, state: ArenaState, player_id: str, reason: str) -> Any | None:
        legal = self.legal_actions_for(state, player_id)
        if "resign" in legal:
            return "resign"
        return legal[0] if legal else None


class ArenaRegistry:
    def __init__(self) -> None:
        self._arenas: dict[str, type[Arena]] = {}

    def register(self, arena_type: type[Arena]) -> None:
        probe = arena_type()
        self._arenas[probe.id] = arena_type

    def create(self, arena_id: str) -> Arena:
        if arena_id not in self._arenas:
            available = ", ".join(sorted(self._arenas))
            raise KeyError(f"unknown arena {arena_id!r}; available: {available}")
        return self._arenas[arena_id]()

    def list(self) -> list[str]:
        return sorted(self._arenas)


registry = ArenaRegistry()
