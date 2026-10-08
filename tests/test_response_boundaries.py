from contextlib import contextmanager

import httpx
import pytest

from eslams.agents import HttpAgent
from eslams.artifacts import ArtifactValidator
from eslams.hashing import canonical_json
from eslams.http_io import bounded_post
from eslams.model_actions import InvalidModelAction, parse_model_action
from eslams.protocol import (
    MAX_PUBLIC_EXPLANATION_BYTES,
    MAX_RESPONSE_BYTES,
    ActResponse,
    ProtocolError,
)
from eslams.runner import RunConfig, Runner


class CountedStream(httpx.SyncByteStream):
    def __init__(self, blocks):
        self.blocks = blocks
        self.reads = 0
        self.closed = False

    def __iter__(self):
        for block in self.blocks:
            self.reads += 1
            yield block

    def close(self):
        self.closed = True


def transport_reply(monkeypatch, blocks, headers=None):
    stream = CountedStream(blocks)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers=headers or {}, stream=stream, request=request)
    )

    @contextmanager
    def mock_stream(method, url, **kwargs):
        assert kwargs["headers"]["Accept-Encoding"] == "identity"
        with (
            httpx.Client(transport=transport) as client,
            client.stream(method, url, **kwargs) as reply,
        ):
            yield reply

    monkeypatch.setattr("eslams.http_io.httpx.stream", mock_stream)
    return stream


@pytest.mark.parametrize("header", [{}, {"content-length": str(MAX_RESPONSE_BYTES + 1)}])
def test_http_reads_are_bounded_and_stream_closed(monkeypatch, header):
    stream = transport_reply(monkeypatch, [b"x" * 65536] * 40, header)
    with pytest.raises(ProtocolError, match="1 MiB"):
        bounded_post("https://fixture.test/act", headers={}, json={}, timeout=1)
    assert stream.reads <= 17
    assert stream.closed


def test_compression_bombs_are_rejected_before_reading_or_decoding(monkeypatch):
    stream = transport_reply(monkeypatch, [b"never-read"], {"content-encoding": "gzip"})
    with pytest.raises(ProtocolError, match="compressed"):
        bounded_post("https://fixture.test/act", headers={}, json={}, timeout=1)
    assert stream.reads == 0
    assert stream.closed


def test_ordinary_identity_reply_is_preserved(monkeypatch):
    stream = transport_reply(monkeypatch, [b'{"action":', b"0}"])
    reply = bounded_post("https://fixture.test/act", headers={}, json={}, timeout=1)
    assert reply.json() == {"action": 0}
    assert stream.closed


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -float("inf"), True, 1.1])
def test_http_and_model_confidence_fail_closed(confidence):
    import json

    payload = {"action": 0, "confidence": confidence}
    with pytest.raises(ProtocolError):
        ActResponse.from_mapping(payload)
    with pytest.raises(InvalidModelAction):
        parse_model_action(json.dumps(payload), [0])


@pytest.mark.parametrize(
    "field,value",
    [
        ("public_explanation", "\ud800"),
        ("metadata", {"nested": "\udfff"}),
        ("metadata", {"nested": float("nan")}),
        ("public_explanation", "x" * (MAX_PUBLIC_EXPLANATION_BYTES + 1)),
    ],
)
def test_invalid_response_values_produce_valid_diagnostics(tmp_path, field, value):
    class InvalidAgent:
        id = "invalid-fixture"
        version = "1"

        def act(self, request):
            # Direct dataclass responses must obey the same boundary as /act JSON.
            return ActResponse(action=request.legal_actions[0], **{field: value})

    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agent_1=InvalidAgent(),
            agent_2="first-legal",
            on_agent_error="invalid-match",
            output_dir=tmp_path,
            archive=False,
        )
    )
    assert result.score.match_valid_for_scoring is False
    assert "action_response_unparseable" in result.score.invalid_reason
    assert ArtifactValidator().validate(result.artifact_path) == []
    for path in result.expanded_path.rglob("*.json*"):
        text = path.read_text(encoding="utf-8")
        assert "NaN" not in text
        assert "Infinity" not in text


def test_oversized_http_response_leaves_diagnostic_artifact(tmp_path, monkeypatch):
    transport_reply(monkeypatch, [b"x" * 65536] * 40)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agent_1=HttpAgent("https://fixture.test/act"),
            agent_2="first-legal",
            on_agent_error="invalid-match",
            output_dir=tmp_path,
        )
    )
    assert result.score.match_valid_for_scoring is False
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_canonical_json_cannot_emit_nonstandard_numeric_tokens():
    with pytest.raises(ValueError):
        canonical_json({"bad": float("nan")})
