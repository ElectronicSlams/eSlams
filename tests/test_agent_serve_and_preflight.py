"""Loopback agent serve default and Gemini live-list key placement."""

from __future__ import annotations

import inspect
from typing import Any

import httpx
import pytest

from eslams.agent.server import AgentServer
from eslams.cli import main
from eslams.provider_preflight import provider_models_live


def test_agent_server_run_defaults_to_loopback():
    params = inspect.signature(AgentServer.run).parameters
    assert params["host"].default == "127.0.0.1"
    assert params["port"].default == 8000


def test_agent_serve_defaults_to_loopback_first_legal(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeServer:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def act(self, func):
            captured["handler"] = func
            return func

        def run(self, *, host: str, port: int) -> None:
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr("eslams.agent.AgentServer", FakeServer)

    assert main(["agent", "serve"]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["init"]["agent_id"] == "sample-first-legal"

    class _Request:
        legal_actions = ["e2e4", "e7e5"]

    assert captured["handler"](_Request()) == {"action": "e2e4", "confidence": 1.0}


def test_agent_serve_open_bind_is_explicit(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeServer:
        def __init__(self, **kwargs: Any) -> None:
            return None

        def act(self, func):
            return func

        def run(self, *, host: str, port: int) -> None:
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr("eslams.agent.AgentServer", FakeServer)

    assert main(["agent", "serve", "--host", "0.0.0.0", "--port", "9"]) == 0
    assert captured == {"host": "0.0.0.0", "port": 9}


def test_agent_serve_help_documents_unauthenticated_opt_in(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["agent", "serve", "--help"])

    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "127.0.0.1" in text
    assert "0.0.0.0" in text
    assert "unauthenticated" in text


def test_gemini_live_list_sends_key_in_header(monkeypatch):
    seen: dict[str, Any] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"models": [{"name": "models/gemini-2.5-flash"}]}

    def _get(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> _Response:
        seen["url"] = url
        seen["headers"] = headers
        seen["params"] = params
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", _get)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    assert provider_models_live("google") == ["gemini-2.5-flash"]
    assert seen["headers"]["x-goog-api-key"] == "gemini-secret"
    assert "key" not in seen["params"]
    assert "gemini-secret" not in seen["url"]


def test_gemini_live_list_swallows_http_errors(monkeypatch):
    def _get(*args: object, **kwargs: object) -> object:
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", _get)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    assert provider_models_live("gemini") is None
