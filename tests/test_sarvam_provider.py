"""Deterministic raw-wire Sarvam tests. Provenance: docs/providers/SARVAM.md."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry

FIXTURE = Path(__file__).parent / "fixtures/provider/sarvam_chat_completions_success.json"
SECRET = "fixture-sarvam-credential-never-persist"


def wire():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="sarvam-wire", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="sarvam-test", version="fixture"), active_player="player_1",
        observation={"private_prompt": "private-prompt-never-publish"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn": turn, "action": turn % 3} for turn in range(150)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(**kwargs):
    return ModelProviderAgent(
        provider="sarvam-ai", model="sarvam-105b", api_key_env="SARVAM_API_KEY", **kwargs,
    )


def mock_wire(monkeypatch, payload=None, *, status=200, headers=None):
    monkeypatch.setenv("SARVAM_API_KEY", SECRET)
    sent = []

    def post(url, **kwargs):
        sent.append((url, kwargs))
        return httpx.Response(status, json=wire() if payload is None else payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return sent


@pytest.mark.parametrize("prefix", ["sarvam", "sarvam-ai", "sarvam_ai", "SARVAM"])
@pytest.mark.parametrize("model", ["sarvam-105b", "sarvam-105b-conversations", "exact:unknown/id"])
def test_aliases_cli_registry_preflight_and_dispatch(monkeypatch, prefix, model):
    sent = mock_wire(monkeypatch)
    selected = _provider_agent(f"{prefix}:{model}")
    assert selected.provider == "sarvam-ai"
    assert selected.model == model
    assert selected.api_key_env == "SARVAM_API_KEY"
    assert selected.act(request()).action == 1
    assert sent[0][1]["json"]["model"] == model
    checks = provider_preflight(prefix, model, "tic-tac-toe")["checks"]
    assert checks["adapter_available"] is True
    assert checks["account_model_visible"] is None
    assert len(sent) == 1  # offline preflight never submits inference
    assert provider_models_live(prefix) is None
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(prefix)


def test_documented_success_native_defaults_full_history_and_privacy(monkeypatch):
    sent = mock_wire(monkeypatch)
    selected = agent()
    result = selected.act(request())
    url, call = sent[0]
    assert url == "https://api.sarvam.ai/v1/chat/completions"
    assert call["headers"] == {
        "api-subscription-key": SECRET, "Content-Type": "application/json",
    }
    assert set(call["json"]) == {"model", "messages"}
    assert call["json"]["messages"][0]["role"] == "system"
    prompt = call["json"]["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request().history
    assert call["timeout"].read is None
    receipt = result.metadata["provider_receipt"]
    assert result.action == 1
    assert receipt["provider"] == "sarvam-ai"
    assert receipt["model"] == "sarvam-105b"
    assert receipt["locked_model_id"] == "sarvam-105b"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["parser_version"] == "sarvam-chat-completions-raw-v1"
    assert receipt["endpoint_kind"] == "sarvam_chat_completions_v1"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["cached_input_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt"] == 1
    public = json.dumps(result.to_dict())
    for private in (SECRET, "private-prompt-never-publish", "private-reasoning-fixture"):
        assert private not in public


@pytest.mark.parametrize("mode,effort,expected", [
    ("auto", None, "absent"), ("enabled", None, "absent"),
    ("auto", "low", "low"), ("enabled", "medium", "medium"),
    ("auto", "high", "high"), ("auto", "max", "max"),
    ("disabled", None, None),
])
def test_explicit_reasoning_wire_including_null(monkeypatch, mode, effort, expected):
    sent = mock_wire(monkeypatch)
    selected = agent(runtime_config=ProviderRuntimeConfig(reasoning=mode, reasoning_effort=effort))
    selected.act(request())
    payload = sent[0][1]["json"]
    assert payload.get("reasoning_effort", "absent") == expected
    assert "max_tokens" not in payload


@pytest.mark.parametrize("budget", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_foreign_reasoning_controls_rejected_before_submission(monkeypatch, budget):
    sent = mock_wire(monkeypatch)
    selected = agent(runtime_config=ProviderRuntimeConfig(**{budget: 2048}))
    with pytest.raises(ProviderCallError, match="thinking budget"):
        selected.act(request())
    assert sent == []


def test_operator_output_temperature_and_time_controls(monkeypatch):
    sent = mock_wire(monkeypatch)
    selected = agent(
        max_output_tokens=9000, temperature=0.7,
        runtime_config=ProviderRuntimeConfig(timeout_ms=12345, read_timeout_ms=12000),
    )
    selected.act(request())
    call = sent[0][1]
    assert call["json"]["max_tokens"] == 9000
    assert call["json"]["temperature"] == 0.7
    assert call["timeout"].read <= 12


@pytest.mark.parametrize("status,code,kind", [
    (400, "invalid_request_error", "provider_request_rejected"),
    (401, "invalid_api_key_error", "provider_auth_failed"),
    (402, "insufficient_quota_error", "provider_request_rejected"),
    (403, "invalid_api_key_error", "provider_auth_failed"),
    (403, "forbidden", "provider_permission_failed"),
    (404, "not_found_error", "provider_unavailable"),
    (413, "invalid_request_error", "provider_request_rejected"),
    (422, "unprocessable_entity_error", "provider_request_rejected"),
    (429, "rate_limit_exceeded_error", "provider_rate_limited"),
    (429, "model_rate_limit_exceeded_error", "provider_rate_limited"),
    (429, "seat_budget_exhausted_error", "provider_rate_limited"),
    (500, "internal_server_error", "provider_unavailable"),
    (502, "model_call_failed", "provider_unavailable"),
    (503, "model_overloaded", "provider_unavailable"),
])
def test_documented_http_errors_one_attempt_no_private_body(monkeypatch, status, code, kind):
    sent = mock_wire(monkeypatch, {"error": {"code": code, "message": SECRET}}, status=status,
                     headers={"Retry-After": "3", "x-request-id": "sarvam-request"})
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert len(sent) == 1
    assert caught.value.error_kind == kind
    assert selected.last_receipt["status_code"] == status
    assert caught.value.retry_after_seconds == 3
    assert selected.last_receipt["retry_after_ms"] == 3000
    assert selected.last_receipt["request_id"] == "sarvam-request"
    assert selected.last_receipt["locked_model_id"] is None
    assert selected.last_receipt["usage"] == {}
    assert SECRET not in str(caught.value) + json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("finish,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("function_call", "provider_response_schema_mismatch"),
    ("unknown", "provider_response_schema_mismatch"), (None, "provider_response_schema_mismatch"),
])
def test_noncomplete_response_never_accepts_legal_looking_content(monkeypatch, finish, kind):
    payload = wire()
    payload["choices"][0]["finish_reason"] = finish
    sent = mock_wire(monkeypatch, payload)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert len(sent) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16


def test_structured_refusal_discards_private_prose(monkeypatch):
    payload = wire()
    payload["choices"][0]["message"]["refusal"] = SECRET
    mock_wire(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_refused"
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("change", ["no-content", "no-choices", "role", "multiple", "finish-type"])
def test_malformed_wire_cannot_use_private_reasoning_as_action(monkeypatch, change):
    payload = wire()
    payload["choices"][0]["message"]["reasoning_content"] = '{"action": 1}'
    if change == "no-content":
        payload["choices"][0]["message"]["content"] = None
    elif change == "no-choices":
        payload["choices"] = []
    elif change == "role":
        payload["choices"][0]["message"]["role"] = "user"
    elif change == "multiple":
        payload["choices"].append(copy.deepcopy(payload["choices"][0]))
    else:
        payload["choices"][0]["finish_reason"] = {"secret": SECRET}
    mock_wire(monkeypatch, payload)
    with pytest.raises(ProviderCallError) as caught:
        agent().act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("field", ["model", "usage", "total_tokens"])
def test_missing_identity_and_accounting_are_not_invented(monkeypatch, field):
    payload = wire()
    if field == "total_tokens":
        del payload["usage"][field]
    else:
        del payload[field]
    mock_wire(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    if field == "model":
        assert receipt["locked_model_id"] is None
        assert receipt["model_identity_source"] is None
    elif field == "usage":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    else:
        assert receipt["usage"]["total_tokens"] is None
        assert receipt["usage"]["total_tokens_source"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_documented_usage_details_and_invalid_counters(monkeypatch):
    payload = wire()
    payload["usage"].update(prompt_tokens_details={"cached_tokens": 5},
                            completion_tokens_details={"reasoning_tokens": 2})
    mock_wire(monkeypatch, payload)
    usage = agent().act(request()).metadata["provider_receipt"]["usage"]
    assert usage["cached_input_tokens"] == 5
    assert usage["reasoning_tokens"] == 2
    payload["usage"]["completion_tokens"] = -1
    mock_wire(monkeypatch, payload)
    usage = agent().act(request()).metadata["provider_receipt"]["usage"]
    assert usage["output_tokens"] is None
    assert usage["usage_validation_errors"]


@pytest.mark.parametrize("code,retries", [
    ("rate_limit_exceeded_error", 1), ("model_rate_limit_exceeded_error", 1),
    ("seat_budget_exhausted_error", 0), ("unknown", 0), ({"bad": "code"}, 0),
])
def test_only_explicit_safe_rate_retry_uses_core_attempt_ledger(monkeypatch, code, retries):
    monkeypatch.setenv("SARVAM_API_KEY", SECRET)
    calls = []
    sleeps = []

    def post(url, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": code, "message": "rate"}},
                                  headers={"Retry-After": "2"})
        return httpx.Response(200, json=wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation", sleeps.append)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_jitter=False))
    if retries:
        assert selected.act(request()).action == 1
        assert sleeps == [2]
        assert [item["attempt"] for item in selected.attempt_receipts] == [1, 2]
    else:
        with pytest.raises(ProviderCallError):
            selected.act(request())
    assert len(calls) == retries + 1


@pytest.mark.parametrize("fault", ["timeout", "transport", "invalid-json", "duplicate-json"])
def test_transport_and_json_faults_are_not_replayed(monkeypatch, fault):
    monkeypatch.setenv("SARVAM_API_KEY", SECRET)
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        if fault == "timeout":
            raise httpx.ReadTimeout(SECRET)
        if fault == "transport":
            raise httpx.ConnectError(SECRET)
        body = b"not-json" if fault == "invalid-json" else b'{"model":"a","model":"b"}'
        return httpx.Response(200, content=body)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        selected.act(request())
    assert len(calls) == 1
    assert SECRET not in str(caught.value) + json.dumps(selected.attempt_receipts)


def test_http200_error_quarantines_identity_and_usage(monkeypatch):
    payload = {"error": {"code": "invalid_api_key_error", "message": SECRET},
               "model": "untrusted-id", "usage": {"prompt_tokens": 100}}
    mock_wire(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_auth_failed"
    assert selected.last_receipt["locked_model_id"] is None
    assert selected.last_receipt["usage"]["input_tokens"] == 100
    assert selected.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert selected.last_receipt["pricing_provenance"]["usage_observation_status"] == (
        "normalized_unverified"
    )
    assert SECRET not in json.dumps(selected.attempt_receipts)


def test_offline_cli_preflight_and_registry_metadata(monkeypatch, capsys):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert main(["providers", "preflight", "--provider", "sarvam", "--model", "sarvam-105b",
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True
    assert result["checks"]["api_key_configured"] is False
    registry = load_provider_registry()
    assert registry.resolve("sarvam", "sarvam-105b").context_window == 128000
    assert registry.resolve("sarvam-ai", "sarvam-105b-conversations").context_window == 32000
    assert registry.resolve("sarvam", "sarvam-105b").max_output_tokens is None
    assert registry.resolve("sarvam", "sarvam-30b").available_from_api is False


@pytest.mark.parametrize("extra", [
    {"usage": {"prompt_tokens": 12}}, {"id": "work-started"},
    {"model": "unexpected"}, {"private_extension": SECRET},
])
def test_rate_rejection_with_work_or_unknown_extensions_is_never_replayed(monkeypatch, extra):
    payload = {"error": {"code": "rate_limit_exceeded_error", "message": "busy"}, **extra}
    sent = mock_wire(monkeypatch, payload, status=429)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert len(sent) == 1
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("total", [None, -1, True, "16"])
def test_invalid_total_is_not_reconstructed(monkeypatch, total):
    payload = wire()
    payload["usage"]["total_tokens"] = total
    mock_wire(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["usage"]["total_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_illegal_action_has_no_implicit_repair_or_fallback(monkeypatch):
    payload = wire()
    payload["choices"][0]["message"]["content"] = '{"action": 500}'
    sent = mock_wire(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "action_response_unparseable"
    assert len(sent) == 1


@pytest.mark.parametrize("key", [None, "contains whitespace"])
def test_missing_or_invalid_key_never_submits(monkeypatch, key):
    sent = mock_wire(monkeypatch)
    if key is None:
        monkeypatch.delenv("SARVAM_API_KEY")
    else:
        monkeypatch.setenv("SARVAM_API_KEY", key)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_auth_failed"
    assert sent == []


@pytest.mark.parametrize("prefix", ["sarvam", "sarvam-ai", "sarvam_ai"])
def test_live_preflight_uses_native_dispatch_with_mocked_inference(monkeypatch, prefix):
    sent = mock_wire(monkeypatch)
    result = provider_preflight(prefix, "sarvam-105b", "tic-tac-toe", live=True)
    assert result["ok"]
    assert result["checks"]["minimal_inference"]
    assert result["checks"]["response_parsing"]
    assert result["checks"]["usage_extraction"]
    assert result["checks"]["account_model_visible"] is None
    assert len(sent) == 1


def test_cli_run_dispatches_native_adapter_and_public_artifacts_are_private_safe(
    monkeypatch, tmp_path, capsys,
):
    monkeypatch.setenv("SARVAM_API_KEY", SECRET)
    models = []

    def post(url, **kwargs):
        payload = kwargs["json"]
        models.append(payload["model"])
        prompt = json.loads(payload["messages"][1]["content"].splitlines()[-1])
        response = wire()
        response["choices"][0]["message"]["content"] = json.dumps(
            {"action": prompt["legal_actions"][0]}
        )
        return httpx.Response(200, json=response)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", "sarvam:sarvam-105b",
        "--opponent", "first-legal", "--output-dir", str(tmp_path), "--run-id", "sarvam-cli",
    ]) == 0
    assert models and set(models) == {"sarvam-105b"}
    output = capsys.readouterr().out
    payload = json.loads(output[output.index("{"):])
    public = Path(payload["expanded_artifact"]) / "public"
    for path in public.rglob("*.json*"):
        text = path.read_text(encoding="utf-8")
        assert SECRET not in text
        assert "private-reasoning-fixture" not in text
