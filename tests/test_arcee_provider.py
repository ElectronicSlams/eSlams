"""Deterministic Arcee raw-wire tests; no credentials or live inference.

Envelope provenance: https://docs.arcee.ai/api-reference/chat-completion
and https://docs.arcee.ai/get-started/quick-start (2026-11-04).
The fixture instantiates the documented OpenAI-compatible standard envelope,
with synthetic redacted IDs/content/counts; it is not a captured paid request.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.arcee import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT

MODEL = "zai-org/glm-5.3-flash"
FIXTURE = Path(__file__).parent / "fixtures/provider/arcee_chat_completions_success.json"


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_arcee", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="arcee-wire", version="fixture-v1"), active_player="player_1",
        observation={"private_marker": "PRIVATE_PROMPT"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"}, history=[{"turn": i} for i in range(60)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(**kwargs):
    return ModelProviderAgent(
        provider="arcee-ai", model=MODEL, api_key_env="ARCEE_API_KEY", **kwargs,
    )


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("ARCEE_API_KEY", "rcai-fixture-credential")
    payload = json.loads(FIXTURE.read_text())
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200, json=copy.deepcopy(payload), headers={"x-request-id": "req-arcee"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return payload, calls


def test_success_exact_wire_history_accounting_and_privacy(wire):
    payload, calls = wire
    payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 2}
    payload["usage"]["cost"] = 999  # Undocumented cost fields are not billing evidence.
    a = agent()
    # Even a catalogue entry with pricing must not price a different service.
    a.capabilities = replace(a.capabilities, pricing={"input": 1, "output": 2})
    result = a.act(request())
    assert result.action == 1
    url, kwargs = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert kwargs["headers"] == {
        "Authorization": "Bearer rcai-fixture-credential", "Content-Type": "application/json",
    }
    body = kwargs["json"]
    assert body["model"] == MODEL
    assert body["stream"] is False
    assert set(body) == {"model", "messages", "stream"}
    assert '"turn": 0' in body["messages"][1]["content"]
    assert '"turn": 59' in body["messages"][1]["content"]
    assert kwargs["timeout"].read is None and kwargs["timeout"].pool is None
    receipt = a.last_receipt
    assert receipt["provider"] == "arcee-ai"
    assert receipt["model"] == receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "arcee_chat_completions"
    assert receipt["parser_version"] == "arcee-chat-completions-raw-v1"
    assert receipt["request_id"] == "req-arcee"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_tokens"] == 2
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(a.attempt_receipts) == 1
    public = json.dumps(result.to_dict())
    for private in (
        "PRIVATE_PROMPT", "PRIVATE_REASONING", "rcai-fixture-credential", "Authorization",
    ):
        assert private not in public


def test_explicit_limits_and_unknown_model_are_preserved(wire):
    _, calls = wire
    a = agent(max_output_tokens=777, temperature=0.3)
    a.model = "Exact/Unlisted:Revision"
    a.act(request())
    assert calls[0][1]["json"]["max_tokens"] == 777
    assert calls[0][1]["json"]["temperature"] == 0.3
    assert calls[0][1]["json"]["model"] == "Exact/Unlisted:Revision"
    assert a.last_receipt["locked_model_id"] == MODEL


def test_ambiguous_arcee_rate_limit_is_not_replayed_even_when_opted_in(monkeypatch, wire):
    calls = []

    def post(*args, **kwargs):
        calls.append(args)
        return httpx.Response(429, json={"detail": "rate limit"}, headers={"Retry-After": "2"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.retry_permitted is False
    assert len(calls) == len(a.attempt_receipts) == 1


def test_missing_credentials_never_submit(monkeypatch):
    monkeypatch.delenv("ARCEE_API_KEY", raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    a = agent()
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == "provider_auth_failed"
    assert a.last_receipt["usage"] == {}


def test_malformed_usage_is_flagged(wire):
    payload, _ = wire
    payload["usage"]["prompt_tokens"] = True
    a = agent()
    a.act(request())
    assert a.last_receipt["usage"]["input_tokens"] is None
    assert a.last_receipt["usage"]["usage_validation_errors"]


@pytest.mark.parametrize("field", ["model", "usage"])
def test_missing_identity_or_usage_stays_unknown(wire, field):
    payload, _ = wire
    payload.pop(field)
    a = agent()
    a.act(request())
    if field == "model":
        assert a.last_receipt["locked_model_id"] is None
        assert a.last_receipt["model_identity_source"] is None
    else:
        assert a.last_receipt["usage"] == {}
        assert a.last_receipt["usage_unavailable_reason"] == "provider_usage_absent"


@pytest.mark.parametrize(("change", "kind"), [
    ({"finish_reason": "length"}, "provider_output_truncated"),
    ({"finish_reason": "content_filter"}, "provider_refused"),
    ({"finish_reason": "tool_calls"}, "provider_request_rejected"),
    ({"finish_reason": None}, "provider_response_schema_mismatch"),
    ({"finish_reason": []}, "provider_response_schema_mismatch"),
    ({"finish_reason": "PRIVATE_UNKNOWN"}, "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "refusal": "PRIVATE_REFUSAL", "content": "{\"action\":1}"}},
     "provider_refused"),
    ({"message": {"role": "assistant", "reasoning": "{\"action\":1}"}},
     "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "content": 1}}, "provider_response_schema_mismatch"),
    ({"error": {"code": 500}}, "provider_unavailable"),
])
def test_semantic_failures_preserve_receipts(wire, change, kind):
    payload, calls = wire
    payload["choices"][0].update(change)
    a = agent()
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == kind
    assert a.last_receipt["outcome"] == kind
    assert a.last_receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1
    assert "PRIVATE_" not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422, 429, 500, 503])
def test_http_errors_are_sanitized_single_attempt(monkeypatch, status):
    monkeypatch.setenv("ARCEE_API_KEY", "rcai-fixture-credential")
    calls = []

    def post(*args, **kwargs):
        calls.append(args)
        return httpx.Response(status, json={"detail": "PRIVATE_ERROR rcai-fixture-credential"},
                              headers={"Retry-After": "2", "x-request-id": "req-failure"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent()
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.status_code == status
    assert a.last_receipt["status_code"] == status
    assert a.last_receipt["request_id"] == "req-failure"
    assert a.last_receipt["provider"] == "arcee-ai"
    assert len(calls) == 1
    if status == 429:
        assert error.value.error_kind == "provider_rate_limited"
        assert a.last_receipt["retry_after_ms"] == 2000
    assert "PRIVATE_ERROR" not in str(error.value) + json.dumps(a.last_receipt)


@pytest.mark.parametrize("mode", ["timeout", "transport", "json", "array", "choices", "error200"])
def test_transport_and_malformed_bodies(monkeypatch, wire, mode):
    def post(*args, **kwargs):
        if mode == "timeout":
            raise httpx.ReadTimeout("PRIVATE_ERROR")
        if mode == "transport":
            raise httpx.ConnectError("PRIVATE_ERROR")
        if mode == "json":
            return httpx.Response(200, text="PRIVATE_ERROR")
        return httpx.Response(200, json={
            "array": [], "choices": {"choices": []},
            "error200": {"error": {"code": 429, "message": "PRIVATE_ERROR"}},
        }[mode])

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent()
    with pytest.raises((ProviderCallError, TimeoutError)):
        a.act(request())
    assert len(a.attempt_receipts) == 1
    assert "PRIVATE_ERROR" not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("controls", [
    {"reasoning": "disabled"}, {"reasoning": "enabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 100}, {"gemini_thinking_budget": 100},
    {"openrouter_provider_order": ("some-backend",)},
])
def test_unsupported_controls_fail_before_submission(wire, controls):
    _, calls = wire
    with pytest.raises(ProviderCallError, match="native reasoning defaults"):
        agent(runtime_config=ProviderRuntimeConfig(**controls)).act(request())
    assert not calls


@pytest.mark.parametrize("alias", ["arcee", "arcee-ai", "arcee_ai", "ARCEE-AI"])
def test_aliases_cli_preflight_dispatch_and_discovery(monkeypatch, wire, capsys, alias):
    a = _provider_agent(f"{alias}:{MODEL}")
    assert a.provider == "arcee-ai" and a.api_key_env == "ARCEE_API_KEY"
    assert a.act(request()).action == 1
    direct = ModelProviderAgent(provider=alias, model=MODEL, api_key_env="ARCEE_API_KEY")
    assert direct.provider == "arcee-ai"
    assert provider_preflight(alias, MODEL, "tic-tac-toe")["checks"]["adapter_available"] is True

    def get(url, **kwargs):
        assert url == MODELS_ENDPOINT
        assert kwargs["headers"]["Authorization"] == "Bearer rcai-fixture-credential"
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == [MODEL]
    assert provider_preflight(alias, MODEL, "tic-tac-toe", live=True)["ok"] is True
    assert main(["providers", "models", "--provider", alias, "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == [MODEL]
    with pytest.raises(ValueError, match="explicit exact model"):
        _provider_agent(alias)
