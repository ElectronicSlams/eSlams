"""FastAPI endpoints for persistent Core runner sessions."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from eslams.runner_session import RunnerSessionStore, default_runner_session_store


def create_runner_app(store: RunnerSessionStore | None = None) -> FastAPI:
    session_store = store or default_runner_session_store
    app = FastAPI(title="eSlams Core Runner")

    @app.get("/runner/session/ping")
    async def ping() -> dict[str, Any]:
        return session_store.ping()

    @app.post("/runner/session/create")
    async def create(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return session_store.create(
                game_id=_required_str(payload, "gameId"),
                ruleset_version=str(payload.get("rulesetVersion") or "standard"),
                initial_seed=_optional_int(payload.get("initialSeed"), default=1),
                session_id=_optional_str(payload.get("sessionId")),
                snapshot=_optional_dict(payload.get("snapshot")),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/runner/session/{session_id}/step")
    async def step(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return session_store.step(
                session_id=session_id,
                action=payload.get("action"),
                actor_id=_optional_str(payload.get("actorId")),
                request_id=_optional_str(payload.get("requestId") or payload.get("turnId")),
                deadline_ms=_optional_positive_int(payload.get("deadlineMs")),
                include_observation=bool(payload.get("includeObservation", True)),
                include_legal_actions=str(payload.get("includeLegalActions") or "compact"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/runner/session/{session_id}/snapshot")
    async def snapshot(session_id: str) -> dict[str, Any]:
        try:
            return session_store.snapshot(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runner/session/{session_id}/ping")
    async def session_ping(session_id: str) -> dict[str, Any]:
        try:
            return session_store.snapshot(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runner/session/{session_id}/close")
    async def close(session_id: str) -> dict[str, Any]:
        try:
            return session_store.close(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_runner_app()


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _optional_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _optional_positive_int(value: Any) -> int | None:
    parsed = _optional_int(value, default=0)
    return parsed if parsed > 0 else None
