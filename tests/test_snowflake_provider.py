"""Deterministic raw-wire tests; never contact a Snowflake account."""

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
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers.snowflake import CHAT_PATH, connection_settings
from eslams.runner import RunConfig, Runner

FIXTURE = Path(__file__).parent / "fixtures/provider/snowflake_chat_completions_success.json"


def wire():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT_URL", "https://org-account.snowflakecomputing.com")
    monkeypatch.setenv("SNOWFLAKE_TOKEN", "fixture-secret")
    monkeypatch.delenv("SNOWFLAKE_TOKEN_TYPE", raising=False)


def agent(**kwargs):
    return ModelProviderAgent(
        kwargs.pop("provider", "snowflake"), kwargs.pop("model", "openai-gpt-5-mini"),
        "SNOWFLAKE_TOKEN", **kwargs,
    )


def post_response(monkeypatch, response):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_native_wire_identity_history_accounting_and_unbounded_defaults(monkeypatch):
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    request = replace(
        _request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        history=[{"turn_id": turn, "action": turn % 3} for turn in range(80)],
        metadata={"model_execution_policy": model_execution_policy(None)},
    )
    result = agent().act(request)
    url, sent = calls[0]
    assert url == "https://org-account.snowflakecomputing.com" + CHAT_PATH
    assert sent["headers"]["Authorization"] == "Bearer fixture-secret"
    assert sent["json"]["model"] == "openai-gpt-5-mini"
    assert sent["json"]["stream"] is False
    assert set(sent["json"]) == {"model", "messages", "stream"}
    assert json.loads(sent["json"]["messages"][1]["content"].splitlines()[-1])["history"] == (
        request.history
    )
    assert sent["timeout"].read is None and not hasattr(sent["timeout"], "deadline")
    assert result.action == 1 and len(calls) == 1
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "snowflake"
    assert receipt["model"] == receipt["locked_model_id"] == "openai-gpt-5-mini"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "snowflake_chat_completions"
    assert receipt["parser_version"] == "snowflake-chat-completions-raw-v1"
    usage = receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (12, 4, 16)
    assert usage["reasoning_tokens"] == 2 and usage["reasoning_included_in_output"] is True
    assert usage["cached_input_tokens"] == 3
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "fixture-secret" not in json.dumps(receipt)


@pytest.mark.parametrize("alias", ["snowflake", "cortex", "snowflake-cortex", "Snowflake_Cortex"])
def test_aliases_through_cli_preflight_and_dispatch(monkeypatch, capsys, alias):
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    selected = _provider_agent(f"{alias}:openai-gpt-5-mini")
    assert selected.provider == "snowflake"
    assert selected.act(_request()).action == 1
    assert agent(provider=alias).act(_request()).action == 1
    assert main([
        "providers", "preflight", "--provider", alias, "--model", "openai-gpt-5-mini",
        "--arena", "tic-tac-toe",
    ]) == 0
    offline = json.loads(capsys.readouterr().out)
    assert offline["checks"]["adapter_available"] is True and len(calls) == 2
    live = provider_preflight(alias, "openai-gpt-5-mini", "tic-tac-toe", live=True)
    assert live["ok"] and live["checks"]["minimal_inference"] is True
    assert live["checks"]["account_model_visible"] is None
    assert len(calls) == 3
    unavailable = provider_models_result(alias)
    assert unavailable["ok"] is False and unavailable["models"] == []


@pytest.mark.parametrize("alias", ["snowflake", "cortex", "snowflake-cortex"])
def test_no_implicit_model(alias):
    with pytest.raises(ValueError, match="explicit native model"):
        _provider_agent(alias)


@pytest.mark.parametrize("token_type", ["", "OAUTH", "KEYPAIR_JWT", "PROGRAMMATIC_ACCESS_TOKEN"])
def test_authentication_headers(monkeypatch, token_type):
    monkeypatch.setenv("SNOWFLAKE_TOKEN_TYPE", token_type)
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    agent().act(_request())
    assert calls[0][1]["headers"].get("X-Snowflake-Authorization-Token-Type", "") == token_type


@pytest.mark.parametrize("origin", [
    "", "http://org-account.snowflakecomputing.com", "https://example.com",
    "https://org-account.snowflakecomputing.com.evil.example",
    "https://user:secret@org-account.snowflakecomputing.com",
    "https://org-account.snowflakecomputing.com:443",
    "https://org-account.snowflakecomputing.com/api/v2",
    "https://org-account.snowflakecomputing.com?token=private",
    "https://org-account.snowflakecomputing.com#private", "https://[bad",
])
def test_bad_account_origin_fails_offline_and_before_network(monkeypatch, origin):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT_URL", origin)
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    result = provider_preflight("snowflake", "openai-gpt-5-mini", "tic-tac-toe")
    assert result["ok"] is False and result["readiness"]["configuration_ready"] is False
    with pytest.raises(ProviderCallError, match="SNOWFLAKE_ACCOUNT_URL"):
        agent().act(_request())
    assert not calls and "private" not in json.dumps(result) and "user:secret" not in str(result)


def test_privatelink_and_regional_host_are_literal(monkeypatch):
    for hostname in (
        "xy12345.eu-west-1.snowflakecomputing.com",
        "org-account.privatelink.snowflakecomputing.com",
    ):
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT_URL", f"https://{hostname}/")
        assert connection_settings()[0] == f"https://{hostname}{CHAT_PATH}"


@pytest.mark.parametrize("name,value", [
    ("SNOWFLAKE_TOKEN", ""), ("SNOWFLAKE_TOKEN", "private bad token"),
    ("SNOWFLAKE_TOKEN_TYPE", "private-invalid-type"),
])
def test_invalid_auth_configuration_does_not_call_network(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    with pytest.raises(ProviderCallError) as failure:
        agent().act(_request())
    assert "private" not in str(failure.value) and calls == []


@pytest.mark.parametrize("model,config,expected", [
    ("openai-gpt-5", {"reasoning_effort": "high"}, {"reasoning_effort": "high"}),
    ("openai-gpt-5", {"reasoning": "disabled"}, {"reasoning_effort": "none"}),
    ("claude-sonnet-4-5", {"reasoning_effort": "high"}, {"reasoning": {"effort": "high"}}),
    ("claude-sonnet-4-5", {"reasoning_budget_tokens": 2048}, {"reasoning": {"max_tokens": 2048}}),
])
def test_explicit_reasoning_and_output_controls(monkeypatch, model, config, expected):
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    selected = agent(
        model=model, runtime_config=ProviderRuntimeConfig(**config), max_output_tokens=24000,
        temperature=0.6,
    )
    selected.act(_request(arena_id="connect-four"))
    payload = calls[0][1]["json"]
    assert payload["model"] == model and payload["max_completion_tokens"] == 24000
    assert payload["temperature"] == 0.6
    for key, value in expected.items():
        assert payload[key] == value
    assert "provider" not in payload and "max_tokens" not in payload and "store" not in payload


@pytest.mark.parametrize("model,config", [
    ("openai-gpt-5", {"reasoning_budget_tokens": 2000}),
    ("claude-sonnet-4-5", {"reasoning_effort": "high", "reasoning_budget_tokens": 2000}),
    ("claude-sonnet-4-5", {"reasoning": "disabled"}),
    ("openai-gpt-5", {"reasoning": "enabled"}),
    ("mistral-large2", {"reasoning_effort": "high"}),
    ("openai-gpt-5", {"gemini_thinking_budget": 2000}),
])
def test_unsupported_controls_are_not_silently_dropped(monkeypatch, model, config):
    calls = post_response(monkeypatch, httpx.Response(200, json=wire()))
    with pytest.raises(ProviderCallError) as failure:
        agent(model=model, runtime_config=ProviderRuntimeConfig(**config)).act(_request())
    assert failure.value.error_kind == "provider_request_rejected" and calls == []


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_error_receipts_no_default_retry_or_private_body(monkeypatch, status, kind):
    calls = post_response(monkeypatch, httpx.Response(
        status, json={"code": "private-code", "message": "private-error fixture-secret"},
        headers={"x-request-id": "request-safe", "set-cookie": "private-cookie"},
    ))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    receipt = selected.last_receipt
    assert receipt["status_code"] == status and receipt["request_id"] == "request-safe"
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert "private" not in json.dumps(receipt) and "fixture-secret" not in str(failure.value)


@pytest.mark.parametrize("change,kind", [
    ({"finish_reason": "length"}, "provider_output_truncated"),
    ({"finish_reason": "content_filter"}, "provider_refused"),
    ({"finish_reason": "tool_calls"}, "provider_request_rejected"),
    ({"finish_reason": "future-unknown"}, "provider_response_schema_mismatch"),
    ({"finish_reason": None}, "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "content": '{"action": 1}', "refusal": "private"}},
     "provider_refused"),
    ({"message": {"role": "assistant", "reasoning": "private", "content": None}},
     "provider_response_schema_mismatch"),
])
def test_semantic_failure_preserves_usage_and_never_accepts_partial_action(
    monkeypatch, change, kind,
):
    payload = wire()
    payload["choices"][0].update(change)
    calls = post_response(monkeypatch, httpx.Response(200, json=payload))
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert "private" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("payload", [
    [], {"output_text": '{"action": 1}'}, {"choices": []},
    {"choices": [{"finish_reason": "stop", "message": {"content": '{"action": 1}'}}]},
])
def test_malformed_envelopes(monkeypatch, payload):
    post_response(monkeypatch, httpx.Response(200, json=payload))
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"


def test_malformed_json_timeout_and_transport_are_not_retried(monkeypatch):
    for fault, kind in (
        (httpx.Response(200, text="private-not-json"), "provider_response_schema_mismatch"),
        (httpx.ReadTimeout("private-timeout"), "provider_timeout"),
        (httpx.ConnectError("private-error"), "provider_transport_error"),
    ):
        calls = post_response(monkeypatch, fault)
        selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
        with pytest.raises((ProviderCallError, TimeoutError)) as failure:
            selected.act(_request())
        assert selected.last_receipt["outcome"] == kind and len(calls) == 1
        assert "private" not in str(failure.value) + json.dumps(selected.last_receipt)


def test_missing_identity_usage_and_cost_are_not_fabricated(monkeypatch):
    payload = wire()
    for key in ("model", "usage", "id"):
        payload.pop(key)
    post_response(monkeypatch, httpx.Response(200, json=payload))
    selected = agent(model="snowflake/catalogue-model-must-not-be-rewritten")
    assert selected.act(_request()).action == 1
    receipt = selected.last_receipt
    assert receipt["model"] == "snowflake/catalogue-model-must-not-be-rewritten"
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None and receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_claude_cached_tokens_does_not_invent_read_write_split(monkeypatch):
    post_response(monkeypatch, httpx.Response(200, json=wire()))
    selected = agent(model="claude-sonnet-4-5")
    selected.act(_request())
    usage = selected.last_receipt["usage"]
    assert usage["cached_input_tokens"] == 3
    assert usage["cache_read_input_tokens"] is None and usage["cache_write_input_tokens"] is None


def test_expired_session_and_http_200_errors_retain_receipts(monkeypatch):
    for payload, kind in (
        ({"code": "390112", "message": "private"}, "provider_auth_failed"),
        ({"error": {"code": "rate_limit_exceeded", "message": "private"}}, "provider_rate_limited"),
    ):
        calls = post_response(monkeypatch, httpx.Response(200, json=payload))
        selected = agent()
        with pytest.raises(ProviderCallError) as failure:
            selected.act(_request())
        assert failure.value.error_kind == kind and len(calls) == 1
        assert selected.last_receipt["status_code"] == 200


def test_explicit_safe_429_retry_and_ambiguous_work_observations(monkeypatch):
    rejection = {"error": {"code": "rate_limit_exceeded", "message": "private"}}
    for payload, expected_attempts in (
        (rejection, 2), ({**rejection, "id": "work-observed"}, 1),
        ({**rejection, "usage": {"prompt_tokens": 1}}, 1),
        ({"code": "429", "message": "private"}, 1),
    ):
        calls = post_response(monkeypatch, httpx.Response(429, json=payload))
        selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
        with pytest.raises(ProviderCallError):
            selected.act(_request())
        assert len(calls) == expected_attempts
        assert [r["attempt_index"] for r in selected.attempt_receipts] == (
            list(range(1, expected_attempts + 1))
        )


def test_shared_bounded_transport_is_used_without_redirects(monkeypatch):
    original_client = httpx.AsyncClient
    seen = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(wire()).encode()

    def handler(request):
        seen.append(request)
        return httpx.Response(200, stream=Stream())

    monkeypatch.setattr(
        "eslams.http_io.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert agent().act(_request()).action == 1
    assert len(seen) == 1 and seen[0].url.path == CHAT_PATH
    assert seen[0].headers["accept-encoding"] == "identity"


def test_error_and_refusal_artifacts_do_not_apply_action_or_leak_private_text(
    monkeypatch, tmp_path,
):
    payload = wire()
    payload["choices"][0]["message"]["refusal"] = "private-response fixture-secret"
    post_response(monkeypatch, httpx.Response(200, json=payload))
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1,
        output_dir=tmp_path, run_id="snowflake-refusal", on_agent_error="invalid-match",
    ))
    assert result.score.integrity_status != "valid"
    receipt_path = result.artifact_path / "receipts/provider_receipts.jsonl"
    assert json.loads(receipt_path.read_text().splitlines()[0])["outcome"] == "provider_refused"
    for path in result.artifact_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert b"fixture-secret" not in content and b"private-response" not in content
            assert b"org-account.snowflakecomputing.com" not in content


def test_schema_rejects_multiple_choices_and_tool_output(monkeypatch):
    payload = wire()
    for altered in (
        {**payload, "choices": payload["choices"] * 2},
        {**payload, "choices": [{**payload["choices"][0], "message": {
            "role": "assistant", "content": '{"action": 1}', "tool_calls": [{"id": "tool"}],
        }}]},
    ):
        post_response(monkeypatch, httpx.Response(200, json=copy.deepcopy(altered)))
        with pytest.raises(ProviderCallError):
            agent().act(_request())
