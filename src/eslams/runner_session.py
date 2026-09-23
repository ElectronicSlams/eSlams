"""Persistent Core runner sessions for interactive Platform integrations."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.arena_transport import (
    SESSION_METADATA_KEY,
    SESSION_STATE_SCHEMA_VERSION,
    deserialize_session_state,
    deserialize_state,
    serialize_session_state,
    serialize_state,
)
from eslams.contracts.versions import (
    CORE_CONTRACT_VERSION,
    CORE_PACKAGE_VERSION,
    CORE_RUNNER_SESSION_SCHEMA_VERSION,
)
from eslams.core_contract import core_step
from eslams.state import ArenaState

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RunnerSessionExists(Exception):
    """Raised when a caller tries to overwrite an existing runner session id."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"runner session {session_id!r} already exists")


@dataclass
class RunnerSession:
    session_id: str
    game_id: str
    ruleset_version: str
    state: ArenaState
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_used_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def touch(self) -> None:
        self.last_used_at_ms = int(time.time() * 1000)

    def summary(self, *, ok: bool = True, message: str | None = None) -> dict[str, Any]:
        return {
            "schemaVersion": CORE_RUNNER_SESSION_SCHEMA_VERSION,
            "ok": ok,
            "message": message,
            "sessionId": self.session_id,
            "gameId": self.game_id,
            "rulesetVersion": self.ruleset_version,
            "stateHash": self.state.state_hash,
            "turn": self.state.turn,
            "activePlayer": self.state.active_player,
            "terminal": self.state.terminal,
            "createdAtMs": self.created_at_ms,
            "lastUsedAtMs": self.last_used_at_ms,
        }


class RunnerSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RunnerSession] = {}
        self._started_at = time.monotonic()

    def create(
        self,
        *,
        game_id: str,
        ruleset_version: str = "standard",
        initial_seed: int = 1,
        session_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        arena = registry.create(game_id)
        resolved_id = session_id or f"runner_{uuid.uuid4().hex[:16]}"
        if _SESSION_ID_RE.fullmatch(resolved_id) is None:
            raise ValueError("sessionId must be a path-safe token")
        if resolved_id in self._sessions:
            raise RunnerSessionExists(resolved_id)
        state = (
            _state_from_signed_snapshot(snapshot, game_id=game_id)
            if snapshot is not None
            else arena.initial_state(initial_seed)
        )
        session = RunnerSession(
            session_id=resolved_id,
            game_id=game_id,
            ruleset_version=ruleset_version,
            state=state,
        )
        self._sessions[resolved_id] = session
        return session.summary(message="created")

    def step(
        self,
        *,
        session_id: str,
        action: Any,
        actor_id: str | None = None,
        request_id: str | None = None,
        deadline_ms: int | None = None,
        include_observation: bool = True,
        include_legal_actions: str = "compact",
    ) -> dict[str, Any]:
        session = self._session(session_id)
        payload: dict[str, Any] = {
            "coreContractVersion": CORE_CONTRACT_VERSION,
            "gameId": session.game_id,
            "rulesetVersion": session.ruleset_version,
            "state": serialize_state(session.state),
            "action": action,
            "actorId": actor_id or session.state.active_player,
            "requestId": request_id or f"{session_id}:{session.state.turn}",
            "includeObservation": include_observation,
            "includeLegalActions": include_legal_actions,
            "includeReplayEvent": True,
        }
        if deadline_ms is not None:
            payload["deadlineMs"] = deadline_ms
        response = core_step(payload)
        if response.get("ok") and isinstance(response.get("state"), dict):
            session.state = deserialize_state(response["state"])
        session.touch()
        response["session"] = session.summary()
        return response

    def snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        session.touch()
        return {**session.summary(message="snapshot"), "state": serialize_state(session.state)}

    def session_ping(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        session.touch()
        return session.summary(message="pong")

    def export_signed_state(self, session_id: str) -> dict[str, Any]:
        """Return the signed session envelope for an authenticated server caller."""

        session = self._session(session_id)
        return serialize_session_state(session.state)

    def close(self, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        del self._sessions[session_id]
        return session.summary(message="closed")

    def ping(self) -> dict[str, Any]:
        game_ids = registry.list()
        return {
            "ok": True,
            "coreVersion": CORE_PACKAGE_VERSION,
            "loadedGames": len(game_ids),
            "warm": True,
            "uptimeMs": int((time.monotonic() - self._started_at) * 1000),
            "activeSessions": len(self._sessions),
            "gameIds": game_ids,
        }

    def _session(self, session_id: str) -> RunnerSession:
        if session_id not in self._sessions:
            raise KeyError(f"unknown runner session {session_id!r}")
        return self._sessions[session_id]


def _state_from_signed_snapshot(snapshot: dict[str, Any], *, game_id: str) -> ArenaState:
    if snapshot.get("schema_version") != SESSION_STATE_SCHEMA_VERSION:
        raise ValueError("snapshot must be a signed session_state envelope")
    state = deserialize_session_state(snapshot)
    session = state.metadata.get(SESSION_METADATA_KEY)
    if isinstance(session, dict):
        slug = session.get("game_slug")
        if isinstance(slug, str) and slug and slug != game_id:
            raise ValueError("snapshot game does not match gameId")
    return state


default_runner_session_store = RunnerSessionStore()
