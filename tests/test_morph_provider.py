"""Morph's documented REST envelope plus deterministic synthetic fault injection.

Fixture provenance: https://docs.morphllm.com/api-reference/endpoint/apply
shares the response schema with general inference (see /endpoints). The sample
envelope and counters are retained; content is replaced with a safe test action.
No model field is invented in the base fixture. Added identities/details below
are explicit synthetic cases, not observed live responses.
"""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers import load_provider_registry
from eslams.providers.morph import CHAT_COMPLETIONS_ENDPOINT, MODEL_EFFORTS, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

SECRET = "opaque-morph-credential-X9"
SECONDARY = "opaque-secondary-credential-Y8"
MODEL = "morph-kimik31"


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider" /
                       "morph_chat_completions_success.json").read_text())


def request(arena="tic-tac-toe"):
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_morph_fixture", episode_id="ep_001",
        turn_id=0, arena=ArenaIdentity(id=arena, version="1.0.0"),
        agent=AgentIdentity(id="morph-test", version="fixture-v1"), active_player="player_1",
        observation={"board": [], "you_are": "player_1"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[{"turn_id": i, "action": i % 3} for i in range(100)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(**kwargs):
    return ModelProviderAgent("morph", kwargs.pop("model", MODEL), "MORPH_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def isolated_provider(monkeypatch):
    monkeypatch.setenv("MORPH_API_KEY", SECRET)
    monkeypatch.setenv("OTHER_PROVIDER_API_KEY", SECONDARY)

    def forbidden(*args, **kwargs):
        pytest.fail("unexpected real network call")

    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", forbidden)


def respond(monkeypatch, data=None, *, status=200, headers=None, content=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        options = {"content": content} if content is not None else {"json": data or wire()}
        return httpx.Response(status, headers=headers or {}, **options)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_exact_endpoint_auth_full_history_and_native_defaults(monkeypatch):
    calls = respond(monkeypatch)
    a = agent()
    result = a.act(request())
    endpoint, options = calls[0]
    assert len(calls) == 1 and endpoint == CHAT_COMPLETIONS_ENDPOINT
    assert options["headers"] == {"Authorization": f"Bearer {SECRET}",
                                  "Content-Type": "application/json"}
    payload = options["json"]
    assert payload["model"] == MODEL and payload["stream"] is False
    assert set(payload) == {"model", "messages", "stream"}
    prompt = payload["messages"][1]["content"]
    history = json.loads(prompt.splitlines()[-1])["history"]
    assert history == request().history
    assert options["timeout"].read is None
    assert result.action == 1
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "morph" and receipt["model"] == MODEL
    assert receipt["endpoint_kind"] == "morph_chat_completions"
    assert receipt["parser_version"] == "morph-chat-completions-raw-v1"
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["usage"]["input_tokens"] == 25
    assert receipt["usage"]["output_tokens"] == 32
    assert receipt["usage"]["total_tokens"] == 57
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(result.to_dict())


@pytest.mark.parametrize("arena", ["tic-tac-toe", "chess", "gridworld"])
def test_controls_do_not_depend_on_game(monkeypatch, arena):
    calls = respond(monkeypatch)
    agent().act(request(arena))
    assert set(calls[0][1]["json"]) == {"model", "messages", "stream"}


@pytest.mark.parametrize("model,efforts", list(MODEL_EFFORTS.items()))
def test_every_documented_model_effort_is_forwarded_exactly(monkeypatch, model, efforts):
    calls = respond(monkeypatch)
    for effort in efforts:
        runtime = ProviderRuntimeConfig(reasoning_effort=effort)
        agent(model=model, runtime_config=runtime).act(request())
        assert calls[-1][1]["json"]["reasoning_effort"] == effort


def test_operator_limits_temperature_gateway_and_disabled_reasoning(monkeypatch):
    calls = respond(monkeypatch)
    runtime = ProviderRuntimeConfig(reasoning="disabled", timeout_ms=20_000,
                                   gateway_base_url="https://gateway.example/morph")
    agent(runtime_config=runtime, temperature=0.3, max_output_tokens=321).act(request())
    endpoint, options = calls[0]
    assert endpoint == "https://gateway.example/morph/v1/chat/completions"
    assert options["json"]["max_tokens"] == 321
    assert options["json"]["temperature"] == 0.3
    assert options["json"]["reasoning_effort"] == "none"
    assert options["timeout"].deadline is not None


@pytest.mark.parametrize("model", [None, "", " ", "model\n", "auto", "morph-v3-fast",
    "morph-v3-large", "morph/morph-v3-fast", "morph-v0", "morph-v2", "morph-compactor",
    "reflex", "morph-warp-grep-v2.1", "morph-router"])
def test_missing_blank_and_specialized_models_fail_without_network(model):
    with pytest.raises(ValueError):
        agent(model=model)
    with pytest.raises(ValueError):
        provider_preflight("morph", model, "tic-tac-toe", live=True)


@pytest.mark.parametrize("model,settings", [
    (MODEL, {"reasoning_effort": "minimal"}),
    ("morph-kimik3-fast", {"reasoning_effort": "max"}),
    (MODEL, {"reasoning_effort": "invented"}),
    (MODEL, {"reasoning_budget_tokens": 1024}),
    (MODEL, {"gemini_thinking_budget": -1}),
    (MODEL, {"reasoning": "enabled"}),
    (MODEL, {"reasoning": "enabled", "reasoning_effort": "none"}),
    (MODEL, {"history_window_turns": 1}),
    (MODEL, {"openrouter_provider_order": ("Morph",)}),
    ("future-model", {"reasoning_effort": "high"}),
    ("future-model", {"reasoning": "disabled"}),
])
def test_unsupported_controls_fail_before_network(model, settings):
    runtime = ProviderRuntimeConfig(**settings)
    with pytest.raises(ValueError):
        agent(model=model, runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("morph", model, "tic-tac-toe", runtime_config=runtime, live=True)


def test_unknown_exact_model_still_dispatches_with_no_implicit_controls(monkeypatch):
    calls = respond(monkeypatch)
    a = agent(model="Future-Exact-Model")
    a.act(request())
    assert calls[0][1]["json"]["model"] == "Future-Exact-Model"
    assert not a.capabilities.known


@pytest.mark.parametrize("key", ["", " \r\n ", "internal key", "nonascii-☃", "tab\tkey"])
def test_bad_credentials_do_not_reach_transport(monkeypatch, key):
    monkeypatch.setenv("MORPH_API_KEY", key)
    a = agent()
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == "provider_auth_failed"
    assert not key.strip() or key.strip() not in str(error.value)
    assert a.last_receipt["usage"] == {}


def test_trimmed_key_and_response_attested_identity(monkeypatch):
    monkeypatch.setenv("MORPH_API_KEY", f"  {SECRET}\r\n")
    data = wire()
    data["model"] = "different-response-attested-model"
    data["usage"]["prompt_tokens_details"] = {"cached_tokens": 10}
    data["usage"]["completion_tokens_details"] = {"reasoning_tokens": 4}
    calls = respond(monkeypatch, data)
    a = agent()
    a.act(request())
    assert calls[0][1]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert a.last_receipt["locked_model_id"] == data["model"]
    assert a.last_receipt["model_identity_source"] == "provider_response"
    assert a.last_receipt["usage"]["cached_input_tokens"] == 10
    assert a.last_receipt["usage"]["reasoning_tokens"] == 4
    assert a.last_receipt["usage"]["output_tokens"] == 32


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable")])
def test_http_failures_receipts_no_credential_echo_or_retries(monkeypatch, status, kind):
    data = {"error": {"code": "rate_limited", "message": SECRET, "id": SECRET,
                      "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}}
    calls = respond(monkeypatch, data, status=status,
                    headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET,
                             "Retry-After": "12"})
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == kind
    assert len(calls) == 1 and len(a.attempt_receipts) == 1
    receipt = a.last_receipt
    assert receipt["status_code"] == status
    assert receipt["request_id"] is None and receipt["gateway_request_id"] is None
    assert receipt["provider_response_id"] is None and receipt["locked_model_id"] is None
    assert receipt["usage"]["input_tokens"] == 2
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in str(error.value) + json.dumps(receipt) + str(error.value.receipt)


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("content", [b'{', b'[]', b'{"id":1,"id":2}', b'{"usage":NaN}',
                                       b'\xff'])
def test_malformed_envelopes_sanitize_header_receipts(monkeypatch, status, content):
    calls = respond(monkeypatch, status=status, content=content,
                    headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET})
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert len(calls) == 1
    assert a.last_receipt["request_id"] is None
    assert a.last_receipt["gateway_request_id"] is None
    assert not a.last_receipt["usage"]
    assert SECRET not in json.dumps(a.attempt_receipts)


@pytest.mark.parametrize("position", ["model", "id", "header", "gateway", "explanation",
                                     "escaped_explanation", "text"])
def test_success_echoes_cannot_escape_in_identity_or_action(monkeypatch, position):
    data = wire()
    headers = {}
    if position in {"model", "id"}:
        data[position] = f"prefix-{SECRET}"
    elif position in {"header", "gateway"}:
        headers["x-request-id" if position == "header" else "cf-aig-request-id"] = SECRET
    elif position in {"explanation", "escaped_explanation"}:
        text = json.dumps({"action": 1, "public_explanation": SECRET})
        if position == "escaped_explanation":
            text = text.replace(SECRET, "".join(f"\\u{ord(char):04x}" for char in SECRET))
        data["choices"][0]["message"]["content"] = text
    else:
        data["choices"][0]["message"]["content"] = f'{{"action": 1}} {SECRET}'
    respond(monkeypatch, data, headers=headers)
    a = agent()
    if position in {"explanation", "escaped_explanation", "text"}:
        with pytest.raises(ProviderCallError):
            a.act(request())
    else:
        result = a.act(request())
        assert SECRET not in json.dumps(result.to_dict())
    assert SECRET not in json.dumps(a.attempt_receipts)
    if position == "model":
        assert a.last_receipt["locked_model_id"] is None
        assert a.last_receipt["model_identity_source"] is None


@pytest.mark.parametrize("reason,kind", [("length", "provider_output_truncated"),
    ("content_filter", "provider_refused"), ("tool_calls", "provider_request_rejected"),
    (None, "provider_response_schema_mismatch"), ("invented", "provider_response_schema_mismatch"),
    ({"echo": SECRET}, "provider_response_schema_mismatch")])
def test_incomplete_and_tool_envelopes_never_accept_legal_looking_text(monkeypatch, reason, kind):
    data = wire()
    data["choices"][0]["finish_reason"] = reason
    calls = respond(monkeypatch, data)
    a = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2, max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == kind
    assert len(calls) == 1 and a.last_receipt["usage"]["total_tokens"] == 57
    assert SECRET not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("field,value", [("choices", []), ("choices", [{}]),
    ("object", "chat.completion.chunk"), ("choices", [wire()["choices"][0]] * 2)])
def test_wrong_wire_shapes_fail_with_usage_retained(monkeypatch, field, value):
    data = wire()
    data[field] = copy.deepcopy(value)
    respond(monkeypatch, data)
    a = agent()
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert a.last_receipt["usage"]["total_tokens"] == 57


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 25},
    {"input_tokens": 25, "output_tokens": 32, "total_tokens": 57},
    {"prompt_tokens": -1, "completion_tokens": 32, "total_tokens": 57},
    {"prompt_tokens": 25, "completion_tokens": True, "total_tokens": 57}])
def test_missing_partial_or_invalid_usage_does_not_become_complete(monkeypatch, usage):
    data = wire()
    data["usage"] = usage
    respond(monkeypatch, data)
    a = agent()
    assert a.act(request()).action == 1
    normalized = a.last_receipt["usage"]
    assert not normalized or normalized.get("usage_validation_errors") or (
        normalized.get("input_tokens") is None or normalized.get("output_tokens") is None
    )
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("failure", ["timeout", "reset", "resource"])
@pytest.mark.parametrize("secret", [SECRET, SECONDARY])
def test_actual_partial_reader_preserves_only_safe_evidence(monkeypatch, status, failure, secret):
    calls = []
    original_client = httpx.AsyncClient

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps({"model": secret, "usage": {"total_tokens": 99}})[:-1].encode()
            if failure == "timeout":
                raise httpx.ReadTimeout(secret)
            if failure == "reset":
                raise httpx.ReadError(secret)
            yield b"x" * (1024 * 1024 + 1)

    def handler(req):
        calls.append(1)
        return httpx.Response(status, stream=Stream(), request=req,
                              headers={"x-request-id": secret, "cf-aig-request-id": secret})

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (
                original_client(transport=httpx.MockTransport(handler)) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                yield response

    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr("eslams.agents.bounded_post", http_io.bounded_post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert calls == [1]
    assert a.last_receipt["status_code"] == status
    assert a.last_receipt["request_id"] is None and a.last_receipt["gateway_request_id"] is None
    assert not a.last_receipt["usage"] and a.last_receipt["locked_model_id"] is None
    assert secret not in str(error.value) + json.dumps(a.last_receipt)


def test_timeout_before_headers_never_retries(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout(SECRET)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(TimeoutError):
        a.act(request())
    assert calls == [1] and not a.last_receipt["usage"]
    assert SECRET not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("code,kind", [("unauthorized", "provider_auth_failed"),
    ("rate_limited", "provider_rate_limited"), ("internal_error", "provider_unavailable"),
    ("invalid_request_error", "provider_request_rejected")])
@pytest.mark.parametrize("position", ["top", "choice"])
def test_http_200_errors_are_quarantined_and_never_retried(monkeypatch, code, kind, position):
    data = wire()
    data["model"] = "unverified-error-model"
    error = {"code": code, "message": SECRET}
    if position == "top":
        data["error"] = error
    else:
        data["choices"][0]["error"] = error
    calls = respond(monkeypatch, data)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == kind
    assert len(calls) == 1 and a.last_receipt["locked_model_id"] is None
    assert a.last_receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert a.last_receipt["usage"]["total_tokens"] == 57
    assert SECRET not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("field,value", [("tool_calls", [{}]), ("tool_calls", {}),
    ("tool_calls", "bad"), ("function_call", {}), ("refusal", "denied"), ("refusal", {})])
def test_tool_and_refusal_extensions_cannot_override_text(monkeypatch, field, value):
    data = wire()
    data["choices"][0]["message"][field] = value
    calls = respond(monkeypatch, data)
    a = agent()
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert len(calls) == 1


def test_parse_failure_preserves_usage_and_receipt_invocation(monkeypatch):
    from eslams.deadlines import receipt_invocation

    data = wire()
    data["choices"][0]["message"]["content"] = '{"action": 999}'
    calls = respond(monkeypatch, data)
    a = agent()
    invocation = object()
    with receipt_invocation(invocation):
        with pytest.raises(ProviderCallError) as error:
            a.act(request())
        assert error.value.error_kind == "action_response_unparseable"
        assert a._receipt_snapshot(invocation)[0]["usage"]["total_tokens"] == 57
    assert calls and len(calls) == 1
    assert a._receipt_snapshot(object()) == []


def test_cli_dispatch_rejects_missing_model_and_preserves_exact_identity():
    a = _provider_agent("morph:Future-Exact-Model")
    assert a.provider == "morph" and a.model == "Future-Exact-Model"
    assert a.api_key_env == "MORPH_API_KEY"
    for value in ("morph", "morph:", "morph: "):
        with pytest.raises(ValueError, match="model ID"):
            _provider_agent(value)


def test_offline_cli_preflight_and_specialized_catalogue(capsys):
    assert main(["providers", "preflight", "--provider", "morph", "--model", MODEL]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] and result["checks"]["registry_entry"]
    assert result["checks"]["game_agent_supported"]
    assert result["checks"]["account_model_visible"] is None
    assert result["preflight_mode"] == "configuration_only"
    assert result["readiness"]["inference"] == "not_attempted"
    assert main(["providers", "preflight", "--provider", "morph", "--model", " "]) == 1
    assert "nonblank model ID" in capsys.readouterr().err
    registry = load_provider_registry()
    for model in ("auto", "morph-v3-fast", "morph/morph-v3-large"):
        assert not registry.resolve("morph", model).game_agent_supported


def test_mocked_models_discovery_and_live_preflight(monkeypatch):
    gets = []

    def get(endpoint, **kwargs):
        gets.append((endpoint, kwargs))
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("morph") == [MODEL]
    calls = respond(monkeypatch)
    result = provider_preflight("morph", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert gets[0][0] == MODELS_ENDPOINT
    assert gets[0][1]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert len(calls) == 1 and calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    assert SECRET not in json.dumps(result)


def test_cli_run_dispatches_native_morph_without_network_or_fallback(monkeypatch, tmp_path, capsys):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        prompt = json.loads(kwargs["json"]["messages"][1]["content"].splitlines()[-1])
        data = wire()
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": prompt["legal_actions"][0],
        })
        return httpx.Response(200, json=data)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", f"morph:{MODEL}",
                 "--out", str(tmp_path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary and calls
    assert all(url == CHAT_COMPLETIONS_ENDPOINT and payload["model"] == MODEL
               for url, payload in calls)
    assert all(set(payload) == {"model", "messages", "stream"} for _, payload in calls)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


def test_runner_invalid_output_cannot_score_or_fallback_and_leak_credentials(monkeypatch, tmp_path):
    respond(monkeypatch, {"error": {"code": "unauthorized", "message": SECRET}}, status=401,
            headers={"x-request-id": SECRET})
    a = agent()
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=a, on_agent_error="forfeit",
                                    output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


@pytest.mark.parametrize("secret", [SECRET, SECONDARY])
def test_discovery_rejects_configured_credential_echoes(monkeypatch, capsys, secret):
    def get(*args, **kwargs):
        return httpx.Response(200, json={"data": [{"id": f"prefix-{secret}-suffix"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    result = provider_models_result("morph")
    assert not result["ok"] and not result["models"]
    assert secret not in json.dumps(result)
    assert main(["providers", "models", "--provider", "morph", "--live"]) == 1
    assert secret not in capsys.readouterr().out


@pytest.mark.parametrize("position", ["model", "id", "header", "gateway", "explanation"])
def test_secondary_credential_echoes_in_success_are_contained(monkeypatch, position):
    data = wire()
    headers = {}
    if position in {"id", "model"}:
        data[position] = SECONDARY
    elif position in {"header", "gateway"}:
        headers["x-request-id" if position == "header" else "cf-aig-request-id"] = SECONDARY
    else:
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": 1, "public_explanation": SECONDARY,
        })
    respond(monkeypatch, data, headers=headers)
    a = agent()
    if position == "explanation":
        with pytest.raises(ProviderCallError):
            a.act(request())
    else:
        result = a.act(request())
        assert SECONDARY not in json.dumps(result.to_dict())
    assert SECONDARY not in json.dumps(a.attempt_receipts)


@pytest.mark.parametrize("budget", [0, 1, 4096])
@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
@pytest.mark.parametrize("live", [False, True])
def test_explicit_budgets_fail_preflight_and_reconfigured_agent_before_transport(
    monkeypatch, field, budget, live,
):
    runtime = ProviderRuntimeConfig(**{field: budget})
    with pytest.raises(ValueError, match="provider-specific control"):
        provider_preflight("morph", MODEL, "tic-tac-toe", live=live, runtime_config=runtime)
    a = agent()
    a.runtime_config = runtime
    monkeypatch.delenv("MORPH_API_KEY")
    with pytest.raises(ValueError, match="provider-specific control"):
        a.act(request())
    assert not a.attempt_receipts


@pytest.mark.parametrize("secret", [SECRET, SECONDARY])
@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 429, 500, 503])
@pytest.mark.parametrize("malformed", [False, True])
def test_error_and_malformed_echoes_are_scrubbed_for_all_credentials(
    monkeypatch, secret, status, malformed,
):
    data = {"error": {"code": "rate_limited", "message": secret, "id": secret,
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}}
    calls = respond(monkeypatch, data, status=status,
                    headers={"x-request-id": secret, "cf-aig-request-id": secret},
                    content=(f'{{"secret_echo":"{secret}",'.encode() if malformed else None))
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert len(calls) == 1 and len(a.attempt_receipts) == 1
    assert a.last_receipt["request_id"] is None
    assert a.last_receipt["gateway_request_id"] is None
    assert a.last_receipt.get("provider_response_id") is None
    observed = json.dumps(a.attempt_receipts) + str(error.value) + str(error.value.receipt)
    assert secret not in observed


@pytest.mark.parametrize("secret", [SECRET, SECONDARY])
@pytest.mark.parametrize("encoding", ["raw", "json_unicode", "url", "url_lower"])
def test_encoded_credentials_in_action_text_fail_before_repair(monkeypatch, secret, encoding):
    from urllib.parse import quote

    text = json.dumps({"action": 1, "ignored_private_field": secret})
    if encoding == "json_unicode":
        text = text.replace(secret, "".join(f"\\u{ord(char):04x}" for char in secret))
    elif encoding in {"url", "url_lower"}:
        # Percent-encode a selected credential that actually contains URI delimiters.
        secret = f"{secret}/+%?"
        monkeypatch.setenv("OTHER_PROVIDER_API_KEY", secret)
        encoded = quote(secret, safe="")
        if encoding == "url_lower":
            encoded = encoded.replace("%2F", "%2f").replace("%2B", "%2b")
        text = json.dumps({"action": 1, "ignored_private_field": encoded})
    data = wire()
    data["choices"][0]["message"]["content"] = text
    calls = respond(monkeypatch, data)
    a = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2, max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        a.act(request())
    assert error.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1
    assert secret not in json.dumps(a.attempt_receipts) + str(error.value)


@pytest.mark.parametrize("name", ["MORPH_API_KEY_SECONDARY", "OTHER_PROVIDER_API_KEY",
    "CLOUDFLARE_AI_GATEWAY_TOKEN", "AWS_BEARER_TOKEN_BEDROCK", "SECONDARY_SECRET",
    "SERVICE_PASSWORD", "SERVICE_CREDENTIALS", "SERVICE_ACCESS_KEY_ID"])
def test_secondary_credential_names_are_redaction_only(monkeypatch, name):
    monkeypatch.delenv("OTHER_PROVIDER_API_KEY")
    monkeypatch.setenv(name, SECONDARY)
    data = wire()
    data["id"] = SECONDARY
    calls = respond(monkeypatch, data)
    a = agent()
    a.act(request())
    assert a.last_receipt["provider_response_id"] is None
    assert calls[0][1]["headers"] == {"Authorization": f"Bearer {SECRET}",
                                     "Content-Type": "application/json"}
    assert SECONDARY not in json.dumps(calls[0][1]["json"])


def test_credential_snapshot_survives_environment_change_until_receipts_publish(monkeypatch):
    data = wire()
    data["id"] = SECONDARY

    def post(*args, **kwargs):
        monkeypatch.delenv("OTHER_PROVIDER_API_KEY")
        monkeypatch.setenv("MORPH_API_KEY", "rotated-primary-Z7")
        return httpx.Response(200, json=data, headers={"x-request-id": SECRET})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent()
    result = a.act(request())
    assert result.action == 1
    assert a.last_receipt["provider_response_id"] is None and a.last_receipt["request_id"] is None
    assert all(value not in json.dumps(a.attempt_receipts) for value in (SECRET, SECONDARY))


@pytest.mark.parametrize("status", [200, 401, 429, 503])
@pytest.mark.parametrize("shape", ["model_list", "malformed", "partial"])
def test_discovery_faults_never_publish_either_credential(monkeypatch, status, shape):
    def get(*args, **kwargs):
        if shape == "partial":
            raise httpx.ReadError(f"{SECRET}/{SECONDARY}")
        if shape == "malformed":
            return httpx.Response(status, content=f'{{"echo":"{SECRET}/{SECONDARY}",'.encode())
        return httpx.Response(status, json={"data": [
            {"id": MODEL}, {"id": SECRET}, {"id": SECONDARY},
        ]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    calls = respond(monkeypatch)
    result = provider_models_result("morph")
    assert not result["ok"] and not result["models"]
    preflight = provider_preflight("morph", MODEL, "tic-tac-toe", live=True,
                                   strict_catalogue=True)
    assert not preflight["ok"] and not calls
    assert all(secret not in json.dumps([result, preflight]) for secret in (SECRET, SECONDARY))


def test_custom_primary_environment_also_protects_default_credential(monkeypatch):
    monkeypatch.setenv("CUSTOM_INFERENCE_PASSWORD", "custom-primary-P6")
    data = wire()
    data["id"] = SECRET
    calls = respond(monkeypatch, data)
    a = ModelProviderAgent("morph", MODEL, "CUSTOM_INFERENCE_PASSWORD")
    result = a.act(request())
    assert calls[0][1]["headers"]["Authorization"] == "Bearer custom-primary-P6"
    assert a.last_receipt["provider_response_id"] is None
    assert SECRET not in json.dumps(result.to_dict())


@pytest.mark.parametrize("content", [
    b'{"data": [{"id":"opaque-secondary-credential-Y8", "id":"morph-kimik3"}]}',
    b'{"data": [], "private": NaN}',
    b'{"data": [], "error": {"message":"opaque-secondary-credential-Y8"}}',
    b'{"data": "opaque-secondary-credential-Y8"}',
    b'\xffopaque-secondary-credential-Y8',
])
def test_discovery_rejects_ambiguous_and_malformed_wire_without_echo(monkeypatch, content):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: httpx.Response(200, content=content))
    result = provider_models_result("morph")
    assert not result["ok"] and not result["models"]
    assert SECONDARY not in json.dumps(result)


def test_discovery_keeps_credential_snapshot_during_environment_rotation(monkeypatch):
    def get(*args, **kwargs):
        monkeypatch.delenv("OTHER_PROVIDER_API_KEY")
        return httpx.Response(200, json={"data": [{"id": SECONDARY}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    result = provider_models_result("morph")
    assert not result["ok"] and not result["models"]
    assert SECONDARY not in json.dumps(result)


def test_credential_patterns_beyond_500_characters_are_rejected_before_repair(monkeypatch):
    data = wire()
    data["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": "a" * 600 + " Bearer unconfigured-opaque-value",
    })
    calls = respond(monkeypatch, data)
    a = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert len(calls) == 1


@pytest.mark.parametrize("secret", [SECRET, SECONDARY])
def test_sensitive_model_identity_cannot_become_an_altered_safe_identity(monkeypatch, secret):
    data = wire()
    data["model"] = f"https://user:{secret}@model.invalid"
    data["id"] = f"https://user:{secret}@request.invalid"
    respond(monkeypatch, data)
    a = agent()
    a.act(request())
    assert a.last_receipt["locked_model_id"] is None
    assert a.last_receipt["model_identity_source"] is None
    assert a.last_receipt["provider_response_id"] is None


@pytest.mark.parametrize("model", ["morph-kimik3", "morph-kimik3-fast", "morph-dsv4flash"])
def test_removed_catalogue_ids_remain_literal_unverified_choices(monkeypatch, model):
    calls = respond(monkeypatch)
    selected = agent(model=model)
    assert not selected.capabilities.known
    selected.act(request())
    assert calls[0][1]["json"]["model"] == model
    with pytest.raises(ValueError, match="unsupported or unverified"):
        agent(model=model, runtime_config=ProviderRuntimeConfig(reasoning_effort="high"))


@pytest.mark.parametrize("model", ["kimi-latest", "deepseek-flash-latest"])
def test_rolling_aliases_are_sent_unchanged_and_identity_is_response_evidence(monkeypatch, model):
    data = wire()
    data["model"] = "morph-kimik31" if model == "kimi-latest" else "morph-dsv41flash-1017"
    calls = respond(monkeypatch, data)
    selected = agent(model=model)
    selected.act(request())
    assert calls[0][1]["json"]["model"] == model
    assert selected.last_receipt["model"] == model
    assert selected.last_receipt["locked_model_id"] == data["model"]
    assert selected.last_receipt["model_identity_source"] == "provider_response"
    with pytest.raises(ValueError, match="unverified"):
        agent(model=model, runtime_config=ProviderRuntimeConfig(reasoning_effort="high"))


@pytest.mark.parametrize("effort", ["0", "1", "25", "100", "101"])
def test_numeric_effort_strings_are_rejected_precisely_without_inventing_a_budget(effort):
    runtime = ProviderRuntimeConfig(reasoning_effort=effort)
    with pytest.raises(ValueError, match="integer effort is not exposed"):
        agent(model="morph-dsv41flash", runtime_config=runtime)
    with pytest.raises(ValueError, match="integer effort is not exposed"):
        provider_preflight("morph", "morph-dsv41flash", "tic-tac-toe", runtime_config=runtime)


@pytest.mark.parametrize("model", ["morph-glm53-744b", "morph-glm52-744b", "morph-glm53flash",
                                    "morph-dsv41flash", "morph-dsv41flash-1017"])
@pytest.mark.parametrize("effort", ["minimal", "medium"])
def test_official_index_effort_aliases_are_accepted_and_forwarded(monkeypatch, model, effort):
    calls = respond(monkeypatch)
    agent(model=model, runtime_config=ProviderRuntimeConfig(reasoning_effort=effort)).act(request())
    assert calls[0][1]["json"]["reasoning_effort"] == effort
