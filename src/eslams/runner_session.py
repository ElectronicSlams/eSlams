"""Persistent Core runner sessions for interactive Platform integrations."""

from __future__ import annotations

import math
import re
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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

    _activity: float = field(default=0.0, repr=False)
    _users: int = field(default=0, repr=False)
    _closed: bool = field(default=False, repr=False)
    _lock: Any = field(default_factory=threading.RLock, repr=False)

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


class RunnerSessionCapacityError(RuntimeError):
    """Optional host admission policy is occupied; no live session was evicted."""


class RunnerSessionStore:
    def __init__(
        self, *, max_sessions: int | None = None, idle_ttl_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_sessions is not None and (
            isinstance(max_sessions, bool) or not isinstance(max_sessions, int) or max_sessions < 1
        ):
            raise ValueError("max_sessions must be a positive host choice or null")
        if idle_ttl_seconds is not None and (
            isinstance(idle_ttl_seconds, bool)
            or not isinstance(idle_ttl_seconds, (int, float))
            or not math.isfinite(idle_ttl_seconds) or idle_ttl_seconds <= 0
        ):
            raise ValueError("idle_ttl_seconds must be a positive finite host choice or null")
        self.max_sessions = max_sessions
        self.idle_ttl_seconds = idle_ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, RunnerSession] = {}
        self._started_at = clock()

    def _reap_locked(self) -> None:
        if self.idle_ttl_seconds is None:
            return
        now = self._clock()
        for key, session in list(self._sessions.items()):
            if session._users == 0 and now - session._activity >= self.idle_ttl_seconds:
                session._closed = True
                del self._sessions[key]

    @contextmanager
    def _lease(self, session_id: str) -> Iterator[RunnerSession]:
        with self._lock:
            self._reap_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"unknown runner session {session_id!r}")
            session._users += 1
        try:
            with session._lock:
                if session._closed:
                    raise KeyError(f"unknown runner session {session_id!r}")
                yield session
        finally:
            with self._lock:
                session._users -= 1
                session._activity = self._clock()

    @staticmethod
    def _signed(session: RunnerSession) -> dict[str, Any]:
        return serialize_session_state(
            session.state, context={"game_id": session.game_id,
                                    "ruleset_version": session.ruleset_version}
        )

    def create(
        self,
        *,
        game_id: str,
        ruleset_version: str = "standard",
        initial_seed: int = 1,
        session_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
        include_signed_state: bool = False,
    ) -> dict[str, Any]:
        arena = registry.create(game_id)
        resolved_id = session_id or f"runner_{uuid.uuid4().hex[:16]}"
        if _SESSION_ID_RE.fullmatch(resolved_id) is None:
            raise ValueError("sessionId must be a path-safe token")
        state = (
            _state_from_signed_snapshot(
                snapshot, game_id=game_id, ruleset_version=ruleset_version
            )
            if snapshot is not None
            else arena.initial_state(initial_seed)
        )
        session = RunnerSession(
            session_id=resolved_id,
            game_id=game_id,
            ruleset_version=ruleset_version,
            state=state,
        )
        result = session.summary(message="created")
        if include_signed_state:
            result["sessionState"] = self._signed(session)
        with self._lock:
            self._reap_locked()
            if resolved_id in self._sessions:
                raise RunnerSessionExists(resolved_id)
            if self.max_sessions is not None and len(self._sessions) >= self.max_sessions:
                raise RunnerSessionCapacityError("runner session admission capacity is occupied")
            session._activity = self._clock()
            self._sessions[resolved_id] = session
        return result

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
        include_signed_state: bool = False,
    ) -> dict[str, Any]:
        with self._lease(session_id) as session:
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
            if include_signed_state:
                response["sessionState"] = self._signed(session)
            return response

    def snapshot(
        self, session_id: str, *, include_signed_state: bool = False,
    ) -> dict[str, Any]:
        with self._lease(session_id) as session:
            session.touch()
            result = {**session.summary(message="snapshot"),
                      "state": serialize_state(session.state)}
            if include_signed_state:
                result["sessionState"] = self._signed(session)
            return result

    def session_ping(self, session_id: str) -> dict[str, Any]:
        with self._lease(session_id) as session:
            session.touch()
            return session.summary(message="pong")

    def export_signed_state(self, session_id: str) -> dict[str, Any]:
        """Return a coherent signed envelope for an authenticated server caller."""
        with self._lease(session_id) as session:
            return self._signed(session)

    def close(self, session_id: str) -> dict[str, Any]:
        with self._lease(session_id) as session:
            with self._lock:
                if self._sessions.get(session_id) is session:
                    del self._sessions[session_id]
                session._closed = True
            return session.summary(message="closed")

    def ping(self) -> dict[str, Any]:
        game_ids = registry.list()
        with self._lock:
            self._reap_locked()
            count = len(self._sessions)
        return {
            "ok": True,
            "coreVersion": CORE_PACKAGE_VERSION,
            "loadedGames": len(game_ids),
            "warm": True,
            "uptimeMs": int((self._clock() - self._started_at) * 1000),
            "activeSessions": count,
            "gameIds": game_ids,
        }


def _state_from_signed_snapshot(
    snapshot: dict[str, Any], *, game_id: str, ruleset_version: str
) -> ArenaState:
    if snapshot.get("schema_version") != SESSION_STATE_SCHEMA_VERSION:
        raise ValueError("snapshot must be a signed session_state envelope")
    state = deserialize_session_state(snapshot)
    if snapshot.get("context") != {"game_id": game_id, "ruleset_version": ruleset_version}:
        raise ValueError("snapshot game/ruleset binding does not match requested session")
    session = state.metadata.get(SESSION_METADATA_KEY)
    if isinstance(session, dict):
        slug = session.get("game_slug")
        if isinstance(slug, str) and slug and slug != game_id:
            raise ValueError("snapshot game does not match gameId")
    return state


default_runner_session_store = RunnerSessionStore()
