"""Keyless tests of documented Agent REST envelopes; no provider inference."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.perplexity import AGENT_ENDPOINT, API_KEY_ENV
from eslams.runner import RunConfig, Runner

MODEL = "perplexity/kimi-k3"
PRIMARY = "primary-perplexity-fixture-key"
SECONDARY = "secondary-perplexity-fixture-key"


def _wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/perplexity_agent_success.json")
                      .read_text())


def _agent(monkeypatch, **kwargs):
    monkeypatch.setenv("CUSTOM_PERPLEXITY_KEY", PRIMARY)
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    return ModelProviderAgent("perplexity", MODEL, "CUSTOM_PERPLEXITY_KEY", **kwargs)


def _safe(agent, error=None):
    serialized = json.dumps(agent.last_receipt) + json.dumps(agent.attempt_receipts)
    if error is not None:
        serialized += str(error) + json.dumps(error.receipt)
    assert PRIMARY not in serialized and SECONDARY not in serialized


def test_exact_wire_full_history_dispatch_and_honest_receipt(monkeypatch):
    seen = []

    def post(url, *, headers, json, timeout):
        seen.append(json)
        assert url == AGENT_ENDPOINT
        assert headers == {"Authorization": f"Bearer {PRIMARY}", "Content-Type": "application/json"}
        assert timeout.read is None and timeout.pool is None
        return httpx.Response(200, json=_wire(), headers={"x-request-id": "req_fixture"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(monkeypatch)
    history = [{"turn_id": i, "public_event": f"public-{i}"} for i in range(75)]
    request = replace(_request(), protocol_version="eslams-act-v2", history=history,
                      time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)})
    result = agent.act(request)
    assert result.action == 1
    wire = seen[0]
    assert wire["model"] == MODEL and wire["tools"] == [] and wire["tool_choice"] == "none"
    assert wire["stream"] is False and wire["store"] is False
    assert not {"models", "effort", "preset", "profile", "skills", "previous_response_id",
                "max_output_tokens", "max_steps", "reasoning", "temperature"} & wire.keys()
    assert wire["input"][0]["content"].endswith(json.dumps({
        "arena": request.arena.to_dict(), "active_player": request.active_player,
        "observation": request.observation, "legal_actions": request.legal_actions,
        "action_schema": request.action_schema, "history": history,
        "memory_policy": request.memory_policy,
    }, sort_keys=True, ensure_ascii=False))
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "perplexity" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "perplexity_agent"
    assert receipt["parser_version"] == "perplexity-agent-raw-v1"
    assert receipt["request_id"] == "req_fixture"
    assert receipt["usage"]["total_tokens"] == 120
    assert receipt["usage"]["cache_read_input_tokens"] == 10
    assert receipt["usage"]["cache_write_input_tokens"] == 5
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"] == {"status": "ok", "currency": "USD",
                                         "cost_usd": 0.0006, "source": "provider_native"}
    _safe(agent)


@pytest.mark.parametrize("model", [None, "", " ", "\t", "sonar", "openai/", "/", " x/y"])
def test_missing_or_invalid_model_never_defaults(model):
    with pytest.raises(ValueError, match="Perplexity"):
        ModelProviderAgent("perplexity", model, API_KEY_ENV)


@pytest.mark.parametrize("value", ["perplexity", "perplexity:", "perplexity:   "])
def test_cli_missing_model_never_defaults(value):
    with pytest.raises(ValueError, match="Perplexity"):
        _provider_agent(value)


@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning="disabled"), ProviderRuntimeConfig(reasoning="enabled"),
    ProviderRuntimeConfig(reasoning_effort="ultra"),
    ProviderRuntimeConfig(reasoning_effort="none"),
    ProviderRuntimeConfig(reasoning_budget_tokens=2048),
    ProviderRuntimeConfig(gemini_thinking_budget=2048),
    ProviderRuntimeConfig(history_window_turns=1),
    ProviderRuntimeConfig(openrouter_provider_order=("other",)),
])
def test_unsupported_controls_rejected_in_constructor_and_preflight(config):
    with pytest.raises(ValueError, match="Perplexity"):
        ModelProviderAgent("perplexity", MODEL, API_KEY_ENV, runtime_config=config)
    with pytest.raises(ValueError, match="Perplexity"):
        provider_preflight("perplexity", MODEL, "tic-tac-toe", runtime_config=config)


@pytest.mark.parametrize("effort", ["minimal", "low", "medium", "high", "xhigh", "max"])
def test_explicit_verified_reasoning_and_limits_forwarded(monkeypatch, effort):
    def post(url, *, json, **kwargs):
        assert json["reasoning"] == {"effort": effort}
        assert json["max_output_tokens"] == 1234
        assert json["temperature"] == 0.3
        return httpx.Response(200, json=_wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert _agent(monkeypatch, max_output_tokens=1234, temperature=0.3,
                  runtime_config=ProviderRuntimeConfig(reasoning_effort=effort)).act(_request())
    with pytest.raises(ValueError, match="not verified"):
        ModelProviderAgent("perplexity", "openai/unknown-model", API_KEY_ENV,
                           runtime_config=ProviderRuntimeConfig(reasoning_effort=effort))


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable")])
def test_http_errors_no_default_retry_and_no_echo(monkeypatch, status, kind):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": f"{PRIMARY} {SECONDARY}",
            "type": "rate_limit_error"}, "id": PRIMARY,
            "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}},
            headers={"x-request-id": SECONDARY, "cf-aig-request-id": PRIMARY, "Retry-After": "1"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind and calls == [1]
    assert agent.last_receipt["usage"]["total_tokens"] == 10
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    _safe(agent, failure.value)


@pytest.mark.parametrize("status,kind", [("failed", "provider_unavailable"),
    ("incomplete", "provider_interrupted"), ("queued", "provider_pending"),
    ("in_progress", "provider_pending"), ("cancelled", "provider_cancelled"),
    (None, "provider_response_schema_mismatch"), (True, "provider_response_schema_mismatch")])
def test_never_accept_partial_legal_text(monkeypatch, status, kind):
    data = _wire()
    data["status"] = status
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind
    assert agent.last_receipt["usage"]["total_tokens"] == 120


@pytest.mark.parametrize("mutation", [
    {"model": None}, {"model": "other/model"}, {"id": None}, {"output": []},
    {"object": "chat.completion"}, {"output_text": '{"action":1}', "output": None},
    {"output": [{"type": "search_results", "results": []}]},
    {"effort": "low"}, {"tools": [{"type": "web_search"}]},
    {"usage": {"tool_calls_details": {"web_search": {"invocation_count": 1}}}},
    {"usage": {"cost": {"tool_calls_cost": 0.001}}},
])
def test_malformed_identity_sdk_shortcut_and_tool_results_rejected(monkeypatch, mutation):
    data = {**_wire(), **mutation}
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    _safe(agent, failure.value)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("target", ["headers", "id", "model", "text", "usage"])
def test_primary_and_secondary_echoes_in_success_never_escape(monkeypatch, credential, target):
    data = _wire()
    headers = {"x-request-id": credential, "cf-aig-request-id": credential}
    if target in {"id", "model"}:
        data[target] = credential
    elif target == "text":
        data["output"][0]["content"][0]["text"] = json.dumps({
            "action": 1, "public_explanation": credential,
        })
    elif target == "usage":
        data["usage"]["input_tokens"] = credential
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=data, headers=headers))
    agent = _agent(monkeypatch)
    if target in {"model", "text"}:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        _safe(agent, failure.value)
    else:
        result = agent.act(_request())
        assert credential not in json.dumps(result.to_dict())
        _safe(agent)


@pytest.mark.parametrize("mode", ["malformed", "duplicate", "partial", "timeout", "transport"])
def test_malformed_and_partial_response_custody_redacts_both_keys(monkeypatch, mode):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if mode in {"partial", "timeout", "transport"}:
            error = (ProtocolError("partial response") if mode == "partial" else
                     httpx.ReadTimeout(PRIMARY) if mode == "timeout" else
                     httpx.ConnectError(SECONDARY))
            if mode == "partial":
                error.__dict__["_eslams_response_observation"] = ResponseObservation(
                    200, (("x-request-id", PRIMARY), ("cf-aig-request-id", SECONDARY)))
            raise error
        body = f'{{"id":"{PRIMARY}","id":"{SECONDARY}"}}' if mode == "duplicate" else PRIMARY
        return httpx.Response(200, text=body, headers={"x-request-id": SECONDARY})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        agent.act(_request())
    assert calls == [1]
    _safe(agent, failure.value if isinstance(failure.value, ProviderCallError) else None)


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 4, "output_tokens": 2},
                                     {"input_tokens": 4, "output_tokens": 2, "total_tokens": None},
                                     {"input_tokens": 4, "output_tokens": 2, "total_tokens": True},
                                     {"input_tokens": True, "total_tokens": -1}])
def test_missing_and_invalid_accounting_never_invented(monkeypatch, usage):
    data = _wire()
    data["usage"] = usage
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch)
    assert agent.act(_request()).action == 1
    receipt = agent.last_receipt
    assert not receipt["usage"] or receipt["usage"]["total_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_cli_preflight_discovery_and_mocked_live_dispatch(monkeypatch, capsys):
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert url == "https://api.perplexity.ai/v1/models"
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    args = ["providers", "preflight", "--provider", "perplexity", "--model", MODEL,
            "--arena", "tic-tac-toe"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] and result["ok"]
    assert calls == []
    assert provider_models_live("perplexity") == [MODEL]
    data = _wire()
    data["output"][0]["content"][0]["text"] = '{"action":0}'
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    assert main([*args, "--live"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["minimal_inference"]
    assert not result["checks"]["usage_extraction"]  # Reasoning inclusion is not attested.
    assert result["model"] == MODEL
    assert _provider_agent(f"perplexity:{MODEL}").model == MODEL


def test_anthropic_requires_operator_cap_without_network(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("no cap"))
    agent = ModelProviderAgent("perplexity", "anthropic/claude-test", API_KEY_ENV)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert agent.last_receipt["usage"] == {}


def test_safe_explicit_rejection_retry_only_same_model(monkeypatch):
    calls = []

    def post(url, *, json, **kwargs):
        calls.append(copy.deepcopy(json))
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error"}})
        return httpx.Response(200, json=_wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(
        max_retries=1, retry_backoff_ms=0))
    assert agent.act(_request()).action == 1
    assert len(agent.attempt_receipts) == 2 and calls[0] == calls[1]


@pytest.mark.parametrize("field,value,kind", [
    ("error", {"type": "rate_limit_error", "message": PRIMARY}, "provider_rate_limited"),
    ("error", {"type": "invalid_api_key", "message": SECONDARY}, "provider_auth_failed"),
    ("incomplete_details", {"reason": "max_output_tokens"}, "provider_output_truncated"),
    ("incomplete_details", {"reason": "content_filter"}, "provider_refused"),
])
def test_embedded_errors_refusal_and_truncation_keep_usage(monkeypatch, field, value, kind):
    data = _wire()
    data[field] = value
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind
    assert len(agent.attempt_receipts) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 120
    _safe(agent, failure.value)


@pytest.mark.parametrize("change", [
    {"type": "function_call"}, {"role": "user"}, {"status": "in_progress"},
    {"content": []}, {"content": [{"type": "refusal", "refusal": PRIMARY}]},
    {"content": [{"type": "output_text", "text": 4}]},
])
def test_noncompleted_and_nontext_output_rejected(monkeypatch, change):
    data = _wire()
    data["output"][0].update(change)
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    _safe(agent)


def test_missing_credentials_fail_before_network(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("missing key"))
    agent = ModelProviderAgent("perplexity", MODEL, API_KEY_ENV)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert agent.last_receipt["usage"] == {}


def test_invalid_action_has_sanitized_receipt_without_repair(monkeypatch):
    data = _wire()
    data["output"][0]["content"][0]["text"] = '{"action":99}'
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=data, headers={"x-request-id": SECONDARY}))
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "action_response_unparseable"
    assert len(agent.attempt_receipts) == 1
    _safe(agent, failure.value)


@pytest.mark.parametrize("partial", [False, True])
def test_actual_bounded_transport_with_raw_byte_stream(monkeypatch, partial):
    client_type = httpx.AsyncClient
    calls = []

    class Raw(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(_wire()).encode()[:20]
            if partial:
                raise httpx.ReadError(SECONDARY)
            yield json.dumps(_wire()).encode()[20:]

    def handler(request):
        calls.append(request)
        assert str(request.url) == AGENT_ENDPOINT
        assert request.headers["Authorization"] == f"Bearer {PRIMARY}"
        payload = json.loads(request.content)
        assert payload["tools"] == [] and payload["tool_choice"] == "none"
        return httpx.Response(200, stream=Raw(), headers={"x-request-id": SECONDARY})

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kw: client_type(
        transport=httpx.MockTransport(handler), **kw))
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=1))
    if partial:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        assert failure.value.error_kind == "provider_transport_error"
        assert agent.last_receipt["status_code"] == 200
        _safe(agent, failure.value)
    else:
        assert agent.act(_request()).action == 1
        _safe(agent)
    assert len(calls) == 1


def test_runner_artifact_receipt_retains_exact_provider_and_model(monkeypatch, tmp_path):
    data = _wire()
    data["output"][0]["content"][0]["text"] = '{"action":0}'
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=data, headers={"x-request-id": PRIMARY}))
    agent = _agent(monkeypatch)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", agents={"player_1": agent},
                                    max_turns=1, output_dir=tmp_path / "run"))
    assert result.trace_events
    receipts = list((tmp_path / "run").rglob("provider_receipts.jsonl"))
    assert receipts
    receipt = json.loads(receipts[0].read_text().splitlines()[0])
    assert receipt["provider"] == "perplexity" and receipt["locked_model_id"] == MODEL
    assert receipt["usage"]["total_tokens"] == 120
    assert not receipt["cost_complete"]  # Native cost alone is no rate-card attestation.
    assert PRIMARY not in receipts[0].read_text()
