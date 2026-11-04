"""Keyless native Mistral wire and integration regressions; see MISTRAL.md."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _fixture, _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator, read_member
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.mistral import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT

KEY = "MISTRAL_API_KEY"
MODEL = "mistral-small-latest"
PRIVATE = "private-mistral-fixture"


def _agent(provider="mistral-ai", **kwargs):
    return ModelProviderAgent(provider=provider, model=MODEL, api_key_env=KEY, **kwargs)


def _success():
    return _fixture("mistral_chat_completions_success.json")


def _post(monkeypatch, response):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setenv(KEY, "fixture-secret-mistral")
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("provider", [
    "mistral-ai", "mistral", "MISTRAL", "mistral_ai", " Mistral ",
])
def test_alias_registry_cli_dispatch_preflight_and_execution(monkeypatch, provider):
    registry = load_provider_registry()
    assert registry.resolve(provider, MODEL).provider == "mistral-ai"
    agent = _provider_agent(f"{provider}:{MODEL}")
    assert agent.provider == "mistral-ai" and agent.model == MODEL and agent.api_key_env == KEY
    with pytest.raises(ValueError, match="explicit model ID"):
        _provider_agent(provider)
    calls = _post(monkeypatch, httpx.Response(200, json=_success()))
    direct = _agent(provider)
    assert direct.act(_request()).action == 1
    assert direct.last_receipt["provider"] == "mistral-ai"
    assert direct.last_receipt["endpoint_kind"] == "mistral_chat_completions"
    assert direct.last_receipt["parser_version"] == "mistral-chat-completions-raw-v1"
    assert len(calls) == 1 and calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    result = provider_preflight(provider, MODEL, "tic-tac-toe")
    assert result["ok"] and result["checks"]["adapter_available"]
    assert result["checks"]["api_key_configured"]


def test_raw_wire_request_usage_identity_privacy_and_full_history(monkeypatch):
    calls = _post(monkeypatch, httpx.Response(
        200, json=_success(), headers={"x-request-id": "req-1"},
    ))
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      history=[{"turn_id": i, "public": PRIVATE} for i in range(40)],
                      metadata={"model_execution_policy": model_execution_policy(None, None)})
    agent = _agent()
    assert agent.act(request).action == 1
    payload = calls[0][1]["json"]
    assert payload["model"] == MODEL
    assert payload["stream"] is False
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    sent_history = json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"]
    assert sent_history == request.history
    assert not {"max_tokens", "tools", "response_format", "prompt_mode", "reasoning_effort",
                "provider", "temperature", "stop"}.intersection(payload)
    assert calls[0][1]["headers"]["Authorization"] == "Bearer fixture-secret-mistral"
    assert calls[0][1]["timeout"].read is None
    receipt = agent.last_receipt
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["request_id"] == "req-1"
    usage = receipt["usage"]
    assert [usage[k] for k in ("input_tokens", "output_tokens", "total_tokens")] == [12, 4, 16]
    for field in ("reasoning_tokens", "cached_input_tokens", "reasoning_included_in_output"):
        assert usage[field] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(agent.attempt_receipts)
    for secret in (PRIVATE, "fixture-secret-mistral", "Authorization", "messages", "content"):
        assert secret not in public


def test_only_explicit_controls_and_exact_model_are_forwarded(monkeypatch):
    response = _success()
    response["model"] = "ft:literal-model:unchanged"
    calls = _post(monkeypatch, httpx.Response(200, json=response))
    agent = ModelProviderAgent(
        provider="mistral", model="ft:literal-model:unchanged", api_key_env=KEY,
        temperature=0.25, max_output_tokens=923,
        runtime_config=ProviderRuntimeConfig(reasoning_effort="high", history_window_turns=2),
    )
    request = replace(_request(), history=[{"turn_id": i} for i in range(5)])
    agent.act(request)
    payload = calls[0][1]["json"]
    assert payload["model"] == "ft:literal-model:unchanged"
    assert payload["max_tokens"] == 923 and payload["temperature"] == 0.25
    assert payload["reasoning_effort"] == "high" and "prompt_mode" not in payload
    sent_history = json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"]
    assert sent_history == request.history[-2:]


def test_typed_chunks_skip_thinking_and_keep_only_answer_text(monkeypatch):
    _post(monkeypatch, httpx.Response(200, json=_fixture("mistral_chat_completions_chunks.json")))
    agent = _agent()
    assert agent.act(_request()).action == 1
    assert "private-thinking-fixture" not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("model_length", "provider_output_truncated"),
    ("tool_calls", "provider_request_rejected"), ("error", "provider_unavailable"),
    ("content_filter", "provider_refused"), ("refusal", "provider_refused"),
    (None, "provider_response_schema_mismatch"), ("unknown", "provider_response_schema_mismatch"),
    ({"private": PRIVATE}, "provider_response_schema_mismatch"),
])
def test_nonterminal_and_refusal_responses_never_accept_partial_action(monkeypatch, reason, kind):
    payload = _success()
    payload["choices"][0]["finish_reason"] = reason
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert agent.last_receipt["outcome"] == kind
    assert PRIVATE not in str(failure.value) + json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(choices=[]),
    lambda p: p["choices"].append(copy.deepcopy(p["choices"][0])),
    lambda p: p["choices"][0].update(index=False),
    lambda p: p["choices"][0].update(index=0.0),
    lambda p: p["choices"][0].update(message=None),
    lambda p: p["choices"][0]["message"].update(role="user"),
    lambda p: p["choices"][0]["message"].update(content=None),
    lambda p: p["choices"][0]["message"].update(content=[{"type": "text", "text": 1}]),
    lambda p: p["choices"][0]["message"].update(
        content=[{"type": "image_url", "text": '{"action":1}'}]),
    lambda p: p["choices"][0]["message"].update(content=[{"type": "thinking", "thinking": []}]),
    lambda p: p.update(status="in_progress"),
])
def test_malformed_envelopes_fail_with_usage_and_no_replay(monkeypatch, mutation):
    payload = _success()
    mutation(payload)
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1 and agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("field,kind", [("tool_calls", "provider_request_rejected"),
                                      ("refusal", "provider_refused")])
def test_message_failures_with_stop_do_not_accept_text(monkeypatch, field, kind):
    payload = _success()
    payload["choices"][0]["message"][field] = PRIVATE
    _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind
    assert PRIVATE not in json.dumps(agent.last_receipt) + str(failure.value)


@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b'{"choices": [], "choices": []}'])
def test_invalid_json_and_duplicate_keys_have_sanitized_attempt_receipts(monkeypatch, body):
    calls = _post(monkeypatch, httpx.Response(200, content=body))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1
    assert agent.last_receipt["usage"] == {}


@pytest.mark.parametrize("code,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (422, "provider_request_rejected"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (502, "provider_unavailable"), (503, "provider_unavailable")])
def test_http_errors_are_redacted_and_ambiguous_native_rejections_not_replayed(
    monkeypatch, code, kind,
):
    body = _fixture("mistral_rate_limited.json")
    body["message"] = PRIVATE + " fixture-secret-mistral"
    calls = _post(monkeypatch, httpx.Response(code, json=body, headers={"Retry-After": "2"}))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert agent.last_receipt["status_code"] == code
    assert agent.last_receipt["retry_after_ms"] == 2000
    assert agent.last_receipt["usage"] == {}
    assert agent.last_receipt["locked_model_id"] is None
    public = json.dumps(agent.attempt_receipts) + str(failure.value)
    assert PRIVATE not in public and "fixture-secret-mistral" not in public


@pytest.mark.parametrize("error,kind", [
    (httpx.ReadTimeout(PRIVATE), "provider_timeout"),
    (httpx.ConnectError(PRIVATE), "provider_transport_error"),
])
def test_transport_ambiguity_is_never_replayed(monkeypatch, error, kind):
    calls = _post(monkeypatch, error)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)):
        agent.act(_request())
    assert len(calls) == 1 and agent.last_receipt["outcome"] == kind
    assert PRIVATE not in json.dumps(agent.attempt_receipts)


def test_http200_error_envelope_preserves_observations_and_never_replays_work(monkeypatch):
    payload = _success()
    payload["error"] = {"code": 429, "message": PRIVATE}
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_rate_limited" and len(calls) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert PRIVATE not in json.dumps(agent.attempt_receipts) + str(failure.value)


@pytest.mark.parametrize("retries,expected", [(0, 1), (1, 2)])
def test_shared_safe_rejection_retry_is_opt_in(monkeypatch, retries, expected):
    # Deliberately the narrow shared rejection envelope; native flat 1300 errors
    # above do not establish this evidence and must never be auto-replayed.
    calls = _post(monkeypatch, httpx.Response(429, json={"error": {"code": 429}},
                                            headers={"Retry-After": "0"}))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=retries))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(calls) == expected and len(agent.attempt_receipts) == expected
    assert [r["attempt_index"] for r in agent.attempt_receipts] == list(range(1, expected + 1))


@pytest.mark.parametrize("code", [429, 503])
def test_error_body_work_observations_are_quarantined_and_prevent_replay(monkeypatch, code):
    payload = {"error": {"code": 429, "message": PRIVATE}, "id": "cmpl-observed",
               "model": "unverified-error-model", "usage": _success()["usage"], "cost": 0.5}
    calls = _post(monkeypatch, httpx.Response(code, json=payload))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    receipt = agent.last_receipt
    assert len(calls) == 1 and receipt["usage"]["total_tokens"] == 16
    assert receipt["provider_response_id"] == "cmpl-observed"
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert PRIVATE not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("repairs", [0, 1])
def test_invalid_action_keeps_usage_and_explicit_repair_is_a_separate_attempt(monkeypatch, repairs):
    responses = [_success(), _success()]
    responses[0]["choices"][0]["message"]["content"] = '{"action": 999}'
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=responses[len(calls) - 1])

    monkeypatch.setenv(KEY, "fixture-secret-mistral")
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=repairs))
    if repairs:
        assert agent.act(_request()).action == 1
        assert agent.attempt_receipts[1]["attempt_kind"] == "action_repair"
    else:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        assert failure.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1 + repairs
    assert agent.attempt_receipts[0]["outcome"] == "action_response_unparseable"
    assert all(r["usage"]["total_tokens"] == 16 for r in agent.attempt_receipts)


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 12},
    {"prompt_tokens": True, "completion_tokens": 4, "total_tokens": 16},
    {"prompt_tokens": -1, "completion_tokens": 4, "total_tokens": 3},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 999}])
def test_usage_and_response_id_gaps_never_become_zero(monkeypatch, usage):
    payload = _success()
    payload.pop("id")
    payload["usage"] = usage
    _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent()
    assert agent.act(_request()).action == 1
    receipt = agent.last_receipt
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["provider_response_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if not usage:
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    else:
        assert receipt["usage"]["reasoning_tokens"] is None
        if "completion_tokens" not in usage:
            assert receipt["usage"]["output_tokens"] is None
        else:
            assert receipt["usage"]["usage_validation_errors"]


def test_unverified_usage_and_cost_extensions_are_not_accounting_evidence(monkeypatch):
    payload = _success()
    payload["usage"].update(cost=0, cached_tokens=4, reasoning_tokens=2,
                            input_tokens=99, reasoning_included_in_output=True)
    _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent()
    agent.capabilities = replace(agent.capabilities, pricing={
        "input_cost_per_token": 1, "output_cost_per_token": 1, "source": "broker",
    })
    agent.act(_request())
    receipt = agent.last_receipt
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["cached_input_tokens"] is None
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("key", [None, "", "bad key", "bad\nkey", "ümlaut"])
def test_missing_and_invalid_credentials_fail_before_transport(monkeypatch, key):
    calls = _post(monkeypatch, httpx.Response(200, json=_success()))
    if key is None:
        monkeypatch.delenv(KEY)
    else:
        monkeypatch.setenv(KEY, key)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed" and calls == []


@pytest.mark.parametrize("provider", ["mistral", "mistral-ai", "mistral_ai"])
def test_cli_live_discovery_and_preflight_use_native_endpoint(monkeypatch, capsys, provider):
    post_calls = _post(monkeypatch, httpx.Response(200, json=_success()))
    discovery_calls = []

    def get(url, **kwargs):
        discovery_calls.append((url, kwargs))
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert main(["providers", "models", "--provider", provider, "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == [MODEL]
    assert main(["providers", "preflight", "--provider", provider, "--model", MODEL,
                 "--arena", "tic-tac-toe", "--live"]) == 0
    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks["account_model_visible"] and checks["response_parsing"]
    assert checks["usage_extraction"]
    assert len(post_calls) == 1 and len(discovery_calls) == 2
    assert all(url == MODELS_ENDPOINT for url, _ in discovery_calls)
    assert discovery_calls[0][1]["headers"]["Authorization"] == "Bearer fixture-secret-mistral"


@pytest.mark.parametrize("response,kind", [
    (httpx.Response(401, text=PRIVATE), "provider_auth_failed"),
    (httpx.Response(429, text=PRIVATE), "provider_rate_limited"),
    (httpx.Response(500, text=PRIVATE), "provider_unavailable"),
    (httpx.Response(200, json={"data": [{}]}), "provider_response_schema_mismatch"),
    (httpx.Response(200, text="{"), "provider_response_schema_mismatch"),
])
def test_discovery_failures_are_diagnostic_and_private(monkeypatch, response, kind):
    monkeypatch.setenv(KEY, "fixture-secret-mistral")
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **kw: response)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("mistral")
    assert failure.value.error_kind == kind and PRIVATE not in str(failure.value)


@pytest.mark.parametrize("failure", [False, True])
def test_cli_run_writes_valid_sanitized_native_attempt_artifacts(
    monkeypatch, tmp_path, capsys, failure,
):
    response = (httpx.Response(503, text=PRIVATE) if failure
                else httpx.Response(200, json=_success()))
    _post(monkeypatch, response)
    main(["run", "--arena", "tic-tac-toe", "--seat-agent", f"player_1=mistral:{MODEL}",
          "--seat-agent", "player_2=first-legal", "--max-turns", "1",
          "--output-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    artifact = Path(payload["artifact"])
    report = ArtifactValidator().validate_report(artifact)
    assert report.valid, report
    receipts = [json.loads(line) for line in
                read_member(artifact, "receipts/provider_receipts.jsonl").decode().splitlines()]
    assert len(receipts) == 1 and receipts[0]["provider"] == "mistral-ai"
    assert receipts[0]["outcome"] == ("provider_unavailable" if failure else "ok")
    assert "fixture-secret-mistral" not in json.dumps(receipts)
    assert PRIVATE not in json.dumps(receipts)
