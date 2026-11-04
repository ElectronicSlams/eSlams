"""Relace Open Models contract and credential-boundary regressions (no live calls)."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

import eslams.agents as agents_module
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import relace

MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
SECRET = "rlc-0123456789abcdef0123456789abcdef"
SECONDARY = "opaque-secondary-credential-90abc"
FIXTURE = Path(__file__).parent / "fixtures/provider/relace_chat_completions_success.json"


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="relace-test", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="relace-test", version="test"), active_player="player_1",
        observation={"board": []}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"}, history=[{"turn": n} for n in range(50)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(**kwargs):
    return ModelProviderAgent(provider="relace", model=MODEL, api_key_env="RELACE_API_KEY",
                              **kwargs)


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("RELACE_API_KEY", SECRET)
    state = {"status": 200, "data": json.loads(FIXTURE.read_text()), "headers": {}, "calls": []}

    def post(url, *, headers, json, timeout):
        state["calls"].append((url, headers, json, timeout))
        return httpx.Response(
            state["status"],
            content=state["raw"] if "raw" in state else __import__("json").dumps(state["data"]),
            headers=state["headers"],
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return state


def test_dispatch_wire_history_usage_and_no_implicit_limits(wire):
    selected = _provider_agent("relace:" + MODEL)
    result = selected.act(request())
    url, headers, payload, timeout = wire["calls"][0]
    assert selected.provider == "relace" and selected.model == MODEL
    assert url == relace.CHAT_COMPLETIONS_ENDPOINT
    assert headers == {"Authorization": "Bearer " + SECRET, "Content-Type": "application/json"}
    assert payload == {
        "model": MODEL, "stream": False,
        "messages": payload["messages"],
    }
    assert '"turn": 0' in payload["messages"][1]["content"]
    assert '"turn": 49' in payload["messages"][1]["content"]
    assert timeout.read is None and timeout.pool is None
    assert result.action == 1
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "relace"
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "relace_chat_completions"
    assert receipt["parser_version"] == relace.PARSER_VERSION
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(result.to_dict())


def test_explicit_output_and_temperature(wire):
    agent(max_output_tokens=9000, temperature=0.3).act(request())
    assert wire["calls"][0][2]["max_tokens"] == 9000
    assert wire["calls"][0][2]["temperature"] == 0.3


@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_blank_model_rejected_without_wire(model, wire):
    with pytest.raises(ValueError, match="explicit nonblank"):
        ModelProviderAgent(provider="relace", model=model, api_key_env="RELACE_API_KEY")
    assert not wire["calls"]


@pytest.mark.parametrize("value", ["relace", "relace:", "relace:  "])
def test_cli_no_default_model(value):
    with pytest.raises(ValueError, match="explicit nonblank"):
        _provider_agent(value)


@pytest.mark.parametrize("settings", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 0}, {"gemini_thinking_budget": 1},
    {"history_window_turns": 2}, {"gateway_base_url": "https://example.invalid"},
    {"openrouter_provider_order": ("other",)},
    {"gateway_auth_mode": "provided_header"}, {"bedrock_region": "eu-west-1"},
])
def test_unverified_controls_rejected_in_adapter_and_offline_preflight(settings, wire):
    runtime = ProviderRuntimeConfig(**settings)
    with pytest.raises(ValueError):
        agent(runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("relace", MODEL, "tic-tac-toe", runtime_config=runtime)
    assert not wire["calls"]


def test_configuration_preflight_cli_is_offline(monkeypatch, capsys):
    monkeypatch.delenv("RELACE_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("unexpected discovery"))
    assert main(["providers", "preflight", "--provider", "relace", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and data["checks"]["adapter_available"]
    assert not data["checks"]["minimal_inference"]


def test_explicit_models_discovery_and_live_preflight_are_mocked(wire, monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": MODEL, "object": "model", "owned_by": "relace"},
        ]})

    monkeypatch.setattr(httpx, "get", get)
    result = provider_preflight("relace", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert calls[0][0] == relace.MODELS_ENDPOINT
    assert calls[0][1]["headers"]["Authorization"] == "Bearer " + SECRET
    assert len(wire["calls"]) == 1
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("field", ["usage", "model", "id"])
def test_missing_evidence_stays_unknown(field, wire):
    del wire["data"][field]
    selected = agent()
    selected.act(request())
    receipt = selected.last_receipt
    if field == "usage":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    elif field == "model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    else:
        assert receipt["provider_response_id"] is None


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (502, "provider_unavailable"),
    (503, "provider_unavailable"), (504, "provider_unavailable"),
])
def test_http_errors_are_sanitized_and_never_retried_by_default(status, kind, wire):
    wire.update(status=status, data={"error": {
        "message": SECRET, "type": "rate_limit_error", "code": None, "param": None,
        "id": SECRET, "model": SECRET,
    }}, headers={"x-request-id": SECRET, "Retry-After": "1"})
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert len(wire["calls"]) == 1
    assert SECRET not in str(caught.value)
    assert SECRET not in json.dumps(selected.attempt_receipts)
    assert SECRET not in json.dumps(caught.value.receipt)


@pytest.mark.parametrize("body", [b"{", b"[]", b'{"model":"x","model":"y"}', b"null"])
def test_malformed_response_receipt_headers_are_sanitized(body, wire):
    wire.update(raw=body, headers={"x-request-id": SECRET})
    selected = agent()
    with pytest.raises(ProviderCallError, match="JSON"):
        selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("finish,kind", [
    ("length", "provider_output_truncated"), ("tool_calls", "provider_request_rejected"),
    ("content_filter", "provider_refused"), (None, "provider_response_schema_mismatch"),
    ("invented", "provider_response_schema_mismatch"),
])
def test_partial_or_nontext_completions_keep_accounting_but_no_action(finish, kind, wire):
    wire["data"]["choices"][0]["finish_reason"] = finish
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert len(wire["calls"]) == 1


@pytest.mark.parametrize("echo", [SECRET, "Bearer " + SECRET, quote(SECRET, safe=""),
                                   SECRET.replace("r", "\\u0072", 1)])
def test_action_fields_cannot_echo_credential(echo, wire):
    wire["data"]["choices"][0]["message"]["content"] = (
        '{"action": 1, "public_explanation": "' + echo + '"}'
    )
    selected = agent()
    with pytest.raises(ProviderCallError, match="unsafe"):
        selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)


def test_success_identifier_echoes_are_unknown(wire):
    wire["data"].update(id=SECRET, model=SECRET)
    wire["headers"] = {"x-request-id": "prefix-" + SECRET, "cf-aig-request-id": SECRET}
    result = agent().act(request())
    receipt = result.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None
    assert receipt["request_id"] is None
    assert SECRET not in json.dumps(result.to_dict())


def test_different_served_model_rejected_without_fallback(wire):
    wire["data"]["model"] = "different-model"
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert selected.last_receipt["model"] == MODEL
    assert selected.last_receipt["locked_model_id"] == "different-model"
    assert len(wire["calls"]) == 1


@pytest.mark.parametrize("changes", [
    {"message": {"content": '{"action": 1}', "tool_calls": [{"id": "call"}]}},
    {"message": {"content": None}}, {"message": {"content": []}},
    {"message": {"role": "user", "content": '{"action": 1}'}},
])
def test_nontext_or_tool_message_cannot_be_action(changes, wire):
    wire["data"]["choices"][0].update(changes)
    with pytest.raises(ProviderCallError):
        agent().act(request())


@pytest.mark.parametrize("secret", ["arbitrary-opaque-key", "key+with/slash=and?query"])
def test_nonstandard_credential_echo_is_sanitized(secret, wire, monkeypatch):
    monkeypatch.setenv("RELACE_API_KEY", secret)
    wire["headers"] = {"x-request-id": quote(secret, safe="")}
    wire["data"].update(id=secret, model=secret)
    result = agent().act(request())
    assert result.metadata["provider_receipt"]["locked_model_id"] is None
    assert secret not in json.dumps(result.to_dict())
    wire["data"]["choices"][0]["message"]["content"] = json.dumps(
        {"action": 1, "public_explanation": secret},
    )
    with pytest.raises(ProviderCallError):
        agent().act(request())


@pytest.mark.parametrize("wrapper", ["```json\n%s\n```", "Here is the action: %s"])
def test_wrapped_json_escape_cannot_bypass_action_credential_guard(wrapper, wire):
    escaped = SECRET.replace("r", "\\u0072", 1)
    wire["data"]["choices"][0]["message"]["content"] = wrapper % (
        '{"action": 1, "public_explanation": "' + escaped + '"}'
    )
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)


def test_200_error_is_not_an_action_and_error_observations_stay_private(wire):
    wire["data"]["error"] = {"type": "api_error", "message": SECRET}
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)
    assert selected.last_receipt["usage"]["total_tokens"] == 16


def test_missing_usage_does_not_trust_extra_cost_or_reasoning_extensions(wire):
    wire["data"]["usage"] = {"cost": 0.01, "reasoning_tokens": 30}
    selected = agent()
    selected.act(request())
    assert selected.last_receipt["usage"] == {}
    assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_incoherent_accounting_is_retained_as_invalid(wire):
    wire["data"]["usage"]["total_tokens"] = 1
    selected = agent()
    selected.act(request())
    assert selected.last_receipt["usage"]["usage_validation_errors"]


def test_absent_total_is_not_synthesized(wire):
    del wire["data"]["usage"]["total_tokens"]
    selected = agent()
    selected.act(request())
    assert selected.last_receipt["usage"]["total_tokens"] is None
    assert selected.last_receipt["usage"]["total_tokens_source"] is None


@pytest.mark.parametrize("status", [201, 301, 307])
def test_non200_status_is_not_a_successful_completion(status, wire):
    wire["status"] = status
    wire["headers"] = {"location": "https://example.invalid", "x-request-id": SECRET}
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert selected.last_receipt["status_code"] == status
    assert SECRET not in json.dumps(selected.attempt_receipts)
    assert len(wire["calls"]) == 1


def test_discovery_rejects_secret_model_ids(wire, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(
        200, json={"data": [{"id": SECRET}]},
    ))
    with pytest.raises(ProviderCallError):
        provider_models_live("relace")


def test_timeout_never_replayed_even_with_retry_opt_in(wire, monkeypatch):
    count = []

    def post(*args, **kwargs):
        count.append(1)
        raise httpx.ReadTimeout(SECRET)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(TimeoutError, match="provider timed out"):
        selected.act(request())
    assert len(count) == 1
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("echo", [SECRET, SECONDARY])
def test_real_safe_transport_partial_body_sanitizes_header_evidence(monkeypatch, echo):
    monkeypatch.setenv("RELACE_API_KEY", SECRET)
    monkeypatch.setenv("RELACE_SECONDARY_API_KEY", SECONDARY)
    original_client = httpx.AsyncClient

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"choices":'
            raise httpx.ReadError(echo)

    def handler(incoming):
        assert str(incoming.url) == relace.CHAT_COMPLETIONS_ENDPOINT
        assert incoming.headers["authorization"] == "Bearer " + SECRET
        assert json.loads(incoming.content)["model"] == MODEL
        return httpx.Response(200, headers={
            "x-request-id": echo, "cf-aig-request-id": echo,
        }, stream=BrokenBody())

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handler),
    ))
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_transport_error"
    assert selected.last_receipt["status_code"] == 200
    assert not selected.last_receipt["usage"]
    assert SECRET not in json.dumps(selected.attempt_receipts)
    assert SECONDARY not in json.dumps(selected.attempt_receipts)
    assert selected.last_receipt["request_id"] is None
    assert selected.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_blank_model_preflight_fails_before_discovery(model, wire, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("unexpected discovery"))
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight("relace", model, "tic-tac-toe", live=True)
    assert not wire["calls"]


@pytest.mark.parametrize("budget", [0, 1, 4096])
def test_explicit_budget_revalidated_before_transport_and_live_discovery(budget, wire, monkeypatch):
    runtime = ProviderRuntimeConfig(reasoning_budget_tokens=budget)
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("unexpected discovery"))
    with pytest.raises(ValueError, match="controls are unverified"):
        provider_preflight("relace", MODEL, "tic-tac-toe", live=True, runtime_config=runtime)
    selected = agent()
    selected.runtime_config = runtime
    with pytest.raises(ValueError, match="controls are unverified"):
        selected.act(request())
    assert not wire["calls"]


@pytest.mark.parametrize("boundary", ["success", "error", "malformed", "action", "discovery"])
def test_secondary_credential_is_private_across_boundaries(boundary, wire, monkeypatch):
    monkeypatch.setenv("RELACE_SECONDARY_API_KEY", SECONDARY)
    wire["headers"] = {"x-request-id": SECONDARY, "cf-aig-request-id": SECONDARY}
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    if boundary == "success":
        wire["data"].update(id=SECONDARY, model=SECONDARY)
        result = selected.act(request())
        assert SECONDARY not in json.dumps(result.to_dict())
        assert selected.last_receipt["locked_model_id"] is None
        return
    if boundary == "error":
        wire.update(status=429, data={"error": {
            "type": "rate_limit_error", "message": SECONDARY, "id": SECONDARY,
        }})
    elif boundary == "malformed":
        wire["raw"] = ('{"unfinished": "' + SECONDARY).encode()
    elif boundary == "action":
        wire["data"]["choices"][0]["message"]["content"] = json.dumps(
            {"action": 1, "public_explanation": SECONDARY},
        )
    else:
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(
            200, json={"data": [{"id": SECONDARY}]},
        ))
        with pytest.raises(ProviderCallError):
            provider_models_live("relace")
        assert not wire["calls"]
        return
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert len(wire["calls"]) == 1
    assert SECONDARY not in str(caught.value)
    assert SECONDARY not in json.dumps(caught.value.receipt)
    assert SECONDARY not in json.dumps(selected.attempt_receipts)
    assert selected.last_receipt["request_id"] is None
    assert selected.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("name", [
    "OPENAI_API_KEY", "AWS_SESSION_TOKEN", "CUSTOM_CLIENT_SECRET", "RELACE_SECONDARY_KEY",
])
def test_other_configured_credentials_cannot_be_action_text(name, wire, monkeypatch):
    monkeypatch.setenv(name, SECONDARY)
    wire["data"]["choices"][0]["message"]["content"] = (
        '```json\n{"action": 1, "public_explanation": "'
        + SECONDARY.replace("o", "\\u006f", 1) + '"}\n```'
    )
    with pytest.raises(ProviderCallError):
        agent().act(request())


def test_custom_primary_and_canonical_secondary_credentials_are_both_private(wire, monkeypatch):
    monkeypatch.setenv("CUSTOM_RELACE_AUTH", "custom-opaque-primary")
    monkeypatch.setenv("RELACE_API_KEY", SECONDARY)
    wire["data"].update(id=SECONDARY, model=SECONDARY)
    selected = ModelProviderAgent(provider="relace", model=MODEL, api_key_env="CUSTOM_RELACE_AUTH")
    result = selected.act(request())
    assert wire["calls"][0][1]["Authorization"] == "Bearer custom-opaque-primary"
    assert selected.last_receipt["locked_model_id"] is None
    assert SECONDARY not in json.dumps(result.to_dict())


@pytest.mark.parametrize("echo", [
    "Bearer unconfigured-secondary", "api_key=unconfigured-secondary",
    "https://example.invalid/?key=unconfigured-secondary",
])
def test_marked_credentials_are_rejected_without_environment_match(echo, wire):
    wire["data"]["choices"][0]["message"]["content"] = json.dumps(
        {"action": 1, "public_explanation": echo},
    )
    with pytest.raises(ProviderCallError):
        agent().act(request())


def test_secondary_credential_snapshot_survives_environment_rotation(wire, monkeypatch):
    monkeypatch.setenv("RELACE_API_KEY_SECONDARY", SECONDARY)
    wire["data"].update(id=SECONDARY, model=SECONDARY)
    wire["headers"] = {"x-request-id": SECONDARY}
    original = agents_module.bounded_post

    def post(*args, **kwargs):
        monkeypatch.setenv("RELACE_API_KEY_SECONDARY", "rotated-secondary")
        return original(*args, **kwargs)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent()
    result = selected.act(request())
    assert selected.last_receipt["locked_model_id"] is None
    assert SECONDARY not in json.dumps(result.to_dict())


def test_discovery_credential_snapshot_survives_environment_rotation(wire, monkeypatch):
    monkeypatch.setenv("RELACE_SECONDARY_KEY", SECONDARY)

    def get(*args, **kwargs):
        monkeypatch.setenv("RELACE_SECONDARY_KEY", "rotated-secondary")
        return httpx.Response(200, json={"data": [{"id": SECONDARY}]})

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("relace")
    assert SECONDARY not in str(caught.value)
    assert not wire["calls"]
