"""Keyless native REST fixtures; every network entry point is intercepted."""

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
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.runner import RunConfig, Runner

FIXTURES = Path(__file__).parent / "fixtures" / "provider"


def fixture(name="cohere_chat_success.json"):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "fixture-cohere-key")

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected network access")

    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)


def agent(**kwargs):
    return ModelProviderAgent("cohere", "command-a-03-2025", "COHERE_API_KEY", **kwargs)


def wire(monkeypatch, payload=None, *, content=None, status=200, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status, headers=headers,
            **({"content": content} if content is not None
               else {"json": fixture() if payload is None else payload}),
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("provider", ["cohere", "cohere-ai", " COHERE_AI "])
def test_canonical_registry_cli_preflight_dispatch_and_exact_model(monkeypatch, capsys, provider):
    model = "command-a-03-2025"
    registry = load_provider_registry()
    assert registry.resolve(provider, model).provider == "cohere"
    assert registry.resolve(provider, model).known
    assert main(["providers", "preflight", "--provider", provider, "--model", model,
                 "--arena", "tic-tac-toe"]) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["provider"] == "cohere"
    assert preflight["checks"]["adapter_available"]
    calls = wire(monkeypatch)
    selected = _provider_agent(f"{provider}:{model}")
    assert selected.provider == "cohere"
    assert selected.act(_request()).action == 1
    assert calls[0][1]["json"]["model"] == model
    assert selected.last_receipt["provider"] == "cohere"
    direct = ModelProviderAgent(provider, "exact/custom-model:revision", "COHERE_API_KEY")
    assert direct.act(_request()).action == 1
    assert calls[-1][1]["json"]["model"] == "exact/custom-model:revision"
    assert direct.last_receipt["model"] == "exact/custom-model:revision"
    assert direct.last_receipt["locked_model_id"] is None


def test_native_wire_preserves_full_history_defaults_and_usage(monkeypatch):
    calls = wire(monkeypatch, headers={"x-request-id": "cohere-request"})
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None, None)},
                      history=[{"turn_id": turn, "action": turn % 3} for turn in range(140)])
    selected = agent()
    assert selected.act(request).action == 1
    url, submitted = calls[0]
    assert url == "https://api.cohere.com/v2/chat"
    assert submitted["headers"]["Authorization"] == "Bearer fixture-cohere-key"
    assert submitted["timeout"].read is None
    assert not hasattr(submitted["timeout"], "deadline")
    payload = submitted["json"]
    assert payload["stream"] is False
    assert [msg["role"] for msg in payload["messages"]] == ["system", "user"]
    history = json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"]
    assert history == request.history
    for field in ("max_tokens", "thinking", "temperature", "tools", "response_format"):
        assert field not in payload
    receipt = selected.last_receipt
    assert receipt["endpoint_kind"] == "cohere_chat_v2"
    assert receipt["parser_version"] == "cohere-chat-raw-v1"
    assert receipt["request_id"] == "cohere-request"
    assert receipt["provider_response_id"] == fixture()["id"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["usage"]["input_tokens"] == 71
    assert receipt["usage"]["output_tokens"] == 10
    assert receipt["usage"]["total_tokens"] == 81
    assert receipt["usage"]["billed_input_tokens"] == 5
    assert receipt["usage"]["billed_output_tokens"] == 6
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "cost_usd" not in receipt["estimated_cost"]
    assert "fixture-cohere-key" not in json.dumps(receipt)
    assert "board" not in json.dumps(receipt)


def test_explicit_controls_gateway_and_thinking_are_separate_from_final_text(monkeypatch):
    calls = wire(monkeypatch, fixture("cohere_chat_thinking.json"))
    config = ProviderRuntimeConfig(reasoning="enabled", reasoning_budget_tokens=500,
                                   gateway_base_url="https://gateway.example/cohere")
    selected = agent(runtime_config=config, max_output_tokens=1200, temperature=0.4)
    response = selected.act(_request())
    assert response.action == 1
    assert calls[0][0] == "https://gateway.example/cohere/v2/chat"
    payload = calls[0][1]["json"]
    assert payload["thinking"] == {"type": "enabled", "token_budget": 500}
    assert payload["max_tokens"] == 1200 and payload["temperature"] == 0.4
    assert "private fixture thinking" not in json.dumps(response.to_dict())
    assert "private fixture thinking" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning="disabled"),
    ProviderRuntimeConfig(reasoning_budget_tokens=123),
])
def test_explicit_thinking_policy_is_forwarded(monkeypatch, config):
    calls = wire(monkeypatch)
    agent(runtime_config=config).act(_request())
    thinking = calls[0][1]["json"]["thinking"]
    assert thinking == ({"type": "disabled"} if config.reasoning == "disabled"
                        else {"type": "enabled", "token_budget": 123})


@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(gemini_thinking_budget=500),
])
def test_unsupported_control_is_rejected_before_submission(config):
    selected = agent(runtime_config=config)
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert selected.last_receipt.get("provider_response_id") is None


@pytest.mark.parametrize(("reason", "kind"), [
    ("MAX_TOKENS", "provider_output_truncated"),
    ("TOOL_CALL", "provider_request_rejected"),
    ("ERROR", "provider_unavailable"),
    ("TIMEOUT", "provider_timeout"),
    ("future-finish", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"),
    ({"private": "secret response"}, "provider_response_schema_mismatch"),
])
def test_noncomplete_parseable_action_is_rejected_without_replay(monkeypatch, reason, kind):
    data = fixture()
    data["finish_reason"] = reason
    calls = wire(monkeypatch, data)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == len(selected.attempt_receipts) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 81
    assert selected.last_receipt["locked_model_id"] is None
    assert "secret response" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("mutation", [
    {"message": "SDK text convenience property"},
    {"message": {"role": "user", "content": [{"type": "text", "text": '{"action":1}'}]}},
    {"message": {"role": "assistant", "content": "not raw content blocks"}},
    {"message": {"role": "assistant", "content": [{"type": "text", "text": 1}]}},
    {"message": {"role": "assistant", "content": [{"type": "image", "url": "private"}]}},
    {"message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "private"}]}},
    {"message": {"role": "assistant", "content": []}},
    {"error": {}},
    {"status": "in_progress"},
])
def test_malformed_or_unsupported_response_does_not_become_action(monkeypatch, mutation):
    data = {**fixture(), **mutation}
    wire(monkeypatch, data)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert selected.last_receipt["usage"]["total_tokens"] == 81


@pytest.mark.parametrize("content", [b'{"message":', b'[]', b'not json',
                                     b'{"id":"a","id":"b"}', b'{"usage":NaN}'])
def test_malformed_json_keeps_transport_receipt(monkeypatch, content):
    calls = wire(monkeypatch, content=content, headers={"x-request-id": "wire-failure"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    assert selected.last_receipt["request_id"] == "wire-failure"
    assert selected.last_receipt["usage"] == {}


def test_unsolicited_tools_and_plain_text_refusal_do_not_supply_actions(monkeypatch):
    data = fixture()
    data["message"]["tool_calls"] = [{"id": "unsolicited", "type": "function",
                                      "function": {"name": "engine", "arguments": "{}"}}]
    wire(monkeypatch, data)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    # Cohere documents no dedicated refusal discriminator. Do not invent one
    # or guess from prose: ordinary refusals fail Core's legal-action parser.
    data = fixture()
    data["message"]["content"][0]["text"] = "I cannot assist. Private refusal fixture."
    wire(monkeypatch, data)
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "action_response_unparseable"
    assert "Private refusal" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (422, "provider_request_rejected"), (429, "provider_rate_limited"),
    (498, "provider_auth_failed"), (499, "provider_cancelled"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
    (504, "provider_unavailable"),
])
def test_http_failures_redact_credentials_and_never_replay_native_errors(monkeypatch, status, kind):
    data = fixture("cohere_rate_limit.json")
    data["message"] += " Authorization: Bearer fixture-cohere-key private provider prose"
    calls = wire(monkeypatch, data, status=status,
                 headers={"x-request-id": "http-failure", "Retry-After": "20"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == len(selected.attempt_receipts) == 1
    receipt = selected.last_receipt
    assert receipt["status_code"] == status
    assert receipt["request_id"] == "http-failure"
    assert receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "fixture-cohere-key" not in str(failure.value) + json.dumps(receipt)
    assert "private provider prose" not in str(failure.value) + json.dumps(receipt)


@pytest.mark.parametrize("data", [
    {"message": "private native error"},
    {"error": {"code": 429, "message": "private error"}},
    {"error": {"code": 503}},
])
def test_http200_error_envelopes_are_not_actions(monkeypatch, data):
    calls = wire(monkeypatch, data)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        selected.act(_request())
    assert len(calls) == 1
    assert "private" not in json.dumps(selected.last_receipt)
    assert selected.last_receipt["usage"] == {}


def test_interrupted_observed_response_keeps_only_verified_headers(monkeypatch):
    def post(*args, **kwargs):
        exc = ProtocolError("response exceeded bounded body")
        exc._eslams_response_observation = ResponseObservation(
            status_code=200,
            headers=(("x-request-id", "partial-response"), ("authorization", "private-key")),
        )
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(selected.attempt_receipts) == 1
    assert selected.last_receipt["status_code"] == 200
    assert selected.last_receipt["request_id"] == "partial-response"
    assert selected.last_receipt["usage"] == {}
    assert "private-key" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status", [200, 429, 503])
def test_error_with_work_observations_retains_usage_and_never_replays(monkeypatch, status):
    data = fixture()
    data["error"] = {"code": 429}
    data["message"] = "native error with private provider prose"
    calls = wire(monkeypatch, data, status=status)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        selected.act(_request())
    assert len(calls) == 1
    assert selected.last_receipt["provider_response_id"] == data["id"]
    assert selected.last_receipt["usage"]["total_tokens"] == 81
    assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "private provider prose" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status", [200, 401, 429, 503])
def test_opaque_identifiers_cannot_echo_credentials(monkeypatch, status):
    data = fixture()
    data["id"] = "prefix-fixture-cohere-key-suffix"
    wire(monkeypatch, data, status=status, headers={
        "x-request-id": "fixture-cohere-key", "cf-aig-request-id": "fixture-cohere-key",
    })
    selected = agent()
    if status == 200:
        selected.act(_request())
    else:
        with pytest.raises(ProviderCallError):
            selected.act(_request())
    assert "fixture-cohere-key" not in json.dumps(selected.last_receipt)
    assert selected.last_receipt["provider_response_id"] is None
    assert selected.last_receipt["request_id"] is None
    assert selected.last_receipt["gateway_request_id"] is None


def test_malformed_response_header_cannot_echo_credentials(monkeypatch):
    wire(monkeypatch, content=b'not json', headers={"x-request-id": "fixture-cohere-key"})
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(_request())
    assert "fixture-cohere-key" not in json.dumps(selected.last_receipt)


def test_explicit_action_repair_preserves_attempts_and_model(monkeypatch):
    invalid = fixture()
    invalid["message"]["content"][0]["text"] = '{"action":999}'
    responses = iter([invalid, fixture()])
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=next(responses))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=1))
    assert selected.act(_request()).action == 1
    assert [r["attempt_index"] for r in selected.attempt_receipts] == [1, 2]
    assert [r["attempt_kind"] for r in selected.attempt_receipts] == ["primary", "action_repair"]
    assert all(payload["model"] == selected.model for payload in calls)
    assert selected.attempt_receipts[0]["outcome"] == "action_response_unparseable"
    assert selected.attempt_receipts[1]["outcome"] == "ok"


def test_stop_sequence_is_complete_and_malformed_tools_are_not(monkeypatch):
    data = fixture()
    data["finish_reason"] = "STOP_SEQUENCE"
    wire(monkeypatch, data)
    selected = agent()
    assert selected.act(_request()).action == 1
    data["message"]["tool_calls"] = {}
    wire(monkeypatch, data)
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("private key"),
                                httpx.ConnectError("private key")])
def test_transport_failure_does_not_replay(monkeypatch, exc):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        selected.act(_request())
    assert len(calls) == 1
    assert selected.last_receipt["outcome"] in {"provider_timeout", "provider_transport_error"}
    assert "private key" not in str(failure.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize("usage", [None, {}, {"tokens": {}},
                                   {"billed_units": {"input_tokens": 0, "output_tokens": 0}}])
def test_usage_gaps_remain_unknown_and_billed_only_usage_is_not_processed_usage(monkeypatch, usage):
    data = fixture()
    data["usage"] = usage
    data["model"] = "unverified-extension-model"
    wire(monkeypatch, data)
    selected = agent()
    assert selected.act(_request()).action == 1
    receipt = selected.last_receipt
    assert receipt["usage"].get("input_tokens") is None
    assert receipt["usage"].get("output_tokens") is None
    assert receipt["usage"].get("total_tokens") is None
    if isinstance(usage, dict) and usage.get("billed_units"):
        assert receipt["usage"]["billed_input_tokens"] == 0
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("invalid", [True, -1, 2.5, "71"])
def test_malformed_usage_is_recorded_without_cost(monkeypatch, invalid):
    data = fixture()
    data["usage"]["tokens"]["input_tokens"] = invalid
    data["usage"]["billed_units"]["input_tokens"] = invalid
    wire(monkeypatch, data)
    selected = agent()
    selected.act(_request())
    usage = selected.last_receipt["usage"]
    assert usage["input_tokens"] is None and usage["total_tokens"] is None
    assert usage["billed_input_tokens"] is None
    assert "input_tokens_invalid" in usage["usage_validation_errors"]
    assert "billed_input_tokens_invalid" in usage["usage_validation_errors"]


@pytest.mark.parametrize("value", [None, "", "bad key", "unicode-☃", "bad\tkey"])
def test_credential_failures_stop_before_submission(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("COHERE_API_KEY")
    else:
        monkeypatch.setenv("COHERE_API_KEY", value)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert selected.last_receipt["usage"] == {}


def test_discovery_pages_native_shape_and_live_preflight(monkeypatch, capsys):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        data = ({"models": [{"name": "command-r7b-12-2024"}]} if
                "page_token" in kwargs["params"] else fixture("cohere_models.json"))
        return httpx.Response(200, json=data)

    monkeypatch.setattr(httpx, "get", get)
    assert provider_models_live("COHERE_AI") == ["command-a-03-2025", "command-r7b-12-2024"]
    assert calls[0][0] == "https://api.cohere.com/v1/models"
    assert calls[0][1]["params"] == {"endpoint": "chat", "page_size": "1000"}
    assert calls[1][1]["params"]["page_token"] == "fixture-page-two"
    assert main(["providers", "models", "--provider", "cohere-ai", "--live"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider"] == "cohere" and result["models"][0] == "command-a-03-2025"
    wire(monkeypatch)
    result = provider_preflight("cohere-ai", "command-a-03-2025", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"]
    assert result["checks"]["minimal_inference"] and result["checks"]["usage_extraction"]


@pytest.mark.parametrize("second", [
    {"models": [], "next_page_token": "fixture-page-two"},
    {"models": [], "next_page_token": 10},
    {"models": [], "next_page_token": ""},
    {"data": [{"id": "wrong-envelope"}]},
    {"models": [{"name": None}]},
    {"models": [], "error": {"code": 429}},
])
def test_discovery_rejects_partial_or_malformed_pagination(monkeypatch, second):
    pages = iter([fixture("cohere_models.json"), second])
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json=next(pages)))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("cohere")
    assert failure.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize(("status", "kind"), [
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (429, "provider_rate_limited"), (498, "provider_auth_failed"),
    (499, "provider_cancelled"), (503, "provider_unavailable"),
])
def test_discovery_http_failures_return_sanitized_diagnostics(monkeypatch, status, kind):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        status, json={"message": "fixture-cohere-key private error"},
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("cohere-ai")
    assert failure.value.error_kind == kind
    assert "fixture-cohere-key" not in str(failure.value)
    assert "private error" not in str(failure.value)


@pytest.mark.parametrize(("error", "kind"), [
    (httpx.ReadTimeout("fixture-cohere-key"), "provider_timeout"),
    (httpx.ConnectError("fixture-cohere-key"), "provider_transport_error"),
])
def test_discovery_transport_failure_is_sanitized(monkeypatch, error, kind):
    def get(*args, **kwargs):
        raise error

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("cohere")
    assert failure.value.error_kind == kind
    assert "fixture-cohere-key" not in str(failure.value)


def test_discovery_page_limit_never_returns_partial_success(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(1)
        return httpx.Response(200, json={"models": [{"name": "model"}],
                                        "next_page_token": f"page-{len(calls)}"})

    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ProviderCallError, match="20-page limit"):
        provider_models_live("cohere")
    assert len(calls) == 20


def test_cli_run_constructs_native_adapter_from_alias(monkeypatch, tmp_path, capsys):
    calls = wire(monkeypatch)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "cohere-ai:command-a-03-2025",
                 "--opponent", "first-legal", "--max-turns", "1", "--run-id", "cohere-cli",
                 "--output-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "cohere-cli"
    assert len(calls) == 1
    receipt_path = tmp_path / "cohere-cli.eslams.d/receipts/provider_receipts.jsonl"
    receipt = json.loads(receipt_path.read_text().splitlines()[0])
    assert receipt["provider"] == "cohere" and receipt["locked_model_id"] is None


def test_runner_receipts_and_artifacts_preserve_unknown_identity(monkeypatch, tmp_path):
    wire(monkeypatch)
    # One turn is enough to verify serialization and integrity: no identity is
    # fabricated to turn keyless fixture actions into official eligibility.
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=1, max_turns=1,
                                   output_dir=tmp_path, agent_1=agent(), agent_2="first-legal"))
    assert ArtifactValidator().validate(result.artifact_path) == []
    receipt_path = result.artifact_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert receipts and receipts[0]["locked_model_id"] is None
    assert receipts[0]["model_identity_source"] is None
    assert receipts[0]["cost_complete"] is False
    assert "fixture-cohere-key" not in json.dumps(receipts)
    assert "fixture-cohere-key" not in json.dumps(result.score.to_dict())
