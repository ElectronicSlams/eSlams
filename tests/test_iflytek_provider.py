"""Spark's documented raw HTTP envelopes, with synthetic private text and IDs."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.iflytek import V1_ENDPOINT, V1_MODELS, X2_ENDPOINT
from eslams.runner import RunConfig, Runner

FIXTURES = Path(__file__).parent / "fixtures" / "provider"
ALIASES = ["iflytek", "spark", "iflytek-spark", "xfyun", "SPARK"]


def wire(version="x2"):
    return json.loads((FIXTURES / f"iflytek_{version}_success.json").read_text())


def install(monkeypatch, body=None, *, status=200, raw=None, failure=None):
    monkeypatch.setenv("IFLYTEK_API_PASSWORD", "synthetic-password")
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if failure is not None:
            raise failure
        options = {"content": raw} if raw is not None else {"json": body}
        return httpx.Response(status, **options, headers={"Retry-After": "2",
                              "x-request-id": "synthetic-request"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def native(provider="iflytek", model="spark-x", **kwargs):
    return ModelProviderAgent(provider, model, "IFLYTEK_API_PASSWORD", **kwargs)


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_reach_cli_preflight_and_native_dispatch(monkeypatch, capsys, alias):
    calls = install(monkeypatch, wire())
    agent = _provider_agent(f"{alias}:spark-x")
    assert agent is not None and agent.provider == "iflytek"
    assert agent.model == "spark-x" and agent.api_key_env == "IFLYTEK_API_PASSWORD"
    assert native(alias).act(request()).action == 0
    result = provider_preflight(alias, "spark-x", "connect-four")
    assert result["ok"] and result["checks"]["adapter_available"]
    assert len(calls) == 1  # configuration-only preflight is offline
    assert provider_models_live(alias) is None
    assert main(["providers", "preflight", "--provider", alias, "--model", "spark-x",
                 "--arena", "connect-four"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    live = provider_preflight(alias, "spark-x", "connect-four", live=True)
    assert live["ok"] and live["checks"]["minimal_inference"]
    assert live["checks"]["account_model_visible"] is None
    assert len(calls) == 2 and all(url == X2_ENDPOINT for url, _ in calls)


@pytest.mark.parametrize("model", ["spark-x", *sorted(V1_MODELS)])
def test_exact_model_endpoint_and_documented_success(monkeypatch, model):
    calls = install(monkeypatch, wire("x2" if model == "spark-x" else "v1"))
    agent = native(model=model)
    response = agent.act(request())
    assert response.action == 0
    url, kwargs = calls[0]
    assert url == (X2_ENDPOINT if model == "spark-x" else V1_ENDPOINT)
    payload = kwargs["json"]
    assert payload["model"] == model and payload["stream"] is False
    assert kwargs["headers"]["Authorization"] == "Bearer synthetic-password"
    assert "max_tokens" not in payload and "thinking" not in payload
    assert "temperature" not in payload and "provider" not in payload
    assert kwargs["timeout"].read is None
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    receipt = agent.last_receipt
    assert receipt["provider"] == "iflytek" and receipt["model"] == model
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["endpoint_kind"] == "iflytek_chat_completions"
    assert receipt["provider_response_id"].startswith("cha-synthetic-")
    assert receipt["usage"]["total_tokens_source"] == "provider"
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(response.to_dict())
    assert "synthetic-password" not in public and "synthetic private reasoning" not in public


def test_full_history_and_explicit_controls(monkeypatch):
    calls = install(monkeypatch, wire())
    history = [{"turn": index, "action": index % 3} for index in range(200)]
    agent = native(max_output_tokens=12345, temperature=1.2,
                   runtime_config=ProviderRuntimeConfig(reasoning="enabled"))
    agent.act(replace(request(), history=history))
    payload = calls[0][1]["json"]
    assert payload["max_tokens"] == 12345 and payload["temperature"] == 1.2
    assert payload["thinking"] == {"type": "enabled"}
    assert all(json.dumps(item, sort_keys=True) in payload["messages"][0]["content"]
               for item in history)
    assert payload["tools"] == [{"type": "web_search", "web_search": {"enable": False}}]


@pytest.mark.parametrize("reasoning", ["auto", "disabled", "enabled"])
def test_reasoning_mode_is_never_selected_by_arena(monkeypatch, reasoning):
    calls = install(monkeypatch, wire())
    native(runtime_config=ProviderRuntimeConfig(reasoning=reasoning)).act(request())
    payload = calls[0][1]["json"]
    assert payload.get("thinking") == (None if reasoning == "auto" else {"type": reasoning})


@pytest.mark.parametrize("config", [
    {"reasoning_effort": "high"}, {"reasoning_budget_tokens": 2048},
    {"gemini_thinking_budget": 1},
])
def test_unsupported_controls_fail_without_call(monkeypatch, config):
    calls = install(monkeypatch, wire())
    with pytest.raises(ProviderCallError, match="thinking mode"):
        native(runtime_config=ProviderRuntimeConfig(**config)).act(request())
    assert calls == []


@pytest.mark.parametrize("model", ["x1", "x1.5", "Spark-X2", "spark-x ", "unknown"])
def test_unverified_model_pairs_do_not_remap_or_fallback(monkeypatch, model):
    calls = install(monkeypatch, wire())
    with pytest.raises(ProviderCallError, match="model/endpoint"):
        native(model=model).act(request())
    assert calls == []


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_errors_are_private_and_never_replayed(monkeypatch, status, kind):
    body = {"error": {"message": "synthetic private prompt Bearer synthetic-password",
                      "type": "api_error", "param": None, "code": None}}
    calls = install(monkeypatch, body, status=status)
    agent = native(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as caught:
        agent.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    receipt = agent.last_receipt
    assert receipt["status_code"] == status and receipt["usage"] == {}
    assert receipt["locked_model_id"] is None
    assert "synthetic private" not in json.dumps(receipt) + str(caught.value)
    assert "synthetic-password" not in json.dumps(receipt) + str(caught.value)
    if status == 429:
        assert caught.value.retry_after_seconds == 2


@pytest.mark.parametrize("status", [200, 500])
@pytest.mark.parametrize("code,kind", [
    (10013, "provider_refused"), (10014, "provider_refused"), (10019, "provider_refused"),
    (10007, "provider_rate_limited"), (11201, "provider_rate_limited"),
    (11202, "provider_rate_limited"), (11203, "provider_rate_limited"),
    (11200, "provider_permission_failed"), (10907, "provider_request_rejected"),
    (99999, "provider_unavailable"),
])
def test_business_errors_override_legal_looking_text(monkeypatch, status, code, kind):
    body = wire()
    body.update(code=code, message="synthetic private rejection")
    calls = install(monkeypatch, body, status=status)
    agent = native(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        agent.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1 and agent.last_receipt["outcome"] == kind
    assert agent.last_receipt["usage"]["total_tokens"] == 1183
    assert "synthetic private" not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_interrupted"), ("unexpected", "provider_interrupted"),
])
def test_incomplete_and_refusal_finish_never_accept_action(monkeypatch, reason, kind):
    body = wire()
    body["choices"][0]["finish_reason"] = reason
    calls = install(monkeypatch, body)
    agent = native()
    with pytest.raises(ProviderCallError) as caught:
        agent.act(request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert agent.last_receipt["usage"]["output_tokens"] == 1175


@pytest.mark.parametrize("change", [
    {"choices": []}, {"choices": [{"message": {"role": "assistant",
      "reasoning_content": '{"action": 0}'}}]}, {"code": False}, {"code": "0"},
    {"status": "incomplete"}, {"choices": [{"delta": {"content": '{"action": 0}'}}]},
])
def test_malformed_or_reasoning_only_output_fails_closed(monkeypatch, change):
    body = {**wire(), **change}
    install(monkeypatch, body)
    with pytest.raises(ProviderCallError):
        native().act(request())


@pytest.mark.parametrize("raw", [b"<html>private</html>", b'{"code":0,"code":0}', b"[]"])
def test_bad_json_preserves_failure_receipt(monkeypatch, raw):
    calls = install(monkeypatch, raw=raw)
    agent = native()
    with pytest.raises(ProviderCallError) as caught:
        agent.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1 and agent.last_receipt["usage"] == {}


@pytest.mark.parametrize("failure,kind", [
    (httpx.ReadTimeout("private transport"), "provider_timeout"),
    (httpx.ConnectError("private transport"), "provider_transport_error"),
])
def test_transport_failures_never_replay(monkeypatch, failure, kind):
    calls = install(monkeypatch, failure=failure)
    agent = native(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)):
        agent.act(request())
    assert len(calls) == 1 and agent.last_receipt["outcome"] == kind
    assert "private transport" not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 8},
    {"prompt_tokens": 8, "completion_tokens": 1175},
    {"prompt_tokens": True, "completion_tokens": -1, "total_tokens": "1183"}])
def test_missing_accounting_is_never_invented(monkeypatch, usage):
    body = wire()
    body["usage"] = usage
    install(monkeypatch, body)
    agent = native()
    assert agent.act(request()).action == 0
    assert agent.last_receipt["usage"].get("total_tokens") is None
    assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("status", [200, 429])
def test_untrusted_error_identity_and_cost_remain_quarantined(monkeypatch, status):
    body = wire()
    body.update(code=11202, model="unverified-model", cost=100)
    install(monkeypatch, body, status=status)
    agent = native()
    with pytest.raises(ProviderCallError):
        agent.act(request())
    receipt = agent.last_receipt
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"


def test_missing_or_invalid_credentials_never_call(monkeypatch):
    calls = install(monkeypatch, wire())
    for value in [None, "bad\npassword"]:
        if value is None:
            monkeypatch.delenv("IFLYTEK_API_PASSWORD")
        else:
            monkeypatch.setenv("IFLYTEK_API_PASSWORD", value)
        with pytest.raises(ProviderCallError) as caught:
            native().act(request())
        assert caught.value.error_kind == "provider_auth_failed"
    assert calls == []


def test_artifact_preserves_attempts_and_private_reasoning_boundary(monkeypatch, tmp_path):
    calls = install(monkeypatch, wire())
    result = Runner().run(RunConfig("connect-four", agent_1=native(), agent_2=native(),
                                   max_turns=2, output_dir=tmp_path, archive=False))
    rows = [json.loads(line) for line in (result.expanded_path /
            "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(calls) == len(rows) == 2
    assert all(row["provider"] == "iflytek" and row["attempt_index"] == 1 for row in rows)
    assert all(row["locked_model_id"] is None and not row["usage_complete"] for row in rows)
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert b"synthetic-password" not in content
            assert b"synthetic private reasoning" not in content


@pytest.mark.parametrize("temperature", [0, -1, 2.1, float("inf"), True])
def test_x2_invalid_sampling_fails_without_call(monkeypatch, temperature):
    calls = install(monkeypatch, wire())
    with pytest.raises(ProviderCallError, match="temperature"):
        native(temperature=temperature).act(request())
    assert calls == []


def test_v1_rejects_explicit_thinking_and_lite_omits_search(monkeypatch):
    calls = install(monkeypatch, wire("v1"))
    with pytest.raises(ProviderCallError, match="thinking control"):
        native(model="lite", runtime_config=ProviderRuntimeConfig(reasoning="enabled")).act(
            request())
    assert calls == []
    native(model="lite", temperature=0).act(request())
    assert "tools" not in calls[0][1]["json"]


@pytest.mark.parametrize("code", [10013, 11202, 11200, 10907])
def test_nested_business_errors_are_classified(monkeypatch, code):
    body = {"error": {"code": code, "message": "private", "type": "api_error"}}
    calls = install(monkeypatch, body)
    agent = native()
    with pytest.raises(ProviderCallError):
        agent.act(request())
    assert agent.last_receipt["outcome"] != "ok" and len(calls) == 1


def test_usage_inconsistency_is_reported_and_never_prices(monkeypatch):
    body = wire()
    body["usage"].update(total_tokens=1, search_prompt_tokens=12)
    install(monkeypatch, body)
    agent = native()
    agent.act(request())
    usage = agent.last_receipt["usage"]
    assert usage["total_tokens"] == 1
    assert usage["usage_validation_errors"] == [
        "provider_total_tokens_inconsistent", "search_prompt_tokens_accounting_unsupported"]
    assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
