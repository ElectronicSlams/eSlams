import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from eslams.arena_transport import (
    SessionSecretError,
    deserialize_session_state,
    initial_state,
    start_session,
    step_session,
)
from eslams.cli import main
from eslams.contracts.security import (
    RunnerAuthConfig,
    RunnerRequestAuthError,
    sign_runner_request,
    verify_signed_runner_request,
)
from eslams.runner_server import create_runner_app
from eslams.runner_session import RunnerSessionStore

PLAYERS = {player: {"kind": "human"} for player in ("player_1", "player_2")}


@pytest.mark.parametrize("environment", ["production", "prod", "staging"])
def test_session_development_secret_opt_in_is_refused_on_shared_environments(
    monkeypatch, environment
):
    monkeypatch.delenv("ESLAMS_ARENA_SESSION_SECRET", raising=False)
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET", "1")
    monkeypatch.setenv("ESLAMS_ENV", environment)
    with pytest.raises(SessionSecretError, match="is required"):
        start_session("tic-tac-toe", None, 1, PLAYERS)


@pytest.mark.usefixtures("arena_session_env")
def test_session_explicit_secret_and_unsigned_state_boundaries(monkeypatch):
    monkeypatch.delenv("ESLAMS_ARENA_SESSION_SECRET")
    with pytest.raises(SessionSecretError, match="is required"):
        start_session("tic-tac-toe", None, 1, PLAYERS)
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET", "1")
    started = start_session("tic-tac-toe", None, 1, PLAYERS)
    assert started["session_state"]["signature"]["keyId"] == "development-unconfigured"
    raw = initial_state("tic-tac-toe")
    assert step_session(raw, "player_1", "0")["accepted"] is False
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_SECRET", "short")
    with pytest.raises(SessionSecretError, match="misconfigured"):
        start_session("tic-tac-toe", None, 1, PLAYERS)


@pytest.mark.usefixtures("arena_session_env")
def test_signed_runner_snapshot_cannot_switch_games_rules_or_context():
    store = RunnerSessionStore()
    store.create(game_id="tic-tac-toe", session_id="first")
    envelope = store.export_signed_state("first")
    for game, rules in [("connect-four", "standard"), ("tic-tac-toe", "invented")]:
        with pytest.raises(ValueError, match="binding"):
            store.create(game_id=game, ruleset_version=rules, snapshot=envelope)
    altered = {**envelope, "context": {"game_id": "connect-four", "ruleset_version": "standard"}}
    with pytest.raises(ValueError, match="body does not match"):
        store.create(game_id="connect-four", snapshot=altered)
    store.create(game_id="tic-tac-toe", session_id="restored", snapshot=envelope)
    assert store.snapshot("restored")["state"] == store.snapshot("first")["state"]
    assert deserialize_session_state(envelope).state_hash == store.snapshot("first")["stateHash"]


def test_clock_skew_cannot_shorten_nonce_replay_protection():
    config = RunnerAuthConfig("signed", {"key": "secret"}, 300)
    now = 1000000000.0
    signature = sign_runner_request(secret="secret", method="GET", path="/runner/session/ping",
                                    body={}, timestamp=datetime.fromtimestamp(
                                        now + 60, timezone.utc).isoformat(),
                                    nonce="same", request_id="request", key_id="key")
    seen = {}
    verify_signed_runner_request(config=config, method="GET", path="/runner/session/ping",
                                 body={}, signature_payload=signature, seen_nonces=seen, now=now)
    with pytest.raises(RunnerRequestAuthError):
        verify_signed_runner_request(config=config, method="GET", path="/runner/session/ping",
                                     body={}, signature_payload=signature, seen_nonces=seen,
                                     now=now + 301)


def test_malformed_unicode_signature_digest_returns_401(monkeypatch):
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_SECRET", "x" * 32)
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_KEY_ID", "key")
    signature = sign_runner_request(secret="x" * 32, method="GET", path="/runner/session/ping",
                                    body={}, timestamp=datetime.now(timezone.utc).isoformat(),
                                    nonce="n", request_id="r", key_id="key")
    signature["bodySha256"] = "é" * 64
    client = TestClient(create_runner_app(RunnerSessionStore()))
    response = client.get("/runner/session/ping",
                          headers={"X-Eslams-Runner-Signature": json.dumps(signature)})
    assert response.status_code == 401


def test_process_local_session_shell_workflow_is_removed(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["runner", "session-create", "--game", "tic-tac-toe"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
