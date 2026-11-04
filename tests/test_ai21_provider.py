"""Deterministic AI21 raw REST tests; no credentials or live inference required."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.ai21 import CHAT_COMPLETIONS_ENDPOINT, normalize_usage
from eslams.runner import RunConfig, Runner

SECRET = "plainAi21CredentialNoPrefix9381"
MODEL = "jamba-mini-2-2026-01"
FIXTURE = Path(__file__).parent / "fixtures/provider/ai21_chat_completions_success.json"


def wire():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def agent(**kwargs):
    return ModelProviderAgent(
        provider="ai21-labs", model=MODEL, api_key_env="AI21_API_KEY", **kwargs,
    )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("AI21_API_KEY", SECRET)

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network access")

    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)


def respond(monkeypatch, payload, *, status=200, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_native_wire_identity_accounting_and_unbounded_history(monkeypatch):
    calls = respond(monkeypatch, wire())
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      history=[{"turn": i, "public_action": i % 3} for i in range(100)],
                      metadata={"model_execution_policy": model_execution_policy(None, None)})
    response = agent().act(request)
    receipt = response.metadata["provider_receipt"]
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    payload = sent["json"]
    assert set(payload) == {"model", "messages", "stream", "n"}
    assert payload["model"] == MODEL
    assert payload["stream"] is False and payload["n"] == 1
    assert payload["messages"][0]["role"] == "system"
    prompt = payload["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request.history
    assert sent["timeout"].read is None
    assert sent["timeout"].pool is None
    assert response.action == 1
    assert receipt["provider"] == "ai21-labs" and receipt["model"] == MODEL
    assert receipt["endpoint_kind"] == "ai21_chat_completions"
    assert receipt["parser_version"] == "ai21-chat-completions-raw-v1"
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] == "ai21-wire-fixture"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    for field in ("reasoning_tokens", "cached_input_tokens", "reasoning_included_in_output"):
        assert receipt["usage"][field] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(response.to_dict())


def test_operator_controls_and_gateway_preserve_model(monkeypatch):
    calls = respond(monkeypatch, wire())
    native = agent(
        max_output_tokens=111,
        temperature=0.3,
        runtime_config=ProviderRuntimeConfig(
            gateway_base_url="https://gateway.example/ai21", timeout_ms=20_000,
        ),
    )
    native.act(_request())
    url, sent = calls[0]
    assert url == "https://gateway.example/ai21/studio/v1/chat/completions"
    assert sent["json"]["model"] == MODEL
    assert sent["json"]["max_tokens"] == 111
    assert sent["json"]["temperature"] == 0.3
    assert sent["timeout"].read <= 20


@pytest.mark.parametrize("model", [None, "", " ", "\n\t"])
def test_missing_model_rejected_every_entrypoint(model):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent(provider="ai21-labs", model=model, api_key_env="AI21_API_KEY")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        provider_preflight("ai21-labs", model, "tic-tac-toe")


@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning="enabled"),
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(gemini_thinking_budget=-1),
])
def test_unsupported_reasoning_rejected_before_transport(config):
    with pytest.raises(ValueError, match="no documented reasoning controls"):
        agent(runtime_config=config)
    with pytest.raises(ValueError, match="no documented reasoning controls"):
        provider_preflight("ai21-labs", MODEL, "tic-tac-toe", runtime_config=config)


@pytest.mark.parametrize("mode", ["auto", "disabled"])
def test_reasoning_modes_do_not_change_with_arena(monkeypatch, mode):
    calls = respond(monkeypatch, wire())
    native = agent(runtime_config=ProviderRuntimeConfig(reasoning=mode))
    native.act(_request(arena_id="tic-tac-toe"))
    native.act(_request(arena_id="chess"))
    assert len(calls) == 2
    assert all(set(call[1]["json"]) == {"model", "messages", "n", "stream"} for call in calls)


@pytest.mark.parametrize(("code", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (422, "provider_request_rejected"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_faults_never_retry_or_echo_credentials(monkeypatch, code, kind):
    payload = {"error": {"code": "rate_limit_exceeded", "message": SECRET},
               "id": SECRET, "model": SECRET, "usage": wire()["usage"]}
    calls = respond(monkeypatch, payload, status=code, headers={
        "x-request-id": SECRET, "cf-aig-request-id": SECRET, "Retry-After": "2",
    })
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        native.act(_request())
    assert caught.value.error_kind == kind
    assert caught.value.status_code == code
    assert caught.value.retry_permitted is False
    assert len(calls) == 1
    receipt = native.last_receipt
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["provider_response_id"] is None
    assert receipt["request_id"] is None
    assert receipt["locked_model_id"] is None
    assert SECRET not in json.dumps([receipt, caught.value.receipt, str(caught.value)])


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize(("exception_type", "kind"), [
    (httpx.ReadTimeout, "provider_timeout"),
    (httpx.ReadError, "provider_transport_error"),
    (ProtocolError, "provider_response_schema_mismatch"),
])
def test_partial_and_transport_failures_preserve_only_safe_evidence(
    monkeypatch, observed, exception_type, kind,
):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        exc = exception_type(SECRET)
        if observed:
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                200, (("x-request-id", SECRET), ("cf-aig-request-id", SECRET)),
            )
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        native.act(_request())
    assert len(calls) == 1
    assert native.last_receipt["outcome"] == kind
    assert native.last_receipt["status_code"] == (200 if observed else None)
    assert native.last_receipt["usage"] == {}
    assert SECRET not in json.dumps([native.attempt_receipts, str(caught.value)])


@pytest.mark.parametrize("body", [
    b"not-json", b"[]", b'{"id":"first","id":"second"}', b'{"usage":{"x":NaN}}',
])
def test_malformed_wire_is_sanitized(monkeypatch, body):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *args, **kwargs: httpx.Response(
        200, content=body, headers={"x-request-id": SECRET},
    ))
    native = agent()
    with pytest.raises(ProviderCallError, match="provider_response_schema_mismatch"):
        native.act(_request())
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["usage"] == {}
    assert SECRET not in json.dumps(native.attempt_receipts)


@pytest.mark.parametrize("code", [202, 302])
def test_nonfinal_http_status_cannot_accept_legal_looking_body(monkeypatch, code):
    respond(monkeypatch, wire(), status=code)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert native.last_receipt["status_code"] == code


@pytest.mark.parametrize("fault", [
    "length", "missing-finish", "unknown-finish", "nontext", "tools", "extra-choice",
    "missing-message", "empty", "index", "body-error", "choice-error",
])
def test_incomplete_unsupported_output_never_becomes_an_action(monkeypatch, fault):
    payload = wire()
    choice = payload["choices"][0]
    if fault == "length":
        choice["finish_reason"] = "length"
    elif fault == "missing-finish":
        choice.pop("finish_reason")
    elif fault == "unknown-finish":
        choice["finish_reason"] = SECRET
    elif fault == "nontext":
        choice["message"]["content"] = [{"text": '{"action":1}'}]
    elif fault == "tools":
        choice["message"]["tool_calls"] = [{"id": SECRET}]
    elif fault == "extra-choice":
        payload["choices"].append(dict(choice))
    elif fault == "missing-message":
        choice.pop("message")
    elif fault == "empty":
        choice["message"]["content"] = " "
    elif fault == "index":
        choice["index"] = True
    elif fault == "body-error":
        payload["error"] = {"message": SECRET}
    elif fault == "choice-error":
        choice["error"] = {"message": SECRET}
    respond(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(_request())
    expected = "provider_output_truncated" if fault == "length" else (
        "provider_response_schema_mismatch"
    )
    assert caught.value.error_kind == expected
    assert native.last_receipt["usage"]["total_tokens"] == 16
    assert SECRET not in json.dumps(native.attempt_receipts)


@pytest.mark.parametrize("field", ["id", "model", "header", "explanation", "escaped", "action"])
def test_success_envelope_cannot_publish_a_credential_echo(monkeypatch, field):
    payload = wire()
    headers = {}
    if field in {"id", "model"}:
        payload[field] = SECRET
    elif field == "header":
        headers = {"x-request-id": SECRET, "cf-aig-request-id": SECRET}
    else:
        echoed = "".join(f"\\u{ord(char):04x}" for char in SECRET) if field == "escaped" else SECRET
        name = "action" if field == "action" else "public_explanation"
        payload["choices"][0]["message"]["content"] = (
            '{"action": 1, "' + name + '": "' + echoed + '"}'
        )
    respond(monkeypatch, payload, headers=headers)
    native = agent()
    if field in {"action", "explanation", "escaped"}:
        with pytest.raises(ProviderCallError) as caught:
            native.act(_request())
        serialized = json.dumps([str(caught.value), caught.value.receipt])
    else:
        serialized = json.dumps(native.act(_request()).to_dict())
    assert SECRET not in serialized
    assert SECRET not in json.dumps(native.attempt_receipts)
    assert native.last_receipt["locked_model_id"] is None


def test_missing_and_malformed_accounting_stays_unknown(monkeypatch):
    payload = wire()
    payload.pop("usage")
    respond(monkeypatch, payload)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"] == {}
    assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    usage = normalize_usage({"prompt_tokens": 12, "completion_tokens": 4})
    assert usage["total_tokens"] is None
    assert usage["total_tokens_source"] == "unavailable"
    for bad in (-1, True, "12", 1.5):
        assert normalize_usage({"prompt_tokens": bad})["usage_validation_errors"]
    assert "provider_total_tokens_inconsistent" in normalize_usage({
        "prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 20,
    })["usage_validation_errors"]
    # Undocumented SDK/extensions cannot supply a model, bill, or reasoning count.
    payload.update(model=MODEL, cost=0.1, usage={
        "input_tokens": 100, "reasoning_tokens": 10, "cost": 0.1,
    })
    respond(monkeypatch, payload)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_cli_preflight_and_discovery_are_native_and_offline(monkeypatch, capsys):
    for name in ("ai21-labs", "ai21"):
        native = _provider_agent(f"{name}:{MODEL}")
        assert native.provider == "ai21-labs" and native.model == MODEL
        assert native.api_key_env == "AI21_API_KEY"
        for value in (name, f"{name}:", f"{name}: "):
            with pytest.raises(ValueError, match="explicit nonblank"):
                _provider_agent(value)
        assert provider_models_live(name) is None
        result = provider_preflight(name, MODEL, "tic-tac-toe")
        assert result["ok"] and result["checks"]["adapter_available"]
        assert result["checks"]["account_model_visible"] is None
        assert result["model_availability"] == "unverified"
    assert main(["providers", "models", "--provider", "ai21-labs", "--live"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["error_class"] == (
        "provider_discovery_unavailable"
    )
    respond(monkeypatch, wire())
    assert main(["providers", "preflight", "--provider", "ai21-labs", "--model", MODEL,
                 "--arena", "tic-tac-toe", "--live"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["minimal_inference"] is True
    assert result["checks"]["usage_extraction"] is True
    assert result["checks"]["account_model_visible"] is None


def test_runner_failure_has_no_fallback_or_scoring(monkeypatch, tmp_path):
    respond(monkeypatch, {"error": {"message": SECRET}}, status=401)
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1,
        output_dir=tmp_path, execution_profile="official_eval",
    ))
    assert result.score.match_valid_for_scoring is False
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    assert "provider_auth_failed" in result.score.invalid_reason_codes
    assert result.trace_events == []


def test_cli_run_dispatches_exact_native_model(monkeypatch, tmp_path, capsys):
    calls = respond(monkeypatch, wire())
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", f"ai21-labs:{MODEL}",
        "--max-turns", "1", "--output-dir", str(tmp_path),
    ]) == 0
    assert len(calls) == 1
    assert calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    assert calls[0][1]["json"]["model"] == MODEL
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize("text", ["not-json", '{"action": 999}'])
def test_invalid_action_preserves_usage_without_default_repair(monkeypatch, text):
    payload = wire()
    payload["choices"][0]["message"]["content"] = text
    calls = respond(monkeypatch, payload)
    native = agent()
    assert native.runtime_config.max_retries == 0
    assert native.runtime_config.action_repair_attempts == 0
    with pytest.raises(ProviderCallError) as caught:
        native.act(_request())
    assert caught.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 16


def test_missing_and_invalid_credentials_do_not_call_provider(monkeypatch):
    for key in (None, "bad\nkey"):
        if key is None:
            monkeypatch.delenv("AI21_API_KEY", raising=False)
        else:
            monkeypatch.setenv("AI21_API_KEY", key)
        native = agent()
        with pytest.raises(ProviderCallError) as caught:
            native.act(_request())
        assert caught.value.error_kind == "provider_auth_failed"
        assert native.last_receipt["outcome"] == "provider_auth_failed"
