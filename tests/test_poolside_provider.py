"""Offline Poolside wire regressions; provenance and unknowns: docs/POOLSIDE.md."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.poolside import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

MODEL = "poolside/laguna-s-2.1"
ALIASES = ("poolside", "poolside-ai", "poolsideai", "POOLSIDE_AI")
FIXTURE = Path(__file__).parent / "fixtures/provider/poolside_chat_completions_success.json"


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="poolside_test", episode_id="episode_001",
        turn_id=100, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="poolside_test", version="1.0.0"), active_player="player_1",
        observation={"private_marker": "PROMPT_SENTINEL"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn": i, "action": i % 3} for i in range(100)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def fixture():
    return json.loads(FIXTURE.read_text())


def agent(provider="poolside", **kwargs):
    return ModelProviderAgent(provider, MODEL, "POOLSIDE_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch):
    monkeypatch.setenv("POOLSIDE_API_KEY", "fixture-secret-never-persisted")
    monkeypatch.setattr(
        "eslams.agents.bounded_post", lambda *a, **k: pytest.fail("unexpected POST"),
    )
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("unexpected GET"))


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_cli_preflight_dispatch_and_models(monkeypatch, capsys, alias):
    posts = []

    def post(url, *, headers, json, timeout):
        posts.append(json)
        assert url == CHAT_COMPLETIONS_ENDPOINT
        assert headers["Authorization"] == "Bearer fixture-secret-never-persisted"
        assert json["model"] == MODEL
        assert json["stream"] is False
        assert "max_tokens" not in json
        assert "temperature" not in json
        assert "provider" not in json
        assert "chat_template_kwargs" not in json
        assert timeout.read is None
        return httpx.Response(200, json=fixture(), headers={"x-request-id": "req-poolside"})

    def get(url, *, headers, params, timeout):
        assert url == MODELS_ENDPOINT
        assert headers["Authorization"] == "Bearer fixture-secret-never-persisted"
        assert params == {}
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    monkeypatch.setattr(httpx, "get", get)
    parsed = _provider_agent(f"{alias}:{MODEL}")
    assert parsed.provider == "poolside" and parsed.model == MODEL
    assert load_provider_registry().resolve(alias, MODEL).provider == "poolside"
    response = parsed.act(request())
    assert response.action == 1
    assert agent(alias).act(request()).action == 1
    prompt = posts[0]["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request().history
    assert provider_models_live(alias) == [MODEL]
    offline = provider_preflight(alias, MODEL, "tic-tac-toe")
    assert offline["ok"] and offline["checks"]["adapter_available"]
    live = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert live["ok"] and live["checks"]["usage_extraction"]
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["providers", "models", "--provider", alias, "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == [MODEL]


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("suffix", ["", ":", ":   "])
def test_cli_never_selects_a_default_model(alias, suffix):
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent(alias + suffix)


@pytest.mark.parametrize("model", ["", "   "])
def test_transport_rejects_blank_model_without_submission(model):
    selected = ModelProviderAgent("poolside", model, "POOLSIDE_API_KEY")
    with pytest.raises(ProviderCallError, match="explicit model"):
        selected.act(request())
    assert selected.last_receipt["outcome"] == "provider_request_rejected"


@pytest.mark.parametrize("mode,expected", [("auto", None), ("enabled", True), ("disabled", False)])
def test_thinking_controls_are_explicit_and_not_game_dependent(monkeypatch, mode, expected):
    def post(url, *, headers, json, timeout):
        if expected is None:
            assert "chat_template_kwargs" not in json
        else:
            assert json["chat_template_kwargs"] == {"enable_thinking": expected}
        assert json["temperature"] == 0.25
        assert json["max_tokens"] == 4567
        return httpx.Response(200, json=fixture())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(temperature=0.25, max_output_tokens=4567,
                     runtime_config=ProviderRuntimeConfig(reasoning=mode))
    for arena_id in ("tic-tac-toe", "chess"):
        req = replace(request(), arena=ArenaIdentity(id=arena_id, version="1.0.0"))
        assert selected.act(req).action == 1


@pytest.mark.parametrize("control", [
    {"reasoning_effort": "high"}, {"reasoning_budget_tokens": 100}, {"gemini_thinking_budget": 10},
])
def test_unsupported_controls_reject_before_network(control):
    selected = agent(runtime_config=ProviderRuntimeConfig(**control))
    with pytest.raises(ProviderCallError, match="thinking on/off"):
        selected.act(request())
    assert selected.last_receipt["outcome"] == "provider_request_rejected"


def test_success_receipt_and_reasoning_privacy(monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=fixture(),
        headers={"x-request-id": "req-poolside", "set-cookie": "COOKIE_SENTINEL"},
    ))
    selected = agent()
    # Even an existing broker catalogue row cannot attest native hosted pricing.
    selected.capabilities = replace(selected.capabilities, pricing={"input": "1", "output": "2"})
    response = selected.act(request())
    receipt = selected.last_receipt
    assert receipt["provider"] == "poolside" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "poolside_chat_completions"
    assert receipt["parser_version"] == "poolside-chat-completions-raw-v1"
    assert receipt["request_id"] == "req-poolside"
    assert receipt["usage"]["input_tokens"] == 447
    assert receipt["usage"]["output_tokens"] == 88
    assert receipt["usage"]["total_tokens"] == 535
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(selected.attempt_receipts) == 1 and receipt["attempt_index"] == 1
    serialized = json.dumps(response.to_dict())
    for private in ("PRIVATE_REASONING_SENTINEL", "PROMPT_SENTINEL", "COOKIE_SENTINEL",
                    "fixture-secret-never-persisted", "Authorization"):
        assert private not in serialized


@pytest.mark.parametrize("wire_model", [None, "poolside/laguna-xs-2.1"])
def test_identity_is_only_observed_never_inferred(monkeypatch, wire_model):
    payload = fixture()
    payload["model"] = wire_model
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=payload,
    ))
    selected = agent()
    selected.act(request())
    assert selected.last_receipt["model"] == MODEL
    assert selected.last_receipt["locked_model_id"] == wire_model
    assert selected.last_receipt["model_identity_source"] == (
        "provider_response" if wire_model else None
    )


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 4},
    {"prompt_tokens": 4, "completion_tokens": 2},
    {"prompt_tokens": -1, "completion_tokens": True, "total_tokens": "6"},
    {"input_tokens": 4, "output_tokens": 2, "cost": 0, "reasoning_tokens": 2},
])
def test_missing_or_invalid_accounting_is_not_fabricated(monkeypatch, usage):
    payload = fixture()
    payload["usage"] = usage
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=payload,
    ))
    selected = agent()
    selected.act(request())
    receipt = selected.last_receipt
    assert receipt["usage"].get("total_tokens") is None
    assert receipt["usage"].get("reasoning_tokens") is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"), (503, "provider_unavailable"),
])
def test_http_errors_are_private_and_never_replayed(monkeypatch, status, kind):
    calls = []

    def post(*a, **k):
        calls.append(1)
        return httpx.Response(status, json={"error": {
            "type": "rate_limit_error", "message": "ERROR_SENTINEL fixture-secret-never-persisted",
        }}, headers={"Retry-After": "3", "x-request-id": "req-error"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1
    assert selected.last_receipt["status_code"] == status
    assert caught.value.retry_after_seconds == 3
    assert selected.last_receipt["retry_after_ms"] == 3000
    assert selected.last_receipt["request_id"] == "req-error"
    assert selected.last_receipt["locked_model_id"] is None
    assert "ERROR_SENTINEL" not in str(caught.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize("reason,refusal,kind", [("length", None, "provider_output_truncated"),
    ("content_filter", None, "provider_refused"), ("stop", "REFUSAL_SENTINEL", "provider_refused"),
    ("tool_calls", None, "provider_request_rejected"),
    (None, None, "provider_response_schema_mismatch"),
    ("future-reason", None, "provider_response_schema_mismatch"),
])
def test_semantic_failures_reject_legal_looking_text(monkeypatch, reason, refusal, kind):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = reason
    payload["choices"][0]["message"]["refusal"] = refusal
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=payload,
    ))
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == kind
    assert selected.last_receipt["usage"]["total_tokens"] == 535
    assert "REFUSAL_SENTINEL" not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("body", [
    b"not json PRIVATE_SENTINEL", b"[]", b'{"choices":[],"choices":[]}',
    b'{"choices":[]}', b'{"choices":[{}]}', b'{"output_text":"{\\"action\\":1}"}',
])
def test_malformed_raw_wire_never_becomes_action(monkeypatch, body):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, content=body,
    ))
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(selected.attempt_receipts) == 1
    assert "PRIVATE_SENTINEL" not in str(caught.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize("error", [httpx.ReadTimeout("PRIVATE_SENTINEL"),
                                  httpx.ConnectError("PRIVATE_SENTINEL")])
def test_transport_failures_preserve_one_attempt(monkeypatch, error):
    calls = []

    def post(*a, **k):
        calls.append(1)
        raise error

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((TimeoutError, ProviderCallError)) as caught:
        selected.act(request())
    assert len(calls) == 1 and len(selected.attempt_receipts) == 1
    assert "PRIVATE_SENTINEL" not in str(caught.value) + json.dumps(selected.last_receipt)


def test_body_error_and_unparseable_action_are_not_retried(monkeypatch):
    for payload, kind in [
        ({"error": {"code": 429, "message": "PRIVATE_SENTINEL"}}, "provider_rate_limited"),
        (fixture(), "action_response_unparseable"),
    ]:
        payload = copy.deepcopy(payload)
        if "choices" in payload:
            payload["choices"][0]["message"]["content"] = "invalid action"
        calls = []

        def post(*a, calls=calls, payload=payload, **k):
            calls.append(1)
            return httpx.Response(200, json=payload)

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        selected = agent()
        with pytest.raises(ProviderCallError) as caught:
            selected.act(request())
        assert caught.value.error_kind == kind and len(calls) == 1


@pytest.mark.parametrize("key", [None, "  ", "bad key", "bad\nkey"])
def test_credentials_are_required_and_validated_without_leaking(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("POOLSIDE_API_KEY")
    else:
        monkeypatch.setenv("POOLSIDE_API_KEY", key)
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(request())
    assert caught.value.error_kind == "provider_auth_failed"
    assert not selected.last_receipt["usage"]


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_models_discovery_errors_are_explicit(monkeypatch, status):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        status, text="PRIVATE_SENTINEL",
    ))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("poolside-ai")
    assert caught.value.status_code == status
    assert "PRIVATE_SENTINEL" not in str(caught.value)


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("model,control", [("", {}), ("  ", {}),
    (MODEL, {"reasoning_effort": "high"}), (MODEL, {"reasoning_budget_tokens": 0}),
    (MODEL, {"gemini_thinking_budget": -1}),
])
def test_preflight_rejects_unsupported_configuration_without_network(alias, model, control):
    for live in (False, True):
        result = provider_preflight(alias, model, "tic-tac-toe", live=live,
                                    runtime_config=ProviderRuntimeConfig(**control))
        assert not result["ok"]
        assert not result["readiness"]["configuration_ready"]
        assert result["error"]["error_class"] == "provider_request_rejected"


@pytest.mark.parametrize("path", ["success", "http_error", "malformed", "partial", "transport"])
def test_echoed_opaque_credential_is_scrubbed_from_every_receipt_path(monkeypatch, path):
    secret = "opaquePoolsideCredential123"
    monkeypatch.setenv("POOLSIDE_API_KEY", secret)

    def post(*a, **k):
        headers = {"x-request-id": "req-" + secret, "x-gateway-request-id": "gw-" + secret}
        if path in {"partial", "transport"}:
            exc = httpx.ReadError("private transport")
            if path == "partial":
                exc._eslams_response_observation = ResponseObservation(200, tuple(headers.items()))
            raise exc
        if path == "malformed":
            return httpx.Response(200, content=b"not-json", headers=headers)
        payload = fixture()
        payload["id"] = "chat-" + secret
        payload["model"] = "model-" + secret
        payload["choices"][0]["message"]["content"] = json.dumps({
            "action": 1, "public_explanation": "echo " + secret,
        })
        return httpx.Response(429 if path == "http_error" else 200, json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent()
    if path == "success":
        response = selected.act(request())
        assert secret not in json.dumps(response.to_dict())
    else:
        with pytest.raises(ProviderCallError) as caught:
            selected.act(request())
        assert secret not in str(caught.value)
    receipt = selected.last_receipt
    assert secret not in json.dumps(selected.attempt_receipts)
    for field in ("request_id", "gateway_request_id", "locked_model_id", "provider_response_id"):
        assert receipt.get(field) is None


def test_discovery_rejects_credential_echo(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={
        "data": [{"id": "fixture-secret-never-persisted"}],
    }))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("poolside")
    assert "fixture-secret-never-persisted" not in str(caught.value)


def test_runner_preserves_receipts_and_never_applies_truncated_action(monkeypatch, tmp_path):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = "length"
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=payload,
    ))
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, output_dir=tmp_path,
    ))
    assert not result.score.match_valid_for_scoring
    receipts = [json.loads(line) for line in (
        result.artifact_path / "receipts/provider_receipts.jsonl"
    ).read_text().splitlines()]
    assert len(receipts) == 1
    assert receipts[0]["provider"] == "poolside"
    assert receipts[0]["usage"]["total_tokens"] == 535
    assert receipts[0]["finish_status"] == "incomplete"
    assert not receipts[0]["action_applied"]
    assert "PRIVATE_REASONING_SENTINEL" not in json.dumps(receipts)
    assert ArtifactValidator().validate(result.artifact_path) == []
