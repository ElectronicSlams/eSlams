"""Documented direct REST envelopes; every inference is a deterministic fake."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import httpx
import pytest
from test_provider_wire_v06 import _fixture, _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers import load_provider_registry
from eslams.providers.zai import API_KEY_ENVS, ENDPOINTS
from eslams.runner import RunConfig, Runner


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch):
    # Tests must never depend on credentials or a reachable inference service.
    for env in API_KEY_ENVS.values():
        monkeypatch.delenv(env, raising=False)

    def unexpected(*args, **kwargs):
        pytest.fail("unexpected provider network request")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    monkeypatch.setattr(httpx.Client, "get", unexpected)


def wire():
    return _fixture("zai_chat_completions_success.json")


def setup(monkeypatch, provider="zai", *, payload=None, status=200, runtime=None, model="glm-5.3"):
    monkeypatch.setenv(API_KEY_ENVS[provider], "fixture-secret-never-persisted")
    calls = []

    def post(url, *, headers, json, timeout):
        calls.append((url, headers, copy.deepcopy(json), timeout))
        return httpx.Response(
            status,
            json=payload if payload is not None else wire(),
            headers={"Retry-After": "0", "x-request-id": "header-request"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return ModelProviderAgent(
        provider, model, API_KEY_ENVS[provider], runtime_config=runtime
    ), calls


@pytest.mark.parametrize("provider", ENDPOINTS)
def test_success_exact_route_history_native_defaults_and_unknown_accounting(monkeypatch, provider):
    agent, calls = setup(monkeypatch, provider)
    request = replace(
        _request(),
        protocol_version="eslams-act-v2",
        time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None)},
    )
    # Same public-history records used by Core. No adapter-local window or arena policy.
    request = replace(
        request, history=[{"turn": i, "public_explanation": f"history-{i}"} for i in range(100)]
    )
    response = agent.act(request)
    url, headers, body, timeout = calls[0]
    assert url == ENDPOINTS[provider]
    assert headers == {
        "Authorization": "Bearer fixture-secret-never-persisted",
        "Content-Type": "application/json",
    }
    assert body["model"] == "glm-5.3" and body["stream"] is False
    assert set(body) == {"model", "messages", "stream"}
    prompt = json.loads(body["messages"][1]["content"].split("\n")[-1])
    assert prompt["history"] == request.history
    assert timeout.read is None and timeout.connect == 10
    assert response.action == 1
    receipt = agent.last_receipt
    assert receipt["provider"] == provider and receipt["model"] == "glm-5.3"
    assert receipt["locked_model_id"] == "glm-5.3"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["request_id"] == "header-request"
    assert receipt["endpoint_kind"] == f"{provider}_chat_completions"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "PRIVATE_REASONING_SENTINEL" not in json.dumps(response.to_dict())
    assert "fixture-secret-never-persisted" not in json.dumps(receipt)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "alias,canonical",
    [
        ("zai", "zai"),
        ("Z.AI", "zai"),
        ("Z_AI", "zai"),
        ("z-ai", "zai"),
        ("zhipu", "zhipu"),
        ("ZHIPUAI", "zhipu"),
    ],
)
def test_cli_preflight_registry_and_direct_dispatch_agree(monkeypatch, capsys, alias, canonical):
    _, calls = setup(monkeypatch, canonical)
    agent = _provider_agent(f"{alias}:glm-5.3")
    assert agent.provider == canonical and agent.api_key_env == API_KEY_ENVS[canonical]
    assert load_provider_registry().resolve(alias, "glm-5.3").provider == canonical
    assert agent.act(_request()).action == 1
    assert calls[0][0] == ENDPOINTS[canonical]
    assert main(["providers", "preflight", "--provider", alias, "--model", "glm-5.3"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True
    assert result["checks"]["minimal_inference"] is False
    assert len(calls) == 1
    live = provider_preflight(alias, "glm-5.3", "tic-tac-toe", live=True)
    assert live["ok"] is True
    assert live["checks"]["account_model_visible"] is None
    assert calls[-1][0] == ENDPOINTS[canonical]


@pytest.mark.parametrize(
    "provider", ["zhipuai-coding-plan", "zai-coding-plan", "zhipu-coding-plan"]
)
def test_coding_plan_names_never_dispatch_standard_api(provider):
    assert _provider_agent(f"{provider}:glm-5.3") is None
    result = provider_preflight(provider, "glm-5.3", "tic-tac-toe")
    assert not result["ok"] and not result["checks"]["adapter_available"]
    assert result["error"]["error_class"] == "provider_adapter_unavailable"


@pytest.mark.parametrize("provider", ENDPOINTS)
def test_no_undocumented_models_discovery_and_missing_credentials(monkeypatch, provider):
    assert provider_models_live(provider) is None
    result = provider_models_result(provider)
    assert result["error"]["error_class"] == "provider_discovery_unavailable"
    agent = ModelProviderAgent(provider, "glm-5.3", API_KEY_ENVS[provider])
    with pytest.raises(ProviderCallError, match="missing API key"):
        agent.act(_request())
    assert agent.last_receipt["usage"] == {}


@pytest.mark.parametrize(
    "mode,effort",
    [
        ("auto", None),
        ("enabled", None),
        ("disabled", None),
        ("enabled", "max"),
        ("auto", "low"),
        ("auto", "unknown-effort"),
    ],
)
def test_explicit_reasoning_is_never_rewritten(monkeypatch, mode, effort):
    agent, calls = setup(
        monkeypatch, runtime=ProviderRuntimeConfig(reasoning=mode, reasoning_effort=effort)
    )
    agent.temperature = 0.7
    agent.max_output_tokens = 9876
    agent.act(_request())
    body = calls[0][2]
    assert body.get("thinking") == ({"type": mode} if mode != "auto" else None)
    assert body.get("reasoning_effort") == effort
    assert body["temperature"] == 0.7 and body["max_tokens"] == 9876


@pytest.mark.parametrize("budget", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_unsupported_token_budget_fails_before_submission(monkeypatch, budget):
    agent, calls = setup(monkeypatch, runtime=ProviderRuntimeConfig(**{budget: 100}))
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == "provider_request_rejected"
    assert calls == []


@pytest.mark.parametrize("provider", ENDPOINTS)
@pytest.mark.parametrize(
    "reason,kind",
    [
        ("sensitive", "provider_refused"),
        ("length", "provider_output_truncated"),
        ("model_context_window_exceeded", "provider_output_truncated"),
        ("network_error", "provider_interrupted"),
        ("tool_calls", "provider_request_rejected"),
        (None, "provider_response_schema_mismatch"),
        ("PRIVATE_REASON", "provider_response_schema_mismatch"),
        ({"private": True}, "provider_response_schema_mismatch"),
    ],
)
def test_incomplete_envelope_rejects_legal_looking_text_and_retains_usage(
    monkeypatch, provider, reason, kind
):
    payload = wire()
    payload["choices"][0]["finish_reason"] = reason
    agent, calls = setup(monkeypatch, provider, payload=payload)
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == kind
    assert agent.last_receipt["outcome"] == kind
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1
    assert "PRIVATE_REASON" not in json.dumps(agent.last_receipt)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(choices=[]),
        lambda p: p["choices"][0]["message"].update(content=None),
        lambda p: p["choices"][0]["message"].update(content=""),
        lambda p: p["choices"][0]["message"].update(role="user"),
        lambda p: p["choices"].append(copy.deepcopy(p["choices"][0])),
    ],
)
def test_malformed_success_has_receipt_and_no_action(monkeypatch, mutation):
    payload = wire()
    mutation(payload)
    agent, _ = setup(monkeypatch, payload=payload)
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert agent.last_receipt["status_code"] == 200
    assert agent.last_receipt["usage"]["input_tokens"] == 12


@pytest.mark.parametrize(
    "status,kind",
    [
        (400, "provider_request_rejected"),
        (401, "provider_auth_failed"),
        (403, "provider_permission_failed"),
        (404, "provider_unavailable"),
        (429, "provider_rate_limited"),
        (500, "provider_unavailable"),
        (503, "provider_unavailable"),
    ],
)
def test_http_error_privacy_and_zero_default_retries(monkeypatch, status, kind):
    body = {
        "error": {"code": "1302" if status == 429 else "1214", "message": "PRIVATE_ERROR_PROMPT"}
    }
    agent, calls = setup(monkeypatch, status=status, payload=body)
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == kind
    assert agent.last_receipt["status_code"] == status
    assert agent.last_receipt["request_id"] == "header-request"
    assert agent.last_receipt["usage"] == {}
    assert len(calls) == 1
    assert "PRIVATE_ERROR_PROMPT" not in str(caught.value) + json.dumps(agent.last_receipt)


@pytest.mark.parametrize(
    "code,kind",
    [
        ("1301", "provider_refused"),
        ("1211", "provider_request_rejected"),
        ("1001", "provider_auth_failed"),
        ("1302", "provider_rate_limited"),
    ],
)
def test_http_200_business_error_is_quarantined(monkeypatch, code, kind):
    payload = {
        "error": {"code": code, "message": "PRIVATE_ERROR"},
        "model": "untrusted-model",
        "usage": wire()["usage"],
        "cost": 123,
    }
    agent, calls = setup(monkeypatch, payload=payload)
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == kind
    receipt = agent.last_receipt
    assert receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert receipt["usage"]["total_tokens"] == 16
    assert len(calls) == 1


@pytest.mark.parametrize(
    "code,extra,attempts",
    [
        ("1302", {}, 2),
        ("1305", {}, 2),
        ("1113", {}, 1),
        ("1308", {}, 1),
        ("unknown", {}, 1),
        ("1302", {"usage": {"total_tokens": 1}}, 1),
        ("1302", {"id": "work-observed"}, 1),
        ("1302", {"model": "unverified"}, 1),
    ],
)
def test_only_definitive_rate_rejections_can_use_explicit_retries(
    monkeypatch, code, extra, attempts
):
    payload = {"error": {"code": code, "message": "private"}, **extra}
    agent, calls = setup(
        monkeypatch,
        status=429,
        payload=payload,
        runtime=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0),
    )
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(calls) == attempts
    assert [r["attempt"] for r in agent.attempt_receipts] == list(range(1, attempts + 1))


@pytest.mark.parametrize("failure", ["timeout", "transport", "malformed", "duplicate", "array"])
def test_transport_and_invalid_json_keep_failed_attempts(monkeypatch, failure):
    agent, calls = setup(monkeypatch, runtime=ProviderRuntimeConfig(max_retries=2))

    def post(*args, **kwargs):
        calls.append(True)
        if failure == "timeout":
            raise httpx.ReadTimeout("PRIVATE_TIMEOUT")
        if failure == "transport":
            raise httpx.ConnectError("PRIVATE_TRANSPORT")
        return httpx.Response(
            200,
            content={
                "malformed": b"{PRIVATE_BODY",
                "duplicate": b'{"model":"a","model":"b"}',
                "array": b"[]",
            }[failure],
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        agent.act(_request())
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    assert "PRIVATE" not in str(caught.value) + json.dumps(agent.last_receipt)


def test_unknown_model_and_missing_accounting_never_gain_identity_or_zeroes(monkeypatch):
    payload = wire()
    del payload["model"], payload["usage"], payload["id"]
    agent, calls = setup(monkeypatch, payload=payload, model="EXACT-unknown/vendor-model")
    response = agent.act(_request())
    assert calls[0][2]["model"] == "EXACT-unknown/vendor-model"
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None and receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_missing_total_and_undocumented_reasoning_usage_stay_unknown(monkeypatch):
    payload = wire()
    payload["usage"] = {
        "prompt_tokens": 12,
        "completion_tokens": 4,
        "reasoning_tokens": 99,
        "reasoning_included_in_output": True,
    }
    agent, _ = setup(monkeypatch, payload=payload)
    agent.act(_request())
    usage = agent.last_receipt["usage"]
    assert usage["total_tokens"] is None and usage["reasoning_tokens"] is None
    assert usage["reasoning_included_in_output"] is None


def test_runner_receipt_custody_and_public_artifact_privacy(monkeypatch, tmp_path):
    agent, calls = setup(monkeypatch)

    def post(url, *, headers, json, timeout):
        calls.append(json)
        payload = wire()
        import json as json_module

        request = json_module.loads(json["messages"][1]["content"].split("\n")[-1])
        payload["choices"][0]["message"]["content"] = json_module.dumps(
            {"action": request["legal_actions"][0]}
        )
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", agents={"player_1": agent}, output_dir=tmp_path)
    )
    assert ArtifactValidator().validate(result.artifact_path) == []
    receipts = [
        json.loads(line)
        for line in (result.artifact_path / "receipts/provider_receipts.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(receipts) == len(calls) and receipts
    assert all(r["provider"] == "zai" for r in receipts)
    assert all(r["reasoning_included_in_output"] is None for r in receipts)
    assert all(r["cost_complete"] is False for r in receipts)
    for path in result.artifact_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert b"PRIVATE_REASONING_SENTINEL" not in content
            assert b"fixture-secret-never-persisted" not in content


@pytest.mark.parametrize("alias,provider", [("z.ai", "zai"), ("zhipuai", "zhipu")])
def test_python_constructor_aliases_dispatch_identically(monkeypatch, alias, provider):
    _, calls = setup(monkeypatch, provider)
    agent = ModelProviderAgent(alias, "EXACT-model-id", API_KEY_ENVS[provider])
    agent.act(_request())
    assert agent.provider == provider
    assert calls[0][0] == ENDPOINTS[provider] and calls[0][2]["model"] == "EXACT-model-id"


@pytest.mark.parametrize("provider", ENDPOINTS)
def test_full_cli_run_uses_native_dispatch(monkeypatch, tmp_path, capsys, provider):
    _, calls = setup(monkeypatch, provider)

    def post(url, *, headers, json, timeout):
        import json as json_module

        calls.append(url)
        payload = wire()
        prompt = json_module.loads(json["messages"][1]["content"].split("\n")[-1])
        payload["choices"][0]["message"]["content"] = json_module.dumps(
            {"action": prompt["legal_actions"][0]}
        )
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert (
        main(
            [
                "run",
                "--arena",
                "tic-tac-toe",
                "--agent",
                f"{provider}:glm-5.3",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert calls and all(url == ENDPOINTS[provider] for url in calls)


@pytest.mark.parametrize("counter", [True, -1, 1.5, "12"])
def test_invalid_usage_is_not_coerced(monkeypatch, counter):
    payload = wire()
    payload["usage"]["prompt_tokens"] = counter
    agent, _ = setup(monkeypatch, payload=payload)
    agent.act(_request())
    assert agent.last_receipt["usage"]["input_tokens"] is None
    assert agent.last_receipt["usage"]["usage_validation_errors"]


def test_reasoning_is_never_parsed_as_an_action(monkeypatch):
    payload = wire()
    payload["choices"][0]["message"].update(
        content="plain non-json text", reasoning_content='{"action": 1}'
    )
    agent, calls = setup(monkeypatch, payload=payload)
    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())
    assert caught.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1


def test_body_request_id_and_explicit_output_policy(monkeypatch):
    from eslams.providers.zai import call

    agent, _ = setup(monkeypatch)
    # No header ID: retain the documented body request_id.
    body = wire()

    def post(*args, **kwargs):
        assert kwargs["json"]["max_tokens"] == 1234
        return httpx.Response(200, json=body)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent._request_max_output_tokens = 1234
    _, receipt = call(agent, "fixture-key", "private prompt")
    assert receipt["request_id"] == body["request_id"]
    assert "private prompt" not in json.dumps(receipt)
