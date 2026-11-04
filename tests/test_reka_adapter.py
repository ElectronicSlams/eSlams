"""Offline tests of Reka's documented REST shape plus synthetic fault injection."""

from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
from test_provider_wire_v06 import _fixture, _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _agent_arg, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight

KEY = "reka-secret-test-value"
MODEL = "reka-flash-3"
URL = "https://api.reka.ai/v1/chat/completions"
ALIASES = ("reka", "reka-ai", "reka_ai", "ReKa")


def _agent(provider="reka-ai", model=MODEL, **kwargs):
    return ModelProviderAgent(provider, model, "REKA_API_KEY", **kwargs)


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("REKA_API_KEY", KEY)
    payload = _fixture("reka_chat_completions_success.json")
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=payload, headers={"X-Request-ID": "reka-request-id"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return payload, calls


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_reach_cli_preflight_and_dispatch(alias, wire, capsys):
    payload, calls = wire
    agent = _agent_arg(f"{alias}:{MODEL}")
    assert isinstance(agent, ModelProviderAgent)
    assert agent.provider == "reka-ai" and agent.model == MODEL
    assert agent.act(_request()).action == 1
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"]
    assert result["preflight_mode"] == "configuration_only"
    assert len(calls) == 1
    direct = _agent(alias)
    assert direct.act(_request()).action == 1
    assert direct.last_receipt["provider"] == "reka-ai"


def test_exact_endpoint_auth_full_history_and_native_defaults(wire):
    payload, calls = wire
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None)}, history=[
        {"turn_id": turn, "public_event": f"history-{turn}"} for turn in range(20)
    ])
    agent = _agent(model="exact/Uncatalogued:Revision")
    response = agent.act(request)
    url, kwargs = calls[0]
    assert url == URL
    assert kwargs["headers"] == {
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
    }
    body = kwargs["json"]
    assert body["model"] == "exact/Uncatalogued:Revision"
    assert set(body) == {"model", "messages"}
    prompt = body["messages"][1]["content"]
    assert all(f"history-{turn}" in prompt for turn in range(20))
    assert kwargs["timeout"].read is None
    assert response.action == 1
    receipt = agent.last_receipt
    assert receipt["model"] == "exact/Uncatalogued:Revision"
    assert receipt["locked_model_id"] == MODEL  # Evidence comes from the actual response.
    assert receipt["endpoint_kind"] == "reka_chat_completions"
    assert receipt["parser_version"] == "reka-chat-completions-raw-v1"
    assert receipt["request_id"] == "reka-request-id"
    assert receipt["provider_response_id"] == "reka-wire-fixture"
    assert receipt["usage"]["total_tokens"] == 16  # Includes the two reasoning tokens once.
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] == 2
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt_index"] == 1 and len(agent.attempt_receipts) == 1
    for secret in (KEY, "private-reka-reasoning-fixture", "history-19", "weight_version"):
        assert secret not in json.dumps(response.to_dict())


@pytest.mark.parametrize("effort", [None, "none", "max", "provider-future-effort"])
def test_explicit_controls_are_forwarded_without_catalogue_rewriting(effort, wire):
    payload, calls = wire
    runtime = ProviderRuntimeConfig(reasoning_effort=effort)
    agent = _agent(model="glm5.3", max_output_tokens=12345, temperature=0.4,
                   runtime_config=runtime)
    agent.act(_request())
    body = calls[0][1]["json"]
    assert body["max_tokens"] == 12345 and body["temperature"] == 0.4
    assert body.get("reasoning_effort") == effort
    assert "reasoning" not in body


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_reasoning_trace_cannot_be_parsed_as_an_action(field, wire):
    payload, calls = wire
    message = payload["choices"][0]["message"]
    message["content"] = None
    message[field] = '{"action": 1}'
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1


@pytest.mark.parametrize(("reason", "expected"), [
    ("length", "provider_output_truncated"),
    ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("unknown-future-stop", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"),
    (123, "provider_response_schema_mismatch"),
])
def test_noncompletion_rejects_even_a_legal_looking_action(reason, expected, wire):
    payload, calls = wire
    payload["choices"][0]["finish_reason"] = reason
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == expected
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1


def test_refusal_prose_is_private_and_not_repaired(wire):
    payload, calls = wire
    payload["choices"][0]["message"]["refusal"] = "private-refusal-prose"
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_refused"
    assert "private-refusal-prose" not in str(failure.value) + json.dumps(agent.last_receipt)
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [
    {"model": None, "id": None, "usage": None},
    {"usage": {"prompt_tokens": 12}},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 4,
               "completion_tokens_details": {"reasoning_tokens": 2}}},
])
def test_missing_identity_or_accounting_stays_missing(changes, wire):
    payload, calls = wire
    payload.update(changes)
    agent = _agent()
    agent.act(_request())
    receipt = agent.last_receipt
    if payload.get("model") is None:
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
        assert receipt["provider_response_id"] is None and receipt["usage"] == {}
    elif "completion_tokens" not in payload["usage"]:
        assert receipt["usage"]["output_tokens"] is None
        assert receipt["usage"]["total_tokens"] is None
    else:
        assert receipt["usage"]["total_tokens"] == 16
        assert receipt["usage"]["total_tokens_source"] == "derived_input_plus_output"
        assert receipt["usage"]["reasoning_tokens"] == 2
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("choices", [None, [], [None], [{"message": {"content": '{"action": 1}'}}]])
def test_malformed_choices_retain_usage_and_receipt(choices, wire):
    payload, calls = wire
    payload["choices"] = choices
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_errors_use_safe_transport_and_never_retry_by_default(status, kind, monkeypatch):
    monkeypatch.setenv("REKA_API_KEY", KEY)
    calls = []
    # Exercise the real bounded transport with a local MockTransport, never a paid endpoint.
    client = httpx.AsyncClient

    def handler(request):
        calls.append(request)
        assert str(request.url) == URL
        assert request.headers["authorization"] == f"Bearer {KEY}"
        body = {"error": {
            "type": "rate_limit_error" if status == 429 else "invalid_request_error",
            "message": f"private-error-prompt {KEY}", "code": None, "param": None,
        }}
        return httpx.Response(status, stream=httpx.ByteStream(json.dumps(body).encode()),
            headers={"X-Request-ID": "reka-error-request", "Retry-After": "6"})

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient",
                        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == kind and failure.value.status_code == status
    assert len(calls) == 1
    receipt = agent.last_receipt
    assert receipt["request_id"] == "reka-error-request"
    assert receipt["usage"] == {}
    assert "private-error-prompt" not in json.dumps(receipt) + str(failure.value)
    assert KEY not in json.dumps(receipt) + str(failure.value)


def test_only_explicit_safe_429_retries_have_separate_receipts(monkeypatch, wire):
    payload, calls = wire
    attempts = []

    def post(*args, **kwargs):
        attempts.append(kwargs["json"])
        if len(attempts) == 1:
            return httpx.Response(429, json={"error": {"type": "rate_limit_error",
                "message": "capacity", "code": "rate_limit_exceeded", "param": None}},
                headers={"Retry-After": "0"})
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(
        max_retries=1, retry_backoff_ms=0, retry_jitter=False))
    agent.act(_request())
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert [r["attempt_index"] for r in agent.attempt_receipts] == [1, 2]
    assert [r["outcome"] for r in agent.attempt_receipts] == ["provider_rate_limited", "ok"]


@pytest.mark.parametrize("response", [
    httpx.ReadTimeout("private-timeout"), httpx.ConnectError("private-transport"),
    httpx.Response(200, text="private-malformed-response"),
    httpx.Response(200, text='{"choices": [], "choices": []}'),
])
def test_transport_and_malformed_body_fail_closed_without_replay(response, monkeypatch):
    monkeypatch.setenv("REKA_API_KEY", KEY)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)):
        agent.act(_request())
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    assert "private-" not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize("alias", ALIASES)
def test_models_discovery_and_live_preflight_aliases(alias, monkeypatch, wire, capsys):
    payload, calls = wire
    discoveries = []

    def get(url, *, headers, **kwargs):
        discoveries.append(url)
        assert url == "https://api.reka.ai/v1/models"
        assert headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == [MODEL]
    assert main(["providers", "models", "--provider", alias, "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == [MODEL]
    result = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"]
    assert result["checks"]["usage_extraction"] and len(calls) == 1


@pytest.mark.parametrize("key", [None, "bad key", "bad\tkey", "☃"])
def test_invalid_credentials_never_reach_network(key, monkeypatch):
    if key is None:
        monkeypatch.delenv("REKA_API_KEY", raising=False)
    else:
        monkeypatch.setenv("REKA_API_KEY", key)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": -1, "completion_tokens": 4, "total_tokens": 3},
    {"prompt_tokens": 12, "completion_tokens": True, "total_tokens": 13},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 19},
    {"prompt_tokens": 12, "completion_tokens": 4, "reasoning_tokens": 5},
    {"prompt_tokens": 12, "completion_tokens": 4, "reasoning_tokens": 2,
     "completion_tokens_details": {"reasoning_tokens": 3}},
])
def test_invalid_accounting_is_unavailable_in_receipts_and_preflight(usage, wire, monkeypatch):
    payload, calls = wire
    payload["usage"] = usage
    agent = _agent()
    assert agent.act(_request()).action == 1
    assert agent.last_receipt["usage"] == {}
    assert agent.last_receipt["usage_unavailable_reason"] == "provider_usage_malformed"
    assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        httpx.Response(200, json={"data": [{"id": MODEL}]}))
    result = provider_preflight("reka", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and not result["checks"]["usage_extraction"]


@pytest.mark.parametrize("work", [
    {"id": "observed-generation-id"},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}},
    {"unknown_extension": "private-work-marker"},
])
def test_429_with_work_evidence_or_unknown_extension_is_not_replayed(work, wire, monkeypatch):
    payload, calls = wire
    observed = []

    def post(*args, **kwargs):
        observed.append(1)
        return httpx.Response(429, json={"error": {"type": "rate_limit_error",
            "code": "rate_limit_exceeded", "message": "private-error"}, **work})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_rate_limited" and observed == [1]
    assert "private-" not in json.dumps(agent.last_receipt)


def test_http200_error_envelope_is_classified_before_text_parsing(wire):
    payload, calls = wire
    payload["error"] = {"type": "authentication_error", "message": "private-error"}
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert "private-error" not in json.dumps(agent.last_receipt)


def test_truncation_artifact_keeps_usage_without_action_or_private_trace(wire, tmp_path):
    from eslams.artifacts import ArtifactValidator
    from eslams.runner import RunConfig, Runner

    payload, calls = wire
    payload["choices"][0]["finish_reason"] = "length"
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": _agent()}, output_dir=tmp_path,
    ))
    assert not result.score.match_valid_for_scoring
    receipt_path = result.artifact_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(row) for row in receipt_path.read_text().splitlines()]
    assert len(receipts) == 1 and not receipts[0]["action_applied"]
    assert receipts[0]["usage"]["total_tokens"] == 16
    assert receipts[0]["finish_reason"] == "length"
    assert ArtifactValidator().validate(result.artifact_path) == []
    for path in result.artifact_path.rglob("*.json*"):
        content = path.read_text()
        assert KEY not in content and "private-reka-reasoning-fixture" not in content


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("model", [None, "", " ", "\t\r\n"])
def test_explicit_model_is_required_by_constructor_and_preflight(alias, model, monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        pytest.fail("discovery"))
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _agent(provider=alias, model=model)
    for live in (False, True):
        result = provider_preflight(alias, model, "tic-tac-toe", live=live)
        assert not result["ok"] and not result["readiness"]["configuration_ready"]
        assert result["error"]["error_class"] == "provider_request_rejected"
        assert not result["checks"]["minimal_inference"]


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("suffix", ["", ":", ":   "])
def test_cli_cannot_silently_choose_a_reka_model(alias, suffix, monkeypatch, capsys):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _agent_arg(alias + suffix)
    assert main(["run", "--agent", alias + suffix]) == 1
    assert "explicit nonblank model" in capsys.readouterr().err


@pytest.mark.parametrize("control", [
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 1024},
    {"gemini_thinking_budget": 0}, {"gemini_thinking_budget": -1},
    {"gemini_thinking_budget": 2048},
    {"reasoning_effort": "high", "reasoning_budget_tokens": 1024},
])
@pytest.mark.parametrize("alias", ALIASES)
def test_explicit_reasoning_budgets_fail_preflight_and_before_transport(alias, control, wire,
                                                                       monkeypatch):
    payload, calls = wire
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        pytest.fail("discovery must not precede configuration validation"))
    runtime = ProviderRuntimeConfig(**control)
    for live in (False, True):
        result = provider_preflight(alias, MODEL, "tic-tac-toe", live=live, runtime_config=runtime)
        assert not result["ok"] and not result["readiness"]["configuration_ready"]
        assert result["error"]["error_class"] == "provider_request_rejected"
        assert "reasoning token budgets" in result["error"]["message"]
        assert not result["checks"]["minimal_inference"]
    agent = _agent(provider=alias, runtime_config=runtime)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected" and calls == []
    assert not agent.last_receipt["usage"]


SECONDARY_KEY = "OpaqueSecondaryCredential789"


def _assert_private(agent, failure=None):
    published = [agent.last_receipt, agent.attempt_receipts, agent._receipt_batch[1]]
    if failure is not None:
        published.extend([failure.receipt, str(failure)])
    dumped = json.dumps(published)
    assert KEY not in dumped and SECONDARY_KEY not in dumped


@pytest.mark.parametrize("secret", [KEY, SECONDARY_KEY])
@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "cf-aig-request-id"])
def test_success_receipt_ids_cannot_echo_any_configured_credential(secret, field, wire,
                                                                  monkeypatch):
    payload, calls = wire
    monkeypatch.setenv("OTHER_PROVIDER_API_KEY", f"  {SECONDARY_KEY}\n")
    headers = {"x-request-id": "safe-request", "cf-aig-request-id": "safe-gateway"}
    if field in {"id", "model"}:
        payload[field] = f"prefix-{secret}-suffix"
    else:
        headers[field] = f"prefix-{secret}-suffix"
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k:
                        httpx.Response(200, json=payload, headers=headers))
    agent = _agent()
    response = agent.act(_request())
    _assert_private(agent)
    assert KEY not in json.dumps(response.to_dict())
    assert SECONDARY_KEY not in json.dumps(response.to_dict())
    receipt_key = {"id": "provider_response_id", "model": "locked_model_id",
                   "x-request-id": "request_id", "cf-aig-request-id": "gateway_request_id"}[field]
    assert agent.last_receipt[receipt_key] is None
    if field == "model":
        assert agent.last_receipt["model_identity_source"] is None
    assert agent.last_receipt["model"] == MODEL
    assert agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("status", [400, 401, 429, 503])
def test_http_error_credential_ids_are_redacted_without_enabling_replay(status, wire, monkeypatch):
    payload, calls = wire
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY_KEY)
    attempts = []

    def post(*a, **k):
        attempts.append(1)
        return httpx.Response(status, json={
            "id": f"work-{SECONDARY_KEY}",
            "error": {"type": "rate_limit_error", "code": "rate_limit_exceeded",
                      "message": f"{KEY} {SECONDARY_KEY}"},
        }, headers={"x-request-id": KEY, "cf-aig-request-id": SECONDARY_KEY})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    _assert_private(agent, failure.value)
    assert attempts == [1]
    assert agent.last_receipt["provider_response_id"] is None
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None
    assert agent.last_receipt["pricing_provenance"]["work_observation_present"]


@pytest.mark.parametrize("body", ["invalid", '{"id":', '{"id":"duplicate","id":"again"}'])
def test_malformed_response_credential_headers_are_private(body, wire, monkeypatch):
    payload, calls = wire
    monkeypatch.setenv("OTHER_API_TOKEN", SECONDARY_KEY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k:
                        httpx.Response(200, text=body, headers={
                            "x-request-id": f"request-{KEY}",
                            "x-gateway-request-id": f"gateway-{SECONDARY_KEY}",
                        }))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    _assert_private(agent, failure.value)
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("interruption", ["timeout", "reset", "resource"])
def test_actual_partial_reader_never_publishes_credential_headers(status, interruption,
                                                                monkeypatch):
    monkeypatch.setenv("REKA_API_KEY", KEY)
    monkeypatch.setenv("SECONDARY_PROVIDER_KEY", SECONDARY_KEY)
    client = httpx.AsyncClient
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps({"id": KEY, "private": SECONDARY_KEY}).encode()[:20]
            if interruption == "timeout":
                raise httpx.ReadTimeout(f"private-{KEY}-{SECONDARY_KEY}")
            if interruption == "reset":
                raise httpx.ReadError(f"private-{KEY}-{SECONDARY_KEY}")
            yield b"x" * (1024 * 1024 + 1)

    def handler(request):
        calls.append(request)
        return httpx.Response(status, stream=Stream(), headers={
            "x-request-id": f"partial-{KEY}", "cf-aig-request-id": f"partial-{SECONDARY_KEY}",
        })

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs:
                        client(transport=httpx.MockTransport(handler), **kwargs))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    _assert_private(agent, failure.value)
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    assert agent.last_receipt["status_code"] == status
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None
    assert agent.last_receipt["usage"] == {}


@pytest.mark.parametrize("secret", [KEY, SECONDARY_KEY])
def test_credential_echo_in_action_text_is_rejected_without_repair(secret, wire, monkeypatch):
    payload, calls = wire
    monkeypatch.setenv("OTHER_PROVIDER_API_KEY", SECONDARY_KEY)
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": f"echo-{secret}",
    })
    agent = _agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2, max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    _assert_private(agent, failure.value)
    assert agent.last_receipt["usage"]["total_tokens"] == 16


def test_custom_primary_environment_and_secondary_discovery_ids_are_private(wire, monkeypatch):
    payload, calls = wire
    monkeypatch.setenv("CUSTOM_ACCESS", KEY)
    monkeypatch.setenv("OTHER_API_KEY", SECONDARY_KEY)
    payload["id"] = KEY
    agent = ModelProviderAgent("reka", MODEL, "CUSTOM_ACCESS")
    agent.act(_request())
    _assert_private(agent)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        httpx.Response(200, json={"data": [{"id": SECONDARY_KEY}]}))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("reka")
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert SECONDARY_KEY not in str(failure.value)
