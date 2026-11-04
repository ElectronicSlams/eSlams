"""Synthetic wire fixtures following the pinned official SenseNova API guide."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers import load_provider_registry
from eslams.providers.sensenova import API_KEY_ENV, CHAT_COMPLETIONS_ENDPOINT

ALIASES = ("sensetime", "sensenova", "sense-nova", "sense-time", "SenseNova")
SECRET = "fixture-secret-never-persisted"
DEFAULT_MODEL = "sensenova-6.8-flash-lite"  # Fixture model, never an adapter default.


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_sensenova", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="sensenova-wire", version="fixture-v1"),
        active_player="player_1", observation={"board": []}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn_id": i, "public_event": f"event-{i}"} for i in range(300)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def success():
    path = Path(__file__).parent / "fixtures/provider/sensenova_chat_completions_success.json"
    return json.loads(path.read_text())


def agent(provider="sensetime", **kwargs):
    return ModelProviderAgent(provider=provider, model=DEFAULT_MODEL, api_key_env=API_KEY_ENV,
                              **kwargs)


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    def install(payload, status=200, headers=None, raw=None):
        def post(url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(status, content=raw if raw is not None else json.dumps(payload),
                                  headers=headers)
        monkeypatch.setattr("eslams.agents.bounded_post", post)
        return calls

    return install


@pytest.mark.parametrize("provider", ALIASES)
def test_aliases_cli_preflight_registry_and_dispatch(provider, wire, capsys):
    calls = wire(success())
    configured = _provider_agent(f"{provider}:{DEFAULT_MODEL}")
    assert configured.provider == "sensetime"
    assert configured.model == DEFAULT_MODEL
    assert load_provider_registry().resolve(provider, DEFAULT_MODEL).provider == "sensetime"
    assert main(["providers", "preflight", "--provider", provider,
                 "--model", DEFAULT_MODEL, "--arena", "tic-tac-toe"]) == 0
    offline = json.loads(capsys.readouterr().out)
    assert offline["checks"]["adapter_available"] is True
    assert offline["readiness"]["inference"] == "not_attempted"
    assert not calls
    response = configured.act(request())
    assert response.action == 1
    receipt = response.metadata["provider_receipt"]
    assert receipt["provider"] == "sensetime"
    assert receipt["model"] == receipt["locked_model_id"] == DEFAULT_MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["provider_response_id"] == "sensenova-fixture-response"
    assert receipt["request_id"] == "sensenova-fixture-request"
    assert receipt["endpoint_kind"] == "sensenova_chat_completions"
    assert receipt["parser_version"] == "sensenova-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(calls) == 1
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {"Authorization": f"Bearer {SECRET}",
                               "Content-Type": "application/json"}
    assert set(sent["json"]) == {"model", "messages", "stream"}
    assert sent["json"]["model"] == DEFAULT_MODEL
    assert sent["json"]["stream"] is False
    assert sent["timeout"].read is None
    prompt = json.loads(sent["json"]["messages"][1]["content"].splitlines()[-1])
    assert prompt["history"] == request().history
    public = json.dumps(response.to_dict()) + json.dumps(configured.attempt_receipts)
    assert SECRET not in public
    assert "PRIVATE_REASONING_DO_NOT_PERSIST" not in public


def test_default_and_exact_operator_model(wire):
    calls = wire({**success(), "model": "operator-Exact:Model"})
    selected = _provider_agent("sensenova:operator-Exact:Model")
    selected.act(request())
    assert calls[0][1]["json"]["model"] == "operator-Exact:Model"


def test_explicit_output_temperature_and_timeout(wire):
    calls = wire(success())
    selected = agent(max_output_tokens=12345, temperature=0.7,
                     runtime_config=ProviderRuntimeConfig(timeout_ms=54321))
    selected.act(request())
    sent = calls[0][1]
    assert sent["json"]["max_tokens"] == 12345
    assert sent["json"]["temperature"] == 0.7
    assert sent["timeout"].read <= 54.321


@pytest.mark.parametrize("control", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 5000}, {"gemini_thinking_budget": 2000},
])
@pytest.mark.parametrize("live", [False, True])
def test_unsupported_reasoning_controls_fail_without_call(wire, control, live):
    calls = wire(success())
    selected = agent(runtime_config=ProviderRuntimeConfig(**control))
    with pytest.raises(ProviderCallError, match="no verified reasoning control"):
        selected.act(request())
    assert not calls
    assert selected.last_receipt["outcome"] == "provider_request_rejected"
    preflight = provider_preflight("sensenova", DEFAULT_MODEL, "tic-tac-toe",
                                   runtime_config=ProviderRuntimeConfig(**control), live=live)
    assert preflight["ok"] is False
    assert preflight["readiness"]["configuration_ready"] is False
    assert preflight["error"]["error_class"] == "provider_request_rejected"
    assert not calls


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("future_finish", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"), (12, "provider_response_schema_mismatch"),
])
def test_semantic_failure_rejects_legal_looking_text(wire, reason, kind):
    payload = success()
    payload["choices"][0]["finish_reason"] = reason
    calls = wire(payload)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["outcome"] == kind


def test_refusal_is_private_and_never_repaired(wire):
    payload = success()
    payload["choices"][0]["message"]["refusal"] = SECRET
    calls = wire(payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_refused"
    assert SECRET not in str(caught.value) + json.dumps(selected.attempt_receipts)
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", [
    "empty_choices", "multiple_choices", "missing_message", "reasoning_only", "wrong_role",
    "content_array", "legacy_data", "tool_call", "wrong_model",
])
def test_malformed_or_substituted_output_is_rejected(wire, mutation):
    payload = success()
    message = payload["choices"][0]["message"]
    if mutation == "empty_choices":
        payload["choices"] = []
    elif mutation == "multiple_choices":
        payload["choices"] *= 2
    elif mutation == "missing_message":
        del payload["choices"][0]["message"]
    elif mutation == "reasoning_only":
        del message["content"]
    elif mutation == "wrong_role":
        message["role"] = "user"
    elif mutation == "content_array":
        message["content"] = [{"type": "text", "text": '{"action": 1}'}]
    elif mutation == "legacy_data":
        payload = {"data": payload}
    elif mutation == "tool_call":
        message["tool_calls"] = [{"id": "call-1"}]
    else:
        payload["model"] = "substituted-model"
    calls = wire(payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [b'{"choices": [], "choices": []}', b'not-json', b'[]'])
def test_strict_json_failure_keeps_header_evidence(wire, raw):
    wire(None, raw=raw, headers={"x-request-id": "wire-request"})
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert selected.last_receipt["status_code"] == 200
    assert selected.last_receipt["request_id"] == "wire-request"


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
])
def test_http_errors_zero_default_retries_private_receipts(wire, status, kind):
    calls = wire({"error": {"type": "authentication_error", "message": SECRET}}, status=status,
                 headers={"x-request-id": "wire-error", "retry-after": "3"})
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1
    receipt = selected.last_receipt
    assert receipt["status_code"] == status
    assert receipt["request_id"] == "wire-error"
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in str(caught.value) + json.dumps(receipt)


def test_http_200_error_and_usage_are_preserved(wire):
    payload = success()
    payload["error"] = {"type": "not_found_error", "code": "5", "message": SECRET}
    calls = wire(payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_unavailable"
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1
    assert SECRET not in str(caught.value) + json.dumps(selected.last_receipt)


def test_explicit_retry_only_for_definitive_429(wire):
    calls = wire({"error": {"code": 429, "message": SECRET}}, status=429,
                 headers={"retry-after": "0"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.retry_permitted is True
    assert len(calls) == 2
    assert len(selected.attempt_receipts) == 2


def test_usage_bearing_429_never_replayed(wire):
    payload = {"error": {"code": 429}, "usage": success()["usage"], "id": "work-started"}
    calls = wire(payload, status=429)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert len(calls) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"


def test_missing_identity_and_usage_are_never_fabricated(wire):
    payload = success()
    for name in ("model", "usage", "id", "request_id"):
        del payload[name]
    wire(payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None
    assert receipt["request_id"] is None
    assert receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": 12}, {"prompt_tokens": True, "completion_tokens": -1},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 999},
])
def test_incomplete_or_invalid_accounting_stays_visible(wire, usage):
    wire({**success(), "usage": usage})
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if usage.get("prompt_tokens") is True:
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    elif usage.get("total_tokens") == 999:
        assert receipt["usage"]["usage_validation_errors"]
    else:
        assert receipt["usage"]["output_tokens"] is None
        assert receipt["usage"]["total_tokens"] is None


def test_no_discovery_is_invented_live_preflight_is_explicit(wire):
    calls = wire(success())
    assert provider_models_live("sensenova") is None
    assert not calls
    result = provider_preflight("sensenova", DEFAULT_MODEL, "tic-tac-toe", live=True)
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["minimal_inference"] is True
    assert result["checks"]["usage_extraction"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("key", [None, "bad key", "bad\nkey"])
def test_missing_or_invalid_key_never_submits(monkeypatch, wire, key):
    calls = wire(success())
    if key is None:
        monkeypatch.delenv(API_KEY_ENV)
    else:
        monkeypatch.setenv(API_KEY_ENV, key)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_auth_failed"
    assert not calls


@pytest.mark.parametrize("provider", ALIASES)
@pytest.mark.parametrize("model", ["", " ", "\t"])
def test_empty_models_rejected_in_cli_preflight_and_transport(provider, model, wire):
    calls = wire(success())
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(f"{provider}:{model}")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(provider)
    result = provider_preflight(provider, model, "tic-tac-toe")
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_request_rejected"
    selected = ModelProviderAgent(provider=provider, model=model, api_key_env=API_KEY_ENV)
    with pytest.raises(ProviderCallError, match="explicit nonblank model"):
        selected.act(request())
    assert not calls


@pytest.mark.parametrize("secret_env", [API_KEY_ENV, "SENSENOVA_ACCESS_KEY_SECRET"])
@pytest.mark.parametrize("path", ["success", "error", "malformed", "partial"])
def test_reflected_credentials_removed_from_all_receipt_paths(monkeypatch, wire, secret_env, path):
    secondary = "secondary-super-secret"
    monkeypatch.setenv("SENSENOVA_ACCESS_KEY_SECRET", secondary)
    echo = SECRET if secret_env == API_KEY_ENV else secondary
    payload = success()
    payload["id"] = f"response-{echo}"
    payload["request_id"] = f"request-{echo}"
    payload["usage"]["untrusted_note"] = echo
    headers = {"x-request-id": f"request-{echo}", "cf-aig-request-id": f"gateway-{echo}"}
    if path == "success":
        wire(payload, headers=headers)
    elif path == "error":
        wire({**payload, "error": {"code": 429, "message": echo}}, status=429, headers=headers)
    elif path == "malformed":
        wire(None, raw=b'not-json', headers=headers)
    else:
        from eslams.http_io import ResponseObservation
        from eslams.protocol import ProtocolError

        wire(payload)

        def interrupted(*args, **kwargs):
            exc = ProtocolError("partial response body")
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                status_code=200, headers=tuple(headers.items()),
            )
            raise exc
        monkeypatch.setattr("eslams.agents.bounded_post", interrupted)
    selected = agent()
    if path == "success":
        result = selected.act(request())
        assert echo not in json.dumps(result.metadata["provider_receipt"])
    else:
        with pytest.raises(ProviderCallError) as caught:
            selected.act(request())
        assert echo not in json.dumps(caught.value.receipt) + str(caught.value)
    assert echo not in json.dumps(selected.attempt_receipts)
    assert selected.last_receipt["request_id"] is None


@pytest.mark.parametrize("failure", ["timeout", "transport"])
def test_ambiguous_transport_failures_never_retried(monkeypatch, wire, failure):
    wire(success())
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout detail")
        raise httpx.ConnectError("private connection detail")

    monkeypatch.setattr("eslams.agents.bounded_post", fail)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        selected.act(request())
    assert len(calls) == 1
    assert selected.last_receipt["usage"] == {}


@pytest.mark.parametrize("secondary", [False, True])
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("location", ["prose", "explanation", "action", "metadata", "key"])
def test_action_text_credential_echo_fails_before_parsing_or_repair(
    monkeypatch, wire, secondary, encoded, location,
):
    secondary_secret = "secondary-super-secret"
    monkeypatch.setenv("SENSENOVA_ACCESS_KEY_SECRET", secondary_secret)
    echo = secondary_secret if secondary else SECRET
    action = {"action": 1}
    if location == "explanation":
        action["public_explanation"] = echo
    elif location == "action":
        action["action"] = echo
    elif location == "metadata":
        action["metadata"] = {"note": [echo]}
    elif location == "key":
        action[echo] = "untrusted extension"
    text = json.dumps(action)
    if location == "prose":
        text = echo + "\n" + text
    if encoded:
        text = text.replace(echo, "".join(f"\\u{ord(char):04x}" for char in echo))
    payload = success()
    payload["choices"][0]["message"]["content"] = text
    calls = wire(payload)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert echo not in str(caught.value) + json.dumps(caught.value.receipt)
    assert echo not in json.dumps(selected.attempt_receipts)
    assert len(calls) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["provider_response_id"] == "sensenova-fixture-response"


@pytest.mark.parametrize("secondary", [False, True])
def test_live_preflight_rejects_echoed_action_text_without_disclosure(monkeypatch, wire, secondary):
    secondary_secret = "secondary-super-secret"
    monkeypatch.setenv("SENSENOVA_SECRET_KEY", secondary_secret)
    echo = secondary_secret if secondary else SECRET
    payload = success()
    payload["choices"][0]["message"]["content"] = json.dumps(
        {"action": 1, "public_explanation": echo},
    )
    calls = wire(payload)
    result = provider_preflight("sensenova", DEFAULT_MODEL, "tic-tac-toe", live=True)
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_response_schema_mismatch"
    assert echo not in json.dumps(result)
    assert len(calls) == 1


@pytest.mark.parametrize("provider", ALIASES)
def test_discovery_has_no_network_or_credential_echo_path(monkeypatch, wire, capsys, provider):
    calls = wire(success())
    monkeypatch.setenv("SENSENOVA_SECRET_KEY", "secondary-super-secret")

    def fail(*args, **kwargs):
        pytest.fail("SenseNova discovery must not read credentials or make a network call")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", fail)
    monkeypatch.setattr("eslams.provider_preflight.provider_key", fail)
    assert provider_models_live(provider) is None
    result = provider_models_result(provider)
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_discovery_unavailable"
    assert main(["providers", "models", "--provider", provider, "--live"]) == 1
    output = capsys.readouterr().out
    for secret in (SECRET, "secondary-super-secret"):
        assert secret not in output + json.dumps(result)
    assert not calls


def test_privacy_scan_of_nested_invalid_action_retains_receipt(wire):
    payload = success()
    depth = 1100
    payload["choices"][0]["message"]["content"] = (
        '{"action":' + '[' * depth + '0' + ']' * depth + '}'
    )
    calls = wire(payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind in {
        "provider_response_schema_mismatch", "action_response_unparseable",
    }
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1
