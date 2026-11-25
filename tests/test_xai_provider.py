"""Keyless native xAI fixtures; every inference call is intercepted offline."""

import copy
import json
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.runner import RunConfig, Runner

SECRET = "xai-private-fixture-secret"
PRIVATE = "private-provider-prose"
FIXTURE = Path(__file__).parent / "fixtures/provider/xai_responses_success.json"


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", SECRET)
    payload = json.loads(FIXTURE.read_text())
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=copy.deepcopy(payload), headers={"x-request-id": "req_xai"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return payload, calls


def agent(provider="xai", model="grok-4.7", **runtime):
    return ModelProviderAgent(
        provider, model, "XAI_API_KEY", runtime_config=ProviderRuntimeConfig(**runtime),
    )


@pytest.mark.parametrize("provider", ["xai", "x-ai", "XAI", "X_AI", " x-ai "])
def test_alias_registry_cli_preflight_dispatch_and_receipt(wire, provider, capsys):
    assert load_provider_registry().resolve(provider, "grok-4.7").provider == "xai"
    a = _provider_agent(f"{provider}:grok-4.7")
    assert a.provider == "xai" and a.model == "grok-4.7"
    assert a.act(_request()).action == 1
    r = a.last_receipt
    assert r["provider"] == "xai" and r["model"] == "grok-4.7"
    assert r["endpoint_kind"] == "xai_responses"
    assert r["parser_version"] == "xai-responses-raw-v1"
    assert r["locked_model_id"] == "grok-4.7" and r["model_identity_source"] == "provider_response"
    assert r["request_id"] == "req_xai" and r["attempt"] == 1
    assert r["usage"]["input_tokens"] == 125 and r["usage"]["cached_input_tokens"] == 98
    assert r["usage"]["output_tokens"] == 48 and r["usage"]["total_tokens"] == 173
    assert r["estimated_cost"]["cost_usd"] == pytest.approx(0.0028896)
    assert r["rate_card_reference"]["sourceUri"] == "https://docs.x.ai/developers/cost-tracking"
    assert r["rate_card_reference"]["complete"] is True
    assert SECRET not in json.dumps(r) and "private-ciphertext-fixture" not in json.dumps(r)
    assert main(["providers", "preflight", "--provider", provider,
                 "--model", "grok-4.7", "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] and result["provider"] == "xai"
    assert len(wire[1]) == 1  # Configuration preflight never calls inference.


def test_payload_full_history_native_defaults_and_exact_model(wire):
    request = replace(
        _request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        history=[{"turn": i, "action": i % 3} for i in range(200)],
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )
    a = agent(model="grok-exact-requested-alias")
    assert a.act(request).action == 1
    url, kwargs = wire[1][0]
    assert url == "https://api.x.ai/v1/responses"
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
    body = kwargs["json"]
    assert body["model"] == "grok-exact-requested-alias"
    assert body["input"][0]["role"] == "system"
    prompt = json.loads(body["input"][1]["content"].splitlines()[-1])
    assert prompt["history"] == request.history
    assert prompt["action_schema"] == request.action_schema
    assert body["store"] is False and body["truncation"] == "disabled"
    assert set(body) == {"model", "input", "store", "truncation"}
    assert a.runtime_config.max_retries == 0
    assert kwargs["timeout"].read is None
    assert a.last_receipt["model"] == "grok-exact-requested-alias"
    assert a.last_receipt["locked_model_id"] == "grok-4.7"


def test_explicit_controls_forwarded_without_model_substitution(wire):
    a = agent(reasoning_effort="low", timeout_ms=20000)
    a.max_output_tokens = 123
    a.temperature = 0.2
    a.act(_request())
    body = wire[1][0][1]["json"]
    assert body["max_output_tokens"] == 123
    assert body["reasoning"] == {"effort": "low"} and body["temperature"] == 0.2


@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_unsupported_budget_control_fails_before_submission(wire, field):
    a = agent(**{field: 100})
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == "provider_request_rejected" and not wire[1]


@pytest.mark.parametrize("field", ["model", "usage"])
def test_missing_identity_and_usage_are_not_fabricated(wire, field):
    wire[0].pop(field)
    a = agent()
    assert a.act(_request()).action == 1
    r = a.last_receipt
    if field == "model":
        assert r["locked_model_id"] is None and r["model_identity_source"] is None
    else:
        assert r["usage"] == {} and r["usage_unavailable_reason"]
        assert r["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("ticks", [None, True, -1, "100", 1.2, 10**1000])
def test_missing_or_invalid_cost_stays_unknown(wire, ticks):
    wire[0]["usage"]["cost_in_usd_ticks"] = ticks
    a = agent(model="grok-4.5")  # Even a catalogue entry with prices must not estimate.
    a.act(_request())
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_explicit_zero_native_cost_is_distinct_from_absent_cost(wire):
    wire[0]["usage"]["cost_in_usd_ticks"] = 0
    a = agent()
    a.act(_request())
    assert a.last_receipt["estimated_cost"]["cost_usd"] == 0


def test_reasoning_accounting_preserves_current_uncertainty_and_legacy_exclusion(wire):
    usage = wire[0]["usage"]
    usage["output_tokens_details"]["reasoning_tokens"] = 5
    a = agent()
    a.act(_request())
    assert a.last_receipt["usage"]["reasoning_included_in_output"] is None
    assert "reasoning_inclusion_unknown" in a.last_receipt["usage"]["usage_validation_errors"]
    wire[0]["usage"] = {
        "prompt_tokens": 32, "completion_tokens": 9, "total_tokens": 151,
        "prompt_tokens_details": {"cached_tokens": 8},
        "completion_tokens_details": {"reasoning_tokens": 110},
    }
    a.act(_request())
    normalized = a.last_receipt["usage"]
    assert normalized["reasoning_included_in_output"] is False
    assert normalized["total_tokens"] == 151 and normalized["usage_validation_errors"] == []


@pytest.mark.parametrize("usage", [
    {"input_tokens": True, "output_tokens": 1},
    {"input_tokens": -1, "output_tokens": 1},
    {"input_tokens": "12", "output_tokens": 1},
    {"input_tokens": 12, "output_tokens": 4, "total_tokens": 99},
    {"input_tokens": 12, "output_tokens": 4, "input_tokens_details": {"cached_tokens": 13}},
])
def test_malformed_usage_is_flagged_and_never_priced(wire, usage):
    wire[0]["usage"] = usage
    a = agent()
    a.act(_request())
    assert a.last_receipt["usage"]["usage_validation_errors"]
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("status,reason,kind", [
    ("incomplete", "max_output_tokens", "provider_output_truncated"),
    ("incomplete", None, "provider_interrupted"),
    ("in_progress", None, "provider_pending"),
    ("cancelled", None, "provider_cancelled"),
    ("incomplete", "content_filter", "provider_refused"),
    ("nonsense", None, "provider_response_schema_mismatch"),
    (None, None, "provider_response_schema_mismatch"),
])
def test_noncomplete_responses_never_accept_parseable_action(wire, status, reason, kind):
    wire[0].update(status=status, incomplete_details={"reason": reason})
    a = agent(max_retries=2, action_repair_attempts=1)
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == kind and len(wire[1]) == 1
    assert a.last_receipt["usage"]["total_tokens"] == 173


def test_refusal_is_sanitized_and_usage_retained(wire):
    wire[0]["output"][1]["content"].append({"type": "refusal", "refusal": PRIVATE + SECRET})
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == "provider_refused" and len(wire[1]) == 1
    public = str(failure.value) + json.dumps(a.last_receipt)
    assert PRIVATE not in public and SECRET not in public
    assert a.last_receipt["finish_status"] == "refused"


@pytest.mark.parametrize("mutation", [
    {"object": "chat.completion"}, {"output": []}, {"output": [None]},
    {"incomplete_details": []}, {"error": {}},
    {"output": [{"type": "message", "role": "assistant",
                 "content": [{"type": "output_text", "text": '{"action": 1}'}]}]},
    {"output": [{"type": "function_call", "arguments": '{"action": 1}'}]},
    {"output": [{"type": "message", "role": "assistant", "status": "incomplete",
                 "content": [{"type": "output_text", "text": '{"action": 1}'}]}]},
    {"output": [{"type": "message", "role": "user",
                 "content": [{"type": "output_text", "text": '{"action": 1}'}]}]},
    {"output": [{"type": "message", "role": "assistant",
                 "content": [{"type": "output_text", "text": 7}]}]},
    {"output": [{"type": "message", "role": "assistant", "content": []}]},
    {"output": [{"type": "reasoning", "summary": [{"text": '{"action": 1}'}]}]},
])
def test_malformed_or_unsolicited_output_is_not_an_action(wire, mutation):
    wire[0].update(mutation)
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(wire[1]) == 1 and a.last_receipt["provider_response_id"]


@pytest.mark.parametrize("body", ['{"id":', '[]', '{"output": [], "output": []}',
                                   '{"usage":{"input_tokens":NaN}}'])
def test_invalid_json_and_truncated_body_has_sanitized_receipt(monkeypatch, wire, body):
    monkeypatch.setattr(
        "eslams.agents.bounded_post", lambda *a, **k: httpx.Response(200, text=body),
    )
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(a.attempt_receipts) == 1 and a.last_receipt["status_code"] == 200


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (422, "provider_request_rejected"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_failures_preserve_sanitized_attempt_without_default_retries(
    monkeypatch, wire, status, kind,
):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={"code": "not-found", "error": PRIVATE + SECRET},
                              headers={"Retry-After": "0", "x-request-id": "req_failure"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent()
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert failure.value.error_kind == kind and calls == [1]
    assert a.last_receipt["request_id"] == "req_failure"
    public = str(failure.value) + json.dumps(a.last_receipt)
    assert PRIVATE not in public and SECRET not in public
    assert a.last_receipt["usage"] == {}
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("body", [
    {"error": {"code": "rate_limit_exceeded", "message": PRIVATE}},
    {"status": "failed", "error": {"code": "server_error", "message": PRIVATE}},
    {"code": "not-found", "error": PRIVATE},
])
def test_http200_errors_never_parse_or_replay_accepted_work(wire, body):
    wire[0].update(body)
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError):
        a.act(_request())
    assert len(wire[1]) == 1 and a.last_receipt["usage"]["total_tokens"] == 173
    assert PRIVATE not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("failure_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_ambiguous_transport_failures_never_retry(monkeypatch, wire, failure_type):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise failure_type(PRIVATE + SECRET)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(max_retries=2)
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        a.act(_request())
    assert calls == [1] and len(a.attempt_receipts) == 1
    assert SECRET not in str(failure.value) + json.dumps(a.last_receipt)


def test_safe_429_retry_retains_each_physical_attempt(monkeypatch, wire):
    calls = []
    success = copy.deepcopy(wire[0])

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}},
                              headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(
                                  200, json=success)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(max_retries=1, retry_backoff_ms=0, retry_jitter=False)
    assert a.act(_request()).action == 1 and calls == [1, 1]
    assert [r["attempt"] for r in a.attempt_receipts] == [1, 2]
    assert [r["outcome"] for r in a.attempt_receipts] == ["provider_rate_limited", "ok"]


@pytest.mark.parametrize("status", [429, 503])
def test_error_observations_prevent_retry_and_remain_quarantined(monkeypatch, wire, status):
    payload = {"error": {"code": "rate_limit_exceeded"}, "usage": wire[0]["usage"],
               "id": "resp_accepted"}
    monkeypatch.setattr(
        "eslams.agents.bounded_post", lambda *a, **k: httpx.Response(status, json=payload),
    )
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError):
        a.act(_request())
    assert len(a.attempt_receipts) == 1
    assert a.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_discovery_and_live_preflight_alias_are_keyless_fixtures(monkeypatch, wire, capsys):
    discovery = []

    def get(url, **kwargs):
        discovery.append(url)
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "grok-4.7"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("X_AI") == ["grok-4.7"]
    assert main(["providers", "models", "--provider", "x-ai", "--live"]) == 0
    discovered = json.loads(capsys.readouterr().out)
    assert discovered["models"] == ["grok-4.7"] and discovered["provider"] == "xai"
    # Preflight's arena has a different legal-action set; return its first legal action.
    wire[0]["output"][1]["content"][0]["text"] = '{"action": 0}'
    result = provider_preflight("x-ai", "grok-4.7", "tic-tac-toe", live=True)
    assert result["checks"]["minimal_inference"] and result["checks"]["account_model_visible"]
    assert result["readiness"]["usage_complete"] is False
    assert result["ok"] and discovery == ["https://api.x.ai/v1/models"] * 3


def test_missing_or_invalid_credentials_do_not_submit(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("credentials must be checked before HTTP")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    for key in (None, "bad key\nprivate"):
        if key is None:
            monkeypatch.delenv("XAI_API_KEY", raising=False)
        else:
            monkeypatch.setenv("XAI_API_KEY", key)
        a = agent("x-ai")
        with pytest.raises(ProviderCallError) as failure:
            a.act(_request())
        assert failure.value.error_kind == "provider_auth_failed"
        assert "bad key" not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("status,body,kind", [
    (401, {"error": SECRET}, "provider_auth_failed"),
    (429, {"error": PRIVATE}, "provider_rate_limited"),
    (503, {"error": PRIVATE}, "provider_unavailable"),
    (200, {"data": [None]}, "provider_response_schema_mismatch"),
    (200, {"data": "bad"}, "provider_response_schema_mismatch"),
])
def test_live_discovery_errors_are_sanitized(monkeypatch, wire, status, body, kind):
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(status, json=body),
    )
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("x-ai")
    assert failure.value.error_kind == kind
    assert SECRET not in str(failure.value) and PRIVATE not in str(failure.value)


def test_registry_cli_and_direct_agent_aliases_preserve_model(wire, capsys):
    assert main(["providers", "models", "--provider", "x-ai"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "xai" and payload["models"]
    assert all(row["provider"] == "xai" for row in payload["models"])
    assert main(["models", "list", "--provider", "X_AI", "--json"]) == 0
    assert any(row["model"] == "grok-4.7" for row in json.loads(capsys.readouterr().out))
    a = agent("x-ai", "x-ai/grok-exact-model")
    assert a.act(_request()).action == 1
    assert wire[1][0][1]["json"]["model"] == "x-ai/grok-exact-model"
    assert a.last_receipt["provider"] == "xai"


def test_cli_run_alias_executes_native_provider_and_validates_artifact(
    wire, monkeypatch, tmp_path, capsys,
):
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        prompt = json.loads(kwargs["json"]["input"][1]["content"].splitlines()[-1])
        payload = copy.deepcopy(wire[0])
        payload["output"][1]["content"][0]["text"] = json.dumps({
            "action": prompt["legal_actions"][0],
        })
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "x-ai:grok-4.7",
                 "--output-dir", str(tmp_path), "--run-id", "native-xai-cli"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls and set(calls) == {"https://api.x.ai/v1/responses"}
    artifact = Path(result["artifact"])
    assert ArtifactValidator().validate(artifact) == []
    with ZipFile(artifact) as archive:
        receipts = [json.loads(line) for line in archive.read(
            "receipts/provider_receipts.jsonl").decode().splitlines()]
    assert receipts and all(row["provider"] == "xai" for row in receipts)


def test_truncated_run_artifact_has_no_applied_action_and_valid_receipt(wire, tmp_path):
    wire[0].update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, output_dir=tmp_path,
    ))
    assert not result.score.match_valid_for_scoring
    rows = [json.loads(line) for line in (
        result.artifact_path / "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["action_applied"] is False
    assert rows[0]["outcome"] == "provider_output_truncated"
    assert rows[0]["usage"]["total_tokens"] == 173
    assert ArtifactValidator().validate(result.artifact_path) == []
