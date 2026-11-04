"""Deterministic native REST envelopes, never paid inference or provider credentials."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.perceptron import CHAT_COMPLETIONS_ENDPOINT

KEY = "opaqueFixtureCredential92834"
MODEL = "perceptron-mk1.5"
FIXTURE = Path(__file__).parent / "fixtures/provider/perceptron_chat_completions_success.json"


def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="perceptron-wire", episode_id="episode-1",
        turn_id=90, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="wire-agent", version="1"), active_player="player_1",
        observation={"board": [], "marker": "private-prompt-fixture"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"}, history=[{"turn": i} for i in range(90)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(runtime=None, model=MODEL, **kwargs):
    return ModelProviderAgent(provider="perceptron", model=model,
                              api_key_env="PERCEPTRON_API_KEY", runtime_config=runtime, **kwargs)


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    monkeypatch.setenv("PERCEPTRON_API_KEY", KEY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("unexpected IO"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("unexpected discovery"))


def respond(monkeypatch, data=None, *, status=200, headers=None, content=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload() if data is None else data,
                              headers=headers) if content is None else httpx.Response(
                                  status, content=content, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_native_dispatch_wire_history_accounting_and_privacy(monkeypatch):
    calls = respond(monkeypatch, headers={"x-trace-id": "trace-perceptron"})
    result = _provider_agent("perceptron:" + MODEL).act(request())
    assert result.action == 1
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    body = sent["json"]
    assert set(body) == {"model", "messages"}
    assert body["model"] == MODEL
    sent_prompt = json.loads(body["messages"][1]["content"].split("\n")[-1])
    assert sent_prompt["history"] == request().history
    assert sent["timeout"].read is None and sent["timeout"].pool is None
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "perceptron" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "perceptron_chat_completions"
    assert receipt["parser_version"] == "perceptron-chat-completions-raw-v1"
    assert receipt["request_id"] == "trace-perceptron"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(result.to_dict())
    for private in (KEY, "Private fixture reasoning", "private-prompt-fixture", "Authorization"):
        assert private not in public


@pytest.mark.parametrize("model,runtime,expected", [
    (MODEL, ProviderRuntimeConfig(reasoning_effort=effort), {"reasoning_effort": effort})
    for effort in ("none", "minimal", "low", "medium", "high")
] + [
    (MODEL, ProviderRuntimeConfig(reasoning="disabled"), {"reasoning_effort": "none"}),
    (MODEL, ProviderRuntimeConfig(reasoning="enabled", reasoning_effort="high"),
     {"reasoning_effort": "high"}),
    ("perceptron-mk1", ProviderRuntimeConfig(reasoning="enabled"),
     {"vision_config": {"enable_thinking": True}}),
    ("perceptron-mk1", ProviderRuntimeConfig(reasoning="disabled"),
     {"vision_config": {"enable_thinking": False}}),
    ("perceptron-mk1", ProviderRuntimeConfig(), {}),
])
def test_explicit_controls_only(monkeypatch, model, runtime, expected):
    calls = respond(monkeypatch)
    agent(runtime, model, max_output_tokens=1777, temperature=0.2).act(request())
    body = calls[0][1]["json"]
    assert body == {"model": model, "messages": body["messages"],
                    "max_completion_tokens": 1777, "temperature": 0.2, **expected}


@pytest.mark.parametrize("model,runtime", [
    (None, None), ("", None), ("   ", None),
    (MODEL, ProviderRuntimeConfig(reasoning_effort="xhigh")),
    (MODEL, ProviderRuntimeConfig(reasoning="enabled")),
    (MODEL, ProviderRuntimeConfig(reasoning="enabled", reasoning_effort="none")),
    (MODEL, ProviderRuntimeConfig(reasoning_budget_tokens=0)),
    (MODEL, ProviderRuntimeConfig(gemini_thinking_budget=1)),
    ("perceptron-mk1", ProviderRuntimeConfig(reasoning_effort="high")),
    ("unknown-exact-model", ProviderRuntimeConfig(reasoning_effort="low")),
    ("unknown-exact-model", ProviderRuntimeConfig(reasoning="disabled")),
])
def test_invalid_model_and_reasoning_fail_before_io(model, runtime):
    with pytest.raises(ValueError):
        agent(runtime, model)
    with pytest.raises(ValueError):
        provider_preflight("perceptron", model, "tic-tac-toe", runtime_config=runtime)


@pytest.mark.parametrize("value", ["perceptron", "perceptron:", "perceptron:  "])
def test_cli_requires_model(value):
    with pytest.raises(ValueError, match="model ID"):
        _provider_agent(value)


def test_unknown_model_passes_exactly_without_identity_or_usage_fabrication(monkeypatch):
    data = payload()
    del data["model"], data["usage"]
    calls = respond(monkeypatch, data)
    result = agent(model="Some/Future:Exact-ID").act(request())
    assert calls[0][1]["json"]["model"] == "Some/Future:Exact-ID"
    receipt = result.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["usage"] == {} and receipt["usage_unavailable_reason"] == "provider_usage_absent"


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (502, "provider_unavailable"), (503, "provider_unavailable"), (504, "provider_unavailable"),
])
def test_http_errors_are_redacted_and_not_retried(monkeypatch, status, kind):
    calls = respond(monkeypatch, {"error": {"message": KEY, "type": "rate_limit_error"}},
                    status=status, headers={"x-trace-id": KEY, "x-request-id": KEY,
                                            "cf-aig-request-id": KEY, "Retry-After": "9"})
    instance = agent()
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1
    assert instance.last_receipt["status_code"] == status
    assert KEY not in json.dumps(instance.attempt_receipts) + str(caught.value)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"), (None, "provider_response_schema_mismatch"),
    ("interrupted", "provider_response_schema_mismatch"),
    ("unexpected-secret-" + KEY, "provider_response_schema_mismatch"),
])
def test_nonfinal_responses_retain_usage_without_accepting_action(monkeypatch, reason, kind):
    data = payload()
    data["choices"][0]["finish_reason"] = reason
    calls = respond(monkeypatch, data)
    instance = agent()
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert instance.last_receipt["usage"]["total_tokens"] == 16
    assert KEY not in json.dumps(instance.attempt_receipts)


@pytest.mark.parametrize("field", ["id", "model", "header", "gateway", "action", "explanation",
                                  "escaped_explanation"])
def test_credential_echo_never_enters_identity_or_action(monkeypatch, field):
    data = payload()
    headers = {}
    if field in {"id", "model"}:
        data[field] = "prefix-" + KEY
    elif field in {"header", "gateway"}:
        headers["x-trace-id" if field == "header" else "cf-aig-request-id"] = KEY
    else:
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": KEY if field == "action" else 1, "public_explanation": KEY,
        })
        if field == "escaped_explanation":
            data["choices"][0]["message"]["content"] = (
                data["choices"][0]["message"]["content"].replace(
                    KEY, "".join(f"\\u{ord(c):04x}" for c in KEY)))
    data["choices"][0]["message"]["reasoning_content"] = KEY
    respond(monkeypatch, data, headers=headers)
    instance = agent()
    if field in {"action", "explanation", "escaped_explanation"}:
        with pytest.raises(ProviderCallError):
            instance.act(request())
    else:
        assert KEY not in json.dumps(instance.act(request()).to_dict())
    assert KEY not in json.dumps(instance.attempt_receipts)
    if field == "model":
        assert instance.last_receipt["locked_model_id"] is None
        # No source can attest an observation that was removed as secret-bearing.
        assert instance.last_receipt["model_identity_source"] is None


@pytest.mark.parametrize("body", [b'{"echo":', b'not JSON', b'[]', b'{"id":1,"id":2}'])
def test_malformed_body_retains_only_safe_headers(monkeypatch, body):
    respond(monkeypatch, content=body + (KEY.encode() if body == b'not JSON' else b''),
            headers={"x-request-id": KEY, "x-trace-id": KEY, "cf-aig-request-id": KEY})
    instance = agent()
    with pytest.raises(ProviderCallError, match="provider_response_schema_mismatch"):
        instance.act(request())
    assert KEY not in json.dumps(instance.attempt_receipts)
    assert instance.last_receipt["usage"] == {}


@pytest.mark.parametrize("partial", [False, True])
def test_transport_timeout_never_replayed_even_when_retries_requested(monkeypatch, partial):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        exc = httpx.ReadTimeout(KEY)
        if partial:
            exc._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", KEY), ("x-trace-id", KEY), ("cf-aig-request-id", KEY)))
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    instance = agent(ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        instance.act(request())
    assert calls == [1] and KEY not in json.dumps(instance.attempt_receipts)
    assert instance.last_receipt["usage"] == {}


def test_models_preflight_and_cli_are_keyless_unless_live(monkeypatch, capsys):
    monkeypatch.delenv("PERCEPTRON_API_KEY")
    result = provider_preflight("perceptron", MODEL, "tic-tac-toe")
    assert result["ok"] and result["checks"]["adapter_available"]
    assert not result["checks"]["api_key_configured"]
    assert result["model_availability"] == "unverified"
    assert main(["providers", "preflight", "--provider", "perceptron", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    monkeypatch.setenv("PERCEPTRON_API_KEY", KEY)

    def get(url, **kwargs):
        assert url == "https://api.perceptron.inc/v1/models"
        assert kwargs["headers"]["Authorization"] == "Bearer " + KEY
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("perceptron") == [MODEL]
    respond(monkeypatch)
    result = provider_preflight("perceptron", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"]
    assert result["checks"]["response_parsing"] and result["checks"]["usage_extraction"]


def test_cli_run_dispatches_native_adapter_and_writes_safe_artifact(monkeypatch, tmp_path, capsys):
    calls = respond(monkeypatch)
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", "perceptron:" + MODEL,
        "--opponent", "first-legal", "--max-turns", "1", "--run-id", "perceptron-cli",
        "--output-dir", str(tmp_path), "--expanded",
    ]) == 0
    assert len(calls) == 1 and calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    assert KEY not in capsys.readouterr().out
    receipts = list(tmp_path.rglob("provider_receipts.jsonl"))
    assert len(receipts) == 1
    receipt_text = receipts[0].read_text()
    assert KEY not in receipt_text and "Private fixture reasoning" not in receipt_text
    assert '"perceptron"' in receipt_text


def test_registry_native_records_are_independent_of_router_prices():
    registry = load_provider_registry()
    for model in ("perceptron-mk1", MODEL):
        record = registry.resolve("perceptron", model)
        assert record.known and record.allows_text_game_agent() and record.lifecycle == "active"
        assert record.available_from_api is None and record.pricing == {}


@pytest.mark.parametrize("usage", [None, {}, {"completion_tokens": 4},
                                   {"prompt_tokens": True, "completion_tokens": -1},
                                   {"prompt_tokens": KEY}])
def test_missing_or_bad_usage_does_not_invent_accounting(monkeypatch, usage):
    data = payload()
    data["usage"] = usage
    respond(monkeypatch, data)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    observed = receipt["usage"]
    assert not observed or observed["input_tokens"] is None
    assert not observed or observed["total_tokens"] is None
    assert KEY not in json.dumps(receipt)


@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("kind,work,retry", [
    ("rate_limit_error", False, True),
    ("insufficient_quota", False, False),
    ("rate_limit_error", True, False),
])
def test_opt_in_retries_only_unambiguous_rate_rejections(monkeypatch, status, kind, work, retry):
    data = {"error": {"type": kind, "code": kind, "param": None, "message": KEY}}
    if work:
        data.update(id=KEY, model=KEY, usage=payload()["usage"], cost=0.0001)
    calls = respond(monkeypatch, data, status=status, headers={"x-trace-id": KEY})
    instance = agent(ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        instance.act(request())
    assert len(calls) == (2 if retry else 1)
    assert KEY not in json.dumps(instance.attempt_receipts)
    assert instance.last_receipt["locked_model_id"] is None
    if work:
        assert instance.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
        assert instance.last_receipt["usage"]["total_tokens"] == 16
        assert instance.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_opaque_transport_error_message_cannot_echo_key(monkeypatch):
    def post(*args, **kwargs):
        raise httpx.ConnectError(KEY)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    instance = agent(ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert KEY not in str(caught.value) + json.dumps(instance.attempt_receipts)
    assert instance.last_receipt["outcome"] == "provider_transport_error"


def test_model_mismatch_is_preserved_as_response_evidence(monkeypatch):
    data = payload()
    data["model"] = "different-attested-model"
    respond(monkeypatch, data)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["model"] == MODEL and receipt["locked_model_id"] == "different-attested-model"


def test_invalid_action_does_not_retry_or_return_fallback(monkeypatch):
    data = payload()
    data["choices"][0]["message"]["content"] = '{"action": 999}'
    calls = respond(monkeypatch, data)
    instance = agent()
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert caught.value.error_kind == "action_response_unparseable" and len(calls) == 1
    assert instance.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("field", ["choices", "message", "content", "role", "index", "tools"])
def test_malformed_native_wire_cannot_become_action(monkeypatch, field):
    data = copy.deepcopy(payload())
    choice = data["choices"][0]
    if field == "choices":
        data["choices"] = []
    elif field == "message":
        choice["message"] = None
    elif field == "content":
        choice["message"]["content"] = None
    elif field == "role":
        choice["message"]["role"] = "user"
    elif field == "index":
        choice["index"] = True
    else:
        choice["message"]["tool_calls"] = [{"id": "call", "function": {"arguments": KEY}}]
    respond(monkeypatch, data)
    instance = agent()
    with pytest.raises(ProviderCallError):
        instance.act(request())
    assert KEY not in json.dumps(instance.attempt_receipts)
