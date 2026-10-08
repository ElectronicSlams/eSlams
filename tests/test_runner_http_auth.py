"""Authentication and private-state boundaries for the runner HTTP app."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from eslams.arena_transport import SESSION_STATE_SCHEMA_VERSION
from eslams.contracts.security import sign_runner_request
from eslams.runner_server import create_runner_app
from eslams.runner_session import RunnerSessionStore

RUNNER_SECRET = "runner-request-test-secret-32chars"
RUNNER_KEY_ID = "runner-key-current"
PREVIOUS_SECRET = "runner-request-previous-secret-32ch"
PREVIOUS_KEY_ID = "runner-key-previous"
ARENA_SECRET = "arena-session-test-secret-32chars-ok"


@pytest.fixture
def runner_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_SECRET", RUNNER_SECRET)
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_KEY_ID", RUNNER_KEY_ID)
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS", raising=False)
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS", raising=False)
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("ESLAMS_ENV", raising=False)
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_SECRET", ARENA_SECRET)


def _headers(
    method: str,
    path: str,
    body: dict[str, Any],
    *,
    secret: str = RUNNER_SECRET,
    key_id: str = RUNNER_KEY_ID,
    nonce: str,
    timestamp: str | None = None,
) -> dict[str, str]:
    signature = sign_runner_request(
        secret=secret,
        method=method,
        path=path,
        body=body,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        nonce=nonce,
        request_id=nonce,
        key_id=key_id,
    )
    return {"X-Eslams-Runner-Signature": json.dumps(signature)}


def _assert_no_private_state(value: Any) -> None:
    if isinstance(value, dict):
        assert "private_state_by_player" not in value
        for item in value.values():
            _assert_no_private_state(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_private_state(item)


def test_runner_http_fails_closed_without_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_SECRET", raising=False)
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED", raising=False)
    client = TestClient(create_runner_app(RunnerSessionStore()))

    response = client.get("/runner/session/ping")

    assert response.status_code == 503
    assert response.json()["detail"] == "runner request secret is not configured"


def test_runner_http_refuses_unsigned_dev_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_SECRET", raising=False)
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED", "1")
    monkeypatch.setenv("ESLAMS_ENV", "production")
    client = TestClient(create_runner_app(RunnerSessionStore()))

    assert client.get("/runner/session/ping").status_code == 503


def test_runner_http_requires_a_fresh_signature(runner_env: None) -> None:
    del runner_env
    client = TestClient(create_runner_app(RunnerSessionStore()))
    path = "/runner/session/ping"

    missing = client.get(path)
    assert missing.status_code == 401

    stale = client.get(
        path,
        headers=_headers("GET", path, {}, nonce="stale", timestamp="2020-01-01T00:00:00Z"),
    )
    assert stale.status_code == 401

    headers = _headers("GET", path, {}, nonce="once")
    assert client.get(path, headers=headers).status_code == 200
    replay = client.get(path, headers=headers)
    assert replay.status_code == 401


def test_runner_http_accepts_previous_key_during_rotation(
    monkeypatch: pytest.MonkeyPatch,
    runner_env: None,
) -> None:
    del runner_env
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS", PREVIOUS_SECRET)
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS", PREVIOUS_KEY_ID)
    client = TestClient(create_runner_app(RunnerSessionStore()))
    path = "/runner/session/ping"

    previous = client.get(
        path,
        headers=_headers(
            "GET",
            path,
            {},
            secret=PREVIOUS_SECRET,
            key_id=PREVIOUS_KEY_ID,
            nonce="previous-nonce",
        ),
    )
    current = client.get(path, headers=_headers("GET", path, {}, nonce="current-nonce"))

    assert previous.status_code == 200
    assert current.status_code == 200


def test_runner_step_hides_private_state_and_rejects_bad_snapshots(runner_env: None) -> None:
    del runner_env
    store = RunnerSessionStore()
    client = TestClient(create_runner_app(store))
    create_path = "/runner/session/create"
    create_body = {"gameId": "battleship", "sessionId": "arena_hidden", "initialSeed": 1}
    created = client.post(
        create_path,
        json=create_body,
        headers=_headers("POST", create_path, create_body, nonce="create-1"),
    )
    assert created.status_code == 200
    payload = created.json()
    _assert_no_private_state(payload)
    assert payload["sessionState"]["schema_version"] == SESSION_STATE_SCHEMA_VERSION
    hidden = store.snapshot("arena_hidden")["state"]
    assert hidden["private_state_by_player"]["player_1"]["own_ships"]

    step_path = "/runner/session/arena_hidden/step"
    step_body = {"action": "0,0", "actorId": "player_1"}
    stepped = client.post(
        step_path,
        json=step_body,
        headers=_headers("POST", step_path, step_body, nonce="step-1"),
    )
    assert stepped.status_code == 200
    stepped_payload = stepped.json()
    assert stepped_payload["ok"] is True
    assert "state" not in stepped_payload
    _assert_no_private_state(stepped_payload)
    assert "own_ships" not in stepped.text

    raw_snapshot = {
        "gameId": "battleship",
        "sessionId": "arena_raw",
        "snapshot": {"state_id": "state_000000", "turn": 0},
    }
    rejected = client.post(
        create_path,
        json=raw_snapshot,
        headers=_headers("POST", create_path, raw_snapshot, nonce="create-raw"),
    )
    assert rejected.status_code == 422

    duplicate = client.post(
        create_path,
        json=create_body,
        headers=_headers("POST", create_path, create_body, nonce="create-dup"),
    )
    assert duplicate.status_code == 409

    ping_path = "/runner/session/arena_hidden/ping"
    ping = client.post(ping_path, headers=_headers("POST", ping_path, {}, nonce="ping-1"))
    assert ping.status_code == 200
    assert "state" not in ping.json()
    _assert_no_private_state(ping.json())


def test_signed_snapshot_can_restore_a_session(runner_env: None) -> None:
    del runner_env
    store = RunnerSessionStore()
    client = TestClient(create_runner_app(store))
    create_path = "/runner/session/create"
    create_body = {"gameId": "tic-tac-toe", "sessionId": "arena_src", "initialSeed": 3}
    created = client.post(
        create_path,
        json=create_body,
        headers=_headers("POST", create_path, create_body, nonce="src"),
    )
    envelope = created.json()["sessionState"]
    restore_body = {"gameId": "tic-tac-toe", "sessionId": "arena_dst", "snapshot": envelope}
    restored = client.post(
        create_path,
        json=restore_body,
        headers=_headers("POST", create_path, restore_body, nonce="dst"),
    )

    assert restored.status_code == 200
    assert restored.json()["sessionId"] == "arena_dst"
    _assert_no_private_state(restored.json())


def test_runner_signature_timestamp_uses_a_short_window(runner_env: None) -> None:
    del runner_env
    client = TestClient(create_runner_app(RunnerSessionStore()))
    path = "/runner/session/ping"
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    response = client.get(path, headers=_headers("GET", path, {}, nonce="oldish", timestamp=old))
    assert response.status_code == 401
