"""Liquid direct API: documented REST envelope and keyless deterministic faults."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from test_model_agents import _request

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers.registry import load_provider_registry

KEY = "synthetic-Liquid-secret"
SECONDARY_KEY = "synthetic-other-Liquid-secret"


def wire():
    path = Path(__file__).parent / "fixtures/provider/liquid_chat_success.json"
    return json.loads(path.read_text())


def agent(monkeypatch, **kwargs):
    monkeypatch.setenv("LIQUID_API_KEY", KEY)
    return ModelProviderAgent("liquid", "lfm3-1.7b", "LIQUID_API_KEY", **kwargs)


def custom_agent(monkeypatch, **kwargs):
    monkeypatch.setenv("CUSTOM_LIQUID_KEY", KEY)
    monkeypatch.setenv("LIQUID_API_KEY", SECONDARY_KEY)
    return ModelProviderAgent("liquid-ai", "lfm3-1.7b", "CUSTOM_LIQUID_KEY", **kwargs)


def respond(monkeypatch, body, status=200, headers=None):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=body, headers=headers)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_direct_dispatch_preserves_model_history_and_unbounded_defaults(monkeypatch):
    calls = respond(monkeypatch, wire())
    a = agent(monkeypatch)
    history = [{"turn_id": n, "action": n % 3} for n in range(100)]
    response = a.act(replace(
        _request(), protocol_version="eslams-act-v2", history=history, time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    ))
    url, options = calls[0]
    assert url == "https://api.liquid.ai/openai/v1/chat/completions"
    assert options["headers"]["Authorization"] == f"Bearer {KEY}"
    payload = options["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == "lfm3-1.7b" and payload["stream"] is False
    assert json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"] == history
    assert options["timeout"].read is None and len(calls) == 1
    assert response.action == 0 and response.metadata["provider"] == "liquid-ai"
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] == "lfm3-1.7b"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["usage"]["input_tokens"] == 19
    assert receipt["usage"]["output_tokens"] == 10
    assert receipt["usage"]["total_tokens"] == 29
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert KEY not in json.dumps(response.to_dict())


@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_missing_model_rejected(model):
    with pytest.raises(ValueError, match="model ID"):
        ModelProviderAgent("liquid-ai", model, "LIQUID_API_KEY")


@pytest.mark.parametrize("alias", ["liquid", "liquid-ai", " LIQUID_AI "])
@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_preflight_missing_model_never_reaches_transport(monkeypatch, alias, model):
    calls = respond(monkeypatch, wire())
    with pytest.raises(ValueError, match="model ID"):
        provider_preflight(alias, model, "tic-tac-toe", live=True)
    assert calls == []


@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "cf-aig-request-id",
                                   "action"])
@pytest.mark.parametrize("credential", [KEY, SECONDARY_KEY])
@pytest.mark.parametrize("encoding", ["plain", "url", "unicode"])
def test_custom_and_standard_credentials_never_escape(monkeypatch, field, credential, encoding):
    encoded = (credential if encoding == "plain" else
               quote(credential).replace("s", "%73") if encoding == "url" else
               credential.replace("s", "\\u0073"))
    body = wire()
    headers = {}
    if field in {"id", "model"}:
        body[field] = encoded
    elif field == "action":
        body["choices"][0]["message"]["content"] = json.dumps(
            {"action": 0, "public_explanation": encoded})
    else:
        headers[field] = encoded
    calls = respond(monkeypatch, body, headers=headers)
    a = custom_agent(monkeypatch)
    try:
        result = a.act(_request())
        assert field != "action", "credential-echoing action must be rejected"
        assert credential not in json.dumps(result.to_dict())
    except ProviderCallError as error:
        assert credential not in str(error) + json.dumps(error.receipt)
    assert credential not in json.dumps(a.last_receipt)
    receipt_field = {"id": "provider_response_id", "model": "locked_model_id",
                     "x-request-id": "request_id", "cf-aig-request-id": "gateway_request_id"}
    if field in receipt_field:
        assert a.last_receipt[receipt_field[field]] is None
    assert len(calls) == 1
    assert calls[0][1]["headers"]["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("value", ["liquid", "liquid:", "liquid-ai", "liquid-ai: "])
def test_cli_requires_explicit_model(value):
    with pytest.raises(ValueError, match="model ID"):
        _provider_agent(value)


@pytest.mark.parametrize("settings", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 0}, {"gemini_thinking_budget": -1},
    {"history_window_turns": 2}, {"gateway_base_url": "https://example.com"},
    {"openrouter_provider_order": ("other",)},
])
@pytest.mark.parametrize("alias", ["liquid", "liquid-ai", " LIQUID_AI "])
def test_unsupported_controls_rejected_before_submission(monkeypatch, settings, alias):
    calls = respond(monkeypatch, wire())
    runtime = ProviderRuntimeConfig(**settings)
    with pytest.raises(ValueError):
        ModelProviderAgent(alias, "lfm3-1.7b", "LIQUID_API_KEY", runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight(alias, "lfm3-1.7b", "tic-tac-toe", runtime_config=runtime)
    assert calls == []


@pytest.mark.parametrize("budget", [0, 1, 1000])
def test_explicit_budget_rechecked_if_runtime_changes(monkeypatch, budget):
    calls = respond(monkeypatch, wire())
    a = agent(monkeypatch)
    a.runtime_config = ProviderRuntimeConfig(reasoning_budget_tokens=budget)
    with pytest.raises(ValueError, match="reasoning"):
        a.act(_request())
    assert calls == []


@pytest.mark.parametrize("alias", ["liquid", "liquid-ai", " LIQUID_AI "])
def test_discovery_unavailable_without_transport_or_credential_output(monkeypatch, alias):
    custom_agent(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("Liquid discovery is not implemented"))
    result = provider_models_result(alias)
    assert result["models"] == [] and result["ok"] is False
    assert result["error"]["error_class"] == "provider_discovery_unavailable"
    assert KEY not in json.dumps(result) and SECONDARY_KEY not in json.dumps(result)


def test_explicit_output_and_temperature(monkeypatch):
    calls = respond(monkeypatch, wire())
    agent(monkeypatch, max_output_tokens=1234, temperature=0.2).act(_request())
    assert calls[0][1]["json"]["max_tokens"] == 1234
    assert calls[0][1]["json"]["temperature"] == 0.2


@pytest.mark.parametrize("alias", ["liquid", "liquid-ai"])
def test_cli_and_configuration_preflight_never_submit(monkeypatch, capsys, alias):
    calls = respond(monkeypatch, wire())
    assert _provider_agent(f"{alias}:exact-model").model == "exact-model"
    assert main(["providers", "preflight", "--provider", alias, "--model", "lfm3-1.7b",
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["model_availability"] == "unverified" and calls == []
    registry = load_provider_registry()
    assert registry.resolve(alias, "unlisted").provider == "liquid-ai"


def test_explicit_live_preflight_uses_native_dispatch(monkeypatch):
    calls = respond(monkeypatch, wire())
    monkeypatch.setenv("LIQUID_API_KEY", KEY)
    result = provider_preflight("liquid", "lfm3-1.7b", "tic-tac-toe", live=True)
    assert result["ok"] and len(calls) == 1


def test_cli_run_writes_valid_sanitized_native_receipt(monkeypatch, tmp_path, capsys):
    body = wire()
    body["usage"]["cost"] = 0.001
    calls = respond(monkeypatch, body, headers={"x-request-id": KEY})
    monkeypatch.setenv("LIQUID_API_KEY", KEY)
    main(["run", "--arena", "tic-tac-toe", "--agent", "liquid-ai:lfm3-1.7b",
          "--opponent", "first-legal", "--max-turns", "1", "--run-id", "liquid-cli",
          "--output-dir", str(tmp_path), "--expanded"])
    capsys.readouterr()
    assert len(calls) == 1
    receipt_path = next(tmp_path.rglob("provider_receipts.jsonl"))
    receipt = json.loads(receipt_path.read_text().splitlines()[0])
    assert receipt["provider"] == "liquid-ai"
    assert receipt["estimated_cost"]["cost_usd"] == 0.001
    assert receipt["cost_complete"] is False  # No invented price-card evidence.
    assert KEY not in receipt_path.read_text()
    assert ArtifactValidator().validate(receipt_path.parent.parent) == []


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 429, 500, 502, 503, 504])
@pytest.mark.parametrize("credential", [KEY, SECONDARY_KEY])
def test_http_errors_preserve_custody_without_default_retry_or_echo(
    monkeypatch, status, credential,
):
    body = {"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded",
                      "message": credential, "param": None},
            "id": credential, "model": credential}
    calls = respond(monkeypatch, body, status, {
        "x-request-id": credential, "cf-aig-request-id": credential, "Retry-After": "7",
    })
    a = custom_agent(monkeypatch)
    with pytest.raises(ProviderCallError) as error:
        a.act(_request())
    assert error.value.status_code == status and len(calls) == 1
    assert not a.last_receipt["usage"]
    assert a.last_receipt["locked_model_id"] is None
    assert credential not in json.dumps(a.last_receipt) + str(error.value)
    assert credential not in json.dumps(error.value.receipt)
    assert a.last_receipt["provider_response_id"] is None
    assert a.last_receipt["request_id"] is None
    assert a.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("work_evidence", [False, True])
def test_explicit_retry_requires_definitive_rejection_and_honors_retry_after(
    monkeypatch, work_evidence,
):
    body = {"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}}
    if work_evidence:
        body["usage"] = {"prompt_tokens": 19}
    calls = []
    delays = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return (httpx.Response(429, json=body, headers={"Retry-After": "7"})
                if len(calls) == 1 else httpx.Response(200, json=wire()))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation", delays.append)
    a = agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=1))
    if work_evidence:
        with pytest.raises(ProviderCallError):
            a.act(_request())
        assert len(calls) == 1 and delays == []
    else:
        assert a.act(_request()).action == 0
        assert len(calls) == 2 and delays == [7.0]
        assert [r["attempt_index"] for r in a.attempt_receipts] == [1, 2]


@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "cf-aig-request-id"])
def test_echoed_receipt_identifiers_are_removed(monkeypatch, field):
    body = wire()
    headers = {}
    if field in {"id", "model"}:
        body[field] = KEY
    else:
        headers[field] = KEY
    respond(monkeypatch, body, headers=headers)
    a = agent(monkeypatch)
    try:
        result = a.act(_request())
        assert KEY not in json.dumps(result.to_dict())
    except ProviderCallError as error:
        assert KEY not in str(error) + json.dumps(error.receipt)
    assert KEY not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("encoded", [False, True])
def test_action_credential_echo_rejected(monkeypatch, encoded):
    body = wire()
    text = json.dumps({"action": 0, "public_explanation": KEY})
    if encoded:
        text = text.replace("s", "\\u0073")
    body["choices"][0]["message"]["content"] = text
    respond(monkeypatch, body)
    a = agent(monkeypatch)
    with pytest.raises(ProviderCallError):
        a.act(_request())
    assert KEY not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("mutation", ["usage", "model", "cost", "badcost"])
def test_missing_accounting_identity_and_native_cost(monkeypatch, mutation):
    body = wire()
    if mutation in {"usage", "model"}:
        body.pop(mutation)
    else:
        body["usage"]["cost"] = 0.001 if mutation == "cost" else -1
    respond(monkeypatch, body)
    receipt = agent(monkeypatch).act(_request()).metadata["provider_receipt"]
    if mutation == "usage":
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    if mutation == "model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    if mutation == "cost":
        assert receipt["estimated_cost"]["cost_usd"] == 0.001
        assert receipt["estimated_cost"]["source"] == "provider_native"
    else:
        assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("mutation", ["length", "tool_calls", "content_filter", "unknown",
                                      "missing_finish", "wrong_model", "missing_choices"])
def test_incomplete_or_unexpected_envelopes_never_apply_actions(monkeypatch, mutation):
    body = wire()
    if mutation == "missing_choices":
        body.pop("choices")
    elif mutation == "wrong_model":
        body["model"] = "other-model"
    elif mutation == "missing_finish":
        body["choices"][0].pop("finish_reason")
    else:
        body["choices"][0]["finish_reason"] = mutation
    calls = respond(monkeypatch, body)
    a = agent(monkeypatch)
    with pytest.raises(ProviderCallError):
        a.act(_request())
    assert len(calls) == 1 and a.last_receipt["usage"]["input_tokens"] == 19


@pytest.mark.parametrize("body", [b'not JSON', b'{"id":"synthetic-Liquid-secret"',
                                  b'{"choices":[],"choices":[]}'])
@pytest.mark.parametrize("credential", [KEY, SECONDARY_KEY])
def test_malformed_body_and_echoed_headers(monkeypatch, body, credential):
    body = body.replace(KEY.encode(), credential.encode())
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k:
                        httpx.Response(200, content=body, headers={"x-request-id": credential}))
    a = custom_agent(monkeypatch)
    with pytest.raises(ProviderCallError) as error:
        a.act(_request())
    assert credential not in str(error.value) + json.dumps(a.last_receipt)
    assert credential not in json.dumps(error.value.receipt)


def test_deeply_nested_action_retains_sanitized_receipt(monkeypatch):
    body = wire()
    body["choices"][0]["message"]["content"] = "[" * 2000 + '"' + KEY + '"' + "]" * 2000
    respond(monkeypatch, body, headers={"x-request-id": KEY})
    a = agent(monkeypatch)
    with pytest.raises(ProviderCallError):
        a.act(_request())
    assert a.last_receipt["usage"]["input_tokens"] == 19
    assert KEY not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("failure", ["timeout", "reset", "oversize"])
@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("credential", [KEY, SECONDARY_KEY])
def test_actual_partial_reader_failure_scrubs_echoed_headers(
    monkeypatch, failure, status, credential,
):
    original = httpx.AsyncClient
    calls = []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('{"model":"' + credential + '",').encode()
            if failure == "timeout":
                raise httpx.ReadTimeout(credential)
            if failure == "reset":
                raise httpx.ReadError(credential)
            yield b"x" * (1024 * 1024 + 1)
    def handler(request):
        calls.append(1)
        return httpx.Response(status, stream=Stream(), request=request,
                              headers={"x-request-id": credential, "cf-aig-request-id": credential})
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (original(transport=httpx.MockTransport(handler)) as client,
                        client.stream(method, url, **kwargs) as response):
                yield response
    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    a = custom_agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(_request())
    assert calls == [1] and a.last_receipt["status_code"] == status
    assert not a.last_receipt["usage"] and a.last_receipt["locked_model_id"] is None
    assert credential not in json.dumps(a.last_receipt) + str(error.value)
    assert credential not in json.dumps(error.value.receipt)
