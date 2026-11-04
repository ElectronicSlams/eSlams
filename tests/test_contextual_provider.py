"""Keyless raw REST fixtures; no SDK, remote inference, or retrieval."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.contextual import API_KEY_ENV, GENERATE_ENDPOINT

SECRET = "opaqueContextualCredential92847"
SUCCESS = json.loads((Path(__file__).parent / "fixtures/provider/"
                      "contextual_generate_success.json").read_text())


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)


def _agent(**kwargs):
    return ModelProviderAgent("contextual-ai", "v2", API_KEY_ENV, **kwargs)


def test_documented_wire_and_full_history_without_framework_limits(monkeypatch):
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append(json)
        assert url == GENERATE_ENDPOINT
        assert headers == {"Authorization": f"Bearer {SECRET}",
                           "Content-Type": "application/json"}
        assert json["model"] == "v2"
        assert json["knowledge"] == [""]
        assert json["messages"][0]["role"] == "user"
        assert set(json) == {"model", "messages", "knowledge", "system_prompt"}
        assert "full-history-299" in json["messages"][0]["content"]
        assert "full-history-0\"" in json["messages"][0]["content"]
        assert timeout.read is None and not hasattr(timeout, "deadline")
        return httpx.Response(200, json=SUCCESS, headers={"x-request-id": "ctx-request"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    request = replace(
        _request(), time_budget_ms=None, protocol_version="eslams-act-v2",
        metadata={"model_execution_policy": model_execution_policy(None)},
        history=[{"event": f"full-history-{i}"} for i in range(300)],
    )
    result = _agent().act(request)
    assert result.action == 1 and len(calls) == 1
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "contextual-ai" and receipt["model"] == "v2"
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["endpoint_kind"] == "contextual_generate"
    assert receipt["parser_version"] == "contextual-generate-raw-v1"
    assert receipt["usage"] == {} and receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["request_id"] == "ctx-request"
    assert SECRET not in json.dumps(result.to_dict())


def test_exact_model_and_explicit_output_temperature_gateway(monkeypatch):
    def post(url, *, json, **kwargs):
        assert url == "https://gateway.example/v1/generate"
        assert json["model"] == "Pinned-Model/Case:Version"
        assert json["max_new_tokens"] == 2048 and json["temperature"] == 0.4
        return httpx.Response(200, json=SUCCESS)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent(
        "contextual-ai", "Pinned-Model/Case:Version", API_KEY_ENV,
        temperature=0.4, max_output_tokens=2048,
        runtime_config=ProviderRuntimeConfig(gateway_base_url="https://gateway.example"),
    )
    assert agent.act(_request()).action == 1


@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_missing_model_rejected_without_a_default(model):
    with pytest.raises(ValueError, match="explicit nonblank"):
        ModelProviderAgent("contextual-ai", model, API_KEY_ENV)
    if isinstance(model, str):
        with pytest.raises(ValueError, match="explicit nonblank"):
            _provider_agent(f"contextual-ai:{model}")
        with pytest.raises(ValueError, match="explicit nonblank"):
            provider_preflight("contextual-ai", model, "tic-tac-toe")
    with pytest.raises(ValueError):
        _provider_agent("contextual-ai")


@pytest.mark.parametrize("settings", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 100}, {"gemini_thinking_budget": -1},
    {"history_window_turns": 2}, {"openrouter_provider_order": ("Other",)},
])
def test_unsupported_controls_fail_closed(settings):
    runtime = ProviderRuntimeConfig(**settings)
    with pytest.raises(ValueError):
        _agent(runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("contextual-ai", "v2", "tic-tac-toe", runtime_config=runtime)


@pytest.mark.parametrize("maximum", [True, 0, 2049, 1.5])
def test_invalid_output_limit_rejected(maximum):
    with pytest.raises(ValueError):
        _agent(max_output_tokens=maximum)


@pytest.mark.parametrize("temperature", [True, -0.1, 1.1, float("inf")])
def test_invalid_temperature_rejected(temperature):
    with pytest.raises(ValueError):
        _agent(temperature=temperature)


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (422, "provider_request_rejected"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_errors_never_echo_credentials_or_invent_accounting_or_retry(monkeypatch, status, kind):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={
            "detail": [{"loc": [SECRET], "msg": SECRET, "type": SECRET}],
            "id": SECRET, "model": SECRET,
            "error": {"type": "rate_limit_error", "message": SECRET},
            "usage": {"input_tokens": 20, "output_tokens": 2, "total_tokens": 22},
        }, headers={"x-request-id": f"prefix-{SECRET}",
                    "cf-aig-request-id": SECRET, "Retry-After": "0"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert agent.last_receipt["status_code"] == status
    assert agent.last_receipt["usage"] == {}
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["attempt_index"] == 1
    assert SECRET not in json.dumps(agent.attempt_receipts)
    assert SECRET not in json.dumps(failure.value.receipt)
    assert SECRET not in str(failure.value)


@pytest.mark.parametrize("body", [
    "not JSON", "[]", '{"response":null}', '{"response":""}',
    '{"response":"{\\"action\\":1}","response":"other"}',
    json.dumps({"response": f'{{"action":1,"public_explanation":"{SECRET}"}}'}),
    json.dumps({"response": '{"action":1,"public_explanation":"'
                + "".join(f"\\u{ord(char):04x}" for char in SECRET) + '"}'}),
    json.dumps({"response": "{\"action\":1}", "model": SECRET}),
    json.dumps({"response": "{\"action\":1}", "usage": {"total_tokens": 20}}),
    json.dumps({"response": "{\"action\":1}", "error": {"message": SECRET}}),
])
def test_malformed_or_extended_or_credential_echo_body_is_rejected(monkeypatch, body):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, text=body, headers={"x-request-id": SECRET, "x-gateway-request-id": SECRET},
    ))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert agent.last_receipt["status_code"] == 200
    assert SECRET not in json.dumps(agent.attempt_receipts)
    assert SECRET not in json.dumps(failure.value.receipt)


def test_success_header_echo_and_unparseable_action_are_safe(monkeypatch):
    for payload in (SUCCESS, {"response": "unparseable"}):
        monkeypatch.setattr(
            "eslams.agents.bounded_post", lambda *a, payload=payload, **k: httpx.Response(
                200, json=payload, headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET},
            ),
        )
        agent = _agent()
        try:
            result = agent.act(_request())
        except ProviderCallError:
            assert agent.last_receipt["outcome"] == "action_response_unparseable"
        else:
            assert SECRET not in json.dumps(result.to_dict())
        assert SECRET not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("failure_type", [httpx.ReadTimeout, httpx.ReadError])
def test_transport_and_partial_response_keep_safe_receipts(monkeypatch, observed, failure_type):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        failure = failure_type(SECRET)
        if observed:
            failure.__dict__["_eslams_response_observation"] = ResponseObservation(
                200, (("x-request-id", SECRET), ("cf-aig-request-id", SECRET)),
            )
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        agent.act(_request())
    assert len(calls) == 1 and agent.last_receipt["usage"] == {}
    assert agent.last_receipt["status_code"] == (200 if observed else None)
    assert SECRET not in json.dumps(agent.attempt_receipts)


def test_cli_dispatch_and_keyless_preflight(monkeypatch, capsys):
    agent = _provider_agent("contextual-ai:v1")
    assert agent.provider == "contextual-ai" and agent.model == "v1"
    assert agent.api_key_env == API_KEY_ENV
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("offline"))
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("no Models"),
    )
    assert provider_models_live("contextual-ai") is None
    assert main(["providers", "preflight", "--provider", "contextual-ai", "--model", "v2",
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True
    assert result["checks"]["minimal_inference"] is False
    monkeypatch.delenv(API_KEY_ENV)
    assert not provider_preflight("contextual-ai", "v2", "tic-tac-toe", live=True)["ok"]


def test_mocked_live_preflight_has_unknown_usage_and_identity(monkeypatch):
    monkeypatch.setattr(
        "eslams.agents.bounded_post", lambda *a, **k: httpx.Response(200, json=SUCCESS),
    )
    result = provider_preflight("contextual-ai", "v2", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["minimal_inference"]
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["usage_extraction"] is False
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("partial", [False, True])
def test_actual_stream_reader_rejects_incomplete_bodies_without_credential_echo(
    monkeypatch, status, partial,
):
    calls = []
    original = httpx.AsyncClient

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if partial:
                yield ('{"response":"' + SECRET).encode()
            raise httpx.ReadError(SECRET)

    def respond(request):
        assert request.url == GENERATE_ENDPOINT
        calls.append(1)
        return httpx.Response(status, stream=Stream(), headers={
            "x-request-id": SECRET, "cf-aig-request-id": SECRET,
        })

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (
                original(transport=httpx.MockTransport(respond)) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                yield response

    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert calls == [1] and agent.last_receipt["status_code"] == status
    assert agent.last_receipt["usage"] == {} and not failure.value.retry_permitted
    assert SECRET not in json.dumps(agent.attempt_receipts)


def test_cli_run_writes_valid_unknown_accounting_artifact(monkeypatch, tmp_path, capsys):
    def post(*args, **kwargs):
        # Prompt contains the entire ActRequest projection as its final line.
        payload = kwargs["json"]
        prompt = json.loads(payload["messages"][0]["content"].splitlines()[-1])
        action = prompt["legal_actions"][0]
        return httpx.Response(200, json={"response": json.dumps({"action": action})})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", "contextual-ai:v2",
        "--opponent", "first-legal", "--output-dir", str(tmp_path),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    artifact = Path(output["artifact"])
    assert ArtifactValidator().validate(artifact) == []
    with ZipFile(artifact) as archive:
        for name in archive.namelist():
            assert SECRET.encode() not in archive.read(name)
    # The CLI output itself also includes no credentials or fabricated accounting.
    assert SECRET not in json.dumps(output)
    assert output["score"]["aggregate_usage"]["totalCostUsd"] is None
