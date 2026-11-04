"""Keyless, synthetic raw REST fixtures; provenance in docs/providers/DEEPSEEK.md."""
from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError, _normalize_usage
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.runner import RunConfig, Runner

FIXTURES = Path(__file__).parent / "fixtures/provider/deepseek"
SECRET = "offline-secret-never-persisted"


def fixture(name="success"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", SECRET)


def agent(**kwargs):
    return ModelProviderAgent("deepseek", "deepseek-flash", "DEEPSEEK_API_KEY", **kwargs)


def wire(monkeypatch, payload, status=200):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload, headers={"x-request-id": "req-offline"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_success_preserves_history_policy_usage_and_redaction(monkeypatch):
    calls = wire(monkeypatch, fixture())
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None, None)},
                      history=[{"turn_id": i, "action": i % 3} for i in range(80)])
    model = agent()
    response = model.act(request)
    receipt = model.last_receipt
    assert response.action == 1
    url, sent = calls[0]
    assert url == "https://api.deepseek.com/chat/completions"
    assert sent["headers"]["Authorization"] == f"Bearer {SECRET}"
    body = sent["json"]
    assert body["model"] == "deepseek-flash" and body["stream"] is False
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert all(str(i) in body["messages"][1]["content"] for i in range(80))
    assert json.loads(body["messages"][1]["content"].splitlines()[-1])["history"] == request.history
    assert set(body) == {"model", "messages", "stream"}
    assert receipt["provider"] == "deepseek"
    assert receipt["locked_model_id"] == "deepseek-flash"
    assert receipt["endpoint_kind"] == "deepseek_chat_completions"
    assert receipt["parser_version"] == "deepseek-chat-completions-raw-v1"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["cache_read_input_tokens"] == 8
    assert receipt["usage"]["reasoning_tokens"] == 2
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["usage_validation_errors"] == []
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt_index"] == 1
    assert SECRET not in json.dumps(receipt)
    assert "private-reasoning" not in json.dumps(receipt)


@pytest.mark.parametrize("provider", ["deepseek", "deep-seek", "deep_seek", " DEEPSEEK "])
def test_namespace_alias_end_to_end(monkeypatch, provider):
    calls = wire(monkeypatch, fixture())
    assert load_provider_registry().resolve(provider, "deepseek-flash").provider == "deepseek"
    preflight = provider_preflight(provider, "deepseek-flash", "tic-tac-toe", strict_catalogue=True)
    assert preflight["ok"] and preflight["checks"]["adapter_available"]
    model = _provider_agent(f"{provider}:deepseek-flash")
    assert model is not None and model.provider == "deepseek"
    assert model.act(_request()).action == 1
    assert model.last_receipt["provider"] == "deepseek" and len(calls) == 1
    assert _provider_agent(provider).model == "deepseek-flash"


def test_exact_unknown_model_and_missing_identity_usage_stay_unknown(monkeypatch):
    payload = fixture()
    payload.pop("model")
    payload.pop("usage")
    calls = wire(monkeypatch, payload)
    model = ModelProviderAgent("deep-seek", "exact/unknown:version", "DEEPSEEK_API_KEY")
    assert model.act(_request()).action == 1
    assert calls[0][1]["json"]["model"] == "exact/unknown:version"
    assert model.last_receipt["locked_model_id"] is None
    assert model.last_receipt["model_identity_source"] is None
    assert model.last_receipt["usage"] == {}
    assert model.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("mode,effort", [("auto", None), ("disabled", None),
                                        ("enabled", "max"), ("auto", "none")])
def test_explicit_controls_and_operator_limit(monkeypatch, mode, effort):
    calls = wire(monkeypatch, fixture())
    model = agent(max_output_tokens=100_000, temperature=0.3,
                  runtime_config=ProviderRuntimeConfig(reasoning=mode, reasoning_effort=effort))
    model.act(_request())
    body = calls[0][1]["json"]
    assert body["max_tokens"] == 100_000
    assert body.get("thinking") == ({"type": mode} if mode != "auto" else None)
    assert body.get("reasoning_effort") == effort
    assert ("temperature" in body) == (mode == "disabled")
    assert not {"tools", "response_format", "stop"} & set(body)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("insufficient_system_resource", "provider_interrupted"),
    ("aborted", "provider_interrupted"), (None, "provider_response_schema_mismatch"),
    ("unknown-private-reason", "provider_response_schema_mismatch"),
])
def test_finish_failures_never_accept_parseable_partial_actions(monkeypatch, reason, kind):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = reason
    calls = wire(monkeypatch, payload)
    model = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as caught:
        model.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert model.last_receipt["usage"]["total_tokens"] == 16
    assert model.last_receipt["outcome"] == kind
    assert "unknown-private-reason" not in json.dumps(model.last_receipt)


@pytest.mark.parametrize("patch", [
    {"choices": []}, {"object": "chat.completion.chunk"},
    {"choices": [{"index": 0, "finish_reason": "stop", "delta": {"content": '{"action":1}'}}]},
    {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "user",
                                                                            "content": "1"}}]},
])
def test_malformed_rest_envelopes(monkeypatch, patch):
    payload = {**fixture(), **patch}
    calls = wire(monkeypatch, payload)
    model = agent()
    with pytest.raises(ProviderCallError) as caught:
        model.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1
    assert model.last_receipt["status_code"] == 200
    assert model.last_receipt["request_id"] == "req-offline"


@pytest.mark.parametrize("content", [None, "", "   ", [{"type": "text", "text": "1"}]])
def test_missing_blank_or_non_string_content(monkeypatch, content):
    payload = fixture()
    payload["choices"][0]["message"]["content"] = content
    wire(monkeypatch, payload)
    with pytest.raises(ProviderCallError) as caught:
        agent().act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (402, "provider_request_rejected"),
    (403, "provider_permission_failed"), (422, "provider_request_rejected"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable")])
def test_http_failures_are_sanitized_without_ambiguous_replay(monkeypatch, status, kind):
    calls = wire(monkeypatch, {"error": {"message": SECRET}}, status)
    model = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        model.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert SECRET not in str(caught.value) + json.dumps(model.last_receipt)
    assert model.last_receipt["status_code"] == status
    assert model.last_receipt["usage"] == {}


@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("work", [False, True])
def test_only_definitive_rate_rejections_can_retry(monkeypatch, status, work):
    payload = fixture("rate_rejection")
    if work:
        payload.update(id="accepted-work", usage=fixture()["usage"])
    calls = wire(monkeypatch, payload, status)
    model = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        model.act(_request())
    assert caught.value.error_kind == "provider_rate_limited"
    assert len(calls) == (1 if work else 2)
    assert len(model.attempt_receipts) == len(calls)
    assert [r["attempt_index"] for r in model.attempt_receipts] == list(range(1, len(calls) + 1))
    assert "offline-private-error" not in json.dumps(model.attempt_receipts)


def test_default_retries_zero_and_http200_5xx_error(monkeypatch):
    calls = wire(monkeypatch, fixture("rate_rejection"))
    with pytest.raises(ProviderCallError):
        agent().act(_request())
    assert len(calls) == 1
    calls = wire(monkeypatch, {"error": {"code": 503, "message": SECRET}})
    with pytest.raises(ProviderCallError) as caught:
        agent(runtime_config=ProviderRuntimeConfig(max_retries=2)).act(_request())
    assert caught.value.error_kind == "provider_unavailable" and len(calls) == 1


@pytest.mark.parametrize("fault", ["timeout", "transport", "json", "duplicate"])
def test_transport_and_invalid_json_fail_closed(monkeypatch, fault):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if fault == "timeout":
            raise httpx.ReadTimeout(SECRET)
        if fault == "transport":
            raise httpx.ConnectError(SECRET)
        return httpx.Response(200, content=b'{"choices":' if fault == "json" else
                              b'{"id":"one","id":"two"}',
                              headers={"x-request-id": "req-broken"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    model = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        model.act(_request())
    assert len(calls) == 1
    assert SECRET not in str(caught.value) + json.dumps(model.last_receipt)
    if fault in {"json", "duplicate"}:
        assert model.last_receipt["status_code"] == 200
        assert model.last_receipt["request_id"] == "req-broken"


@pytest.mark.parametrize("patch", [
    {"prompt_cache_hit_tokens": True}, {"prompt_cache_miss_tokens": -1},
    {"prompt_cache_miss_tokens": 999}, {"prompt_tokens_details": {"cached_tokens": 1}},
    {"prompt_tokens_details": []}, {"completion_tokens_details": []},
    {"completion_tokens_details": {"reasoning_tokens": 99}}, {"total_tokens": 1},
    {"completion_tokens": "4"},
])
def test_malformed_usage_is_observed_without_zero_or_cost_invention(patch):
    usage = _normalize_usage("deepseek", {**fixture()["usage"], **patch})
    assert usage["usage_validation_errors"]


def test_usage_cache_missing_stays_unknown_and_reasoning_not_double_counted():
    usage = _normalize_usage("deepseek", {"prompt_tokens": 12, "completion_tokens": 4,
                          "completion_tokens_details": {"reasoning_tokens": 2}})
    assert usage["total_tokens"] == 16
    assert usage["cache_read_input_tokens"] is None
    assert usage["cache_write_input_tokens"] is None
    assert _normalize_usage("deepseek", usage)["total_tokens"] == 16


def test_discovery_and_live_preflight_use_native_alias_and_bearer(monkeypatch):
    calls = wire(monkeypatch, fixture())

    def get(url, **kwargs):
        assert url == "https://api.deepseek.com/models"
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": "deepseek-flash", "object": "model", "owned_by": "deepseek"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("deep_seek") == ["deepseek-flash"]
    result = provider_preflight("deep-seek", "deepseek-flash", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert result["checks"]["account_model_visible"] and len(calls) == 1


@pytest.mark.parametrize("value", ["", "invalid key", "non-ascii-☃"])
def test_missing_or_invalid_credentials_never_call(monkeypatch, value):
    monkeypatch.setenv("DEEPSEEK_API_KEY", value)
    calls = wire(monkeypatch, fixture())
    with pytest.raises(ProviderCallError) as caught:
        agent().act(_request())
    assert caught.value.error_kind == "provider_auth_failed" and calls == []
    assert value == "" or value not in str(caught.value)


def test_truncation_is_unscoreable_and_retains_billable_usage(tmp_path, monkeypatch):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = "length"
    wire(monkeypatch, payload)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", agents={"player_1": agent()},
                                   max_turns=1, output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring and result.trace_events == []
    assert "provider_output_truncated" in result.score.invalid_reason_codes
    rows = [json.loads(line) for line in
            (result.artifact_path / "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and not rows[0]["action_applied"]
    assert rows[0]["usage"]["total_tokens"] == 16


def test_missing_usage_artifacts_cannot_be_official(tmp_path, monkeypatch):
    payload = copy.deepcopy(fixture())
    payload.pop("usage")
    wire(monkeypatch, payload)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", agents={"player_1": agent()},
                                   max_turns=1, output_dir=tmp_path))
    report = ArtifactValidator().validate_report(result.artifact_path, profile="official_case")
    assert not report.valid and "usage_incomplete" in report.errors


def test_cli_preflight_and_run_alias_use_native_adapter(tmp_path, capsys, monkeypatch):
    calls = wire(monkeypatch, fixture())
    assert main(["providers", "preflight", "--provider", "deep-seek", "--model",
                 "deepseek-flash", "--strict-catalogue"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider"] == "deepseek" and result["ok"]
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "deep_seek:deepseek-flash",
                 "--max-turns", "1", "--output-dir", str(tmp_path)]) == 0
    capsys.readouterr()
    assert len(calls) == 1 and calls[0][1]["json"]["model"] == "deepseek-flash"


@pytest.mark.parametrize("payload,status", [({"data": [{"id": ""}]}, 200),
    ({"data": "broken"}, 200), ({"error": {"message": SECRET}}, 401)])
def test_discovery_failures_are_typed_and_sanitized(monkeypatch, payload, status):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **kw: httpx.Response(status, json=payload))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("deep-seek")
    assert caught.value.error_kind == ("provider_auth_failed" if status == 401 else
                                       "provider_response_schema_mismatch")
    assert SECRET not in str(caught.value)


def test_returned_alias_is_only_response_attestation(monkeypatch):
    payload = fixture()
    payload["model"] = "deepseek-flash"
    calls = wire(monkeypatch, payload)
    model = ModelProviderAgent("deepseek", "deepseek-v4-flash", "DEEPSEEK_API_KEY")
    model.act(_request())
    assert calls[0][1]["json"]["model"] == "deepseek-v4-flash"
    assert model.last_receipt["model"] == "deepseek-v4-flash"
    assert model.last_receipt["locked_model_id"] == "deepseek-flash"
    assert model.last_receipt["model_identity_source"] == "provider_response"
    assert model.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_gateway_keeps_native_path_and_identity_gap(monkeypatch):
    payload = fixture()
    payload.pop("model")
    calls = wire(monkeypatch, payload)
    model = agent(runtime_config=ProviderRuntimeConfig(gateway_base_url="https://gateway.test"))
    model.act(_request())
    assert calls[0][0] == "https://gateway.test/chat/completions"
    assert model.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("status", [200, 429, 503])
def test_actual_partial_body_custody_never_replays(monkeypatch, status):
    from eslams import http_io

    original_client = httpx.AsyncClient
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"id":"accepted-but-incomplete","usage":'
            raise httpx.ReadTimeout(SECRET)

    def respond(request):
        calls.append(1)
        return httpx.Response(status, stream=Stream(), request=request,
                              headers={"x-request-id": "partial-deepseek"})

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (
                original_client(transport=httpx.MockTransport(respond)) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                yield response

    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    model = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        model.act(_request())
    assert caught.value.error_kind == "provider_timeout" and calls == [1]
    assert model.last_receipt["status_code"] == status
    assert model.last_receipt["request_id"] == "partial-deepseek"
    assert model.last_receipt["usage"] == {}
    assert model.last_receipt.get("provider_response_id") is None
    assert SECRET not in json.dumps(model.last_receipt)


def test_whitespace_keepalive_is_accepted(monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **kw:
                        httpx.Response(200, content=b"\n\r\n " + json.dumps(fixture()).encode()))
    assert agent().act(_request()).action == 1
