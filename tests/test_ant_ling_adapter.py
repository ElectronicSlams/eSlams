"""Deterministic direct Ant Ling wire tests. No provider/network access."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.ant_ling import API_KEY_ENV, CHAT_COMPLETIONS_ENDPOINT

SECRET = "fixture-Ant-key-never-persisted"
FIXTURE = Path(__file__).parent / "fixtures/provider/ant_ling_chat_completions_success.json"


def _wire():
    return json.loads(FIXTURE.read_text())


def _agent(**kwargs):
    return ModelProviderAgent("ant-group", "Ling-3.1-flash", API_KEY_ENV, **kwargs)


def _respond(monkeypatch, data=None, *, status=200, headers=None, content=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        options = {"content": content} if content is not None else {"json": data}
        return httpx.Response(status, headers=headers or {}, **options)

    monkeypatch.setenv(API_KEY_ENV, SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_documented_success_exact_wire_full_history_native_defaults(monkeypatch):
    calls = _respond(monkeypatch, _wire(), headers={"x-request-id": "req-ant-1"})
    request = replace(
        _request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None)},
        history=[{"turn_id": turn, "public": "history-value"} for turn in range(45)],
    )
    agent = _agent()
    result = agent.act(request)
    url, options = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert options["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    payload = options["json"]
    assert set(payload) == {"model", "messages", "stream", "enable_search"}
    assert payload["model"] == "Ling-3.1-flash"
    assert payload["stream"] is False
    assert payload["enable_search"] is False
    assert '"turn_id": 0' in payload["messages"][1]["content"]
    assert '"turn_id": 44' in payload["messages"][1]["content"]
    assert options["timeout"].read is None
    assert result.action == 1
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "ant-group"
    assert receipt["model"] == receipt["locked_model_id"] == "Ling-3.1-flash"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "ant_ling_chat_completions"
    assert receipt["parser_version"] == "ant-ling-chat-completions-raw-v1"
    assert receipt["request_id"] == "req-ant-1"
    assert receipt["usage"]["input_tokens"] == 25
    assert receipt["usage"]["output_tokens"] == 9
    assert receipt["usage"]["total_tokens"] == 34
    assert receipt["usage"]["cached_input_tokens"] == 24
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt_index"] == 1
    assert receipt["attempt_kind"] == "primary"
    assert len(agent.attempt_receipts) == 1
    assert SECRET not in json.dumps(result.to_dict())
    assert "history-value" not in json.dumps(receipt)


@pytest.mark.parametrize("mode", ["auto", "enabled", "disabled"])
def test_reasoning_is_operator_choice_and_not_game_specific(monkeypatch, mode):
    calls = _respond(monkeypatch, _wire())
    runtime = ProviderRuntimeConfig(reasoning=mode)
    for arena in ("connect-four", "chess", "poker"):
        request = _request()
        request = replace(request, arena=type(request.arena)(id=arena, version="1.0.0"))
        assert _agent(runtime_config=runtime).act(request).action == 1
        payload = calls[-1][1]["json"]
        assert payload.get("thinking") == (None if mode == "auto" else {"type": mode})
        assert "reasoning_effort" not in payload


def test_explicit_limits_temperature_and_exact_model_colon(monkeypatch):
    data = _wire()
    data["model"] = "Future:Exact-Model"
    calls = _respond(monkeypatch, data)
    agent = _provider_agent("bailing:Future:Exact-Model")
    agent.temperature = 0.2
    agent.max_output_tokens = 123
    assert agent.act(_request()).action == 1
    payload = calls[0][1]["json"]
    assert payload["model"] == "Future:Exact-Model"
    assert payload["max_tokens"] == 123
    assert payload["temperature"] == 0.2
    assert "thinking" not in payload


@pytest.mark.parametrize("value", ["ant-group", "ant-group:", "ant-group:  ", "bailing:"])
def test_cli_requires_explicit_nonblank_model(value):
    with pytest.raises(ValueError, match="explicit nonblank"):
        _provider_agent(value)


@pytest.mark.parametrize("model", [None, "", "  ", " Ling-3.1-flash", "inclusionai/ling-3.1-flash"])
def test_native_rejects_missing_or_routed_identity(model):
    with pytest.raises(ValueError):
        ModelProviderAgent("ant-group", model, API_KEY_ENV)


@pytest.mark.parametrize("runtime", [
    {"reasoning_effort": "high"}, {"reasoning_budget_tokens": 0},
    {"gemini_thinking_budget": -1}, {"openrouter_provider_order": ("Novita",)},
    {"gateway_base_url": "https://example.com"}, {"gateway_mode": "generic_base_url"},
    {"gateway_auth_mode": "provided_header"},
    {"bedrock_region": "eu-west-1"},
])
def test_unsupported_controls_rejected_before_network(runtime):
    with pytest.raises(ValueError):
        _agent(runtime_config=ProviderRuntimeConfig(**runtime))


@pytest.mark.parametrize("temperature", [True, -1, 1.1, float("nan"), float("inf")])
def test_invalid_temperature_rejected(temperature):
    with pytest.raises(ValueError, match="temperature"):
        _agent(temperature=temperature)


def test_unknown_model_does_not_claim_reasoning_control():
    with pytest.raises(ValueError, match="not documented"):
        ModelProviderAgent("ant-group", "Ring-2.6-1T", API_KEY_ENV,
                           runtime_config=ProviderRuntimeConfig(reasoning="enabled"))


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (413, "provider_request_rejected"),
    (428, "provider_refused"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
    (504, "provider_timeout"),
])
def test_http_failures_no_credential_echo_no_retry(monkeypatch, status, kind):
    # Error JSON is synthetic fault injection: official docs specify statuses,
    # not a normative error JSON envelope. Never treat these as success evidence.
    calls = _respond(monkeypatch, {"error": {"code": status, "message": SECRET, "id": SECRET}},
                     status=status, headers={"x-request-id": SECRET, "Retry-After": "0"})
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1
    assert agent.last_receipt["outcome"] == kind
    assert failure.value.receipt["outcome"] == kind
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["usage"] == {}
    assert SECRET not in json.dumps(agent.attempt_receipts)
    assert SECRET not in str(failure.value)
    assert SECRET not in json.dumps(failure.value.receipt)


@pytest.mark.parametrize("patch,kind", [
    ({"choices": []}, "provider_response_schema_mismatch"),
    ({"choices": [{"finish_reason": "length", "message": {"content": '{"action":1}'}}]},
     "provider_output_truncated"),
    ({"choices": [{"finish_reason": "content_filter", "message": {"content": SECRET}}]},
     "provider_refused"),
    ({"choices": [{"finish_reason": "tool_calls", "message": {"content": '{"action":1}'}}]},
     "provider_response_schema_mismatch"),
    ({"choices": [{"message": {"role": "assistant", "content": '{"action":1}'}}]},
     "provider_response_schema_mismatch"),
    ({"object": "chat.completion.chunk"}, "provider_response_schema_mismatch"),
    ({"model": "Ling-3.0-flash"}, "provider_response_schema_mismatch"),
    ({"error": {"code": 401, "message": SECRET}}, "provider_auth_failed"),
])
def test_no_action_on_incomplete_malformed_error_or_wrong_identity(monkeypatch, patch, kind):
    data = _wire()
    data.update(patch)
    calls = _respond(monkeypatch, data)
    agent = _agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1
    assert agent.last_receipt["usage"]["input_tokens"] == 25
    assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("field", ["model", "id", "request-id", "gateway-id"])
def test_identifier_echo_never_becomes_public_evidence(monkeypatch, field):
    data = _wire()
    headers = {}
    if field in {"model", "id"}:
        data[field] = SECRET
    else:
        headers["x-request-id" if field == "request-id" else "cf-aig-request-id"] = SECRET
    _respond(monkeypatch, data, headers=headers)
    agent = _agent()
    if field == "model":
        with pytest.raises(ProviderCallError):
            agent.act(_request())
        assert agent.last_receipt["locked_model_id"] is None
        assert agent.last_receipt["model_identity_source"] is None
    else:
        result = agent.act(_request())
        assert SECRET not in json.dumps(result.to_dict())
    assert SECRET not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("text", [
    '{"action":1,"public_explanation":"' + SECRET + '"}',
    '{"action":"' + SECRET + '"}',
    '{"action":1,"metadata":{"token":"' + SECRET + '"}}',
])
def test_content_echo_is_rejected_before_action_parsing(monkeypatch, text):
    data = _wire()
    data["choices"][0]["message"]["content"] = text
    _respond(monkeypatch, data)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert SECRET not in str(failure.value)
    assert SECRET not in json.dumps(agent.attempt_receipts)
    assert failure.value.error_kind == "provider_response_schema_mismatch"


def test_json_escaped_credential_cannot_enter_public_explanation(monkeypatch):
    data = _wire()
    escaped = "".join(f"\\u{ord(character):04x}" for character in SECRET)
    data["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"' + escaped + '"}'
    )
    _respond(monkeypatch, data)
    agent = _agent()
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert SECRET not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("content", [b"not-json", b'{"usage":', b"[]", b'{"x":NaN}', b'{}{}'])
def test_malformed_body_receipt_sanitizes_headers(monkeypatch, content):
    _respond(monkeypatch, content=content, headers={"x-request-id": SECRET})
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert SECRET not in json.dumps(agent.last_receipt)
    assert SECRET not in json.dumps(failure.value.receipt)


@pytest.mark.parametrize("exception,kind", [
    (httpx.ReadTimeout, "provider_timeout"),
    (httpx.ReadError, "provider_transport_error"),
])
@pytest.mark.parametrize("observed", [False, True])
def test_timeout_and_partial_response_do_not_retry_or_leak(monkeypatch, exception, kind, observed):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        error = exception(SECRET)
        if observed:
            error._eslams_response_observation = ResponseObservation(
                status_code=200, headers=(("x-request-id", SECRET),),
            )
        raise error

    monkeypatch.setattr("eslams.agents.bounded_post", fail)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        agent.act(_request())
    assert len(calls) == 1
    assert agent.last_receipt["outcome"] == kind
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["usage"] == {}
    assert SECRET not in str(failure.value)
    assert SECRET not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("field", ["model", "usage", "total_tokens"])
def test_missing_evidence_remains_unknown(monkeypatch, field):
    data = _wire()
    if field == "total_tokens":
        data["usage"].pop(field)
    else:
        data.pop(field)
    _respond(monkeypatch, data)
    receipt = _agent().act(_request()).metadata["provider_receipt"]
    if field == "model":
        assert receipt["locked_model_id"] is None
        assert receipt["model_identity_source"] is None
    elif field == "usage":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    else:
        assert receipt["usage"]["total_tokens"] is None
        assert receipt["usage"]["total_tokens_source"] == "unavailable"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_reasoning_prose_undocumented_usage_and_cost_are_not_accounting(monkeypatch):
    data = _wire()
    data["choices"][0]["message"]["reasoning_content"] = SECRET
    data["usage"].update(reasoning_tokens=91, cost=0.01)
    _respond(monkeypatch, data)
    result = _agent().act(_request())
    assert SECRET not in json.dumps(result.to_dict())
    usage = result.metadata["provider_receipt"]["usage"]
    assert usage["reasoning_tokens"] is None
    assert usage["reasoning_included_in_output"] is None
    assert result.metadata["provider_receipt"]["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("text", ['{"action":99}', 'not an action'])
def test_illegal_or_unparseable_action_preserves_attempt(monkeypatch, text):
    data = _wire()
    data["choices"][0]["message"]["content"] = text
    calls = _respond(monkeypatch, data)
    agent = _agent()
    with pytest.raises(ProviderCallError, match="action"):
        agent.act(_request())
    assert len(calls) == 1
    assert agent.last_receipt["outcome"] == "action_response_unparseable"
    assert agent.last_receipt["usage"]["output_tokens"] == 9


def test_preflight_cli_and_catalogue_identity(monkeypatch, capsys):
    calls = _respond(monkeypatch, _wire())
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("no documented Models API"))
    assert provider_models_live("ant-group") is None
    assert provider_models_live("bailing") is None
    for provider in ("ant-group", "bailing"):
        result = provider_preflight(provider, "Ling-3.1-flash", "tic-tac-toe")
        assert result["ok"]
        assert result["checks"]["adapter_available"]
    assert calls == []
    assert main(["providers", "preflight", "--provider", "ant-group", "--model",
                 "Ling-3.1-flash", "--arena", "tic-tac-toe", "--live"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["minimal_inference"]
    assert result["checks"]["account_model_visible"] is None
    assert len(calls) == 1
    unsupported = provider_preflight("inclusionai", "inclusionai/ling-3.1-flash", "tic-tac-toe")
    assert unsupported["error"]["error_class"] == "provider_adapter_unavailable"
    registry = load_provider_registry()
    assert registry.resolve("ant-group", "Ling-1T").lifecycle == "retired"
    assert registry.resolve("ant-group", "Ring-1T").available_from_api is False
    assert registry.resolve("ant-group", "Ring-2.6-1T").lifecycle == "deprecated"
    assert not provider_preflight("ant-group", "Ring-1T", "tic-tac-toe",
                                  strict_catalogue=True)["ok"]


@pytest.mark.parametrize("key", ["", " \n", "bad key", "bad\tkey", "bad-☃"])
def test_missing_or_invalid_credential_never_calls(monkeypatch, key):
    monkeypatch.setenv(API_KEY_ENV, key)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("no request"))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert agent.last_receipt["usage"] == {}


def test_partial_wire_stream_uses_real_bounded_transport(monkeypatch):
    # Exercise header observation and partial-body failure through the real
    # bounded transport, replacing only its HTTPX network transport.
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    original = httpx.AsyncClient

    class PartialBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"choices":'
            raise httpx.ReadError(SECRET)

    def handle(request):
        return httpx.Response(200, headers={"x-request-id": SECRET}, stream=PartialBody())

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    agent = _agent()
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert agent.last_receipt["status_code"] == 200
    assert agent.last_receipt["usage"] == {}
    assert SECRET not in json.dumps(agent.last_receipt)


def test_cli_run_writes_validated_artifact_without_credential_echo(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    def post(url, **kwargs):
        calls.append(1)
        public_request = json.loads(kwargs["json"]["messages"][1]["content"].splitlines()[-1])
        data = _wire()
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": public_request["legal_actions"][0],
        })
        return httpx.Response(200, json=data, headers={"x-request-id": SECRET})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "ant-group:Ling-3.1-flash",
                 "--opponent", "first-legal", "--output-dir", str(tmp_path),
                 "--run-id", "ant-native-cli", "--expanded", "--require-scoring-valid"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["match_valid_for_scoring"]
    assert calls
    artifact = Path(result["expanded_artifact"])
    for path in artifact.rglob("*.json*"):
        assert SECRET not in path.read_text()
    assert main(["validate", str(artifact)]) == 0


@pytest.mark.parametrize("model", [None, "", "  "])
def test_preflight_rejects_missing_model(model):
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight("ant-group", model, "tic-tac-toe")


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": True, "completion_tokens": -1, "total_tokens": "34"},
    {"prompt_tokens": 25, "completion_tokens": 9, "total_tokens": 100},
])
def test_invalid_accounting_is_not_filled_or_priced(monkeypatch, usage):
    data = _wire()
    data["usage"] = usage
    _respond(monkeypatch, data)
    receipt = _agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["usage_validation_errors"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if usage["prompt_tokens"] is True:
        assert receipt["usage"]["input_tokens"] is None
        assert receipt["usage"]["output_tokens"] is None
        assert receipt["usage"]["total_tokens"] is None
