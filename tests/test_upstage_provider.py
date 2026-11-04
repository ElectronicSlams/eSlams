"""Keyless Upstage REST contract and integration tests; never call a provider."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.deadlines import receipt_invocation
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers import upstage
from eslams.runner import RunConfig, Runner


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/provider" /
                       "upstage_chat_completions_success.json").read_text())


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


def agent(**kwargs):
    return ModelProviderAgent("upstage", "solar-pro4", "UPSTAGE_API_KEY", **kwargs)


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "synthetic-upstage-secret")
    body = fixture()
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=body, headers={"x-request-id": "wire-request"})
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return body, calls


def test_dispatch_wire_history_unbounded_defaults_and_accounting(wire):
    body, calls = wire
    native = agent()
    history = [{"turn_id": i, "action": i % 3} for i in range(100)]
    response = native.act(replace(request(), history=history))
    url, sent = calls[0]
    assert url == upstage.CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"]["Authorization"] == "Bearer synthetic-upstage-secret"
    assert sent["json"]["model"] == "solar-pro4"
    assert sent["json"]["stream"] is False
    assert set(sent["json"]) == {"model", "messages", "stream"}
    assert sent["timeout"].read is None and sent["timeout"].pool is None
    assert json.dumps(history, sort_keys=True) in sent["json"]["messages"][1]["content"]
    assert response.action == 1
    receipt = native.last_receipt
    assert receipt["model"] == "solar-pro4"
    assert receipt["locked_model_id"] == body["model"]
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == upstage.ENDPOINT_KIND
    assert receipt["parser_version"] == upstage.PARSER_VERSION
    assert receipt["request_id"] == "wire-request"
    assert receipt["usage"]["input_tokens"] == 57
    assert receipt["usage"]["output_tokens"] == 66
    assert receipt["usage"]["total_tokens"] == 123
    assert receipt["usage"]["reasoning_tokens"] == 17
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(response.to_dict())
    assert "redacted-private-reasoning" not in public
    assert "synthetic-upstage-secret" not in public
    assert "Authorization" not in public
    assert len(native.attempt_receipts) == 1


@pytest.mark.parametrize("effort", sorted(upstage.REASONING_EFFORTS))
def test_explicit_reasoning_efforts_are_forwarded(wire, effort):
    _, calls = wire
    agent(runtime_config=ProviderRuntimeConfig(reasoning_effort=effort)).act(request())
    assert calls[0][1]["json"]["reasoning_effort"] == effort


def test_explicit_output_temperature_timeout_and_disabled_reasoning(wire):
    _, calls = wire
    native = agent(temperature=0.2, max_output_tokens=2345,
                   runtime_config=ProviderRuntimeConfig(reasoning="disabled", timeout_ms=12345))
    native.act(request())
    sent = calls[0][1]
    assert sent["json"]["reasoning_effort"] == "none"
    assert sent["json"]["max_tokens"] == 2345 and sent["json"]["temperature"] == 0.2
    assert 0 < sent["timeout"].read <= 12.345


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(reasoning="enabled"),
    ProviderRuntimeConfig(reasoning="enabled", reasoning_effort="minimal"),
    ProviderRuntimeConfig(reasoning_effort="invented"),
    ProviderRuntimeConfig(reasoning_budget_tokens=400),
    ProviderRuntimeConfig(gemini_thinking_budget=100),
])
def test_unsupported_or_ambiguous_controls_rejected_before_transport(wire, runtime):
    _, calls = wire
    with pytest.raises(ProviderCallError, match="Upstage"):
        agent(runtime_config=runtime).act(request())
    assert calls == []


@pytest.mark.parametrize("model", ["solar-pro4", "solar-pro4-260806", "solar-mini4",
                                   "syn-pro", "future/Model:Exact"])
def test_cli_provider_case_normalization_preserves_model_aliases_and_snapshots(wire, model):
    _, calls = wire
    native = _provider_agent(f"UPSTAGE:{model}")
    assert native.provider == "upstage" and native.model == model
    native.act(request())
    assert calls[0][1]["json"]["model"] == model
    assert _provider_agent("upstage").model == upstage.DEFAULT_MODEL


def test_configuration_preflight_and_discovery_are_offline(monkeypatch, capsys):
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("configuration preflight or unsupported discovery used network")
    monkeypatch.setattr("httpx.get", forbidden)
    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    result = provider_preflight("upstage", "solar-pro4", "tic-tac-toe")
    assert result["ok"] and result["checks"]["adapter_available"]
    assert result["checks"]["minimal_inference"] is False
    assert result["checks"]["account_model_visible"] is None
    assert main(["providers", "preflight", "--provider", "upstage", "--model", "solar-pro4",
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    discovery = provider_models_result("upstage")
    assert discovery["error"]["error_class"] == "provider_discovery_unavailable"


@pytest.mark.parametrize("field", ["model", "usage"])
def test_missing_identity_or_usage_remains_unknown(wire, field):
    body, _ = wire
    body.pop(field)
    native = agent()
    native.act(request())
    receipt = native.last_receipt
    if field == "model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    else:
        assert receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize(("reason", "kind"), [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"), (None, "provider_response_schema_mismatch"),
    ("unknown-private-value", "provider_response_schema_mismatch"),
])
def test_semantic_failure_retains_usage_and_never_accepts_partial_action(wire, reason, kind):
    body, calls = wire
    body["choices"][0]["finish_reason"] = reason
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert caught.value.error_kind == kind
    assert native.last_receipt["usage"]["total_tokens"] == 123
    assert native.last_receipt["outcome"] == kind
    assert "unknown-private-value" not in json.dumps(native.last_receipt)
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ["refusal", "wrong-role", "sdk", "empty", "many", "tool"])
def test_invalid_envelopes_and_refusal_cannot_supply_an_action(wire, mutation):
    body, _ = wire
    message = body["choices"][0]["message"]
    if mutation == "refusal":
        message["refusal"] = "private refusal prompt text"
    elif mutation == "wrong-role":
        message["role"] = "user"
    elif mutation == "sdk":
        body["output_text"] = '{"action": 1}'
        body.pop("choices")
    elif mutation == "empty":
        message["content"] = None
    elif mutation == "many":
        body["choices"].append(copy.deepcopy(body["choices"][0]))
    else:
        message["tool_calls"] = [{"id": "private-tool"}]
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(request())
    assert "private refusal prompt text" not in json.dumps(native.last_receipt)
    assert native.last_receipt["usage"]["total_tokens"] == 123


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_faults_have_private_receipts_and_zero_retries(monkeypatch, status, kind):
    monkeypatch.setenv("UPSTAGE_API_KEY", "synthetic-upstage-secret")
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={"error": {
            "type": "invalid_request_error", "code": "too_many_requests",
            "message": "private prompt synthetic-upstage-secret", "param": ""}},
            headers={"x-request-id": "fault-request", "Set-Cookie": "private-cookie"})
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert caught.value.error_kind == kind
    assert native.last_receipt["status_code"] == status
    assert native.last_receipt["request_id"] == "fault-request"
    assert native.last_receipt["usage"] == {}
    assert native.last_receipt["locked_model_id"] is None
    assert len(calls) == 1
    assert "private" not in json.dumps(native.last_receipt)
    assert "synthetic-upstage-secret" not in str(caught.value)


def test_category_retry_timestamps_and_ambiguous_429_are_not_replayed(monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "synthetic-key")
    monkeypatch.setattr(upstage.time, "time", lambda: 1000.0)
    response = httpx.Response(429, headers={
        "X-Upstage-RateLimit-Retry-After-Requests": "1005",
        "X-Upstage-RateLimit-Retry-After-Tokens": "1009",
        "X-Upstage-RateLimit-Retry-After-Pages": "nan",
    }, json={"error": {"type": "invalid_request_error", "code": "too_many_requests",
                      "message": "redacted", "param": ""}})
    assert upstage.retry_after_seconds(response) == 9
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return response
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        native.act(request())
    assert len(calls) == 1
    assert native.last_receipt["retry_after_ms"] == 9000


@pytest.mark.parametrize("fault", ["timeout", "transport", "malformed", "duplicate", "partial"])
def test_transport_and_parse_failures_never_replay_or_borrow_previous_receipt(wire, monkeypatch,
                                                                           fault):
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    native.act(request())
    def post(*args, **kwargs):
        if fault == "timeout":
            raise httpx.ReadTimeout("private-timeout")
        if fault == "transport":
            raise httpx.ConnectError("private-url")
        if fault == "partial":
            from eslams.http_io import ResponseObservation
            failure = httpx.ReadError("private-partial-body")
            failure._eslams_response_observation = ResponseObservation(
                429, (("x-request-id", "partial-request"),))
            raise failure
        return httpx.Response(200, content=(b'{"choices": [], "choices": []}'
                                           if fault == "duplicate" else b'{not-json'))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    invocation = object()
    with receipt_invocation(invocation), pytest.raises((ProviderCallError, TimeoutError)):
        native.act(request())
    rows = native._receipt_snapshot(invocation)
    assert len(rows) == 1 and rows[0]["outcome"] != "ok"
    assert rows[0].get("provider_response_id") is None
    assert rows[0]["usage"] == {}
    if fault == "partial":
        assert rows[0]["status_code"] == 429 and rows[0]["request_id"] == "partial-request"


def test_runner_privacy_failure_scoring_and_receipt_custody(wire, tmp_path):
    body, _ = wire
    body["choices"][0]["finish_reason"] = "length"
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(), max_turns=1,
                                   output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring
    assert result.score.winner is None
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    rows = [json.loads(line) for line in (result.expanded_path /
            "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "provider_output_truncated"
    assert rows[0]["usage"]["total_tokens"] == 123
    for path in result.expanded_path.rglob("*.json*"):
        text = path.read_text()
        assert "redacted-private-reasoning" not in text
        assert "synthetic-upstage-secret" not in text


def test_cli_run_and_simulated_live_preflight(wire, tmp_path, capsys):
    _, calls = wire
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "upstage:solar-pro4",
                 "--max-turns", "1", "--output-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["artifact"]
    result = provider_preflight("upstage", "solar-pro4", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["minimal_inference"]
    assert result["checks"]["usage_extraction"]
    assert result["checks"]["account_model_visible"] is None
    assert len(calls) == 2


@pytest.mark.parametrize("value", [-1, True, "66"])
def test_malformed_usage_is_never_repaired_into_valid_accounting(wire, value):
    body, _ = wire
    body["usage"]["completion_tokens"] = value
    native = agent()
    native.act(request())
    assert native.last_receipt["usage"]["usage_validation_errors"]
    assert native.last_receipt["usage"]["output_tokens"] is None
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_reasoning_only_truncation_is_a_failure(wire):
    body, _ = wire
    body["choices"][0]["message"]["content"] = None
    body["choices"][0]["finish_reason"] = "length"
    native = agent(runtime_config=ProviderRuntimeConfig(reasoning_effort="high"))
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert caught.value.error_kind == "provider_output_truncated"
    assert native.last_receipt["usage"]["reasoning_tokens"] == 17


@pytest.mark.parametrize("partial", [False, True])
def test_real_bounded_transport_with_mocked_raw_bytes(monkeypatch, partial):
    """Exercise real body reading and header custody, with no network socket."""
    monkeypatch.setenv("UPSTAGE_API_KEY", "synthetic-key")
    calls = []
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(fixture()).encode() if not partial else b'{"usage":'
            if partial:
                raise httpx.ReadError("private body interruption")
    def handle(req):
        calls.append(req)
        assert req.url == upstage.CHAT_COMPLETIONS_ENDPOINT
        assert req.headers["authorization"] == "Bearer synthetic-key"
        assert json.loads(req.content)["model"] == "solar-pro4"
        return httpx.Response(200, stream=Body(), headers={"x-request-id": "raw-request"})
    original = httpx.AsyncClient
    def client(**kwargs):
        return original(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", client)
    native = agent()
    if partial:
        with pytest.raises(ProviderCallError):
            native.act(request())
        assert native.last_receipt["usage"] == {}
        assert native.last_receipt["outcome"] == "provider_transport_error"
    else:
        assert native.act(request()).action == 1
        assert native.last_receipt["usage"]["total_tokens"] == 123
    assert native.last_receipt["request_id"] == "raw-request"
    assert len(calls) == len(native.attempt_receipts) == 1
