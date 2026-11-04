"""Offline raw REST tests; provenance is in docs/providers/BYTEPLUS.md."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

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
from eslams.providers.byteplus import ALIASES, CHAT_ENDPOINT
from eslams.runner import RunConfig, Runner

MODEL = "dola-seed-2-1-turbo-260628"
PRIVATE = "private-provider-message-fixture"


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/provider/byteplus_chat_success.json")
                      .read_text())


def agent(**kwargs):
    return ModelProviderAgent("byteplus", MODEL, "BYTEPLUS_API_KEY", **kwargs)


def wire(monkeypatch, data=None, status=200, *, content=None):
    calls = []
    monkeypatch.setenv("BYTEPLUS_API_KEY", "byteplus-test-private-key")

    def post(url, *, headers, json: dict, timeout):
        calls.append((url, headers, json, timeout))
        return httpx.Response(
            status, content=content if content is not None else globals()["json"].dumps(
                fixture() if data is None else data
            ).encode(), headers={"x-request-id": "byteplus-request", "retry-after": "0"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_documented_wire_success_and_full_history_without_default_caps(monkeypatch):
    calls = wire(monkeypatch)
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None, None)},
                      history=[{"turn": turn, "public": f"history-{turn}"} for turn in range(60)])
    request.observation["private-to-request"] = PRIVATE
    result = agent().act(request)
    assert result.action == 1
    url, headers, payload, timeout = calls[0]
    assert url == CHAT_ENDPOINT
    assert headers == {"Authorization": "Bearer byteplus-test-private-key",
                       "Content-Type": "application/json"}
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == MODEL and payload["stream"] is False
    assert payload["messages"][0]["role"] == "system"
    assert all(f"history-{turn}" in payload["messages"][1]["content"] for turn in range(60))
    assert timeout.read is None
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "byteplus" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "byteplus_modelark_chat_completions"
    assert receipt["parser_version"] == "byteplus-modelark-chat-raw-v1"
    assert receipt["request_id"] == "byteplus-request"
    assert receipt["usage"]["input_tokens"] == 19
    assert receipt["usage"]["output_tokens"] == 9
    assert receipt["usage"]["reasoning_tokens"] == 4
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["total_tokens"] == 28
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(result.to_dict())
    for private in (PRIVATE, "private-reasoning-fixture", "private-encrypted-fixture",
                    "byteplus-test-private-key", "Authorization", "messages"):
        assert private not in public
    assert len(calls) == len(result.metadata["attempt_receipts"]) == 1


@pytest.mark.parametrize("alias", sorted(ALIASES | {"BYTEPLUS_MODELARK"}))
def test_aliases_reach_cli_preflight_registry_and_dispatch(monkeypatch, capsys, alias):
    calls = wire(monkeypatch)
    assert load_provider_registry().resolve(alias, MODEL).provider == "byteplus"
    parsed = _provider_agent(f"{alias}:{MODEL}")
    assert parsed.provider == "byteplus" and parsed.model == MODEL
    assert parsed.api_key_env == "BYTEPLUS_API_KEY"
    assert parsed.act(_request()).action == 1
    assert provider_preflight(alias, MODEL, "tic-tac-toe")["ok"]
    # --live is deliberately absent; a CLI configuration check makes no call.
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"]
    assert len(calls) == 1
    # Discovery is explicitly unavailable in this adapter, never guessed.
    assert provider_models_live(alias) is None


def test_no_implicit_model_or_cross_service_alias(monkeypatch):
    wire(monkeypatch)
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent("byteplus")
    for alias in ("bytedance", "volcengine", "ark"):
        assert _provider_agent(f"{alias}:{MODEL}") is None
        assert not provider_preflight(alias, MODEL, "tic-tac-toe")["ok"]
    monkeypatch.delenv("BYTEPLUS_API_KEY")
    monkeypatch.setenv("ARK_API_KEY", "other-service-private-key")
    with pytest.raises(ProviderCallError) as failure:
        agent().act(_request())
    assert failure.value.error_kind == "provider_auth_failed"


@pytest.mark.parametrize("reasoning", ["auto", "enabled", "disabled"])
def test_reasoning_is_explicit_and_independent_of_arena(monkeypatch, reasoning):
    calls = wire(monkeypatch)
    effort = None if reasoning == "disabled" else "high"
    runtime = ProviderRuntimeConfig(reasoning=reasoning, reasoning_effort=effort,
                                    timeout_ms=20_000)
    configured = agent(runtime_config=runtime, max_output_tokens=5000, temperature=0.7)
    configured.act(_request(arena_id="chess"))
    configured.act(_request(arena_id="tic-tac-toe"))
    for _, _, payload, _ in calls:
        assert payload.get("reasoning_effort") == effort
        assert payload["max_completion_tokens"] == 5000
        assert "max_tokens" not in payload
        assert payload["temperature"] == 0.7
        assert payload.get("thinking") == (None if reasoning == "auto" else {"type": reasoning})


@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_unsupported_controls_fail_before_submission(monkeypatch, field):
    calls = wire(monkeypatch)
    with pytest.raises(ProviderCallError, match="no request submitted"):
        agent(runtime_config=ProviderRuntimeConfig(**{field: 100})).act(_request())
    assert calls == []


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_errors_preserve_receipts_and_never_retry(monkeypatch, status, kind):
    calls = wire(monkeypatch, {"error": {"code": "RateLimitExceeded.EndpointRPMExceeded",
                 "type": "TooManyRequests", "message": PRIVATE}}, status)
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1
    receipt = configured.last_receipt
    assert receipt["status_code"] == status and receipt["request_id"] == "byteplus-request"
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert PRIVATE not in str(failure.value) + json.dumps(receipt)


@pytest.mark.parametrize(("code", "kind"), [
    ("InputTextSensitiveContentDetected", "provider_refused"),
    ("OutputTextSensitiveContentDetected", "provider_refused"),
    ("AuthenticationError", "provider_auth_failed"),
    ("InvalidEndpointOrModel.NotFound", "provider_unavailable"),
])
def test_body_error_is_not_an_action(monkeypatch, code, kind):
    data = fixture()
    data["error"] = {"code": code, "message": PRIVATE}
    calls = wire(monkeypatch, data)
    configured = agent()
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert configured.last_receipt["usage"]["total_tokens"] == 28
    assert PRIVATE not in json.dumps(configured.last_receipt)


@pytest.mark.parametrize(("finish", "kind"), [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"),
    ("unknown-private", "provider_response_schema_mismatch"),
])
def test_partial_or_refused_legal_looking_output_is_rejected(monkeypatch, finish, kind):
    data = fixture()
    data["choices"][0]["finish_reason"] = finish
    calls = wire(monkeypatch, data)
    configured = agent(runtime_config=ProviderRuntimeConfig(
        max_retries=2, action_repair_attempts=2,
    ))
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert configured.last_receipt["usage"]["total_tokens"] == 28


@pytest.mark.parametrize("content", [b"not-json", b"[]", b'{"id":1,"id":2}'])
def test_malformed_raw_body(monkeypatch, content):
    calls = wire(monkeypatch, content=content)
    configured = agent()
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert configured.last_receipt["request_id"] == "byteplus-request" and len(calls) == 1


@pytest.mark.parametrize("mode", ["absent", "endpoint", "resolved", "fallback", "different"])
def test_identity_is_attested_and_fallback_rejected(monkeypatch, mode):
    data = fixture()
    configured = agent()
    if mode in {"endpoint", "resolved"}:
        configured.model = "ep-account-owned-deployment"
    if mode == "endpoint":
        data["model"] = configured.model
    if mode == "absent":
        data.pop("model")
    if mode == "fallback":
        data["service_status"] = {"model_fallback": {"fallback_triggered": True}}
    if mode == "different":
        data["model"] = "another-model"
    wire(monkeypatch, data)
    if mode in {"fallback", "different"}:
        with pytest.raises(ProviderCallError, match="fallback or a different model"):
            configured.act(_request())
    else:
        configured.act(_request())
    assert configured.last_receipt["locked_model_id"] == (
        None if mode in {"absent", "endpoint"} else data["model"]
    )


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 19},
    {"prompt_tokens": True, "completion_tokens": -1},
    {"prompt_tokens": 19, "completion_tokens": 9, "total_tokens": 999}])
def test_missing_or_invalid_accounting_is_never_filled_in(monkeypatch, usage):
    data = fixture()
    data["usage"] = usage
    wire(monkeypatch, data)
    configured = agent()
    configured.act(_request())
    receipt = configured.last_receipt
    if not usage:
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    elif usage.get("total_tokens") == 999:
        assert "provider_total_tokens_inconsistent" in receipt["usage"]["usage_validation_errors"]
    else:
        assert receipt["usage"].get("output_tokens") is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_ambiguity_never_replays(monkeypatch, failure):
    calls = wire(monkeypatch)

    def post(*args, **kwargs):
        calls.append(1)
        raise failure(PRIVATE)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        configured.act(_request())
    assert len(calls) == 1 and PRIVATE not in str(caught.value)
    assert configured.last_receipt["usage"] == {}


@pytest.mark.parametrize("fault", ["choices", "role", "object", "refusal", "service", "fallback"])
def test_strict_envelope_and_private_refusal(monkeypatch, fault):
    data = fixture()
    if fault == "choices":
        data["choices"] = []
    elif fault == "role":
        data["choices"][0]["message"]["role"] = "user"
    elif fault == "object":
        data["object"] = "chat.completion.chunk"
    elif fault == "refusal":
        data["choices"][0]["message"]["refusal"] = PRIVATE
    elif fault == "service":
        data["service_status"] = []
    else:
        data["service_status"] = {"model_fallback": {"fallback_triggered": "false"}}
    calls = wire(monkeypatch, data)
    configured = agent()
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == (
        "provider_refused" if fault == "refusal" else "provider_response_schema_mismatch"
    )
    assert len(calls) == 1 and PRIVATE not in json.dumps(configured.last_receipt)


@pytest.mark.parametrize("code", ["InputTextSensitiveContentDetected",
                                  "OutputTextSensitiveContentDetected.PolicyViolation"])
def test_http400_moderation_is_refusal(monkeypatch, code):
    wire(monkeypatch, {"error": {"code": code, "message": PRIVATE}}, 400)
    configured = agent()
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == "provider_refused"
    assert configured.last_receipt["outcome"] == "provider_refused"
    assert PRIVATE not in str(failure.value) + json.dumps(configured.last_receipt)


def test_429_with_work_observations_keeps_unknown_cost_and_identity(monkeypatch):
    data = {"model": MODEL, "id": "response-observed", "usage": fixture()["usage"],
            "cost": 0.4, "error": {"code": 429, "message": PRIVATE}}
    calls = wire(monkeypatch, data, 429)
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=4))
    with pytest.raises(ProviderCallError):
        configured.act(_request())
    receipt = configured.last_receipt
    assert len(calls) == 1
    assert receipt["usage"]["total_tokens"] == 28
    assert receipt["provider_response_id"] == "response-observed"
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"


@pytest.mark.parametrize("fault", ["429", "refusal", "truncated", "missing-usage"])
def test_runner_artifact_has_no_scored_failure_or_private_wire_data(monkeypatch, tmp_path, fault):
    data = fixture()
    status = 200
    if fault == "429":
        data = {"error": {"code": "RateLimitExceeded.EndpointRPMExceeded", "message": PRIVATE}}
        status = 429
    elif fault == "refusal":
        data["choices"][0]["finish_reason"] = "content_filter"
    elif fault == "truncated":
        data["choices"][0]["finish_reason"] = "length"
    else:
        data.pop("usage")
    wire(monkeypatch, data, status)
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1,
        execution_profile="official_eval", output_dir=tmp_path,
    ))
    if fault != "missing-usage":
        assert result.score.match_valid_for_scoring is False
        assert result.trace_events == []
    else:
        assert result.score.usage_complete is False
        report = ArtifactValidator().validate_report(result.artifact_path, profile="official_case")
        assert not report.valid and "usage_incomplete" in report.errors
    for path in tmp_path.rglob("*.json*"):
        if path.is_file():
            contents = path.read_text()
            for private in (PRIVATE, "private-reasoning-fixture", "private-encrypted-fixture",
                            "byteplus-test-private-key", '"Authorization"'):
                assert private not in contents


def test_invalid_action_has_no_default_repair_and_no_fallback(monkeypatch):
    data = fixture()
    data["choices"][0]["message"]["content"] = "no legal action provided"
    calls = wire(monkeypatch, data)
    configured = agent()
    with pytest.raises(ProviderCallError) as failure:
        configured.act(_request())
    assert failure.value.error_kind == "action_response_unparseable"
    assert len(calls) == len(configured.attempt_receipts) == 1
