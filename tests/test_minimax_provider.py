"""Keyless raw-wire MiniMax contract and integration regressions."""

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
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
from eslams.providers.minimax import (
    _CONVERSATION,
    API_KEY_ENV,
    CHAT_COMPLETIONS_ENDPOINT,
    DEFAULT_MODEL,
)
from eslams.runner import RunConfig, Runner


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "minimax_chat_completions_success.json").read_text())


def agent(**runtime):
    return ModelProviderAgent("minimax", DEFAULT_MODEL, API_KEY_ENV,
                              runtime_config=ProviderRuntimeConfig(**runtime))


def mock_wire(monkeypatch, body, status=200, headers=None):
    monkeypatch.setenv(API_KEY_ENV, "synthetic-minimax-secret")
    calls = []

    def post(url, **kwargs):
        calls.append((url, copy.deepcopy(kwargs)))
        return httpx.Response(status, json=body, headers=headers,
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_native_wire_defaults_full_history_and_usage(monkeypatch):
    calls = mock_wire(monkeypatch, wire())
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      history=[{"turn": n} for n in range(80)],
                      metadata={"model_execution_policy": model_execution_policy(None)})
    adapter = agent()
    result = adapter.act(request)
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {"Authorization": "Bearer synthetic-minimax-secret",
                               "Content-Type": "application/json"}
    payload = sent["json"]
    assert set(payload) == {"model", "messages", "stream", "reasoning_split"}
    assert payload["model"] == DEFAULT_MODEL and payload["stream"] is False
    assert payload["reasoning_split"] is True
    assert len(json.loads(payload["messages"][1]["content"].rsplit("\n", 1)[1])["history"]) == 80
    assert sent["timeout"].read is None and sent["timeout"].connect == 10
    receipt = result.metadata["provider_receipt"]
    assert result.action == 1 and receipt["provider"] == "minimax"
    assert receipt["endpoint_kind"] == "minimax_chat_completions"
    assert receipt["parser_version"] == "minimax-chat-completions-raw-v1"
    assert receipt["locked_model_id"] == DEFAULT_MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_tokens"] == 2
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "synthetic-private" not in json.dumps(result.to_dict())
    assert "synthetic-minimax-secret" not in json.dumps(result.to_dict())
    assert _CONVERSATION.get() is None


@pytest.mark.parametrize("mode", ["auto", "enabled", "disabled"])
def test_reasoning_modes_honor_forced_thinking_without_game_specific_policy(monkeypatch, mode):
    calls = mock_wire(monkeypatch, wire())
    adapter = agent(reasoning=mode)
    adapter.temperature = 0.2
    if mode == "disabled":
        with pytest.raises(ProviderCallError, match="cannot be disabled"):
            adapter.act(_request(arena_id="chess"))
        assert not calls
        return
    adapter.act(_request(arena_id="chess"))
    controls = {"reasoning_effort", "temperature", "top_p"}
    assert not (controls & calls[0][1]["json"].keys())
    if mode == "enabled":
        assert calls[0][1]["json"]["thinking"] == {"type": "adaptive"}
    else:
        assert "thinking" not in calls[0][1]["json"]


@pytest.mark.parametrize("model", [DEFAULT_MODEL, "future-model:revision"])
def test_explicit_output_and_supported_effort_preserve_exact_model(monkeypatch, model):
    body = wire()
    body["model"] = model
    calls = mock_wire(monkeypatch, body)
    effort = "high" if model == DEFAULT_MODEL else None
    adapter = ModelProviderAgent("minimax", model, API_KEY_ENV,
        max_output_tokens=12345, runtime_config=ProviderRuntimeConfig(reasoning_effort=effort))
    adapter.act(_request())
    payload = calls[0][1]["json"]
    assert payload["max_completion_tokens"] == 12345
    assert payload.get("reasoning_effort") == effort and payload["model"] == model
    assert "max_tokens" not in payload


def test_repair_preserves_complete_assistant_reasoning_then_clears_memory(monkeypatch):
    body = wire()
    body["choices"][0]["message"].update(content="invalid action text",
        reasoning_details=[{"type": "reasoning.text", "text": "synthetic-private-details"}])
    first_message = copy.deepcopy(body["choices"][0]["message"])
    calls = mock_wire(monkeypatch, body)
    # Change only after the first returned response has been consumed.
    original = __import__("eslams.agents", fromlist=["bounded_post"]).bounded_post

    def post(*args, **kwargs):
        result = original(*args, **kwargs)
        body["choices"][0]["message"]["content"] = '{"action":1}'
        return result

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    adapter = agent(action_repair_attempts=1)
    result = adapter.act(_request())
    assert len(calls) == 2 and result.action == 1
    assert calls[1][1]["json"]["messages"][2] == first_message
    assert len(calls[1][1]["json"]["messages"]) == 4
    assert [r["attempt_kind"] for r in adapter.attempt_receipts] == ["primary", "action_repair"]
    assert "synthetic-private" not in json.dumps(result.to_dict())
    assert _CONVERSATION.get() is None
    adapter.act(_request())
    assert len(calls[2][1]["json"]["messages"]) == 2


@pytest.mark.parametrize("code,kind", [
    (1002, "provider_rate_limited"), (1004, "provider_auth_failed"),
    (2049, "provider_auth_failed"), (1008, "provider_request_rejected"),
    (2013, "provider_request_rejected"), (2022, "provider_unavailable"),
    (2069, "provider_unavailable"), (1026, "provider_refused"), (1027, "provider_refused"),
    (1000, "provider_unavailable"), (1001, "provider_timeout"),
    (1024, "provider_unavailable"), (1033, "provider_unavailable"),
    (2064, "provider_unavailable"), (2066, "provider_timeout"),
    (2056, "provider_request_rejected"), (9999, "provider_request_rejected"),
])
@pytest.mark.parametrize("http_status", [200, 400])
def test_native_errors_are_classified_without_raw_message_or_action_repair(
    monkeypatch, code, kind, http_status,
):
    calls = mock_wire(monkeypatch, {"base_resp": {"status_code": code,
        "status_msg": "synthetic-private-error synthetic-minimax-secret"}}, http_status,
        {"x-request-id": "synthetic-http-id", "cf-aig-request-id": "synthetic-gateway-id"})
    adapter = agent(max_retries=0, action_repair_attempts=1)
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    row = adapter.last_receipt
    assert row["status_code"] == http_status and row["provider_error_code"] == code
    assert row["request_id"] == "synthetic-http-id"
    assert row["gateway_request_id"] == "synthetic-gateway-id"
    assert row["estimated_cost"]["status"] == "cost_unavailable"
    assert row["locked_model_id"] is None and row["usage"] == {}
    assert "synthetic-private-error" not in str(caught.value) + json.dumps(row)
    assert "synthetic-minimax-secret" not in str(caught.value) + json.dumps(row)


@pytest.mark.parametrize("status", [200, 429])
def test_bare_rate_rejection_retries_only_with_explicit_policy(monkeypatch, status):
    calls = mock_wire(monkeypatch, {"base_resp": {"status_code": 1002, "status_msg": "rate"}},
                      status, {"Retry-After": "0"})
    adapter = agent(max_retries=1, retry_backoff_ms=0, retry_jitter=False)
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(_request())
    assert caught.value.retry_permitted and len(calls) == 2
    assert len(adapter.attempt_receipts) == 2
    assert all(r["status_code"] == status for r in adapter.attempt_receipts)
    assert all(r["retry_after_ms"] == 0 for r in adapter.attempt_receipts)
    assert caught.value.retry_after_seconds == 0
    assert calls[0][1]["json"] == calls[1][1]["json"]


@pytest.mark.parametrize("extra", [
    {"id": "observed-generation"}, {"id": None}, {"usage": {}},
    {"usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}},
    {"cost": 0}, {"usage": {"cost": 0}}, {"choices": []},
    {"error": {"code": 401}}, {"unknown": "extension"},
])
@pytest.mark.parametrize("status", [200, 429, 503])
def test_ambiguous_or_observed_rate_work_is_never_retried(monkeypatch, extra, status):
    calls = mock_wire(monkeypatch, {"base_resp": {"status_code": 1002}, **extra}, status)
    adapter = agent(max_retries=1, retry_backoff_ms=0)
    with pytest.raises(ProviderCallError):
        adapter.act(_request())
    assert len(calls) == 1
    row = adapter.last_receipt
    assert row["estimated_cost"]["status"] == "cost_unavailable"
    assert row["locked_model_id"] is None
    if "usage" in extra and extra["usage"].get("total_tokens"):
        assert row["usage"]["total_tokens"] == 16
        assert row["pricing_provenance"]["accounting_status"] == "quarantined"


@pytest.mark.parametrize("mutation,kind", [
    ("length", "provider_output_truncated"), ("filter", "provider_refused"),
    ("input_sensitive", "provider_refused"), ("output_sensitive", "provider_refused"),
    ("refusal", "provider_refused"), ("mismatch", "provider_request_rejected"),
    ("bad_base", "provider_response_schema_mismatch"),
    ("boolean_code", "provider_response_schema_mismatch"),
    ("missing_finish", "provider_response_schema_mismatch"),
    ("unknown_finish", "provider_response_schema_mismatch"),
    ("bad_choice", "provider_response_schema_mismatch"),
    ("bad_message", "provider_response_schema_mismatch"),
    ("inline_thinking", "provider_response_schema_mismatch"),
    ("tool_calls", "provider_response_schema_mismatch"),
])
def test_noncomplete_or_malformed_wire_never_accepts_legal_looking_action(
    monkeypatch, mutation, kind,
):
    body = wire()
    choice = body["choices"][0]
    if mutation == "length":
        choice["finish_reason"] = "length"
    elif mutation == "filter":
        choice["finish_reason"] = "content_filter"
    elif mutation in {"input_sensitive", "output_sensitive"}:
        body[mutation] = True
    elif mutation == "refusal":
        choice["message"]["refusal"] = "synthetic-private-refusal"
    elif mutation == "mismatch":
        body["model"] = "different-model"
    elif mutation == "bad_base":
        body["base_resp"] = "synthetic-private-base"
    elif mutation == "boolean_code":
        body["base_resp"]["status_code"] = False
    elif mutation == "missing_finish":
        choice.pop("finish_reason")
    elif mutation == "unknown_finish":
        choice["finish_reason"] = "synthetic-private-finish"
    elif mutation == "bad_choice":
        body["choices"] = [{}]
    elif mutation == "bad_message":
        choice["message"]["content"] = [{"text": '{"action":1}'}]
    elif mutation == "inline_thinking":
        choice["message"]["content"] = '<think>{"action":1}</think>'
    else:
        choice["message"]["tool_calls"] = [{"id": "synthetic-tool"}]
    calls = mock_wire(monkeypatch, body)
    adapter = agent(max_retries=1, action_repair_attempts=1)
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert adapter.last_receipt["usage"]["total_tokens"] == 16
    assert "synthetic-private" not in str(caught.value) + json.dumps(adapter.last_receipt)


def test_missing_identity_usage_and_cost_remain_unknown(monkeypatch):
    body = wire()
    body.pop("model")
    body.pop("usage")
    mock_wire(monkeypatch, body)
    adapter = agent()
    assert adapter.act(_request()).action == 1
    row = adapter.last_receipt
    assert row["locked_model_id"] is None and row["model_identity_source"] is None
    assert row["usage"] == {} and row["usage_unavailable_reason"] == "provider_usage_absent"
    assert row["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("body", [
    b"not-json", b"[]", b'{"base_resp":{"status_code":1002,"status_code":0}}',
    b'{"base_resp":{"status_code":1002},"usage":{"cost":NaN}}',
    b'{"choices":',
])
@pytest.mark.parametrize("status", [200, 429])
def test_malformed_or_partial_json_never_retried(monkeypatch, body, status):
    monkeypatch.setenv(API_KEY_ENV, "synthetic-minimax-secret")
    calls = []

    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(status, content=body, headers={"x-request-id": "wire-error"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    adapter = agent(max_retries=1)
    with pytest.raises(ProviderCallError):
        adapter.act(_request())
    assert len(calls) == 1 and adapter.last_receipt["status_code"] == status
    assert adapter.last_receipt["request_id"] == "wire-error"
    assert adapter.last_receipt["locked_model_id"] is None
    assert adapter.last_receipt["usage"] == {}


@pytest.mark.parametrize("status,kind", [(401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (429, "provider_rate_limited"),
    (500, "provider_unavailable")])
def test_http_errors_keep_status_and_never_replay_unverified_body(monkeypatch, status, kind):
    calls = mock_wire(monkeypatch, {"message": "synthetic-private-http-error"}, status)
    adapter = agent(max_retries=1)
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(_request())
    assert len(calls) == 1 and caught.value.error_kind == kind
    assert "synthetic-private" not in str(caught.value) + json.dumps(adapter.last_receipt)


def test_explicit_regional_endpoint_is_never_inferred_from_key(monkeypatch):
    calls = mock_wire(monkeypatch, wire())
    adapter = agent(gateway_base_url="https://api.minimax.cn", gateway_mode="generic_base_url")
    adapter.act(_request())
    assert calls[0][0] == "https://api.minimax.cn/v1/chat/completions"
    assert adapter.last_receipt["gateway_mode"] == "generic_base_url"


def test_failed_repair_clears_private_reasoning_and_retains_attempts(monkeypatch):
    body = wire()
    body["choices"][0]["message"]["content"] = "invalid action"
    calls = mock_wire(monkeypatch, body)
    adapter = agent(action_repair_attempts=1)
    with pytest.raises(ProviderCallError):
        adapter.act(_request())
    assert len(calls) == 2 and len(adapter.attempt_receipts) == 2
    assert _CONVERSATION.get() is None
    assert "synthetic-private" not in json.dumps(adapter.attempt_receipts)


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1},
    {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 1},
    {"prompt_tokens": 12, "completion_tokens": 4, "completion_tokens_details":
        {"reasoning_tokens": 5}, "total_tokens": 16},
    {"prompt_tokens": 12, "completion_tokens": 4, "prompt_tokens_details": []},
])
def test_malformed_usage_is_retained_as_incomplete_accounting(monkeypatch, usage):
    body = wire()
    body["usage"] = usage
    mock_wire(monkeypatch, body)
    adapter = agent()
    adapter.act(_request())
    assert adapter.last_receipt["usage"]["usage_validation_errors"]
    assert adapter.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_concurrent_invocations_keep_repair_reasoning_in_their_own_context(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, "synthetic-minimax-secret")
    barrier = threading.Barrier(2)
    repaired = []

    def post(url, **kwargs):
        messages = kwargs["json"]["messages"]
        original_prompt = messages[1]["content"]
        marker = "seat-alpha" if "seat-alpha" in original_prompt else "seat-beta"
        body = wire()
        if len(messages) == 2:
            barrier.wait(timeout=5)
            body["choices"][0]["message"].update(
                content="invalid action", reasoning_content=marker,
            )
        else:
            assert len(messages) == 4
            assert messages[2]["reasoning_content"] == marker
            repaired.append(marker)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    adapter = agent(action_repair_attempts=1, concurrency_limit=2)
    requests = [replace(_request(), observation={"marker": marker})
                for marker in ("seat-alpha", "seat-beta")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(adapter.act, requests))
    assert all(result.action == 1 for result in results)
    assert sorted(repaired) == ["seat-alpha", "seat-beta"]
    assert _CONVERSATION.get() is None


@pytest.mark.parametrize("provider", ["minimax", "MiniMax", "MINIMAX"])
def test_namespace_consistent_in_registry_cli_preflight_and_dispatch(monkeypatch, provider):
    mock_wire(monkeypatch, wire())
    record = load_provider_registry().resolve(provider, DEFAULT_MODEL)
    assert record.provider == "minimax" and record.known
    adapter = _provider_agent(provider + ":" + DEFAULT_MODEL)
    assert adapter.provider == "minimax" and adapter.api_key_env == API_KEY_ENV
    assert adapter.act(_request()).action == 1
    direct = ModelProviderAgent(provider, DEFAULT_MODEL, API_KEY_ENV)
    assert direct.act(_request()).action == 1 and direct.provider == "minimax"
    configured = provider_preflight(provider, DEFAULT_MODEL, "tic-tac-toe")
    assert configured["ok"] and configured["checks"]["adapter_available"]
    assert configured["checks"]["registry_entry"]
    assert provider_models_live(provider) is None


def test_configuration_cli_does_not_make_network_calls(monkeypatch, capsys):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("live call"))
    assert main(["providers", "preflight", "--provider", "minimax", "--model", DEFAULT_MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["preflight_mode"] == "configuration_only" and result["ok"]
    assert not result["checks"]["api_key_configured"]
    assert not result["checks"]["minimal_inference"]


def test_refused_run_artifact_keeps_usage_without_reasoning_or_applied_action(
    tmp_path, monkeypatch,
):
    body = wire()
    body["output_sensitive"] = True
    calls = mock_wire(monkeypatch, body)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(), output_dir=tmp_path))
    assert len(calls) == 1 and not result.score.match_valid_for_scoring
    rows = [json.loads(line) for line in (result.expanded_path /
            "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and not rows[0]["action_applied"]
    assert rows[0]["usage"]["total_tokens"] == 16 and rows[0]["outcome"] == "provider_refused"
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert b"synthetic-private-minimax-reasoning" not in path.read_bytes()
            assert b"synthetic-minimax-secret" not in path.read_bytes()
