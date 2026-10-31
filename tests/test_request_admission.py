"""Body quotas execute before JSON parsing/agent dispatch, including chunked input."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from eslams.agent import AgentServer
from eslams.request_limits import RequestBodyLimitMiddleware
from eslams.runner_server import create_runner_app
from eslams.runner_session import RunnerSessionStore


def exercise(chunks, *, limit=8, headers=()):
    received, dispatched = [], []
    messages = [{"type": "http.request", "body": x, "more_body": i < len(chunks)-1}
                for i, x in enumerate(chunks)]
    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}
    async def send(message):
        received.append(message)
    async def app(scope, read, write):
        dispatched.append(await read())
        await write({"type": "http.response.start", "status": 200, "headers": []})
        await write({"type": "http.response.body", "body": b"ok"})
    wrapped = RequestBodyLimitMiddleware(app, max_bytes=limit)
    asyncio.run(wrapped({"type": "http", "headers": list(headers)}, receive, send))
    return received[0]["status"], dispatched


@pytest.mark.parametrize("chunks", [[b"123456789"], [b"1234", b"56789"], [b""]*20+[b"123456789"]])
def test_chunked_or_unframed_oversized_body_never_reaches_parser(chunks):
    status, dispatched = exercise(chunks)
    assert status == 413 and dispatched == []


def test_exact_byte_boundary_and_empty_chunks_are_coalesced_before_dispatch():
    status, dispatched = exercise([b""]*20+[b"1234", b"5678"])
    assert status == 200 and dispatched == [{"type": "http.request", "body": b"12345678",
                                           "more_body": False}]
    assert exercise([b"123456789"], limit=16)[0] == 200


@pytest.mark.parametrize("headers", [[(b"content-length", b"garbage")],
    [(b"content-length", b"1"), (b"content-length", b"1")], [(b"content-length", b"-1")]])
def test_invalid_body_framing_stops_before_dispatch(headers):
    assert exercise([b"x"], headers=headers) == (400, [])


def test_false_content_length_does_not_disable_actual_byte_limit():
    assert exercise([b"123456789"], headers=[(b"content-length", b"1")]) == (413, [])
    assert exercise([b"x"], headers=[(b"content-length", b"2")]) == (400, [])
    assert exercise([b"x"], headers=[(b"content-length", b"999")]) == (413, [])


def test_agent_server_rejects_before_handler_or_protocol_parsing():
    calls = []
    server = AgentServer(max_request_bytes=16)
    server.act(lambda req: calls.append(req) or {"action": 0})
    with TestClient(server.app) as client:
        response = client.post("/act", content=b'{"x":"'+b"x"*32+b'"}',
                               headers={"content-type": "application/json"})
    assert response.status_code == 413 and calls == []


def test_runner_server_rejects_before_auth_or_store_use(monkeypatch):
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_SECRET", raising=False)
    monkeypatch.delenv("ESLAMS_RUNNER_REQUEST_ALLOW_UNSIGNED", raising=False)
    class NoCalls(RunnerSessionStore):
        def create(self, **kwargs):
            pytest.fail("oversized body reached store")
    with TestClient(create_runner_app(NoCalls(), max_request_bytes=16)) as client:
        result = client.post("/runner/session/create", content=b"x"*17)
    assert result.status_code == 413
