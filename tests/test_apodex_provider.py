"""Offline Apodex Core wire contract and failure/privacy regressions."""

from __future__ import annotations

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
from eslams.providers.apodex import API_KEY_ENV, CHAT_COMPLETIONS_ENDPOINT, CORE_MODELS

SECRET = "opaque-apodex-fixture-credential"
FIXTURE = Path(__file__).parent / "fixtures/provider/apodex_chat_completions_success.json"


def wire():
    return json.loads(FIXTURE.read_text())


def agent(**kwargs):
    return ModelProviderAgent("apodex", kwargs.pop("model", CORE_MODELS[0]), API_KEY_ENV, **kwargs)


def native_request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


@pytest.fixture(autouse=True)
def credential(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)


def install_post(monkeypatch, response):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("model", CORE_MODELS)
@pytest.mark.parametrize("reasoning", ["auto", "enabled"])
def test_direct_wire_native_defaults_full_history_and_usage(monkeypatch, model, reasoning):
    payload = wire()
    payload["model"] = model
    calls = install_post(monkeypatch, httpx.Response(200, json=payload))
    request = native_request()
    request.history.extend({"turn": i, "action": i % 3} for i in range(100))
    subject = agent(model=model, runtime_config=ProviderRuntimeConfig(reasoning=reasoning))
    result = subject.act(request)
    assert result.action == 1
    assert result.metadata["provider"] == "apodex"
    assert result.metadata["model"] == model
    assert len(calls) == 1
    url, options = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert options["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    body = options["json"]
    assert set(body) == {"model", "messages", "stream"}
    assert body["model"] == model and body["stream"] is False
    assert [item["role"] for item in body["messages"]] == ["system", "user"]
    prompt = body["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request.history
    timeout = options["timeout"]
    assert timeout.read is None and timeout.pool is None
    assert timeout.connect == 10 and timeout.write == 10
    receipt = subject.last_receipt
    assert receipt["locked_model_id"] == model
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "apodex_chat_completions"
    assert receipt["parser_version"] == "apodex-chat-completions-raw-v1"
    assert receipt["provider_response_id"] == "chatcmpl-abc123"
    assert receipt["finish_status"] == "completed" and receipt["finish_reason"] == "stop"
    assert receipt["usage"]["input_tokens"] == 42
    assert receipt["usage"]["output_tokens"] == 187
    assert receipt["usage"]["total_tokens"] == 229
    assert receipt["usage"]["cached_input_tokens"] == 32
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt_index"] == 1
    assert SECRET not in json.dumps(result.to_dict())
    assert "Private fixture reasoning" not in json.dumps(result.to_dict())


def test_explicit_operator_limits_temperature_and_history(monkeypatch):
    calls = install_post(monkeypatch, httpx.Response(200, json=wire()))
    request = native_request()
    request.history.extend({"turn": i} for i in range(20))
    subject = agent(temperature=0.6, max_output_tokens=50_000,
                    runtime_config=ProviderRuntimeConfig(timeout_ms=12_000, history_window_turns=5))
    subject.act(request)
    body = calls[0][1]["json"]
    # Forward an explicit choice unchanged; the real endpoint can reject its own limit.
    assert body["max_tokens"] == 50_000 and body["temperature"] == 0.6
    history = json.loads(body["messages"][1]["content"].splitlines()[-1])["history"]
    assert history == request.history[-5:]
    assert calls[0][1]["timeout"].read <= 12


@pytest.mark.parametrize("model", [None, "", " ", "\t\n", "apodex-1-1-deep-research",
                                   "apodex/Apodex-1.1-mini", "apodex-1.1 ", "future-id"])
def test_rejects_missing_or_non_core_model_before_network(monkeypatch, model):
    install_post(monkeypatch, AssertionError("network forbidden"))
    with pytest.raises(ValueError, match="Apodex"):
        agent(model=model)


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(reasoning="disabled"),
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(gemini_thinking_budget=-1),
    ProviderRuntimeConfig(openrouter_provider_order=("other",)),
    ProviderRuntimeConfig(gateway_base_url="https://router.example/v1"),
])
def test_rejects_unsupported_controls_in_dispatch_and_preflight(monkeypatch, runtime):
    install_post(monkeypatch, AssertionError("network forbidden"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("no discovery"))
    with pytest.raises(ValueError, match="Apodex"):
        agent(runtime_config=runtime)
    result = provider_preflight("apodex", CORE_MODELS[0], "tic-tac-toe", live=True,
                                runtime_config=runtime)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
    (504, "provider_unavailable"),
])
def test_http_errors_have_no_default_retry_or_credential_echo(monkeypatch, status, kind):
    calls = install_post(monkeypatch, httpx.Response(
        status, json={"error": {"code": "rate_limited", "type": "rate_limit_error",
                                "message": SECRET}},
        headers={"x-request-id": SECRET, "x-gateway-request-id": f"prefix-{SECRET}",
                 "Retry-After": "3"},
    ))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == kind and failure.value.status_code == status
    assert len(calls) == 1
    assert subject.last_receipt["request_id"] is None
    assert subject.last_receipt["gateway_request_id"] is None
    assert subject.last_receipt["retry_after_ms"] == 3000
    assert SECRET not in str(failure.value) + json.dumps(failure.value.receipt)
    assert SECRET not in json.dumps(subject.attempt_receipts)
    assert subject.last_receipt["locked_model_id"] is None
    assert subject.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("body", [b"not JSON", b"{", b"[]", b"null", b'{"id":1,"id":2}',
                                  b'{"usage":{"total_tokens":NaN}}'])
def test_malformed_wire_retains_safe_headers(monkeypatch, body):
    calls = install_post(monkeypatch, httpx.Response(
        200, content=body, headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET},
    ))
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    assert SECRET not in str(subject.last_receipt)
    assert subject.last_receipt["status_code"] == 200
    assert subject.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("exception,kind", [
    (httpx.ReadTimeout(SECRET), "provider_timeout"),
    (httpx.ConnectError(SECRET), "provider_transport_error"),
    (httpx.ReadError(SECRET), "provider_transport_error"),
    (ProtocolError(SECRET), "provider_response_schema_mismatch"),
])
@pytest.mark.parametrize("observed", [False, True])
def test_transport_partial_body_never_retries_or_leaks(monkeypatch, exception, kind, observed):
    if observed:
        exception.__dict__["_eslams_response_observation"] = ResponseObservation(
            429, (("x-request-id", SECRET), ("x-gateway-request-id", SECRET)),
        )
    calls = install_post(monkeypatch, exception)
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        subject.act(native_request())
    assert len(calls) == 1
    assert subject.last_receipt["outcome"] == kind
    assert subject.last_receipt["status_code"] == (429 if observed else None)
    assert subject.last_receipt["usage"] == {}
    assert SECRET not in str(failure.value) + str(subject.last_receipt)


@pytest.mark.parametrize("mutation,kind", [
    ({"choices": []}, "provider_response_schema_mismatch"),
    ({"choices": [None]}, "provider_response_schema_mismatch"),
    ({"object": "chat.completion.chunk"}, "provider_response_schema_mismatch"),
    ({"error": {"message": SECRET}}, "provider_unavailable"),
    ({"model": "other-model"}, "provider_request_rejected"),
    ({"model": SECRET}, "provider_request_rejected"),
])
def test_malformed_envelopes_retain_observed_usage_without_action(monkeypatch, mutation, kind):
    payload = {**wire(), **mutation}
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == kind
    assert subject.last_receipt["usage"]["total_tokens"] == 229
    assert SECRET not in str(failure.value.receipt)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"), (SECRET, "provider_response_schema_mismatch"),
    ({"untrusted": SECRET}, "provider_response_schema_mismatch"),
])
def test_finish_failure_rejects_even_legal_looking_partial_action(monkeypatch, reason, kind):
    payload = wire()
    payload["choices"][0]["finish_reason"] = reason
    calls = install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1 and subject.last_receipt["usage"]["total_tokens"] == 229
    assert SECRET not in str(subject.last_receipt)


@pytest.mark.parametrize("field,value", [
    ("content", None), ("content", []), ("content", ""),
    ("content", '{"action": 1, "public_explanation": "' + SECRET + '"}'),
    ("content", '{"action": 1, "public_explanation": "' +
     ''.join(f'\\u{ord(c):04x}' for c in SECRET) + '"}'),
    ("refusal", SECRET), ("tool_calls", [{"function": {"name": "web_search"}}]),
    ("function_call", {"name": "search"}), ("role", "user"),
])
def test_message_rejects_tools_refusals_and_credential_actions(monkeypatch, field, value):
    payload = wire()
    payload["choices"][0]["message"][field] = value
    calls = install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    with pytest.raises(ProviderCallError):
        subject.act(native_request())
    assert len(calls) == 1
    assert SECRET not in str(subject.last_receipt)


def test_embedded_choice_error_rejects_legal_looking_text(monkeypatch):
    payload = wire()
    payload["choices"][0]["error"] = {"message": SECRET}
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == "provider_unavailable"
    assert subject.last_receipt["usage"]["total_tokens"] == 229
    assert SECRET not in str(subject.last_receipt)


def test_success_identifiers_private_reasoning_and_usage_cannot_echo_credential(monkeypatch):
    payload = wire()
    payload["id"] = SECRET
    payload["choices"][0]["message"]["reasoning_content"] = SECRET
    payload["usage"]["untrusted"] = SECRET
    payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 100}
    install_post(monkeypatch, httpx.Response(200, json=payload, headers={"x-request-id": SECRET}))
    subject = agent()
    result = subject.act(native_request())
    assert SECRET not in json.dumps(result.to_dict())
    assert subject.last_receipt["provider_response_id"] is None
    assert subject.last_receipt["request_id"] is None
    assert subject.last_receipt["usage"]["reasoning_tokens"] == 100


def test_missing_identity_usage_and_total_are_not_fabricated(monkeypatch):
    payload = wire()
    payload.pop("model")
    payload.pop("usage")
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    assert subject.act(native_request()).action == 1
    assert subject.last_receipt["locked_model_id"] is None
    assert subject.last_receipt["model_identity_source"] is None
    assert subject.last_receipt["usage"] == {}
    assert subject.last_receipt["usage_unavailable_reason"] == "provider_usage_absent"
    payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 4}
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject.act(native_request())
    usage = subject.last_receipt["usage"]
    assert usage["total_tokens"] == 14
    assert usage["total_tokens_source"] == "derived_input_plus_output"
    assert usage["reasoning_tokens"] is None


@pytest.mark.parametrize("bad_usage", [
    {"prompt_tokens": -1, "completion_tokens": True, "total_tokens": "10"},
    {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 99},
    {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
     "prompt_tokens_details": {"cached_tokens": 2}},
    {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
     "completion_tokens_details": {"reasoning_tokens": 3}},
])
def test_invalid_accounting_remains_flagged(monkeypatch, bad_usage):
    payload = wire()
    payload["usage"] = bad_usage
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    subject.act(native_request())
    usage = subject.last_receipt["usage"]
    if usage:
        assert usage["usage_validation_errors"]
    else:
        assert subject.last_receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert subject.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_safe_rate_rejection_can_retry_only_when_explicit(monkeypatch):
    calls = []
    waits = []

    def post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {
                "code": "rate_limited", "type": "rate_limit_error", "message": SECRET,
            }}, headers={"Retry-After": "3"})
        return httpx.Response(200, json=wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation",
                        lambda seconds: waits.append(seconds))
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_jitter=False))
    assert subject.act(native_request()).action == 1
    assert len(calls) == 2 and waits == [3]
    assert [r["attempt_index"] for r in subject.attempt_receipts] == [1, 2]
    assert SECRET not in json.dumps(subject.attempt_receipts)


@pytest.mark.parametrize("extra", [
    {"id": SECRET}, {"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    {"cost": 0.1}, {"choices": [{"message": {"content": '{"action":1}'}}]},
])
def test_error_work_observations_veto_retry(monkeypatch, extra):
    calls = install_post(monkeypatch, httpx.Response(429, json={**extra, "error": {
        "code": "rate_limited", "type": "rate_limit_error", "message": SECRET,
    }}))
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        subject.act(native_request())
    assert len(calls) == 1
    assert SECRET not in json.dumps(subject.last_receipt)
    assert subject.last_receipt["locked_model_id"] is None
    assert subject.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_cli_dispatch_offline_preflight_and_blank_ids(monkeypatch, capsys):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("offline"))
    for value in ("apodex", "apodex:", "apodex:   "):
        with pytest.raises(ValueError, match="explicit nonblank"):
            _provider_agent(value)
    subject = _provider_agent("apodex:apodex-1.1-mini")
    assert subject.provider == "apodex" and subject.model == "apodex-1.1-mini"
    assert subject.api_key_env == API_KEY_ENV
    assert main(["providers", "preflight", "--provider", "apodex", "--model", "apodex-1.1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] and result["checks"]["adapter_available"]
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["model_availability"] == "unverified"
    assert main(["providers", "preflight", "--provider", "apodex", "--model", " "]) == 1
    assert not json.loads(capsys.readouterr().out)["readiness"]["configuration_ready"]


def test_live_preflight_and_discovery_are_only_mocked(monkeypatch):
    def get(url, **kwargs):
        assert url == "https://api.apodex.ai/v1/models"
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"data": [{"id": m} for m in CORE_MODELS]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("apodex") == sorted(CORE_MODELS)
    calls = install_post(monkeypatch, httpx.Response(200, json=wire()))
    result = provider_preflight("apodex", CORE_MODELS[0], "connect-four", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"]
    assert result["checks"]["usage_extraction"]
    assert result["readiness"]["inference"] == "succeeded"
    assert set(calls[0][1]["json"]) == {"model", "messages", "stream"}
    assert calls[0][1]["timeout"].read is None
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": SECRET}]},
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("apodex")
    assert SECRET not in str(failure.value)


def test_cli_gameplay_receipts_and_action_failure_are_validated(monkeypatch, tmp_path, capsys):
    from eslams.artifacts import ArtifactValidator

    calls = []

    def post(url, **kwargs):
        prompt = kwargs["json"]["messages"][1]["content"]
        legal = json.loads(prompt.splitlines()[-1])["legal_actions"]
        payload = wire()
        payload["choices"][0]["message"]["content"] = json.dumps({"action": legal[0]})
        calls.append(url)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "apodex:apodex-1.1",
                 "--opponent", "first-legal", "--output-dir", str(tmp_path),
                 "--run-id", "apodex-cli-success"]) == 0
    expanded = Path(json.loads(capsys.readouterr().out)["expanded_artifact"])
    assert ArtifactValidator().validate(expanded) == []
    rows = [json.loads(line) for line in
            (expanded / "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == len(calls) > 0
    assert all(row["provider"] == "apodex" and row["model"] == "apodex-1.1" for row in rows)
    assert SECRET not in json.dumps(rows)
    payload = wire()
    payload["choices"][0]["message"]["content"] = '{"action": 999}'
    calls = install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1 and subject.last_receipt["usage"]["total_tokens"] == 229


@pytest.mark.parametrize("key", ["", " \r\n ", "bad key", "bad\tkey", "unicode-☃"])
def test_missing_and_invalid_credentials_fail_before_network(monkeypatch, key):
    monkeypatch.setenv(API_KEY_ENV, key)
    calls = install_post(monkeypatch, AssertionError("must not call network"))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == "provider_auth_failed" and calls == []
    assert subject.last_receipt["usage"] == {}


def test_real_bounded_transport_decodes_mock_raw_bytes(monkeypatch):
    client_type = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(request)
        assert str(request.url) == CHAT_COMPLETIONS_ENDPOINT
        assert json.loads(request.content)["model"] == "apodex-1.1"
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, stream=httpx.ByteStream(FIXTURE.read_bytes()),
                              headers={"x-request-id": "safe-id"})

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(handle),
    ))
    subject = agent()
    assert subject.act(native_request()).action == 1
    assert subject.last_receipt["request_id"] == "safe-id" and len(requests) == 1
