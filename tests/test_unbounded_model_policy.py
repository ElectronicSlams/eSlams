"""Keyless regressions for policy intent, provider constraints and truthful outcomes."""
import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import HttpAgent, ModelProviderAgent, _httpx_timeout
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, ProtocolError
from eslams.runner import RunConfig, Runner


def unbounded_request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


def rows(result):
    return [json.loads(line) for line in
            (result.expanded_path / "receipts/provider_receipts.jsonl").read_text().splitlines()]


def test_default_policy_has_no_framework_total_read_or_output_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": '{"action":0}'}}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY")
    assert agent.act(unbounded_request()).action == 0
    assert len(calls) == 1 and "max_tokens" not in calls[0]["json"]
    assert agent.max_output_tokens is None and RunConfig("tic-tac-toe").time_budget_ms is None
    assert calls[0]["timeout"].read is None and calls[0]["timeout"].connect == 10
    assert _httpx_timeout(ProviderRuntimeConfig()).read is None


def test_unbounded_v2_and_legacy_finite_v1_are_distinct_and_roundtrip():
    assert ActRequest.from_mapping(unbounded_request().to_dict()).time_budget_ms is None
    assert ActRequest.from_mapping(_request().to_dict()).time_budget_ms == _request().time_budget_ms


@pytest.mark.parametrize("kind", ["http", "native"])
def test_typed_transport_entrypoints_reject_contradictory_v2_before_submission(monkeypatch, kind):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **kw: calls.append(kw))
    bad = replace(unbounded_request(), time_budget_ms=1)
    agent = (HttpAgent("https://synthetic.invalid/act") if kind == "http" else
             ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY"))
    with pytest.raises(ProtocolError, match="contradicts"):
        agent.act(bad)
    assert calls == []


@pytest.mark.parametrize("invalid", ["finite-with-unbounded", "missing-null", "wrong-placement"])
def test_http_dispatch_rejects_invalid_v2_before_invoking_handler(invalid):
    from fastapi.testclient import TestClient

    from eslams.agent import AgentServer
    calls = []
    server = AgentServer()
    server.act(lambda request: calls.append(request) or {"action": 0})
    body = unbounded_request().to_dict()
    if invalid == "finite-with-unbounded":
        body["time_budget_ms"] = 1
    elif invalid == "missing-null":
        body.pop("time_budget_ms")
    else:
        body["execution_policy"] = {"mode": "none"}
    with TestClient(server.app) as client:
        assert client.post("/act", json=body).status_code == 422
    assert calls == []


def test_http_dispatch_accepts_valid_v2_and_advertises_it():
    from fastapi.testclient import TestClient

    from eslams.agent import AgentServer
    calls = []
    server = AgentServer()
    server.act(lambda request: calls.append(request) or {"action": 0})
    with TestClient(server.app) as client:
        assert "eslams-act-v2" in client.get("/health").json()["supported_protocol_versions"]
        assert client.post("/act", json=unbounded_request().to_dict()).status_code == 200
    assert len(calls) == 1 and calls[0].time_budget_ms is None


@pytest.mark.parametrize("mode", ["auto", "enabled"])
def test_native_default_does_not_inject_catalogue_reasoning_effort(monkeypatch, mode):
    from test_model_agents import _openai_wire
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=_openai_wire('{"action":0}'),
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openai", "gpt-5-mini", "OPENAI_API_KEY",
                              runtime_config=ProviderRuntimeConfig(reasoning=mode))
    assert agent.act(unbounded_request()).action == 0
    assert len(calls) == 1
    assert "reasoning" not in calls[0] and "max_output_tokens" not in calls[0]


def test_full_supplied_history_is_default_and_window_is_explicit():
    from eslams.agents import _provider_prompt
    request = replace(unbounded_request(), history=[{"turn": n} for n in range(30)])
    full = json.loads(_provider_prompt(request).rsplit("\n", 1)[-1])
    bounded = json.loads(_provider_prompt(request, history_window_turns=3).rsplit("\n", 1)[-1])
    assert len(full["history"]) == 30 and len(bounded["history"]) == 3


@pytest.mark.parametrize("status,outcome", [
    ("queued", "provider_pending"), ("in_progress", "provider_pending"),
    ("cancelled", "provider_cancelled"), ("incomplete", "provider_interrupted"),
])
def test_provider_pending_cancel_and_interruption_are_not_request_rejection_or_loss(
    tmp_path, monkeypatch, status, outcome,
):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"id": "synthetic-pending", "status": status,
            "output": [], "model": "synthetic-model"}, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openai", "synthetic-model", "OPENAI_API_KEY")
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent, on_agent_error="forfeit",
                                   output_dir=tmp_path))
    assert len(calls) == len(rows(result)) == 1 and rows(result)[0]["outcome"] == outcome
    assert not result.score.match_valid_for_scoring
    assert all(event.turn_id == 0 for event in result.replay_events)
    assert ArtifactValidator().validate(result.expanded_path) == []


@pytest.mark.parametrize("mutation", ["missing_time", "legacy_null", "missing_policy",
                                     "wrong_version", "contradiction", "top_level", "boolean"])
def test_policy_missing_null_and_contradictory_fields_fail_closed(mutation):
    body = deepcopy(unbounded_request().to_dict())
    if mutation == "missing_time":
        body.pop("time_budget_ms")
    elif mutation == "legacy_null":
        body["protocol_version"] = "eslams-act-v1"
    elif mutation == "missing_policy":
        body["metadata"] = {}
    elif mutation == "wrong_version":
        body["metadata"]["model_execution_policy"]["schema_version"] = "unknown"
    elif mutation == "contradiction":
        body["metadata"]["model_execution_policy"]["thinking"] = {
            "mode": "bounded", "duration_ms": 1,
        }
    elif mutation == "top_level":
        body["execution_policy"] = {"mode": "none"}
    else:
        body["time_budget_ms"] = True
    with pytest.raises(ProtocolError):
        ActRequest.from_mapping(body)


@pytest.mark.parametrize("policy", ["invalid-match", "forfeit", "fallback"])
@pytest.mark.parametrize("known_cost", [False, True])
@pytest.mark.parametrize("partial_legal", [False, True])
def test_length_truncation_preserves_usage_without_action_loss_fallback_or_retry(
    tmp_path, monkeypatch, policy, known_cost, partial_legal,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    usage = {"prompt_tokens": 1605, "completion_tokens": 32768, "total_tokens": 34373,
             "completion_tokens_details": {"reasoning_tokens": 32767}}
    if known_cost:
        usage["cost"] = 0.029206335
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"id": "synthetic-truncated", "model": "synthetic-model",
            "choices": [{"finish_reason": "length", "message": {
                "content": '{"action":0}' if partial_legal else "",
            }}],
            "usage": usage}, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY")
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent,
                                   on_agent_error=policy, output_dir=tmp_path))
    receipt = rows(result)
    assert len(calls) == len(receipt) == 1
    assert receipt[0]["outcome"] == "provider_output_truncated"
    assert receipt[0]["usage"]["reasoning_tokens"] == 32767
    assert result.score.aggregate_usage["totalTokens"] == 34373
    assert result.score.aggregate_usage["totalCostUsd"] == (0.029206335 if known_cost else None)
    assert not result.score.match_valid_for_scoring
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    assert all(event.turn_id == 0 for event in result.replay_events)
    public = json.loads((result.expanded_path / "public/public_result_summary.json").read_text())
    assert public["winner"] is None and public["score"]["primary_score"] is None
    assert ArtifactValidator().validate(result.expanded_path) == []


@pytest.mark.parametrize("policy", ["forfeit", "fallback"])
def test_operator_cancel_before_submission_cannot_fabricate_move_or_loss(tmp_path, policy):
    cancellation = threading.Event()
    cancellation.set()
    result = Runner().run(RunConfig("tic-tac-toe", on_agent_error=policy,
                                   cancellation=cancellation, output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring
    assert "operator_cancelled" in result.score.invalid_reason_codes
    assert all(event.turn_id == 0 for event in result.replay_events)
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert ArtifactValidator().validate(result.expanded_path) == []


def test_cancel_after_receipt_capture_retains_custody_and_unknown_cost(tmp_path, monkeypatch):
    cancellation = threading.Event()
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(504, json={"error": {"details": {"providerReceipt": {
            "schema_version": "eslams.provider.receipt.v1", "provider": "openrouter",
            "model": "synthetic-model", "gateway_request_id": "known-synthetic-request",
            "status_code": 504, "usage": {}}}}}, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    class CancelAfterCapture(HttpAgent):
        def _remember_failure_receipt(self, *args, **kwargs):
            super()._remember_failure_receipt(*args, **kwargs)
            cancellation.set()
    result = Runner().run(RunConfig("tic-tac-toe",
        agent_1=CancelAfterCapture("https://synthetic.invalid/act"), cancellation=cancellation,
        on_agent_error="forfeit", output_dir=tmp_path))
    receipt = rows(result)
    assert len(calls) == len(receipt) == 1
    assert receipt[0]["gateway_request_id"] == "known-synthetic-request"
    assert not receipt[0]["action_applied"] and result.score.aggregate_usage["totalCostUsd"] is None
    assert not result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.expanded_path) == []


def test_explicit_finite_and_unbounded_local_games_have_identical_game_semantics(tmp_path):
    finite = Runner().run(RunConfig("tic-tac-toe", agent_1="first-legal", time_budget_ms=30000,
                                   output_dir=tmp_path / "finite"))
    unbounded = Runner().run(RunConfig("tic-tac-toe", agent_1="first-legal",
                                      output_dir=tmp_path / "unbounded"))
    assert [e.state_hash for e in finite.replay_events] == [
        e.state_hash for e in unbounded.replay_events
    ]
    assert finite.score.winner == unbounded.score.winner
    assert finite.score.match_valid_for_scoring and unbounded.score.match_valid_for_scoring


@pytest.mark.parametrize("cancel", [False, True])
def test_real_bounded_reader_allows_long_silence_until_result_or_operator_cancel(
    tmp_path, monkeypatch, cancel,
):
    from eslams import http_io
    entered, release, closed, done = (threading.Event() for _ in range(4))
    cancellation = threading.Event()
    original_client = httpx.AsyncClient
    virtual = [time.monotonic()]
    calls, results, errors = [], [], []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            await asyncio.to_thread(release.wait)
            yield json.dumps({"action": 0, "metadata": {"provider_receipt": {
                "schema_version": "eslams.provider.receipt.v1", "provider": "openrouter",
                "model": "synthetic-model", "gateway_request_id": "synthetic-long-body",
                "outcome": "ok", "status_code": 200, "usage": {},
            }}}).encode()
        async def aclose(self):
            closed.set()
    def response(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, stream=Stream(), request=request)
    transport = httpx.MockTransport(response)
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with original_client(transport=transport) as client, client.stream(
                method, url, **kwargs,
            ) as result:
                yield result
    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(http_io.time, "monotonic", lambda: virtual[0])
    def run():
        try:
            results.append(Runner().run(RunConfig("tic-tac-toe", max_turns=1,
                agent_1=HttpAgent("https://synthetic.invalid/act", provider="openrouter",
                                  model="synthetic-model"), cancellation=cancellation,
                on_agent_error="forfeit", output_dir=tmp_path)))
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()
    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert entered.wait(3)
        virtual[0] += 7200  # Two hours pass on the injected clock; no real long wait.
        assert not done.is_set() and len(calls) == 1
        assert calls[0]["time_budget_ms"] is None
        assert calls[0]["protocol_version"] == "eslams-act-v2"
        if cancel:
            cancellation.set()
        else:
            release.set()
        assert done.wait(3) and not errors
        result = results[0]
        assert not result.score.match_valid_for_scoring  # Cancelled or explicit max_turns=1.
        assert result.score.provider_action_count_by_player["player_1"] == (0 if cancel else 1)
        assert ArtifactValidator().validate(result.expanded_path) == []
    finally:
        release.set()
        cancellation.set()
        worker.join(3)
    assert closed.wait(3) and not worker.is_alive()


def _shared_vectors():
    from pathlib import Path
    return json.loads((Path(__file__).parents[1] /
        "fixtures/model_execution_policy/wire_vectors.v1.json").read_text())["vectors"]


@pytest.mark.parametrize("vector", _shared_vectors(), ids=lambda v: v["id"])
def test_shared_vectors_parse_and_http_dispatch_before_handler(vector):
    from fastapi.testclient import TestClient

    from eslams.agent import AgentServer
    calls = []
    server = AgentServer()
    server.act(lambda request: calls.append(request) or {"action": 0})
    body = vector["request"]
    if vector["accepted"]:
        assert ActRequest.from_mapping(body).to_dict() == body
    else:
        with pytest.raises(ProtocolError):
            ActRequest.from_mapping(body)
    with TestClient(server.app) as client:
        response = client.post("/act", json=body)
    assert response.status_code == (200 if vector["accepted"] else 422)
    assert len(calls) == int(vector["accepted"])


@pytest.mark.parametrize("vector", [v for v in _shared_vectors()
    if not v["accepted"] and "time_budget_ms" in v["request"]
    and "execution_policy" not in v["request"]], ids=lambda v: v["id"])
@pytest.mark.parametrize("kind", ["native", "http"])
def test_shared_invalid_typed_vectors_never_submit(monkeypatch, vector, kind):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **kw: calls.append(kw))
    body = vector["request"]
    bad = replace(unbounded_request(), protocol_version=body["protocol_version"],
                  time_budget_ms=body["time_budget_ms"], metadata=body["metadata"])
    agent = (HttpAgent("https://synthetic.invalid/act") if kind == "http" else
             ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY"))
    with pytest.raises(ProtocolError):
        agent.act(bad)
    assert calls == []


@pytest.mark.parametrize("provider,reason", [("openai", "max_output_tokens"),
    ("anthropic", "max_tokens"), ("gemini", "MAX_TOKENS"),
    ("openrouter", "length"), ("bedrock", "max_tokens")])
def test_real_provider_envelope_truncation_reaches_runner_without_partial_action(
    tmp_path, monkeypatch, provider, reason,
):
    from test_provider_completion_regressions import _set_finish
    from test_provider_wire_v06 import PROVIDER_CASES, _agent, _fixture
    _, model, key, fixture = next(case for case in PROVIDER_CASES if case[0] == provider)
    monkeypatch.setenv(key, "synthetic-key")
    payload = _fixture(fixture)  # Existing success fixture contains a legal-looking action.
    _set_finish(payload, provider, reason)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        return httpx.Response(200, json=payload)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=_agent(provider, model, key),
                                   on_agent_error="forfeit", output_dir=tmp_path))
    assert calls == [1] and len(rows(result)) == 1
    assert rows(result)[0]["outcome"] == "provider_output_truncated"
    assert rows(result)[0]["usage"]["total_tokens"] == 16
    assert not rows(result)[0]["action_applied"]
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    assert all(event.action is None for event in result.replay_events)
    assert ArtifactValidator().validate(result.expanded_path) == []
