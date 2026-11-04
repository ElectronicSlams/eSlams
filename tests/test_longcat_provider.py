"""Keyless raw HTTP fixtures; no LongCat account or inference is contacted."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry, longcat

ALIASES = (*longcat.PROVIDER_ALIASES, "Meituan_LongCat", "LONGCAT")
PRIVATE = "private-longcat-reasoning-fixture"
KEY = "fixture-longcat-key-never-persist"


def _wire():
    path = Path(__file__).parent / "fixtures/provider/longcat_chat_completions_success.json"
    return json.loads(path.read_text())


def _agent(provider="meituan", **kwargs):
    return ModelProviderAgent(provider, "LongCat-2.5", longcat.API_KEY_ENV, **kwargs)


@pytest.fixture
def transport(monkeypatch):
    """Exercise actual shared serialization and body reading with an offline transport."""
    monkeypatch.setenv(longcat.API_KEY_ENV, KEY)
    requests = []
    responses = []

    def handler(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not response.is_stream_consumed:
            return response
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=httpx.ByteStream(response.content))

    client = httpx.AsyncClient
    monkeypatch.setattr(
        "eslams.http_io.httpx.AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return requests, responses


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_cli_preflight_dispatch_and_exact_unknown_model(alias, transport, capsys):
    requests, responses = transport
    requested = "Exact/LongCat-future:revision-1"
    payload = _wire()
    payload["model"] = "actual-backend-revision"
    responses.append(httpx.Response(200, json=payload))
    agent = _provider_agent(f"{alias}:{requested}")
    assert isinstance(agent, ModelProviderAgent)
    assert agent.provider == "meituan" and agent.model == requested
    assert agent.capabilities.known is False
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)},
                      history=[{"turn": i, "action": i % 3} for i in range(60)])
    result = agent.act(request)
    sent = json.loads(requests[0].content)
    assert str(requests[0].url) == longcat.CHAT_COMPLETIONS_ENDPOINT
    assert requests[0].headers["Authorization"] == f"Bearer {KEY}"
    assert sent["model"] == requested and sent["stream"] is False
    assert {"max_tokens", "thinking", "thinking_budget", "temperature", "provider"}.isdisjoint(sent)
    assert requests[0].extensions["timeout"]["read"] is None
    assert json.loads(sent["messages"][1]["content"].splitlines()[-1])["history"] == request.history
    assert result.action == 1
    receipt = agent.last_receipt
    assert receipt["provider"] == "meituan" and receipt["model"] == requested
    assert receipt["locked_model_id"] == "actual-backend-revision"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == longcat.ENDPOINT_KIND
    assert receipt["parser_version"] == longcat.PARSER_VERSION
    assert receipt["usage"]["reasoning_tokens"] == 78
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert KEY not in json.dumps(result.to_dict()) and PRIVATE not in json.dumps(result.to_dict())

    assert load_provider_registry().resolve(alias, "LongCat-2.5").provider == "meituan"
    assert main(["providers", "preflight", "--provider", alias, "--model", requested]) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["checks"]["adapter_available"] is True
    assert preflight["checks"]["minimal_inference"] is False
    assert preflight["checks"]["registry_entry"] is False
    assert len(requests) == 1


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_requires_explicit_model(alias):
    with pytest.raises(ValueError, match="explicit"):
        _provider_agent(alias)
    with pytest.raises(ValueError, match="explicit"):
        _provider_agent(alias + ":")


@pytest.mark.parametrize("mode", ["auto", "enabled", "disabled"])
@pytest.mark.parametrize("arena_id", ["tic-tac-toe", "chess"])
def test_native_reasoning_controls_do_not_depend_on_arena(mode, arena_id, transport):
    requests, responses = transport
    responses.append(httpx.Response(200, json=_wire()))
    _agent(runtime_config=ProviderRuntimeConfig(reasoning=mode)).act(_request(arena_id=arena_id))
    sent = json.loads(requests[0].content)
    if mode == "auto":
        assert "thinking" not in sent
    else:
        assert sent["thinking"] == {"type": mode}
    assert "thinking_budget" not in sent and "max_tokens" not in sent


def test_explicit_limits_and_reasoning_budget_forward_unchanged(transport):
    requests, responses = transport
    responses.append(httpx.Response(200, json=_wire()))
    _agent(
        max_output_tokens=12345, temperature=0.4,
        runtime_config=ProviderRuntimeConfig(reasoning="enabled", reasoning_budget_tokens=6789),
    ).act(_request())
    sent = json.loads(requests[0].content)
    assert sent["max_tokens"] == 12345 and sent["thinking_budget"] == 6789
    assert sent["temperature"] == 0.4


@pytest.mark.parametrize("control", [{"reasoning_effort": "high"}, {"gemini_thinking_budget": 4}])
def test_unsupported_reasoning_controls_fail_before_submission(control, transport):
    requests, _ = transport
    agent = _agent(runtime_config=ProviderRuntimeConfig(**control))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert error.value.error_kind == "provider_request_rejected" and requests == []


@pytest.mark.parametrize("change,kind", [
    ("refusal", "provider_refused"), ("content_filter", "provider_refused"),
    ("length", "provider_output_truncated"), ("tool_calls", "provider_request_rejected"),
    ("unknown_finish", "provider_response_schema_mismatch"),
    ("missing_finish", "provider_response_schema_mismatch"),
    ("missing_choices", "provider_response_schema_mismatch"),
    ("multiple_choices", "provider_response_schema_mismatch"),
    ("reasoning_only", "provider_response_schema_mismatch"),
    ("wrong_role", "provider_response_schema_mismatch"),
    ("text_parts", "provider_response_schema_mismatch"),
    ("malformed_finish", "provider_response_schema_mismatch"),
    ("invalid_action", "action_response_unparseable"),
])
def test_semantic_errors_never_accept_partial_or_reasoning_action(change, kind, transport):
    requests, responses = transport
    data = _wire()
    choice = data["choices"][0]
    if change == "refusal":
        choice["message"]["refusal"] = PRIVATE
    elif change in {"content_filter", "length", "tool_calls"}:
        choice["finish_reason"] = change
    elif change == "unknown_finish":
        choice["finish_reason"] = PRIVATE
    elif change == "missing_finish":
        choice.pop("finish_reason")
    elif change == "missing_choices":
        data.pop("choices")
    elif change == "multiple_choices":
        data["choices"].append(copy.deepcopy(choice))
    elif change == "reasoning_only":
        choice["message"]["content"] = None
        choice["message"]["reasoning_content"] = '{"action":1}'
    elif change == "wrong_role":
        choice["message"]["role"] = "user"
    elif change == "text_parts":
        choice["message"]["content"] = [{"type": "text", "text": '{"action":1}'}]
    elif change == "malformed_finish":
        choice["finish_reason"] = {"private": PRIVATE}
    elif change == "invalid_action":
        choice["message"]["content"] = "No action available."
    responses.append(httpx.Response(200, json=data, headers={"x-request-id": "longcat-req"}))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert error.value.error_kind == kind and len(requests) == 1
    assert agent.last_receipt["request_id"] == "longcat-req"
    assert agent.last_receipt["usage"]["total_tokens"] == 35
    assert PRIVATE not in str(error.value) + json.dumps(agent.attempt_receipts)
    assert KEY not in str(error.value) + json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (502, "provider_unavailable"),
])
def test_http_errors_privacy_and_zero_default_retries(status, kind, transport):
    requests, responses = transport
    responses.append(httpx.Response(status, json={"error": {
        "code": "rate_limit_exceeded", "type": "rate_limit_error",
        "message": f"{PRIVATE} {KEY}", "retry_after": 60,
    }}, headers={"x-request-id": "error-req"}))
    agent = _agent()
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert error.value.error_kind == kind and error.value.status_code == status
    assert len(requests) == 1
    receipt = agent.last_receipt
    assert receipt["request_id"] == "error-req" and receipt["locked_model_id"] is None
    assert receipt["usage"] == {} and receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert PRIVATE not in json.dumps(receipt) + str(error.value)
    assert KEY not in json.dumps(receipt) + str(error.value)


def _rate_error(**extensions):
    return {"error": {"code": "rate_limit_exceeded", "type": "rate_limit_error",
                      "message": PRIVATE, "retry_after": 0}, **extensions}


def test_explicit_safe_429_retry_preserves_attempt_receipts_and_hint(transport, monkeypatch):
    requests, responses = transport
    responses.extend([httpx.Response(429, json=_rate_error()), httpx.Response(200, json=_wire())])
    delays = []
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation", delays.append)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    assert agent.act(_request()).action == 1
    assert len(requests) == 2 and delays == [0]
    assert [r["outcome"] for r in agent.attempt_receipts] == ["provider_rate_limited", "ok"]
    assert agent.attempt_receipts[0]["retry_after_ms"] == 0


@pytest.mark.parametrize("extensions", [
    {"id": "generation-accepted"}, {"usage": {"prompt_tokens": 1}},
    {"usage": {}}, {"cost": 0}, {"unknown": True},
])
def test_429_with_work_or_unknown_extensions_is_not_replayed(extensions, transport):
    requests, responses = transport
    responses.append(httpx.Response(429, json=_rate_error(**extensions)))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(requests) == 1


@pytest.mark.parametrize("body", [b'{', b'[]', b'{"model":"a","model":"b"}', b'NaN'])
def test_invalid_raw_json_retains_only_header_evidence(body, transport):
    requests, responses = transport
    responses.append(httpx.Response(200, content=body, headers={"x-request-id": "bad-body"}))
    agent = _agent()
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert len(requests) == 1 and agent.last_receipt["request_id"] == "bad-body"
    assert agent.last_receipt["usage"] == {} and agent.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("problem", [
    "missing_usage", "missing_model", "missing_total", "invalid_usage",
])
def test_missing_identity_or_accounting_is_not_invented(problem, transport):
    _, responses = transport
    data = _wire()
    if problem == "missing_usage":
        data.pop("usage")
    elif problem == "missing_model":
        data.pop("model")
    elif problem == "missing_total":
        data["usage"].pop("total_tokens")
    else:
        data["usage"]["prompt_tokens"] = True
    responses.append(httpx.Response(200, json=data))
    agent = _agent()
    agent.act(_request())
    receipt = agent.last_receipt
    if problem == "missing_model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    elif problem == "missing_usage":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    elif problem == "missing_total":
        assert receipt["usage"]["total_tokens"] is None
    else:
        assert receipt["usage"]["input_tokens"] is None
        assert "prompt_tokens_invalid" in receipt["usage"]["usage_validation_errors"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("alias", ALIASES)
def test_mocked_live_discovery_and_preflight_use_native_endpoint(alias, transport, monkeypatch):
    requests, responses = transport
    discovery = []

    def get(url, *, headers, **kwargs):
        discovery.append(url)
        assert url == longcat.MODELS_ENDPOINT and headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "LongCat-2.5"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == ["LongCat-2.5"]
    data = _wire()
    data["choices"][0]["message"]["content"] = '{"action":0}'
    responses.append(httpx.Response(200, json=data))
    result = provider_preflight(alias, "LongCat-2.5", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"] is True
    assert result["readiness"]["inference"] == "succeeded"
    assert result["readiness"]["usage_complete"] is False
    assert result["receipt_shape"]["usage_complete"] is False
    assert len(discovery) == 2 and len(requests) == 1


@pytest.mark.parametrize("exception,kind", [
    (httpx.ReadTimeout(PRIVATE), "provider_timeout"),
    (httpx.ConnectError(PRIVATE), "provider_transport_error"),
])
def test_ambiguous_transport_failures_never_retry(exception, kind, transport):
    requests, responses = transport
    responses.append(exception)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)):
        agent.act(_request())
    assert len(requests) == 1 and agent.last_receipt["outcome"] == kind
    assert PRIVATE not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_run_writes_private_safe_incomplete_accounting_receipts(alias, transport, tmp_path):
    requests, responses = transport
    responses.append(httpx.Response(200, json=_wire()))
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", f"{alias}:LongCat-2.5",
        "--opponent", "first-legal", "--max-turns", "1", "--expanded",
        "--run-id", "longcat-offline-cli", "--output-dir", str(tmp_path),
    ]) == 0
    assert len(requests) == 1
    receipt_files = list(tmp_path.rglob("provider_receipts.jsonl"))
    assert len(receipt_files) == 1
    receipt = json.loads(receipt_files[0].read_text().splitlines()[0])
    assert receipt["provider"] == "meituan" and receipt["locked_model_id"] == "LongCat-2.5"
    assert receipt["usage_complete"] is False and receipt["cost_complete"] is False
    assert receipt["reasoning_included_in_output"] is None
    assert receipt["case_valid_for_scoring"] is False
    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert PRIVATE.encode() not in content and KEY.encode() not in content


@pytest.mark.parametrize("body", [
    {"error": {"code": "rate_limit_exceeded", "type": "rate_limit_error"}},
    {"error": {"code": "invalid_parameter", "type": "invalid_request_error"}},
])
def test_http200_body_errors_do_not_become_actions_or_retries(body, transport):
    requests, responses = transport
    responses.append(httpx.Response(200, json=body))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(requests) == 1
    assert agent.last_receipt["outcome"] in {"provider_rate_limited", "provider_request_rejected"}


@pytest.mark.parametrize("hint", [True, -1, "60", None, [], 10**400])
def test_invalid_rate_delay_hints_do_not_authorize_replay(hint, transport):
    requests, responses = transport
    body = _rate_error()
    body["error"]["retry_after"] = hint
    responses.append(httpx.Response(429, json=body))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(requests) == 1


def test_retry_after_header_precedes_body_hint(transport, monkeypatch):
    _, responses = transport
    responses.extend([
        httpx.Response(429, json=_rate_error(), headers={"Retry-After": "0.25"}),
        httpx.Response(200, json=_wire()),
    ])
    delays = []
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation", delays.append)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    agent.act(_request())
    assert delays == [0.25] and agent.attempt_receipts[0]["retry_after_ms"] == 250


def test_429_accounting_observations_are_quarantined(transport):
    requests, responses = transport
    responses.append(httpx.Response(429, json=_rate_error(
        id="observed-generation", model="untrusted-identity", usage=_wire()["usage"], cost=0.1,
    )))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    receipt = agent.last_receipt
    assert len(requests) == 1
    assert receipt["usage"]["input_tokens"] == 20
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["provider_response_id"] == "observed-generation"
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"


def test_missing_and_invalid_keys_never_submit(transport, monkeypatch):
    requests, _ = transport
    for value in (None, "bad key", "bad\nkey"):
        if value is None:
            monkeypatch.delenv(longcat.API_KEY_ENV)
        else:
            monkeypatch.setenv(longcat.API_KEY_ENV, value)
        agent = _agent()
        with pytest.raises(ProviderCallError) as error:
            agent.act(_request())
        assert error.value.error_kind == "provider_auth_failed"
        assert agent.last_receipt["locked_model_id"] is None
    assert requests == []


def test_response_size_safeguard_retains_header_evidence(transport):
    _, responses = transport
    responses.append(httpx.Response(200, content=b"x", headers={
        "Content-Length": str(2**21), "x-request-id": "oversized-response",
    }))
    agent = _agent()
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert agent.last_receipt["request_id"] == "oversized-response"
    assert agent.last_receipt["usage"] == {} and agent.last_receipt["locked_model_id"] is None


def test_explicit_gateway_preserves_longcat_path_and_model(transport):
    requests, responses = transport
    responses.append(httpx.Response(200, json=_wire()))
    _agent(runtime_config=ProviderRuntimeConfig(
        gateway_base_url="https://gateway.example/native", gateway_mode="generic_base_url",
    )).act(_request())
    assert str(requests[0].url) == "https://gateway.example/native/openai/v1/chat/completions"
    assert json.loads(requests[0].content)["model"] == "LongCat-2.5"


def test_request_operator_output_policy_is_forwarded_without_an_adapter_default(transport):
    requests, responses = transport
    responses.append(httpx.Response(200, json=_wire()))
    request = replace(_request(), metadata={
        "model_execution_policy": model_execution_policy(10000, 9876),
    })
    _agent().act(request)
    assert json.loads(requests[0].content)["max_tokens"] == 9876


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("model", [None, "", " \t\n"])
def test_missing_models_are_rejected_at_construction_and_preflight(alias, model, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("invalid configuration must not reach discovery or inference")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", no_network)
    monkeypatch.setattr("eslams.agents.bounded_post", no_network)
    with pytest.raises(ValueError, match="explicit provider-native model"):
        ModelProviderAgent(alias, model, longcat.API_KEY_ENV)
    for live in (False, True):
        with pytest.raises(ValueError, match="explicit provider-native model"):
            provider_preflight(alias, model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_rejects_blank_model_in_run_and_preflight(alias, monkeypatch, capsys):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda **kw: pytest.fail("no inference"))
    assert main(["run", "--agent", alias + ":   "]) == 1
    assert "explicit provider-native model" in capsys.readouterr().err
    assert main(["providers", "preflight", "--provider", alias, "--model", "   "]) == 1
    assert "explicit provider-native model" in capsys.readouterr().err


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("controls", [
    {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 0},
    {"gemini_thinking_budget": 1234}, {"reasoning_effort": "high"},
])
def test_preflight_rejects_unsupported_explicit_controls_even_offline(alias, controls, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("unsupported controls must not reach any transport")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", no_network)
    monkeypatch.setattr("eslams.agents.bounded_post", no_network)
    runtime = ProviderRuntimeConfig(**controls)
    for live in (False, True):
        with pytest.raises(ValueError, match="unsupported"):
            provider_preflight(alias, "LongCat-2.5", "tic-tac-toe",
                               runtime_config=runtime, live=live)
    agent = _agent(alias, runtime_config=runtime)
    monkeypatch.setenv(longcat.API_KEY_ENV, KEY)
    with pytest.raises(ProviderCallError, match="unsupported") as error:
        agent.act(_request())
    assert error.value.error_kind == "provider_request_rejected"


@pytest.mark.parametrize("budget", [0, 1234])
def test_native_reasoning_budget_remains_supported_in_preflight(budget):
    result = provider_preflight("longcat", "LongCat-2.5", "tic-tac-toe",
                                runtime_config=ProviderRuntimeConfig(reasoning_budget_tokens=budget))
    assert result["ok"] is True


PRIMARY = "opaquePrimaryCredential92x"
SECONDARY = "opaqueSecondaryCredential74z"


def _custom_credentials(monkeypatch):
    monkeypatch.setenv("CUSTOM_LONGCAT_API_KEY", PRIMARY)
    monkeypatch.setenv("LONGCAT_SECONDARY_API_KEY", SECONDARY)
    # The ordinary LONGCAT_API_KEY remains configured separately as KEY.
    return ModelProviderAgent("longcat", "LongCat-2.5", "CUSTOM_LONGCAT_API_KEY")


def _assert_no_credentials(value):
    text = json.dumps(value, sort_keys=True)
    assert all(secret not in text for secret in (PRIMARY, SECONDARY, KEY))


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("field", [
    "id", "model", "x-request-id", "request-id", "cf-aig-request-id", "x-gateway-request-id",
])
def test_success_drops_echoed_credentials_in_identity_fields(
    credential, embedded, field, transport, monkeypatch,
):
    requests, responses = transport
    agent = _custom_credentials(monkeypatch)
    echo = f"prefix-{credential}-suffix" if embedded else credential
    data = _wire()
    headers = {}
    if field in {"id", "model"}:
        data[field] = echo
    else:
        headers[field] = echo
    responses.append(httpx.Response(200, json=data, headers=headers))
    result = agent.act(_request())
    _assert_no_credentials(result.to_dict())
    receipt_field = {"id": "provider_response_id", "model": "locked_model_id",
                     "cf-aig-request-id": "gateway_request_id",
                     "x-gateway-request-id": "gateway_request_id"}.get(field, "request_id")
    assert agent.last_receipt[receipt_field] is None
    if field == "model":
        assert agent.last_receipt["model_identity_source"] is None
    assert result.action == 1 and len(requests) == 1
    assert requests[0].headers["Authorization"] == f"Bearer {PRIMARY}"


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
@pytest.mark.parametrize("location", ["top", "error", "metadata"])
@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_http_error_credential_ids_remain_work_observations_without_leaking(
    credential, location, status, transport, monkeypatch,
):
    requests, responses = transport
    agent = _custom_credentials(monkeypatch)
    agent.runtime_config = ProviderRuntimeConfig(max_retries=2)
    data = _rate_error()
    if location == "top":
        data["id"] = credential
    elif location == "error":
        data["error"]["generation_id"] = credential
    else:
        data["error"]["metadata"] = {"provider_response_id": f"generation-{credential}"}
    responses.append(httpx.Response(status, json=data, headers={
        "x-request-id": PRIMARY, "cf-aig-request-id": SECONDARY,
    }))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    _assert_no_credentials(error.value.receipt)
    _assert_no_credentials(agent.attempt_receipts)
    assert len(requests) == 1 and agent.last_receipt.get("provider_response_id") is None
    assert agent.last_receipt["pricing_provenance"]["work_observation_present"] is True
    assert not error.value.retry_permitted


class _InterruptedBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"id":"incomplete'
        raise httpx.ReadError("connection interrupted")


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("phase", ["malformed", "oversized", "compressed", "interrupted"])
def test_unverified_response_headers_cannot_echo_credentials(
    credential, status, phase, transport, monkeypatch,
):
    requests, responses = transport
    agent = _custom_credentials(monkeypatch)
    agent.runtime_config = ProviderRuntimeConfig(max_retries=2)
    headers = {"x-request-id": f"request-{credential}", "cf-aig-request-id": credential}
    if phase == "oversized":
        headers["Content-Length"] = str(2**21)
    elif phase == "compressed":
        headers["Content-Encoding"] = "gzip"
    if phase == "interrupted":
        responses.append(httpx.Response(status, stream=_InterruptedBody(), headers=headers))
    else:
        responses.append(httpx.Response(status, content=b"{", headers=headers))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert len(requests) == 1
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None
    _assert_no_credentials(error.value.receipt)
    _assert_no_credentials(agent.attempt_receipts)
    assert agent.last_receipt["usage"] == {} and agent.last_receipt["locked_model_id"] is None
    assert not error.value.retry_permitted


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
def test_credentials_in_action_content_fail_closed(credential, transport, monkeypatch):
    _, responses = transport
    agent = _custom_credentials(monkeypatch)
    data = _wire()
    data["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": f"echo-{credential}",
    })
    responses.append(httpx.Response(200, json=data))
    with pytest.raises(ProviderCallError, match="credential-bearing") as error:
        agent.act(_request())
    _assert_no_credentials(error.value.receipt)
    _assert_no_credentials(agent.attempt_receipts)
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert credential not in str(error.value)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
def test_discovery_rejects_credential_echoes(credential, monkeypatch, capsys):
    monkeypatch.setenv(longcat.API_KEY_ENV, KEY)
    _custom_credentials(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": f"model-{credential}"}]},
    ))
    assert main(["providers", "models", "--provider", "longcat", "--live"]) == 1
    payload = json.loads(capsys.readouterr().out)
    _assert_no_credentials(payload)
    assert payload["error"]["error_class"] == "provider_response_schema_mismatch"


def test_credential_scope_does_not_retain_previous_requests(transport, monkeypatch):
    _, responses = transport
    data = _wire()
    data["id"] = KEY
    responses.extend([httpx.Response(200, json=data), httpx.Response(200, json=data)])
    agent = _agent()
    agent.act(_request())
    assert agent.last_receipt["provider_response_id"] is None
    assert not longcat.credential_echo(KEY)
    monkeypatch.setenv(longcat.API_KEY_ENV, "replacementCredential83k")
    agent.act(_request())
    assert agent.last_receipt["provider_response_id"] == KEY


@pytest.mark.parametrize("finish", ["length", "content_filter"])
def test_incomplete_completion_receipts_drop_credentials(finish, transport, monkeypatch):
    _, responses = transport
    agent = _custom_credentials(monkeypatch)
    data = _wire()
    data["id"] = PRIMARY
    data["model"] = SECONDARY
    data["choices"][0]["finish_reason"] = finish
    responses.append(httpx.Response(200, json=data, headers={"request-id": KEY}))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    _assert_no_credentials(error.value.receipt)
    _assert_no_credentials(agent.attempt_receipts)
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["model_identity_source"] is None
    assert agent.last_receipt["usage"]["total_tokens"] == 35


def test_cli_artifact_does_not_persist_echoed_credentials(transport, monkeypatch, tmp_path):
    _, responses = transport
    monkeypatch.setenv("LONGCAT_SECONDARY_API_KEY", SECONDARY)
    data = _wire()
    data["id"] = SECONDARY
    data["model"] = KEY
    responses.append(httpx.Response(200, json=data, headers={
        "x-request-id": KEY, "cf-aig-request-id": SECONDARY,
    }))
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", "longcat:LongCat-2.5",
        "--opponent", "first-legal", "--max-turns", "1", "--expanded",
        "--run-id", "longcat-echo-privacy", "--output-dir", str(tmp_path),
    ]) == 0
    receipt_files = list(tmp_path.rglob("provider_receipts.jsonl"))
    assert len(receipt_files) == 1
    receipt = json.loads(receipt_files[0].read_text().splitlines()[0])
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None
    for path in tmp_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert all(secret.encode() not in content for secret in (KEY, SECONDARY))


@pytest.mark.parametrize("reason", ["stop", "length"])
@pytest.mark.parametrize("choice_count", [1, 2])
def test_known_finish_reason_cannot_echo_a_configured_credential(
    reason, choice_count, transport, monkeypatch,
):
    _, responses = transport
    monkeypatch.setenv(longcat.API_KEY_ENV, reason)
    data = _wire()
    data["choices"][0]["finish_reason"] = reason
    data["choices"] *= choice_count
    responses.append(httpx.Response(200, json=data))
    agent = _agent()
    with pytest.raises(ProviderCallError, match="credential-bearing completion metadata"):
        agent.act(_request())
    assert agent.last_receipt.get("finish_reason") is None
    assert reason not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, KEY])
@pytest.mark.parametrize("fenced", [False, True])
def test_json_escaped_credentials_cannot_leak_through_decoded_explanation(
    credential, fenced, transport, monkeypatch,
):
    _, responses = transport
    agent = _custom_credentials(monkeypatch)
    data = _wire()
    escaped = "".join(f"\\u{ord(character):04x}" for character in credential)
    content = '{"action":1,"public_explanation":"' + escaped + '"}'
    if fenced:
        content = "```json\n" + content + "\n```"
    data["choices"][0]["message"]["content"] = content
    responses.append(httpx.Response(200, json=data))
    with pytest.raises(ProviderCallError, match="credential-bearing") as error:
        agent.act(_request())
    _assert_no_credentials(error.value.receipt)
    _assert_no_credentials(agent.attempt_receipts)
