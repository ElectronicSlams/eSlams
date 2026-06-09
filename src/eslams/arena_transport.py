"""Stateless arena transport helpers for runner/container integrations."""

from __future__ import annotations

from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.state import ArenaState


class StateHashMismatch(ValueError):
    """Raised when serialized state carries a stale canonical hash."""

    def __init__(self, *, provided: str, canonical: str) -> None:
        self.provided = provided
        self.canonical = canonical
        super().__init__("state_hash does not match canonical state")

    def to_dict(self) -> dict[str, str]:
        return {
            "status": "state_hash_mismatch",
            "provided_state_hash": self.provided,
            "canonical_state_hash": self.canonical,
        }


def serialize_state(state: ArenaState) -> dict[str, Any]:
    return state.to_dict()


def deserialize_state(payload: dict[str, Any], strict_hash: bool = True) -> ArenaState:
    provided_hash = str(payload["state_hash"]) if payload.get("state_hash") else None
    state = ArenaState(
        state_id=str(payload["state_id"]),
        turn=int(payload["turn"]),
        active_player=str(payload["active_player"]),
        public_state=_dict(payload["public_state"]),
        private_state_by_player={
            str(key): _dict(value)
            for key, value in _dict(payload["private_state_by_player"]).items()
        },
        legal_actions_by_player={
            str(key): _list(value)
            for key, value in _dict(payload["legal_actions_by_player"]).items()
        },
        scores={str(key): float(value) for key, value in _dict(payload["scores"]).items()},
        terminal=bool(payload["terminal"]),
        outcome=_optional_dict(payload.get("outcome")),
        rng_commitment=str(payload["rng_commitment"]),
        render_hints=_dict(payload["render_hints"]),
        metadata=_dict(payload.get("metadata", {})),
        state_hash=None,
    )
    canonical_hash = str(state.state_hash)
    if provided_hash is None or provided_hash == canonical_hash:
        return state
    diagnostics = {
        "status": "state_hash_repaired",
        "provided_state_hash": provided_hash,
        "canonical_state_hash": canonical_hash,
    }
    if strict_hash:
        raise StateHashMismatch(provided=provided_hash, canonical=canonical_hash)
    object.__setattr__(state, "rehydration_diagnostics", diagnostics)
    return state


def initial_state(arena_id: str, *, seed: int = 1) -> dict[str, Any]:
    arena = registry.create(arena_id)
    return serialize_state(arena.initial_state(seed))


def legal_actions(arena_id: str, state_payload: dict[str, Any], player_id: str) -> list[Any]:
    arena = registry.create(arena_id)
    state = deserialize_state(state_payload)
    return arena.legal_actions_for(state, player_id)


def public_state(state_payload: dict[str, Any]) -> dict[str, Any]:
    return deserialize_state(state_payload).public_view()


def state_hash(state_payload: dict[str, Any]) -> str:
    return str(deserialize_state(state_payload).state_hash)


def step(
    arena_id: str,
    state_payload: dict[str, Any],
    player_id: str,
    action: Any,
) -> dict[str, Any]:
    arena = registry.create(arena_id)
    state = deserialize_state(state_payload)
    next_state = arena.apply_action(state, player_id, action)
    return serialize_state(next_state)


def smoke_all_arenas(*, seed: int = 1) -> dict[str, Any]:
    rows = []
    for arena_id in registry.list():
        arena = registry.create(arena_id)
        state = arena.initial_state(seed)
        serialized = serialize_state(state)
        restored = deserialize_state(serialized)
        actions = arena.legal_actions_for(restored, restored.active_player)
        stepped = None
        if actions:
            stepped = arena.apply_action(restored, restored.active_player, actions[0])
        rows.append(
            {
                "arena_id": arena_id,
                "ok": restored.state_hash == state.state_hash,
                "state_hash": restored.state_hash,
                "legal_action_count": len(actions),
                "can_step": stepped is not None,
                "replay_readiness": "playable" if state.public_state else "setup_only",
            }
        )
    return {
        "ok": all(row["ok"] for row in rows),
        "game_count": len(rows),
        "rows": rows,
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
