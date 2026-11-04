"""Offline MiMo raw-wire regressions; no credentials or paid inference required."""

import copy
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.xiaomi import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT, normalize_usage

ALIASES = ("xiaomi", "mimo", "xiaomi-mimo", "XIAOMI_MIMO")
MODEL = "mimo-v2.6-flash"
KEY = "fixture-key-never-persisted"


def fixture():
    path = Path(__file__).parent / "fixtures/provider/xiaomi_chat_completions_success.json"
    return json.loads(path.read_text(encoding="utf-8"))


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_mimo_wire", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="mimo-wire", version="fixture-v1"), active_player="player_1",
        observation={"board": [], "marker": "PRIVATE_PROMPT_SENTINEL"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn_id": index, "action": index % 3} for index in range(70)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(**kwargs):
    return ModelProviderAgent(provider="xiaomi", model=MODEL, api_key_env="MIMO_API_KEY", **kwargs)


def stub(monkeypatch, response):
    calls = []
    monkeypatch.setenv("MIMO_API_KEY", KEY)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_cli_registry_configuration_preflight_and_real_dispatch(monkeypatch, capsys, alias):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))
    assert load_provider_registry().resolve(alias, MODEL).provider == "xiaomi"
    assert main([
        "providers", "preflight", "--provider", alias, "--model", MODEL, "--arena", "tic-tac-toe",
    ]) == 0
    configuration = json.loads(capsys.readouterr().out)
    assert configuration["checks"]["adapter_available"] is True
    assert configuration["readiness"]["inference"] == "not_attempted"
    assert calls == []
    selected = _provider_agent(f"{alias}:{MODEL}")
    assert selected.provider == "xiaomi" and selected.model == MODEL
    assert selected.api_key_env == "MIMO_API_KEY"
    response = selected.act(request())
    assert response.action == 1
    assert response.metadata["provider_receipt"]["provider"] == "xiaomi"
    assert ModelProviderAgent(provider=alias, model=MODEL, api_key_env="MIMO_API_KEY").provider == (
        "xiaomi"
    )


def test_native_request_defaults_history_identity_usage_and_receipt_privacy(monkeypatch):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture(), headers={
        "x-request-id": "req-mimo", "set-cookie": "PRIVATE_HEADER_SENTINEL",
    }))
    selected = agent()
    response = selected.act(request())
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {"api-key": KEY, "Content-Type": "application/json"}
    payload = sent["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == MODEL and payload["stream"] is False
    prompt = json.loads(payload["messages"][1]["content"].splitlines()[-1])
    assert prompt["history"] == request().history
    assert sent["timeout"].read is None and sent["timeout"].connect == 10
    receipt = response.metadata["provider_receipt"]
    assert receipt["endpoint_kind"] == "xiaomi_chat_completions"
    assert receipt["parser_version"] == "xiaomi-chat-completions-raw-v1"
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["request_id"] == "req-mimo"
    assert receipt["usage"] == {
        "input_tokens": 12, "output_tokens": 4, "total_tokens": 16,
        "cached_input_tokens": 3, "cache_read_input_tokens": 3, "cache_write_input_tokens": None,
        "reasoning_tokens": 2, "reasoning_included_in_output": True,
        "cached_input_is_subset": True, "total_tokens_source": "provider",
        "usage_source": "provider", "usage_validation_errors": [],
    }
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(receipt)
    for marker in (KEY, "PRIVATE_REASONING_SENTINEL", "PRIVATE_PROMPT_SENTINEL",
                   "PRIVATE_HEADER_SENTINEL", "api-key", "reasoning_content", "messages"):
        assert marker not in public
    assert len(selected.attempt_receipts) == 1


@pytest.mark.parametrize("reasoning", ["auto", "enabled", "disabled"])
def test_reasoning_is_an_explicit_native_choice_independent_of_arena(monkeypatch, reasoning):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))
    selected = agent(
        runtime_config=ProviderRuntimeConfig(reasoning=reasoning), max_output_tokens=73,
    )
    selected.act(request())
    payload = calls[0][1]["json"]
    assert payload["max_completion_tokens"] == 73
    assert "max_tokens" not in payload
    if reasoning == "auto":
        assert "thinking" not in payload
    else:
        assert payload["thinking"] == {"type": reasoning}


def test_exact_model_and_response_identity_are_never_substituted(monkeypatch):
    payload = fixture()
    payload["model"] = "mimo-provider-revision"
    calls = stub(monkeypatch, httpx.Response(200, json=payload))
    selected = ModelProviderAgent(
        provider="mimo", model="Unlisted:Exact/Model-ID", api_key_env="MIMO_API_KEY",
    )
    response = selected.act(request())
    assert calls[0][1]["json"]["model"] == "Unlisted:Exact/Model-ID"
    assert response.metadata["provider_receipt"]["locked_model_id"] == "mimo-provider-revision"
    payload.pop("model")
    payload.pop("usage")
    stub(monkeypatch, httpx.Response(200, json=payload))
    response = selected.act(request())
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["usage"] == {} and receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("config", [
    {"reasoning_effort": "high"}, {"reasoning_budget_tokens": 100}, {"gemini_thinking_budget": 100},
])
def test_unsupported_reasoning_controls_fail_before_submission(monkeypatch, config):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))
    selected = agent(runtime_config=ProviderRuntimeConfig(**config))
    with pytest.raises(ProviderCallError, match="no request submitted") as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_request_rejected" and calls == []


def test_temperature_requires_explicit_disabled_thinking(monkeypatch):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))
    with pytest.raises(ProviderCallError, match="temperature"):
        agent(temperature=0.2).act(request())
    assert calls == []
    selected = agent(temperature=0.2, runtime_config=ProviderRuntimeConfig(reasoning="disabled"))
    selected.act(request())
    assert calls[0][1]["json"]["temperature"] == 0.2


@pytest.mark.parametrize("reason,expected", [
    ("length", "provider_output_truncated"), ("repetition_truncation", "provider_output_truncated"),
    ("content_filter", "provider_refused"), ("tool_calls", "provider_request_rejected"),
    (None, "provider_response_schema_mismatch"), ("unknown", "provider_response_schema_mismatch"),
    ([], "provider_response_schema_mismatch"),
])
def test_semantic_failure_rejects_legal_partial_text_without_retries(monkeypatch, reason, expected):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = reason
    calls = stub(monkeypatch, httpx.Response(200, json=payload))
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == expected
    assert len(calls) == 1 and len(selected.attempt_receipts) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["outcome"] == expected


@pytest.mark.parametrize("edit", [
    {"refusal": "PRIVATE_REFUSAL_SENTINEL"}, {"content": None},
    {"content": "", "reasoning_content": '{"action": 1}'},
    {"tool_calls": [{"function": {"name": "PRIVATE_TOOL_SENTINEL"}}]},
    {"role": "user"}, {"content": [{"type": "text", "text": '{"action": 1}'}]},
])
def test_message_wire_shape_and_private_reasoning_are_fail_closed(monkeypatch, edit):
    payload = fixture()
    payload["choices"][0]["message"].update(edit)
    calls = stub(monkeypatch, httpx.Response(200, json=payload))
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert len(calls) == 1
    assert "PRIVATE_" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status,expected", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_errors_have_private_receipts_zero_default_retries_and_no_fallback(
    monkeypatch, status, expected,
):
    payload = {"error": {"code": status, "message": f"PRIVATE_ERROR_SENTINEL {KEY}"}}
    calls = stub(monkeypatch, httpx.Response(status, json=payload, headers={
        "x-request-id": "req-error", "Retry-After": "2",
    }))
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == expected and caught.value.status_code == status
    assert len(calls) == 1 and calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    receipt = selected.last_receipt
    assert receipt["request_id"] == "req-error"
    assert receipt["retry_after_ms"] == 2000
    assert receipt["locked_model_id"] is None and receipt["usage"] == {}
    assert "PRIVATE_ERROR_SENTINEL" not in json.dumps(receipt) + str(caught.value)
    assert KEY not in json.dumps(receipt) + str(caught.value)


@pytest.mark.parametrize("response,kind", [
    (httpx.ReadTimeout(f"PRIVATE_TIMEOUT_SENTINEL {KEY}"), "provider_timeout"),
    (httpx.ConnectError(f"PRIVATE_TRANSPORT_SENTINEL {KEY}"), "provider_transport_error"),
    (httpx.Response(200, text=f"PRIVATE_MALFORMED_SENTINEL {KEY}"),
     "provider_response_schema_mismatch"),
    (httpx.Response(200, text='{"choices":[],"choices":[]}'),
     "provider_response_schema_mismatch"),
    (httpx.Response(200, json=[]), "provider_response_schema_mismatch"),
    (httpx.Response(200, json={"output_text": '{"action":1}'}),
     "provider_response_schema_mismatch"),
])
def test_transport_and_malformed_responses_never_replay_ambiguous_work(monkeypatch, response, kind):
    calls = stub(monkeypatch, response)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        selected.act(request())
    assert selected.last_receipt["outcome"] == kind and len(calls) == 1
    assert KEY not in str(caught.value) + json.dumps(selected.last_receipt)
    assert "PRIVATE_" not in str(caught.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize("status", [200, 429])
def test_only_definitive_rate_rejection_can_opt_into_retry(monkeypatch, status):
    calls = stub(monkeypatch, httpx.Response(status, json={
        "error": {"code": 429, "message": "Rate limit exceeded"},
    }, headers={"Retry-After": "0"}))
    monkeypatch.setattr("eslams.agents._sleep_before_retry", lambda *a, **k: None)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert len(calls) == 2
    assert [row["attempt_index"] for row in selected.attempt_receipts] == [1, 2]


@pytest.mark.parametrize("status", [200, 429])
def test_error_body_work_observations_are_quarantined_and_prevent_retry(monkeypatch, status):
    payload = fixture()
    payload["error"] = {"code": 429, "message": "PRIVATE_ERROR_SENTINEL"}
    calls = stub(monkeypatch, httpx.Response(status, json=payload))
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        selected.act(request())
    receipt = selected.last_receipt
    assert len(calls) == 1 and receipt["outcome"] == "provider_rate_limited"
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "PRIVATE_" not in json.dumps(receipt)


@pytest.mark.parametrize("usage,expected,error", [
    ({"prompt_tokens": 5, "completion_tokens": 3}, None, None),
    ({"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 99}, 99,
     "provider_total_tokens_inconsistent"),
    ({"prompt_tokens": True, "completion_tokens": -1, "total_tokens": "8"}, None,
     "prompt_tokens_invalid"),
    ({"prompt_tokens": 5, "prompt_tokens_details": {"cached_tokens": 6}}, None,
     "cached_input_tokens_exceed_input_tokens"),
    ({"completion_tokens": 3, "completion_tokens_details": {"reasoning_tokens": 4}}, None,
     "reasoning_tokens_exceed_inclusive_output_tokens"),
    ({"prompt_tokens_details": []}, None, "prompt_tokens_details_invalid"),
    ({"input_tokens": 100, "output_tokens": 20}, None, None),
])
def test_accounting_keeps_missing_and_malformed_counts_unknown(usage, expected, error):
    normalized = normalize_usage(usage)
    assert normalized["total_tokens"] == expected
    if error:
        assert error in normalized["usage_validation_errors"]
    else:
        assert normalized["usage_validation_errors"] == []


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_live_models_cli_and_live_preflight_are_deterministic(monkeypatch, capsys, alias):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))

    def get(url, *, headers, params, **kwargs):
        assert url == MODELS_ENDPOINT and headers["api-key"] == KEY
        assert "Authorization" not in headers and params == {}
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": MODEL, "object": "model", "owned_by": "xiaomi"},
        ]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert main(["providers", "models", "--provider", alias, "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == [MODEL]
    result = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"] is True
    assert result["checks"]["usage_extraction"] is True and len(calls) == 1


def test_missing_or_invalid_credentials_do_not_submit_or_leak(monkeypatch):
    calls = stub(monkeypatch, httpx.Response(200, json=fixture()))
    for value in ("", "private key with spaces"):
        monkeypatch.setenv("MIMO_API_KEY", value)
        with pytest.raises(ProviderCallError) as caught:
            agent().act(request())
        assert caught.value.error_kind == "provider_auth_failed"
    assert calls == []


def test_models_discovery_classifies_region_denial_and_unknown_models(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", KEY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        403, json={"error": {"message": "PRIVATE_REGION_SENTINEL"}},
    ))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("mimo")
    assert caught.value.status_code == 403 and "PRIVATE_" not in str(caught.value)


def test_ambiguous_choice_arrays_and_stream_chunks_are_rejected(monkeypatch):
    for edit in ({"choices": []}, {"choices": fixture()["choices"] * 2},
                 {"object": "chat.completion.chunk"}):
        payload = copy.deepcopy(fixture())
        payload.update(edit)
        stub(monkeypatch, httpx.Response(200, json=payload))
        with pytest.raises(ProviderCallError) as caught:
            agent().act(request())
        assert caught.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_run_and_public_artifact_privacy(monkeypatch, tmp_path, capsys, alias):
    payload = fixture()
    payload["private_extension"] = "PRIVATE_RESPONSE_SENTINEL"
    calls = stub(monkeypatch, httpx.Response(200, json=payload, headers={
        "set-cookie": "PRIVATE_HEADER_SENTINEL",
    }))
    assert main([
        "run", "--arena", "tic-tac-toe", "--seat-agent", f"player_1={alias}:{MODEL}",
        "--max-turns", "1", "--output-dir", str(tmp_path),
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    artifact = Path(output["artifact"])
    assert ArtifactValidator().validate_report(artifact).valid
    assert len(calls) == 1
    with zipfile.ZipFile(artifact) as archive:
        receipts = archive.read("receipts/provider_receipts.jsonl").decode("utf-8")
        receipt = json.loads(receipts.strip())
        assert receipt["provider"] == "xiaomi" and receipt["locked_model_id"] == MODEL
        assert receipt["usage_complete"] is True and receipt["cost_complete"] is False
        assert receipt["action_applied"] is True
        for name in archive.namelist():
            if Path(name).suffix in {".json", ".jsonl", ".html"}:
                text = archive.read(name).decode("utf-8")
                assert KEY not in text and "PRIVATE_REASONING_SENTINEL" not in text
                assert "PRIVATE_RESPONSE_SENTINEL" not in text
                assert "PRIVATE_HEADER_SENTINEL" not in text
