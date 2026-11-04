"""Deterministic Azure REST fixtures; no Azure credentials or inference calls."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import azure, load_provider_registry

SECRET = "fixture-azure-credential-private"
PRIVATE = "PRIVATE_PROMPT_AND_ERROR_TEXT"
DEPLOYMENT = "Exact-Deployment-Blue"


@pytest.fixture(autouse=True)
def azure_environment(monkeypatch):
    monkeypatch.setenv("AZURE_AI_API_KEY", SECRET)
    monkeypatch.setenv("AZURE_AI_ENDPOINT", "https://fixture.services.ai.azure.com")
    monkeypatch.delenv("AZURE_AI_AUTH_MODE", raising=False)
    monkeypatch.delenv("AZURE_AI_AUTH_TOKEN", raising=False)


def wire():
    path = Path(__file__).parent / "fixtures/provider/azure_chat_completions_success.json"
    return json.loads(path.read_text())


def request():
    return ActRequest(
        protocol_version="eslams-act-v2",
        run_id="run_azure",
        episode_id="episode_001",
        turn_id=2,
        arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="azure-test", version="test-v1"),
        active_player="player_1",
        observation={"private": PRIVATE},
        legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn": i} for i in range(120)],
        time_budget_ms=None,
        memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(alias="azure", config=None):
    result = _provider_agent(f"{alias}:{DEPLOYMENT}", runtime_config=config)
    assert isinstance(result, ModelProviderAgent)
    return result


def post_fixture(monkeypatch, body=None, status=200, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status,
            json=wire() if body is None else body,
            headers=headers or {"x-request-id": "azure-request-123"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", [*azure.ALIASES, "AZURE_AI_FOUNDRY"])
def test_aliases_cli_preflight_registry_dispatch(monkeypatch, capsys, alias):
    calls = post_fixture(monkeypatch)
    a = agent(alias)
    assert a.provider == "azure"
    assert a.model == DEPLOYMENT
    assert load_provider_registry().resolve(alias, DEPLOYMENT).provider == "azure"
    assert (
        main(
            [
                "providers",
                "preflight",
                "--provider",
                alias,
                "--model",
                DEPLOYMENT,
                "--arena",
                "tic-tac-toe",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"]
    assert not calls
    assert a.act(request()).action == 0
    assert len(calls) == 1
    assert a.last_receipt["provider"] == "azure"
    assert provider_models_live(alias) is None


def test_wire_identity_usage_full_history_and_defaults(monkeypatch):
    calls = post_fixture(monkeypatch)
    a = agent()
    result = a.act(request())
    url, kwargs = calls[0]
    assert url == "https://fixture.services.ai.azure.com/openai/v1/chat/completions"
    assert kwargs["headers"] == {"Content-Type": "application/json", "api-key": SECRET}
    payload = kwargs["json"]
    assert set(payload) == {"model", "messages", "stream", "store"}
    assert payload["model"] == DEPLOYMENT
    assert payload["stream"] is False and payload["store"] is False
    assert payload["messages"][0]["role"] == "system"
    prompt = payload["messages"][1]["content"]
    embedded = json.loads(prompt.split("\n")[-1])
    assert embedded["history"] == request().history
    assert PRIVATE in prompt
    assert kwargs["timeout"].read is None
    r = a.last_receipt
    assert result.action == 0
    assert r["model"] == DEPLOYMENT
    assert r["locked_model_id"] == "o1-2024-12-17"
    assert r["model_identity_source"] == "provider_response"
    assert r["endpoint_kind"] == azure.ENDPOINT_KIND
    assert r["parser_version"] == azure.PARSER_VERSION
    assert r["usage"]["input_tokens"] == 20
    assert r["usage"]["output_tokens"] == 1843
    assert r["usage"]["reasoning_tokens"] == 448
    assert r["usage"]["reasoning_included_in_output"] is True
    assert r["usage"]["total_tokens"] == 1863
    assert r["estimated_cost"]["status"] == "cost_unavailable"
    assert r["request_id"] == "azure-request-123"
    assert r["attempt_index"] == 1
    assert SECRET not in json.dumps(r) and PRIVATE not in json.dumps(r)
    assert "api.openai.com" not in url


@pytest.mark.parametrize(
    "endpoint",
    ["https://fixture.openai.azure.com/", "https://fixture.services.ai.azure.com/openai/v1/"],
)
def test_explicit_controls_and_entra(monkeypatch, endpoint):
    monkeypatch.setenv("AZURE_AI_ENDPOINT", endpoint)
    monkeypatch.setenv("AZURE_AI_AUTH_MODE", "entra")
    monkeypatch.setenv("AZURE_AI_AUTH_TOKEN", SECRET)
    calls = post_fixture(monkeypatch)
    a = agent(config=ProviderRuntimeConfig(reasoning_effort="high"))
    a.max_output_tokens = 7000
    a.temperature = 0.5
    a.act(request())
    _, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert "api-key" not in kwargs["headers"]
    assert kwargs["json"]["max_completion_tokens"] == 7000
    assert kwargs["json"]["reasoning_effort"] == "high"
    assert kwargs["json"]["temperature"] == 0.5


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://fixture.openai.azure.com",
        "https://api.openai.com/v1",
        "https://fixture.openai.azure.com.evil.test",
        "https://key@fixture.openai.azure.com",
        "https://fixture.openai.azure.com/?api-key=secret",
        "https://fixture.openai.azure.com/#secret",
        "https://fixture.openai.azure.com/openai/deployments/x",
        "https://fixture.openai.azure.com:443",
        "https://fixture.services.ai.azure.com/api/projects/test",
        "https://fixture.models.ai.azure.com",
    ],
)
def test_invalid_endpoints_fail_closed(monkeypatch, url):
    monkeypatch.setenv("AZURE_AI_ENDPOINT", url)
    calls = post_fixture(monkeypatch)
    result = provider_preflight("azure", DEPLOYMENT, "tic-tac-toe")
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    with pytest.raises(ProviderCallError) as exc:
        agent().act(request())
    assert exc.value.error_kind == "provider_request_rejected"
    assert not calls
    if url:
        assert url not in str(exc.value)


def test_missing_deployment_gateway_and_invalid_auth(monkeypatch):
    calls = post_fixture(monkeypatch)
    with pytest.raises(ValueError, match="explicit deployment"):
        _provider_agent("azure")
    with pytest.raises(ProviderCallError):
        agent(config=ProviderRuntimeConfig(gateway_base_url="https://gateway.example")).act(
            request()
        )
    monkeypatch.setenv("AZURE_AI_AUTH_MODE", "invalid")
    assert not provider_preflight("azure-ai", DEPLOYMENT, "tic-tac-toe")["ok"]
    assert not calls


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
def test_http_errors_sanitized_without_retries(monkeypatch, status, kind):
    calls = post_fixture(
        monkeypatch,
        {"error": {"code": "429" if status == 429 else "Error", "message": f"{SECRET} {PRIVATE}"}},
        status,
        {"retry-after-ms": "1250", "x-request-id": "azure-error-123", "set-cookie": SECRET},
    )
    a = agent()
    with pytest.raises(ProviderCallError) as exc:
        a.act(request())
    assert exc.value.error_kind == kind and exc.value.status_code == status
    assert len(calls) == 1
    r = a.last_receipt
    assert r["retry_after_ms"] == 1250
    assert r["usage"] == {} and r["locked_model_id"] is None
    assert r["estimated_cost"]["status"] == "cost_unavailable"
    public = str(exc.value) + json.dumps(r)
    assert PRIVATE not in public and SECRET not in public


def test_content_filter_http_rejection(monkeypatch):
    post_fixture(monkeypatch, {"error": {"code": "content_filter", "message": PRIVATE}}, 400)
    a = agent()
    with pytest.raises(ProviderCallError) as exc:
        a.act(request())
    assert exc.value.error_kind == "provider_refused"
    assert PRIVATE not in json.dumps(a.last_receipt)


@pytest.mark.parametrize(
    "case,kind",
    [
        ("length", "provider_output_truncated"),
        ("content_filter", "provider_refused"),
        ("refusal", "provider_refused"),
        ("tool_calls", "provider_request_rejected"),
        ("no_choices", "provider_response_schema_mismatch"),
        ("no_finish", "provider_response_schema_mismatch"),
        ("reasoning_only", "provider_response_schema_mismatch"),
        ("two_choices", "provider_response_schema_mismatch"),
        ("wrong_role", "provider_response_schema_mismatch"),
    ],
)
def test_semantic_failures_retain_usage_never_accept_partial_action(monkeypatch, case, kind):
    body = wire()
    choice = body["choices"][0]
    if case in {"length", "content_filter", "tool_calls"}:
        choice["finish_reason"] = case
    elif case == "refusal":
        choice["message"]["refusal"] = PRIVATE
    elif case == "no_choices":
        body.pop("choices")
    elif case == "no_finish":
        choice.pop("finish_reason")
    elif case == "reasoning_only":
        choice["message"].update(content=None, reasoning_content=PRIVATE)
    elif case == "two_choices":
        body["choices"].append(copy.deepcopy(choice))
    else:
        choice["message"]["role"] = "user"
    calls = post_fixture(monkeypatch, body)
    a = agent(config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as exc:
        a.act(request())
    assert exc.value.error_kind == kind
    assert len(calls) == 1
    assert a.last_receipt["usage"]["total_tokens"] == 1863
    assert PRIVATE not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("case", ["non_json", "array", "duplicate", "invalid_utf8"])
def test_malformed_raw_wire(monkeypatch, case):
    content = {
        "non_json": b"<html>private</html>",
        "array": b"[]",
        "duplicate": b'{"choices":[],"choices":[]}',
        "invalid_utf8": b"\xff",
    }[case]
    monkeypatch.setattr(
        "eslams.agents.bounded_post",
        lambda *a, **k: httpx.Response(
            200, content=content, headers={"x-request-id": "azure-malformed"}
        ),
    )
    a = agent()
    with pytest.raises(ProviderCallError) as exc:
        a.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch"
    assert a.last_receipt["request_id"] == "azure-malformed"
    assert a.last_receipt["usage"] == {}


def test_missing_identity_and_usage_remain_unknown(monkeypatch):
    body = wire()
    body.pop("model")
    body.pop("usage")
    post_fixture(monkeypatch, body)
    a = agent()
    assert a.act(request()).action == 0
    assert a.last_receipt["locked_model_id"] is None
    assert a.last_receipt["model_identity_source"] is None
    assert a.last_receipt["usage"] == {}
    assert a.last_receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("exception", [httpx.ReadTimeout("private"), httpx.ConnectError("private")])
def test_ambiguous_transport_never_replayed(monkeypatch, exception):
    calls = []

    def post(*a, **k):
        calls.append(1)
        raise exception

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((TimeoutError, ProviderCallError)):
        a.act(request())
    assert len(calls) == 1
    assert a.last_receipt["usage"] == {}


def test_ambiguous_429_with_usage_quarantined_no_replay(monkeypatch):
    body = {
        "error": {"code": "rate_limit_exceeded", "message": PRIVATE},
        "usage": wire()["usage"],
        "id": "chatcmpl-possibly-accepted",
    }
    calls = post_fixture(monkeypatch, body, 429)
    a = agent(config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert len(calls) == 1
    assert a.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_live_preflight_is_only_explicit_and_does_not_discover_deployments(monkeypatch):
    calls = post_fixture(monkeypatch)
    result = provider_preflight("azure-ai-foundry", DEPLOYMENT, "tic-tac-toe", live=True)
    assert result["ok"]
    assert len(calls) == 1
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["usage_extraction"] is True
    assert result["checks"]["registry_entry"] is False
    assert load_provider_registry().resolve("microsoft", DEPLOYMENT).provider == "microsoft"


@pytest.mark.parametrize(
    "value,expected",
    [("3000", 3.0), ("0", 0.0), ("-1", None), ("nan", None), ("inf", None), ("invalid", None)],
)
def test_azure_retry_hint_validation(value, expected):
    assert (
        azure.retry_after_seconds(httpx.Response(429, headers={"retry-after-ms": value}))
        == expected
    )


def test_explicit_safe_retry_keeps_attempts_and_azure_delay(monkeypatch):
    calls = []
    waits = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]["model"]))
        if len(calls) == 1:
            return httpx.Response(
                429,
                json={"error": {"code": "rate_limit_exceeded", "message": PRIVATE}},
                headers={"retry-after-ms": "1500", "retry-after": "9"},
            )
        return httpx.Response(200, json=wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    monkeypatch.setattr("eslams.agents.sleep_with_cancellation", waits.append)
    a = agent(config=ProviderRuntimeConfig(max_retries=1, retry_jitter=False))
    assert a.act(request()).action == 0
    assert waits == [1.5]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert [r["attempt_index"] for r in a.attempt_receipts] == [1, 2]
    assert [r["outcome"] for r in a.attempt_receipts] == ["provider_rate_limited", "ok"]


@pytest.mark.parametrize("mutation", ["redirect", "unknown_finish", "tool_beside_text"])
def test_unexpected_completion_is_not_accepted(monkeypatch, mutation):
    body = wire()
    if mutation == "unknown_finish":
        body["choices"][0]["finish_reason"] = PRIVATE
    elif mutation == "tool_beside_text":
        body["choices"][0]["message"]["tool_calls"] = [{"id": "tool-private"}]
    calls = post_fixture(monkeypatch, body, status=302 if mutation == "redirect" else 200)
    with pytest.raises(ProviderCallError):
        agent().act(request())
    assert len(calls) == 1


def test_no_credential_never_submits(monkeypatch):
    monkeypatch.delenv("AZURE_AI_API_KEY")
    calls = post_fixture(monkeypatch)
    a = agent()
    with pytest.raises(ProviderCallError) as exc:
        a.act(request())
    assert exc.value.error_kind == "provider_auth_failed"
    assert not calls
    assert a.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("alias", azure.ALIASES)
def test_direct_agent_aliases(alias, monkeypatch):
    post_fixture(monkeypatch)
    a = ModelProviderAgent(provider=alias, model=DEPLOYMENT, api_key_env=azure.API_KEY_ENV)
    assert a.act(request()).action == 0
    assert a.provider == "azure"


def test_artifacts_do_not_publish_private_wire_material(monkeypatch, tmp_path):
    from eslams.runner import RunConfig, Runner

    actions = iter([0, 2, 4, 6])

    def post(url, **kwargs):
        body = wire()
        body["private_extension"] = PRIVATE
        body["choices"][0]["message"].update(
            content=json.dumps({"action": next(actions)}),
            reasoning_content=PRIVATE,
        )
        return httpx.Response(200, json=body, headers={"set-cookie": SECRET})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": agent()},
            model_id_by_player={"player_1": DEPLOYMENT},
            max_turns=9,
            output_dir=tmp_path,
        )
    )
    for path in result.artifact_path.rglob("*"):
        if path.suffix in {".json", ".jsonl", ".html"}:
            text = path.read_text()
            assert PRIVATE not in text and SECRET not in text
    receipts = [
        json.loads(line)
        for line in (result.artifact_path / "receipts/provider_receipts.jsonl")
        .read_text()
        .splitlines()
    ]
    assert receipts and all(row["provider"] == "azure" for row in receipts)
    assert all(row["cost_complete"] is False for row in receipts)
