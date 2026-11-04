"""Deterministic HTTP fixtures: no Databricks credentials or paid calls."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import databricks

SECRET = "fixture-databricks-secret"
MODEL = "my-exact-deployment"
HOST = "https://dbc-fixture.cloud.databricks.com"
ALIASES = ("databricks", "databricks-mosaicml", "databricks_mosaicml")


def success():
    return {
        "id": "query-fixture", "model": "reported-model-version", "object": "chat.completion",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": '{"action": 1}',
        }}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    }


@pytest.fixture
def wire(monkeypatch):
    """Exercise the actual bounded HTTP path with raw JSON bytes in both directions."""
    monkeypatch.setenv("DATABRICKS_TOKEN", SECRET)
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    seen = []
    replies = []
    original_client = httpx.AsyncClient

    class RawBody(httpx.AsyncByteStream):
        def __init__(self, content):
            self.content = content

        async def __aiter__(self):
            yield self.content

    def handle(request):
        seen.append(request)
        assert request.method == "POST"
        assert str(request.url) == f"{HOST}/serving-endpoints/{MODEL}/invocations"
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.headers["content-type"] == "application/json"
        reply = replies.pop(0) if replies else httpx.Response(200, content=json.dumps(success()))
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(reply.status_code, headers=reply.headers,
                              stream=RawBody(reply.content))

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    return seen, replies


def agent(provider="databricks", **kwargs):
    return ModelProviderAgent(provider, MODEL, databricks.API_KEY_ENV, **kwargs)


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_cli_preflight_dispatch_and_full_history(alias, wire, capsys):
    seen, _ = wire
    selected = _provider_agent(f"{alias}:{MODEL}")
    assert selected.provider == databricks.PROVIDER_ID
    assert selected.model == MODEL
    assert selected.api_key_env == databricks.API_KEY_ENV
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)}, history=[
        {"turn_id": turn, "public": "visible-history"} for turn in range(75)
    ])
    result = selected.act(request)
    assert result.action == 1
    payload = json.loads(seen[-1].content)
    assert set(payload) == {"messages", "stream"}
    assert payload["stream"] is False
    assert '"turn_id": 0' in payload["messages"][1]["content"]
    assert '"turn_id": 74' in payload["messages"][1]["content"]
    assert seen[-1].extensions["timeout"]["read"] is None
    receipt = selected.last_receipt
    assert receipt["provider"] == databricks.PROVIDER_ID
    assert receipt["model"] == MODEL
    assert receipt["locked_model_id"] == "reported-model-version"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == databricks.ENDPOINT_KIND
    assert receipt["parser_version"] == databricks.PARSER_VERSION
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(selected.attempt_receipts) == 1
    before = len(seen)
    preflight = provider_preflight(alias, MODEL, "tic-tac-toe")
    assert preflight["ok"]
    assert preflight["checks"]["workspace_endpoint_configured"]
    assert len(seen) == before
    assert provider_models_live(alias) is None
    live = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert live["ok"]
    assert live["checks"]["account_model_visible"] is None
    assert live["checks"]["usage_extraction"]
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


@pytest.mark.parametrize("alias", ALIASES)
def test_direct_dispatch_aliases(alias, wire):
    selected = agent(alias)
    assert selected.act(_request()).action == 1
    assert selected.provider == databricks.PROVIDER_ID


@pytest.mark.parametrize("reason_field", ["finish_reason", "finishReason"])
def test_reasoning_blocks_usage_and_reported_served_identity(reason_field, wire):
    _, replies = wire
    payload = success()
    payload["choices"][0] = {
        "index": 0, reason_field: "stop", "message": {"role": "assistant", "content": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": SECRET}]},
            {"type": "text", "text": '{"action": 1}'},
        ]},
    }
    payload["usage"].update(reasoning_tokens=2, cache_read_input_tokens=3,
                             cache_creation_input_tokens=1)
    replies.append(httpx.Response(200, content=json.dumps(payload), headers={
        "served-model-name": "deployment-served-entity", "x-request-id": "request-fixture",
    }))
    selected = agent()
    assert selected.act(_request()).action == 1
    receipt = selected.last_receipt
    assert receipt["served_model_name"] == "deployment-served-entity"
    assert receipt["locked_model_id"] == "reported-model-version"
    assert receipt["request_id"] == "request-fixture"
    usage = receipt["usage"]
    assert usage["reasoning_tokens"] == 2
    assert usage["reasoning_included_in_output"] is None
    assert usage["cache_read_input_tokens"] == 3
    assert usage["cache_write_input_tokens"] == 1
    assert usage["total_tokens"] == 16
    assert "reasoning_inclusion_unknown" in usage["usage_validation_errors"]
    assert SECRET not in json.dumps(receipt)


@pytest.mark.parametrize("reason,expected", [
    ("length", "provider_output_truncated"), ("max_tokens", "provider_output_truncated"),
    ("content_filter", "provider_refused"), ("tool_calls", "provider_request_rejected"),
    (None, "provider_response_schema_mismatch"), ("unknown", "provider_response_schema_mismatch"),
    (15, "provider_response_schema_mismatch"),
])
def test_no_legal_action_from_incomplete_or_refused_wire(reason, expected, wire):
    _, replies = wire
    payload = success()
    payload["choices"][0]["finish_reason"] = reason
    replies.append(httpx.Response(200, content=json.dumps(payload)))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == expected
    assert selected.last_receipt["outcome"] == expected
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert len(selected.attempt_receipts) == 1


@pytest.mark.parametrize("mutation", [
    "refusal", "conflict", "no-role", "no-text", "extra-choice", "tools", "reasoning-only",
    "unsupported-block", "empty-choices",
])
def test_strict_choice_schema_and_refusal(mutation, wire):
    _, replies = wire
    payload = success()
    choice = payload["choices"][0]
    message = choice["message"]
    if mutation == "refusal":
        message["refusal"] = SECRET
    elif mutation == "conflict":
        choice["finishReason"] = "length"
    elif mutation == "no-role":
        message.pop("role")
    elif mutation == "no-text":
        message["content"] = None
    elif mutation == "extra-choice":
        payload["choices"].append(copy.deepcopy(choice))
    elif mutation == "tools":
        message["tool_calls"] = [{"function": SECRET}]
    elif mutation == "reasoning-only":
        message["content"] = [{"type": "reasoning", "text": '{"action": 1}'}]
    elif mutation == "unsupported-block":
        message["content"] = [{"type": "unknown", "text": '{"action": 1}'}]
    elif mutation == "empty-choices":
        payload["choices"] = []
    replies.append(httpx.Response(200, content=json.dumps(payload)))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    expected = "provider_refused" if mutation == "refusal" else "provider_response_schema_mismatch"
    assert failure.value.error_kind == expected
    assert SECRET not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status,expected", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_failures_zero_retries_and_private_diagnostics(status, expected, wire):
    seen, replies = wire
    replies.append(httpx.Response(status, content=json.dumps({
        "error_code": "RESOURCE_EXHAUSTED", "message": SECRET,
        "prompt": SECRET, "authorization": SECRET,
    }), headers={"Retry-After": "7", "x-request-id": "failed-request"}))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == expected
    assert selected.last_receipt["outcome"] == expected
    assert selected.last_receipt["status_code"] == status
    assert selected.last_receipt["request_id"] == "failed-request"
    assert selected.last_receipt["usage"] == {}
    assert selected.last_receipt["locked_model_id"] is None
    assert SECRET not in str(failure.value) + json.dumps(selected.last_receipt)
    assert len(seen) == 1
    if status == 429:
        assert failure.value.retry_after_seconds == 7


@pytest.mark.parametrize("raw", [b'{not-json', b'[]', b'{"choices":[],"choices":[]}', b'{}'])
def test_malformed_raw_json(raw, wire):
    _, replies = wire
    replies.append(httpx.Response(200, content=raw))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert selected.last_receipt["status_code"] == 200


@pytest.mark.parametrize("problem", ["absent", "missing-total", "negative", "bool", "inconsistent"])
def test_missing_identity_and_accounting_are_never_invented(problem, wire):
    _, replies = wire
    payload = success()
    payload.pop("model")
    if problem == "absent":
        payload.pop("usage")
    elif problem == "missing-total":
        payload["usage"].pop("total_tokens")
    elif problem == "negative":
        payload["usage"]["prompt_tokens"] = -1
    elif problem == "bool":
        payload["usage"]["completion_tokens"] = True
    else:
        payload["usage"]["total_tokens"] = 500
    replies.append(httpx.Response(200, content=json.dumps(payload)))
    selected = agent()
    assert selected.act(_request()).action == 1
    receipt = selected.last_receipt
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if problem == "absent":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    elif problem == "missing-total":
        assert receipt["usage"]["total_tokens"] is None
        assert receipt["usage"]["total_tokens_source"] == "unavailable"
    else:
        assert receipt["usage"]["usage_validation_errors"]


@pytest.mark.parametrize("kwargs,effort", [
    ({}, None), ({"reasoning_effort": "high"}, "high"),
    ({"reasoning": "disabled"}, "none"),
    ({"reasoning": "enabled", "reasoning_effort": "max"}, "max"),
])
def test_operator_controls_and_no_arena_reasoning(kwargs, effort, wire):
    seen, _ = wire
    selected = agent(runtime_config=ProviderRuntimeConfig(**kwargs), max_output_tokens=321,
                     temperature=0.2)
    assert selected.act(_request()).action == 1
    sent = json.loads(seen[-1].content)
    assert sent["max_tokens"] == 321
    assert sent["temperature"] == 0.2
    assert sent.get("reasoning_effort") == effort
    assert "provider" not in sent and "model" not in sent


@pytest.mark.parametrize("kwargs", [
    {"reasoning_budget_tokens": 1024}, {"gemini_thinking_budget": 1}, {"reasoning": "enabled"},
])
def test_unsupported_reasoning_is_rejected_before_network(kwargs, wire):
    seen, _ = wire
    with pytest.raises(ProviderCallError) as failure:
        agent(runtime_config=ProviderRuntimeConfig(**kwargs)).act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert not seen


@pytest.mark.parametrize("host", ["", "http://workspace.example", "https://u:p@host.example",
    "https://workspace.example/path", "https://workspace.example?token=private",
    "https://workspace.example/#private", "https://workspace.example:443",
    "https://workspace.example?", "https://workspace.example/#",
    "https://workspace.example\t.evil", "https://[bad"])
def test_invalid_host_stops_preflight_and_inference(host, wire, monkeypatch):
    seen, _ = wire
    monkeypatch.setenv("DATABRICKS_HOST", host)
    configured = provider_preflight("databricks", MODEL, "tic-tac-toe", live=True)
    assert not configured["ok"]
    assert not configured["readiness"]["configuration_ready"]
    assert configured["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ProviderCallError):
        agent().act(_request())
    assert not seen


@pytest.mark.parametrize("model", ["", "../endpoint", "databricks/model", " name", "a?token=x"])
def test_never_rewrite_catalogue_slug_or_guess_deployment(model, wire):
    seen, _ = wire
    with pytest.raises(ProviderCallError):
        ModelProviderAgent("databricks", model, databricks.API_KEY_ENV).act(_request())
    assert not seen


def test_cli_requires_deployment_and_credentials_are_validated(wire, monkeypatch):
    seen, _ = wire
    with pytest.raises(ValueError, match="explicit serving endpoint"):
        _provider_agent("databricks")
    for value in ("", "bad key", "bad\tkey", "unicode-☃"):
        monkeypatch.setenv("DATABRICKS_TOKEN", value)
        with pytest.raises(ProviderCallError) as failure:
            agent().act(_request())
        assert failure.value.error_kind == "provider_auth_failed"
    assert not seen


@pytest.mark.parametrize("error,expected", [
    (httpx.ReadTimeout("private"), TimeoutError),
    (httpx.ConnectError("private"), ProviderCallError),
])
def test_transport_failures_have_receipts(error, expected, wire):
    seen, replies = wire
    replies.append(error)
    selected = agent()
    with pytest.raises(expected):
        selected.act(_request())
    assert len(seen) == 1
    assert selected.last_receipt["usage"] == {}
    assert "private" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status", [200, 429])
def test_embedded_error_work_observations_prevent_replay(status, wire):
    seen, replies = wire
    payload = {"error": {"code": 429, "message": SECRET},
               "id": "possibly-billable", "usage": success()["usage"]}
    replies.append(httpx.Response(status, content=json.dumps(payload)))
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_rate_limited"
    assert len(seen) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(selected.last_receipt)


def test_flat_databricks_429_is_not_proven_safe_to_replay(wire):
    seen, replies = wire
    replies.append(httpx.Response(429, content=json.dumps({
        "error_code": "REQUEST_LIMIT_EXCEEDED", "message": SECRET,
    }), headers={"retry-after": "0"}))
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_rate_limited"
    assert len(seen) == 1


@pytest.mark.parametrize("status", [200, 429])
def test_identifier_shaped_credential_echo_is_private(status, wire):
    _, replies = wire
    payload = success() if status == 200 else {"error": {"code": 429}, "usage": {}}
    payload.update(id=SECRET, model=SECRET)
    replies.append(httpx.Response(status, content=json.dumps(payload), headers={
        "served-model-name": SECRET, "x-request-id": SECRET,
    }))
    selected = agent()
    if status == 200:
        assert selected.act(_request()).action == 1
    else:
        with pytest.raises(ProviderCallError):
            selected.act(_request())
    assert SECRET not in json.dumps(selected.last_receipt)
    assert selected.last_receipt["locked_model_id"] is None


def test_refusal_cannot_fall_back_in_official_runner(tmp_path, wire):
    from eslams.runner import RunConfig, Runner

    seen, replies = wire
    payload = success()
    payload["choices"][0]["finish_reason"] = "content_filter"
    replies.append(httpx.Response(200, content=json.dumps(payload)))
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1,
        output_dir=tmp_path, execution_profile="official_eval",
    ))
    assert not result.score.match_valid_for_scoring
    assert "provider_refused" in result.score.invalid_reason_codes
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    assert result.trace_events == []
    assert len(seen) == 1


def test_redirect_is_not_followed_or_accepted_as_an_action(wire):
    seen, replies = wire
    replies.append(httpx.Response(302, content=json.dumps(success()), headers={
        "location": "https://unwanted.example/?token=" + SECRET,
    }))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert selected.last_receipt["status_code"] == 302
    assert len(seen) == 1
    assert SECRET not in json.dumps(selected.last_receipt)
