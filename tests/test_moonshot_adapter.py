"""Keyless Moonshot raw-wire and native routing regressions."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request as legacy_request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry, moonshot
from eslams.runner import RunConfig, Runner

FIXTURE = Path(__file__).parent / "fixtures/provider/moonshot_chat_completions_success.json"


def _request(**changes):
    request = replace(legacy_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)})
    return replace(request, **changes)


def wire():
    return json.loads(FIXTURE.read_text())


def agent(*, provider="moonshot-ai", model=moonshot.DEFAULT_MODEL, runtime=None, **kwargs):
    return ModelProviderAgent(provider, model, moonshot.API_KEY_ENV,
                              runtime_config=runtime, **kwargs)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(moonshot.API_KEY_ENV, "synthetic-moonshot-credential-canary")


def post(monkeypatch, payload=None, status=200, **headers):
    calls = []
    def send(url, **kwargs):
        calls.append((url, copy.deepcopy(kwargs)))
        return httpx.Response(status, json=payload if payload is not None else wire(),
                              headers={"x-request-id": "req-kimi-fixture", **headers})
    monkeypatch.setattr("eslams.agents.bounded_post", send)
    return calls


@pytest.mark.parametrize("alias", sorted(moonshot.ALIASES) + ["MOONSHOT_AI"])
def test_aliases_agree_across_registry_cli_preflight_discovery_and_dispatch(alias, monkeypatch):
    assert load_provider_registry().resolve(alias, "kimi-k3").provider == moonshot.PROVIDER_ID
    native = _provider_agent(alias + ":kimi-k3")
    assert native.provider == moonshot.PROVIDER_ID and native.model == "kimi-k3"
    assert native.api_key_env == moonshot.API_KEY_ENV
    assert _provider_agent(alias).model == moonshot.DEFAULT_MODEL
    ready = provider_preflight(alias, "kimi-k3", "tic-tac-toe")
    assert ready["ok"] and ready["checks"]["adapter_available"]
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer synthetic-moonshot-credential-canary"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "kimi-k3"}]})
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == ["kimi-k3"]
    assert seen == [moonshot.models_endpoint(alias)]
    calls = post(monkeypatch)
    assert native.act(_request()).action == 1
    assert calls[0][0] == moonshot.chat_endpoint(alias)
    assert calls[0][1]["json"]["model"] == "kimi-k3"


def test_wire_history_no_framework_caps_usage_identity_and_privacy(monkeypatch):
    calls = post(monkeypatch)
    history = [{"turn_id": i, "public_event": f"history-{i}"} for i in range(30)]
    native = agent()
    response = native.act(_request(history=history))
    url, sent = calls[0]
    assert url == moonshot.CHAT_COMPLETIONS_ENDPOINT
    payload = sent["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["stream"] is False
    assert sent["headers"] == {"Authorization": "Bearer synthetic-moonshot-credential-canary",
                                "Content-Type": "application/json"}
    assert sent["timeout"].read is None
    assert json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"] == history
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] == "kimi-k3.1-pro"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "moonshot_chat_completions"
    assert receipt["parser_version"] == "moonshot-chat-completions-raw-v1"
    assert receipt["request_id"] == "req-kimi-fixture"
    usage = receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (373, 112, 485)
    assert usage["cache_write_input_tokens"] == 256
    assert usage["cache_read_input_tokens"] is None
    assert usage["reasoning_tokens"] == 90 and usage["reasoning_included_in_output"] is True
    assert usage["usage_validation_errors"] == []
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(receipt)
    assert "credential-canary" not in public and "private-reasoning-canary" not in public
    assert "history-0" not in public and '"messages"' not in public


@pytest.mark.parametrize(("model", "runtime", "controls"), [
    ("kimi-k3", ProviderRuntimeConfig(reasoning_effort="max"), {"reasoning_effort": "max"}),
    ("kimi-k3.1-pro", ProviderRuntimeConfig(reasoning_effort="low"), {"reasoning_effort": "low"}),
    ("kimi-k3.1-pro-highspeed", ProviderRuntimeConfig(reasoning_effort="high"),
     {"reasoning_effort": "high"}),
    ("kimi-k2.7-code", ProviderRuntimeConfig(reasoning="enabled"), {}),
    ("kimi-k2.6", ProviderRuntimeConfig(reasoning="enabled"),
     {"thinking": {"type": "enabled", "keep": "all"}}),
    ("kimi-k2.6", ProviderRuntimeConfig(reasoning="disabled"), {"thinking": {"type": "disabled"}}),
])
def test_explicit_controls(model, runtime, controls, monkeypatch):
    calls = post(monkeypatch)
    agent(model=model, runtime=runtime, max_output_tokens=99999).act(_request())
    sent = calls[0][1]["json"]
    assert sent["max_tokens"] == 99999
    assert {k: v for k, v in sent.items() if k in {"thinking", "reasoning_effort"}} == controls
    assert "temperature" not in sent and "top_p" not in sent


@pytest.mark.parametrize(("model", "runtime"), [
    ("kimi-k3", ProviderRuntimeConfig(reasoning="disabled")),
    ("kimi-k2.7-code", ProviderRuntimeConfig(reasoning="disabled")),
    ("kimi-k2.6", ProviderRuntimeConfig(reasoning_effort="high")),
    ("kimi-k3", ProviderRuntimeConfig(reasoning_effort="medium")),
    ("kimi-k3", ProviderRuntimeConfig(reasoning_budget_tokens=100)),
    ("new-unverified-model", ProviderRuntimeConfig(reasoning="enabled")),
])
def test_unsupported_controls_fail_without_inference(model, runtime, monkeypatch):
    calls = post(monkeypatch)
    with pytest.raises(ProviderCallError) as error:
        agent(model=model, runtime=runtime).act(_request())
    assert error.value.error_kind == "provider_request_rejected" and calls == []


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"), (504, "provider_unavailable"),
])
def test_http_error_receipts_are_private_and_never_fallback(status, kind, monkeypatch):
    calls = post(monkeypatch, {"error": {"type": "invalid_request_error",
                                          "message": "private-error-canary"}}, status)
    native = agent(runtime=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == kind and len(calls) == 1
    receipt = native.last_receipt
    assert receipt["status_code"] == status and receipt["usage"] == {}
    assert receipt["locked_model_id"] is None
    assert "private-error-canary" not in json.dumps(receipt) + str(error.value)


@pytest.mark.parametrize("status", [200, 400])
def test_documented_content_filter_error_is_refusal(status, monkeypatch):
    post(monkeypatch, {"error": {"type": "content_filter", "message": "private-refusal"}}, status)
    native = agent()
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == "provider_refused"
    assert native.last_receipt["outcome"] == "provider_refused"
    assert "private-refusal" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize(("finish", "kind"), [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"), (None, "provider_response_schema_mismatch"),
    ("unknown-private-finish", "provider_response_schema_mismatch"),
])
def test_noncomplete_legal_looking_output_is_never_accepted(finish, kind, monkeypatch):
    payload = wire()
    payload["choices"][0]["finish_reason"] = finish
    calls = post(monkeypatch, payload)
    native = agent(runtime=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == kind and len(calls) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 485


@pytest.mark.parametrize("mutation", ["missing-usage", "partial-usage", "no-model", "cached",
                                     "no-reasoning-count", "invalid-usage"])
def test_incomplete_identity_usage_and_cost_are_never_invented(mutation, monkeypatch):
    payload = wire()
    if mutation == "missing-usage":
        del payload["usage"]
    elif mutation == "partial-usage":
        payload["usage"] = {"prompt_tokens": 373}
    elif mutation == "no-model":
        del payload["model"]
    elif mutation == "cached":
        payload["usage"]["prompt_tokens_details"]["cached_tokens"] = 32
    elif mutation == "no-reasoning-count":
        del payload["usage"]["completion_tokens_details"]
    else:
        payload["usage"]["completion_tokens"] = True
    post(monkeypatch, payload)
    native = agent()
    native.act(_request())
    receipt = native.last_receipt
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if mutation == "missing-usage":
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    elif mutation == "partial-usage":
        assert receipt["usage"]["output_tokens"] is None
        assert receipt["usage"]["total_tokens"] is None
    elif mutation == "no-model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    elif mutation == "cached":
        assert receipt["usage"]["cache_read_input_tokens"] == 32
        assert receipt["usage"]["cached_input_tokens"] == 288
        assert receipt["usage"]["total_tokens"] == 485
    elif mutation == "no-reasoning-count":
        assert receipt["usage"]["reasoning_tokens"] is None
    else:
        assert receipt["usage"]["usage_validation_errors"]


@pytest.mark.parametrize("body", [b"{broken", b"[]", b'{"id":1,"id":2}',
                                 b'{"output_text":"{\\"action\\":1}"}'])
def test_malformed_wire_is_rejected_with_receipt(body, monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, content=body))
    native = agent()
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert native.last_receipt["request_id"] is None


@pytest.mark.parametrize("fault", [httpx.ReadTimeout, httpx.ConnectError])
def test_ambiguous_transport_is_not_replayed(fault, monkeypatch):
    calls = []
    def send(*args, **kwargs):
        calls.append(1)
        raise fault("private-transport-canary")
    monkeypatch.setattr("eslams.agents.bounded_post", send)
    native = agent(runtime=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as error:
        native.act(_request())
    assert calls == [1] and "private-transport-canary" not in str(error.value)
    assert native.last_receipt["usage"] == {}


@pytest.mark.parametrize("error_type", ["rate_limit_reached_error", "engine_overloaded_error"])
@pytest.mark.parametrize("observed_work", [False, True])
def test_documented_429_only_retries_definitive_rejection(observed_work, error_type, monkeypatch):
    calls, waits = [], []
    rejection = {"error": {"type": error_type, "message": "redacted"}}
    if observed_work:
        rejection["usage"] = wire()["usage"]
    def send(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(429 if len(calls) == 1 else 200,
                              json=rejection if len(calls) == 1 else wire(),
                              headers={"Retry-After": "2"})
    monkeypatch.setattr("eslams.agents.bounded_post", send)
    monkeypatch.setattr("eslams.agents._sleep_before_retry",
                        lambda *a, **k: waits.append(k["retry_after_seconds"]))
    native = agent(runtime=ProviderRuntimeConfig(max_retries=1))
    if observed_work:
        with pytest.raises(ProviderCallError):
            native.act(_request())
        assert len(calls) == 1 and waits == []
        assert native.last_receipt["usage"]["total_tokens"] == 485
        assert native.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    else:
        assert native.act(_request()).action == 1
        assert calls[0] == calls[1] and waits == [2.0]
        assert [r["attempt_index"] for r in native.attempt_receipts] == [1, 2]
        assert [r["outcome"] for r in native.attempt_receipts] == ["provider_rate_limited", "ok"]


def test_live_preflight_is_mocked_and_cli_offline_is_keyless(monkeypatch, capsys):
    calls = post(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        httpx.Response(200, json={"data": [{"id": moonshot.DEFAULT_MODEL}]}))
    ready = provider_preflight("moonshotai-cn", moonshot.DEFAULT_MODEL, "tic-tac-toe", live=True)
    assert ready["ok"] and ready["checks"]["usage_extraction"]
    assert calls[0][0] == moonshot.CHINA_CHAT_COMPLETIONS_ENDPOINT
    monkeypatch.delenv(moonshot.API_KEY_ENV)
    assert main(["providers", "preflight", "--provider", "kimi", "--model", moonshot.DEFAULT_MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"]
    assert len(calls) == 1


@pytest.mark.parametrize("finish", ["content_filter", "length", "stop"])
def test_runner_excludes_failure_and_artifacts_exclude_private_wire(finish, tmp_path, monkeypatch):
    payload = wire()
    payload["choices"][0]["finish_reason"] = finish
    payload["private_extension"] = "raw-private-response-canary"
    post(monkeypatch, payload)
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1,
        output_dir=tmp_path, execution_profile="official_eval",
    ))
    assert not result.score.match_valid_for_scoring
    if finish == "content_filter":
        assert "provider_refused" in result.score.invalid_reason_codes
    elif finish == "length":
        assert "provider_output_truncated" in result.score.invalid_reason_codes
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    if finish != "stop":
        assert result.trace_events == []
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*.json*"):
        text = path.read_text()
        for secret in ("credential-canary", "private-reasoning-canary",
                       "raw-private-response-canary"):
            assert secret not in text, path


@pytest.mark.parametrize("payload", [
    {"error": {"type": "exceeded_current_quota_error", "message": "redacted"}},
    {"error": {"type": "rate_limit_reached_error", "code": "server_error"}},
    {"error": {"type": "rate_limit_reached_error"}, "id": "observed-generation"},
    {"error": {"type": "rate_limit_reached_error"}, "cost": 0.01},
    {"error": {"type": "rate_limit_reached_error", "unknown": "private-extension"}},
])
def test_quota_and_ambiguous_429_are_not_replayed(payload, monkeypatch):
    calls = post(monkeypatch, payload, 429)
    native = agent(runtime=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == "provider_rate_limited" and len(calls) == 1
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("credential", [None, "bad key", "bad\nkey"])
def test_missing_and_invalid_credentials_never_submit(credential, monkeypatch):
    if credential is None:
        monkeypatch.delenv(moonshot.API_KEY_ENV)
    else:
        monkeypatch.setenv(moonshot.API_KEY_ENV, credential)
    calls = post(monkeypatch)
    native = agent()
    with pytest.raises(ProviderCallError) as error:
        native.act(_request())
    assert error.value.error_kind == "provider_auth_failed" and calls == []
    assert native.last_receipt["usage"] == {}


def test_explicit_temperature_timeout_gateway_and_unknown_model_forward_unchanged(monkeypatch):
    calls = post(monkeypatch)
    native = agent(model="future-exact-model", temperature=0.75, max_output_tokens=123456,
                   runtime=ProviderRuntimeConfig(
                       timeout_ms=15000, read_timeout_ms=9000,
                       gateway_base_url="https://operator-gateway.example",
                       gateway_mode="generic_base_url",
                   ))
    native.act(_request())
    url, sent = calls[0]
    assert url == "https://operator-gateway.example/v1/chat/completions"
    assert sent["json"]["model"] == "future-exact-model"
    assert sent["json"]["temperature"] == 0.75
    assert sent["json"]["max_tokens"] == 123456
    assert sent["timeout"].read <= 9
    assert "provider" not in sent["json"]


@pytest.mark.parametrize("mutation", ["reasoning-only", "no-choices", "multiple-choices",
                                     "stream-chunk", "refusal", "tools"])
def test_raw_response_boundaries(mutation, monkeypatch):
    payload = wire()
    if mutation == "reasoning-only":
        payload["choices"][0]["message"]["content"] = None
        payload["choices"][0]["message"]["reasoning_content"] = '{"action": 1}'
    elif mutation == "no-choices":
        payload["choices"] = []
    elif mutation == "multiple-choices":
        payload["choices"] *= 2
    elif mutation == "stream-chunk":
        payload["object"] = "chat.completion.chunk"
    elif mutation == "refusal":
        payload["choices"][0]["message"]["refusal"] = "private-refusal-canary"
    else:
        payload["choices"][0]["message"]["tool_calls"] = [{"id": "forbidden-tool"}]
    calls = post(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(_request())
    assert len(calls) == 1 and native.last_receipt["outcome"] != "ok"
    assert native.last_receipt["usage"]["total_tokens"] == 485
    assert "private-refusal-canary" not in json.dumps(native.last_receipt)
