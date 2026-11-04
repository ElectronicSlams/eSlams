"""Documented IBM-hosted chat wire and fail-closed integration; no network calls."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.deadlines import ExecutionCancelled
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.ibm_rhai import ALIASES, API_KEY_ENV, PROVIDER
from eslams.providers.registry import load_provider_registry
from eslams.runner import RunConfig, Runner

MODEL = "granite-4-0-h-small"
SECRET = "IbmCredentialEcho0123456789"
PRIVATE = "private-response-never-persisted"
ALIASES_WITH_UNDERSCORES = sorted(ALIASES | {x.replace("-", "_") for x in ALIASES})


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "ibm_rhai_chat_completions_success.json").read_text())


def agent(**kwargs):
    return ModelProviderAgent(PROVIDER, MODEL, API_KEY_ENV, **kwargs)


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    monkeypatch.setenv("IBM_RHAI_REGION", "us-east")
    monkeypatch.setenv("IBM_RHAI_PROJECT_ID", "project-fixture")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("unmocked call"))


def install(monkeypatch, payload=None, *, status=200, headers=None, content=None):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        if content is not None:
            return httpx.Response(status, content=content, headers=headers)
        return httpx.Response(status, json=wire() if payload is None else payload, headers=headers)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def assert_private(value):
    serialized = json.dumps(value, default=str)
    assert SECRET not in serialized
    assert PRIVATE not in serialized
    assert "Authorization" not in serialized


@pytest.mark.parametrize("alias", ALIASES_WITH_UNDERSCORES)
def test_alias_cli_dispatch_preflight_and_registry_are_one_host(monkeypatch, alias):
    calls = install(monkeypatch)
    selected = _provider_agent(f"{alias}:{MODEL}")
    assert selected.provider == PROVIDER and selected.model == MODEL
    assert selected.act(_request()).action == 1
    result = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert result["provider"] == PROVIDER and result["ok"] is True
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["usage_extraction"] is True
    assert result["readiness"]["usage_complete"] is False
    assert result["receipt_shape"]["usage_complete"] is False
    assert provider_models_live(alias) is None
    assert len(calls) == 2
    assert load_provider_registry().resolve(alias, MODEL).provider == PROVIDER


@pytest.mark.parametrize("alias", ALIASES_WITH_UNDERSCORES)
def test_alias_real_cli_run_and_cli_preflight(monkeypatch, alias, tmp_path, capsys):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        prompt = json.loads(kwargs["json"]["messages"][1]["content"].splitlines()[-1])
        data = wire()
        data["choices"][0]["message"]["content"] = json.dumps(
            {"action": prompt["legal_actions"][0]})
        return httpx.Response(200, json=data)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL]) == 0
    assert calls == []
    assert json.loads(capsys.readouterr().out)["provider"] == PROVIDER
    assert main(["run", "--arena", "tic-tac-toe", "--agent", f"{alias}:{MODEL}",
                 "--opponent", "first-legal", "--out", str(tmp_path / "run")]) == 0
    assert calls


@pytest.mark.parametrize("model", ["", " ", "\t", " padded", "padded ", None])
def test_model_must_be_explicit_and_exact(model):
    with pytest.raises(ValueError, match="exact explicit model"):
        ModelProviderAgent(PROVIDER, model, API_KEY_ENV)
    with pytest.raises(ValueError, match="exact explicit model"):
        provider_preflight(PROVIDER, model, "tic-tac-toe")
    if isinstance(model, str):
        with pytest.raises(ValueError, match="exact explicit model"):
            _provider_agent(f"{PROVIDER}:{model}")
    with pytest.raises(ValueError):
        _provider_agent(PROVIDER)


def test_authors_and_watsonx_do_not_select_this_host():
    for name in ("ibm", "ibm-granite", "watsonx"):
        assert _provider_agent(f"{name}:{MODEL}") is None
        assert load_provider_registry().resolve(name, MODEL).provider != PROVIDER


def test_wire_policy_history_identity_and_usage(monkeypatch):
    data = wire()
    data["choices"][0]["message"]["reasoning_content"] = PRIVATE
    calls = install(monkeypatch, data, headers={"x-request-id": "rhai-req"})
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      history=[{"turn_id": i, "action": i % 3} for i in range(77)],
                      metadata={"model_execution_policy": model_execution_policy(None, None)})
    response = agent().act(request)
    endpoint, kwargs = calls[0]
    assert endpoint == "https://us-east.rhai.ibm.com/v1/projects/project-fixture/inference/chat/completions"
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert set(kwargs["json"]) == {"model", "messages"}
    assert kwargs["json"]["model"] == MODEL
    messages = kwargs["json"]["messages"]
    assert [m["role"] for m in messages] == ["developer", "user"]
    assert json.loads(messages[1]["content"].splitlines()[-1])["history"] == request.history
    assert kwargs["timeout"].read is None
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["request_id"] == "rhai-req"
    assert receipt["endpoint_kind"] == "ibm_rhai_chat_completions"
    assert receipt["parser_version"] == "ibm-rhai-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert_private(response.to_dict())


def test_only_explicit_output_and_temperature_are_sent(monkeypatch):
    calls = install(monkeypatch)
    agent(max_output_tokens=321, temperature=0.2).act(_request())
    assert calls[0][1]["json"]["max_completion_tokens"] == 321
    assert calls[0][1]["json"]["temperature"] == 0.2
    assert "reasoning_effort" not in calls[0][1]["json"]


UNSUPPORTED = [{"reasoning": "enabled"}, {"reasoning": "disabled"},
               {"reasoning_effort": "low"}, {"reasoning_effort": "invented"},
               {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 100},
               {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 0}]


@pytest.mark.parametrize("settings", UNSUPPORTED)
@pytest.mark.parametrize("live", [False, True])
def test_unsupported_reasoning_rejected_before_discovery_and_inference(monkeypatch, settings, live):
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live",
                        lambda *a: pytest.fail("discovery before validation"))
    runtime = ProviderRuntimeConfig(**settings)
    result = provider_preflight(PROVIDER, MODEL, "tic-tac-toe", runtime_config=runtime, live=live)
    assert result["ok"] is False
    assert result["readiness"]["configuration_ready"] is False
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ProviderCallError, match="native reasoning"):
        agent(runtime_config=runtime).act(_request())


@pytest.mark.parametrize(("env", "value"), [("IBM_RHAI_REGION", ""),
    ("IBM_RHAI_REGION", "eu-de"), ("IBM_RHAI_PROJECT_ID", ""),
    ("IBM_RHAI_PROJECT_ID", "../escape"), ("IBM_RHAI_PROJECT_ID", "?key=" + SECRET)])
def test_invalid_configuration_fails_offline_without_value_echo(monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    result = provider_preflight(PROVIDER, MODEL, "tic-tac-toe", live=True)
    assert result["ok"] is False
    assert_private(result)
    with pytest.raises(ProviderCallError):
        agent().act(_request())


def test_gateway_rejected_before_transport():
    runtime = ProviderRuntimeConfig(gateway_base_url="https://example.invalid")
    assert provider_preflight(PROVIDER, MODEL, "tic-tac-toe", runtime_config=runtime)["ok"] is False
    with pytest.raises(ProviderCallError, match="direct public"):
        agent(runtime_config=runtime).act(_request())


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503, 504])
def test_http_failures_suppress_credentials_and_never_retry(monkeypatch, status):
    data = {"id": "id-" + SECRET, "model": SECRET, "error": {"message": PRIVATE},
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}}
    calls = install(monkeypatch, data, status=status,
                    headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET,
                             "Retry-After": "17"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as caught:
        selected.act(_request())
    assert caught.value.status_code == status
    assert caught.value.retry_permitted is False
    assert caught.value.retry_after_seconds == 17
    assert len(calls) == len(selected.attempt_receipts) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert selected.last_receipt["provider_response_id"] is None
    assert_private([str(caught.value), caught.value.receipt, selected.attempt_receipts])


@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls", "function_call",
                                   "cancelled", "error", "time_limit", None, [], "bad-" + SECRET])
def test_incomplete_finish_never_accepts_legal_looking_text(monkeypatch, reason):
    data = wire()
    data["choices"][0]["finish_reason"] = reason
    install(monkeypatch, data)
    selected = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError):
        selected.act(_request())
    assert len(selected.attempt_receipts) == 1
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert_private(selected.last_receipt)


@pytest.mark.parametrize("mutation", ["refusal", "tool", "bad_role", "no_content",
    "only_reasoning", "sdk_text", "two_choices", "no_choices", "stream_chunk", "embedded_error"])
def test_schema_and_semantic_errors_keep_accounting_private(monkeypatch, mutation):
    data = wire()
    message = data["choices"][0]["message"]
    message["reasoning_content"] = PRIVATE
    if mutation == "refusal":
        message["refusal"] = PRIVATE
    elif mutation == "tool":
        message["tool_calls"] = [{"function": {"name": PRIVATE}}]
    elif mutation == "bad_role":
        message["role"] = "user"
    elif mutation in {"no_content", "only_reasoning"}:
        message.pop("content")
    elif mutation == "sdk_text":
        data.pop("choices")
        data["output_text"] = '{"action":1}'
    elif mutation == "two_choices":
        data["choices"].append(copy.deepcopy(data["choices"][0]))
    elif mutation == "no_choices":
        data["choices"] = []
    elif mutation == "stream_chunk":
        data["object"] = "chat.completion.chunk"
    elif mutation == "embedded_error":
        data["error"] = {"message": PRIVATE}
    install(monkeypatch, data)
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(_request())
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert_private(selected.attempt_receipts)


@pytest.mark.parametrize("body", [b"not-json", b'[]', b'{"id":"' + SECRET.encode(),
                                 b'{"id":1,"id":2}', b'{"usage": NaN}'])
def test_malformed_body_and_credential_headers(monkeypatch, body):
    install(monkeypatch, content=body, headers={"x-request-id": SECRET,
                                               "x-gateway-request-id": SECRET})
    selected = agent()
    with pytest.raises(ProviderCallError) as caught:
        selected.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert selected.last_receipt["usage"] == {}
    assert_private([str(caught.value), selected.attempt_receipts])


@pytest.mark.parametrize("identity", [None, "different-model", SECRET, 9, ""])
def test_missing_or_different_identity_never_invented(monkeypatch, identity):
    data = wire()
    if identity is None:
        data.pop("model")
    else:
        data["model"] = identity
    install(monkeypatch, data)
    selected = agent()
    if identity is None:
        selected.act(_request())
    else:
        with pytest.raises(ProviderCallError):
            selected.act(_request())
    assert selected.last_receipt["model"] == MODEL
    assert selected.last_receipt["locked_model_id"] == (
        identity if isinstance(identity, str) and identity and identity != SECRET else None)
    assert_private(selected.attempt_receipts)


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 12},
    {"prompt_tokens": 12, "completion_tokens": 4},
    {"prompt_tokens": -1, "completion_tokens": 4, "total_tokens": 16},
    {"prompt_tokens": True, "completion_tokens": "4", "total_tokens": False},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 1}])
def test_missing_and_invalid_usage_is_not_filled_in(monkeypatch, usage):
    data = wire()
    data["usage"] = usage
    install(monkeypatch, data)
    selected = agent()
    selected.act(_request())
    normalized = selected.last_receipt["usage"]
    if not usage:
        assert normalized == {}
    elif (not isinstance(usage.get("total_tokens"), int)
          or isinstance(usage.get("total_tokens"), bool)):
        assert normalized.get("total_tokens") is None
    if normalized:
        assert normalized["reasoning_included_in_output"] is None
        assert normalized["reasoning_tokens"] is None
    assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("field", ["id", "model", "content", "nested_receipt"])
def test_known_credential_echo_on_success_never_escapes(monkeypatch, field):
    data = wire()
    if field in {"id", "model"}:
        data[field] = "echo-" + SECRET
    elif field == "content":
        data["choices"][0]["message"]["content"] = json.dumps(
            {"action": 1, "public_explanation": SECRET})
    else:
        from eslams import agents
        original = agents._receipt
        def receipt(**kwargs):
            return {**original(**kwargs), "extension": {SECRET: ["echo-" + SECRET]}}
        monkeypatch.setattr(agents, "_receipt", receipt)
    calls = install(monkeypatch, data, headers={"x-request-id": SECRET})
    selected = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    if field in {"model", "content"}:
        with pytest.raises(ProviderCallError):
            selected.act(_request())
    else:
        response = selected.act(_request())
        assert_private(response.to_dict())
    assert len(calls) == 1
    assert_private(selected.attempt_receipts)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError, ProtocolError])
@pytest.mark.parametrize("observed", [False, True])
def test_transport_partial_and_unobserved_failures_are_private(monkeypatch, error_type, observed):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        error = error_type("diagnostic-" + SECRET)
        if observed:
            error._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", SECRET), ("x-gateway-request-id", SECRET)))
        raise error
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        selected.act(_request())
    assert len(calls) == 1
    assert_private([str(caught.value), selected.attempt_receipts])


def test_cancellation_is_never_replayed(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise ExecutionCancelled()
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    with pytest.raises(ExecutionCancelled):
        agent(runtime_config=ProviderRuntimeConfig(max_retries=3)).act(_request())
    assert len(calls) == 1


def test_credential_absence_and_invalid_key_do_not_invoke(monkeypatch):
    for value in ("", "invalid key"):
        monkeypatch.setenv(API_KEY_ENV, value)
        selected = agent()
        with pytest.raises(ProviderCallError) as caught:
            selected.act(_request())
        assert caught.value.error_kind == "provider_auth_failed"
        assert provider_preflight(PROVIDER, MODEL, "tic-tac-toe", live=True)["ok"] is False


def test_strict_catalogue_cannot_invent_host_availability():
    result = provider_preflight(PROVIDER, MODEL, "tic-tac-toe", strict_catalogue=True)
    assert result["ok"] is False
    assert result["checks"]["registry_entry"] is False


def test_generic_rate_rejection_shape_does_not_authorize_host_replay(monkeypatch):
    data = {"error": {"type": "rate_limit_error"}}
    from eslams.agents import _safe_rate_rejection
    assert _safe_rate_rejection(data, 429)
    calls = install(monkeypatch, data, status=429, headers={"retry-after": "0"})
    with pytest.raises(ProviderCallError) as caught:
        agent(runtime_config=ProviderRuntimeConfig(max_retries=2)).act(_request())
    assert caught.value.retry_permitted is False
    assert len(calls) == 1


def test_artifact_preserves_incomplete_accounting_and_privacy(monkeypatch, tmp_path):
    data = wire()
    data["id"] = SECRET
    data["choices"][0]["message"]["reasoning_content"] = PRIVATE
    data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 2}
    install(monkeypatch, data, headers={"x-request-id": SECRET})
    result = Runner().run(RunConfig(arena_id="tic-tac-toe",
        agents={"player_1": agent()}, max_turns=1, output_dir=tmp_path,
        execution_profile="official_eval"))
    assert result.score.usage_complete is False
    for path in result.artifact_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert SECRET.encode() not in content
            assert PRIVATE.encode() not in content


@pytest.mark.parametrize("partial", [False, True])
def test_raw_http_bytes_through_real_bounded_transport(monkeypatch, partial):
    from eslams import agents, http_io
    calls = []
    raw = (Path(__file__).parent / "fixtures/provider/"
           "ibm_rhai_chat_completions_success.json").read_bytes()

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            if partial:
                yield b'{"id":"' + SECRET.encode()
                raise httpx.RemoteProtocolError("body interrupted " + SECRET)
            yield raw

    def handle(request):
        calls.append(request)
        assert request.method == "POST"
        assert str(request.url) == (
            "https://us-east.rhai.ibm.com/v1/projects/project-fixture/inference/chat/completions")
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert json.loads(request.content)["model"] == MODEL
        if partial:
            return httpx.Response(200, stream=Body(), headers={"x-request-id": SECRET})
        return httpx.Response(200, stream=Body(), headers={"content-type": "application/json"})

    original = httpx.AsyncClient
    def client(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(http_io.httpx, "AsyncClient", client)
    monkeypatch.setattr(agents, "bounded_post", http_io.bounded_post)
    selected = agent()
    if partial:
        with pytest.raises(ProviderCallError):
            selected.act(_request())
        assert selected.last_receipt["status_code"] == 200
        assert selected.last_receipt["usage"] == {}
    else:
        assert selected.act(_request()).action == 1
    assert len(calls) == 1
    assert_private(selected.attempt_receipts)
