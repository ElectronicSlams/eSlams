"""FastAPI endpoints for persistent Core runner sessions.

``eslams runner session-*`` talks to the in-process store and is a local operator
tool. This module is the network boundary. Every route requires an HMAC request
signature from ``eslams.contracts.security.sign_runner_request`` carried in the
``X-Eslams-Runner-Signature`` header. The secret is ``ESLAMS_RUNNER_REQUEST_SECRET``
with ``ESLAMS_RUNNER_REQUEST_KEY_ID``. There is no built-in shared secret.

Rotate by installing the current secret and key id as
``ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS`` and
``ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS``, setting the new pair, restarting the
runner and callers, then removing the previous pair. Do not log the secret.

``ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED=1`` skips signatures only for a local
process. It is ignored when ``ESLAMS_ENV`` is ``production``, ``prod``, or
``staging``, and it does not apply when a secret is set.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from eslams.arena_transport import SessionSecretError, require_session_secret
from eslams.contracts.security import (
    RUNNER_SIGNATURE_HEADER,
    RunnerAuthConfigError,
    RunnerRequestAuthError,
    load_runner_auth_config,
    verify_signed_runner_request,
)
from eslams.runner_session import (
    RunnerSessionExists,
    RunnerSessionStore,
    default_runner_session_store,
)


def create_runner_app(store: RunnerSessionStore | None = None) -> FastAPI:
    session_store = store or default_runner_session_store
    seen_nonces: dict[str, float] = {}
    app = FastAPI(title="eSlams Core Runner")

    @app.middleware("http")
    async def authenticate_runner(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path.startswith("/runner/"):
            denial = await _authorize_request(request, seen_nonces)
            if denial is not None:
                return denial
        return await call_next(request)

    @app.get("/runner/session/ping")
    async def ping() -> dict[str, Any]:
        return session_store.ping()

    @app.post("/runner/session/create")
    async def create(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            _require_arena_signing()
            created = session_store.create(
                game_id=_required_str(payload, "gameId"),
                ruleset_version=str(payload.get("rulesetVersion") or "standard"),
                initial_seed=_optional_int(payload.get("initialSeed"), default=1),
                session_id=_optional_str(payload.get("sessionId")),
                snapshot=_optional_dict(payload.get("snapshot")),
            )
            return _with_signed_state(session_store, created, created["sessionId"])
        except RunnerSessionExists as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SessionSecretError as exc:
            raise HTTPException(
                status_code=503,
                detail="arena session secret is not configured",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=_safe_detail(exc)) from exc

    @app.post("/runner/session/{session_id}/step")
    async def step(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            _require_arena_signing()
            response = session_store.step(
                session_id=session_id,
                action=payload.get("action"),
                actor_id=_optional_str(payload.get("actorId")),
                request_id=_optional_str(payload.get("requestId") or payload.get("turnId")),
                deadline_ms=_optional_positive_int(payload.get("deadlineMs")),
                include_observation=bool(payload.get("includeObservation", True)),
                include_legal_actions=str(payload.get("includeLegalActions") or "compact"),
            )
            return _with_signed_state(session_store, response, session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SessionSecretError as exc:
            raise HTTPException(
                status_code=503,
                detail="arena session secret is not configured",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=_safe_detail(exc)) from exc

    @app.post("/runner/session/{session_id}/snapshot")
    async def snapshot(session_id: str) -> dict[str, Any]:
        try:
            _require_arena_signing()
            payload = session_store.snapshot(session_id)
            return _with_signed_state(session_store, payload, session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SessionSecretError as exc:
            raise HTTPException(
                status_code=503,
                detail="arena session secret is not configured",
            ) from exc

    @app.post("/runner/session/{session_id}/ping")
    async def session_ping(session_id: str) -> dict[str, Any]:
        try:
            return _strip_private_state(session_store.session_ping(session_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runner/session/{session_id}/close")
    async def close(session_id: str) -> dict[str, Any]:
        try:
            return _strip_private_state(session_store.close(session_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_runner_app()


async def _authorize_request(
    request: Request,
    seen_nonces: dict[str, float],
) -> JSONResponse | None:
    try:
        config = load_runner_auth_config()
    except RunnerAuthConfigError:
        return _auth_error(503, "runner request secret is not configured")
    if config.mode == "unsigned_dev":
        return None
    header = request.headers.get(RUNNER_SIGNATURE_HEADER)
    if not header:
        return _auth_error(401, "runner request signature is required")
    try:
        parsed = json.loads(header)
    except json.JSONDecodeError:
        return _auth_error(401, "runner request signature is invalid")
    if not isinstance(parsed, dict):
        return _auth_error(401, "runner request signature is invalid")
    raw_body = await request.body()
    if raw_body:
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            return _auth_error(401, "runner request signature is invalid")
    else:
        body = {}
    if not isinstance(body, dict):
        return _auth_error(401, "runner request signature is invalid")
    try:
        verify_signed_runner_request(
            config=config,
            method=request.method,
            path=request.url.path,
            body=body,
            signature_payload=parsed,
            seen_nonces=seen_nonces,
        )
    except RunnerRequestAuthError:
        return _auth_error(401, "runner request signature is invalid")
    return None


def _auth_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _require_arena_signing() -> None:
    require_session_secret()


def _with_signed_state(
    store: RunnerSessionStore,
    payload: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    public = _strip_private_state(payload)
    public.pop("state", None)
    public["sessionState"] = store.export_signed_state(session_id)
    return public


def _strip_private_state(value: dict[str, Any]) -> dict[str, Any]:
    stripped: dict[str, Any] = {}
    for key, item in value.items():
        if key == "private_state_by_player":
            continue
        stripped[key] = _strip_private_value(item)
    return stripped


def _strip_private_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _strip_private_state(value)
    if isinstance(value, list):
        return [_strip_private_value(item) for item in value]
    return value


def _safe_detail(exc: Exception) -> str:
    if isinstance(exc, (ValueError, KeyError)):
        return str(exc)
    return "runner request failed"


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
