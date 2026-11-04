"""Deterministic Arcee raw-wire tests; no credentials or live inference.

Envelope provenance: https://docs.arcee.ai/api-reference/chat-completion
and https://docs.arcee.ai/get-started/quick-start (2026-11-04).
The fixture instantiates the documented OpenAI-compatible standard envelope,
with synthetic redacted IDs/content/counts; it is not a captured paid request.
"""

from __future__ import annotations

import copy
import json
import traceback
from contextlib import asynccontextmanager
from dataclasses import replace
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
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.arcee import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

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


@pytest.mark.parametrize("model", ["", " ", "\t\n", None])
@pytest.mark.parametrize("alias", ["arcee", "arcee-ai", "arcee_ai", "ARCEE-AI"])
def test_nonblank_exact_model_required_for_direct_agent_and_cli(model, alias):
    with pytest.raises(ValueError, match="explicit exact model"):
        ModelProviderAgent(provider=alias, model=model, api_key_env="ARCEE_API_KEY")
    if model is not None:
        with pytest.raises(ValueError, match="explicit exact model"):
            _provider_agent(f"{alias}:{model}")


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("model", ["", " ", "\t\n", None])
def test_preflight_rejects_blank_model_before_any_network(monkeypatch, live, model):
    monkeypatch.setenv("ARCEE_API_KEY", "fixture-primary-key")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("inference"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    result = provider_preflight("arcee_ai", model, "tic-tac-toe", live=live)
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert result["readiness"]["configuration_ready"] is False
    assert result["readiness"]["inference"] == "not_attempted"


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("controls", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 2048},
    {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 0},
    {"openrouter_provider_order": ("backend",)},
])
def test_preflight_rejects_explicit_controls_before_discovery_or_inference(
    monkeypatch, live, controls,
):
    monkeypatch.setenv("ARCEE_API_KEY", "fixture-primary-key")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("inference"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    result = provider_preflight("arcee", MODEL, "tic-tac-toe", live=live,
                                runtime_config=ProviderRuntimeConfig(**controls))
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert result["readiness"]["configuration_ready"] is False
    assert result["readiness"]["inference"] == "not_attempted"


def test_changed_model_and_zero_reasoning_budget_rejected_before_transport(wire):
    _, calls = wire
    a = agent()
    a.model = " "
    with pytest.raises(ProviderCallError, match="explicit exact model"):
        a.act(request())
    with pytest.raises(ProviderCallError, match="native reasoning defaults"):
        agent(runtime_config=ProviderRuntimeConfig(reasoning_budget_tokens=0)).act(request())
    assert not calls


@pytest.mark.parametrize("mode", [
    "success", "http_error", "error200", "malformed_json", "malformed_choices",
    "refused", "truncated", "partial_timeout", "partial_reset", "partial_resource",
])
@pytest.mark.parametrize("selected_env", ["ARCEE_API_KEY", "ARCEE_SECONDARY_API_KEY"])
def test_actual_wire_credentials_never_persist_in_receipts_or_artifacts(
    monkeypatch, tmp_path, mode, selected_env,
):
    # Arbitrary printable secrets deliberately lack known API-key prefixes.
    primary, secondary = "PrimaryCredential12345", "SecondaryCredential67890"
    monkeypatch.setenv("ARCEE_API_KEY", primary)
    monkeypatch.setenv("ARCEE_SECONDARY_API_KEY", secondary)
    # When the alternate is selected, both configured values need protection.
    # When the primary is selected, secondary remains private body prose only.
    echoed_secondary = secondary if selected_env != "ARCEE_API_KEY" else primary
    payload = json.loads(FIXTURE.read_text())
    payload["id"] = f"generation-{primary}"
    payload["model"] = f"model/{echoed_secondary}"
    payload["usage"]["debug"] = primary
    payload["choices"][0]["message"]["reasoning"] = secondary
    status = 200
    if mode == "http_error":
        status = 429
        payload["detail"] = secondary
    elif mode == "error200":
        payload["error"] = {"code": 429, "message": secondary}
    elif mode == "malformed_choices":
        payload["choices"] = []
    elif mode == "refused":
        payload["choices"][0]["message"]["refusal"] = secondary
    elif mode == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    calls = []
    original_client = httpx.AsyncClient

    class PartialStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps({"private": primary, "private2": secondary}).encode()
            if mode == "partial_timeout":
                raise httpx.ReadTimeout(secondary)
            if mode == "partial_reset":
                raise httpx.ReadError(secondary)
            yield b"x" * (1024 * 1024 + 1)

    def respond(sent_request):
        calls.append(sent_request)
        expected = primary if selected_env == "ARCEE_API_KEY" else secondary
        assert sent_request.headers["Authorization"] == f"Bearer {expected}"
        headers = {
            "x-request-id": f"request-{primary}",
            "cf-aig-request-id": f"gateway-{echoed_secondary}",
            "Retry-After": "2",
        }
        if mode.startswith("partial_"):
            return httpx.Response(status, stream=PartialStream(), headers=headers)
        content = (
            f"invalid JSON: {primary} {secondary}".encode() if mode == "malformed_json"
            else json.dumps(payload).encode()
        )
        return httpx.Response(status, stream=httpx.ByteStream(content), headers=headers)

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (
                original_client(transport=httpx.MockTransport(respond)) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                yield response

    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    a = ModelProviderAgent("arcee-ai", MODEL, selected_env,
                           runtime_config=ProviderRuntimeConfig(max_retries=2))
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=a, max_turns=1,
                                    on_agent_error="forfeit", output_dir=tmp_path))
    assert len(calls) == len(a.attempt_receipts) == 1
    receipt = a.last_receipt
    assert receipt["request_id"] is None
    assert receipt["gateway_request_id"] is None
    assert receipt.get("provider_response_id") is None
    assert receipt.get("locked_model_id") is None
    assert receipt.get("model_identity_source") is None
    if mode == "success":
        assert receipt["outcome"] == "ok"
        assert receipt["usage"]["total_tokens"] == 16
    else:
        assert receipt["outcome"] != "ok"
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            for credential in (primary, secondary):
                assert credential.encode() not in path.read_bytes(), path


@pytest.mark.parametrize("credential_field", ["public_explanation", "action", "unknown"])
def test_credential_echo_in_action_text_never_reaches_public_output(wire, credential_field):
    payload, calls = wire
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, credential_field: "rcai-fixture-credential",
    })
    a = agent()
    with pytest.raises(ProviderCallError, match="credential material"):
        a.act(request())
    assert len(calls) == 1
    assert a.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert "rcai-fixture-credential" not in json.dumps(a.last_receipt)


def test_escaped_credential_echo_in_action_json_is_rejected(wire):
    payload, _ = wire
    payload["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"\\u0072cai-fixture-credential"}'
    )
    with pytest.raises(ProviderCallError, match="credential material"):
        agent().act(request())


def test_uninspectable_action_text_preserves_sanitized_usage_receipt(wire):
    payload, _ = wire
    payload["choices"][0]["message"]["content"] = "[" * 2000 + "0" + "]" * 2000
    payload["id"] = "rcai-fixture-credential"
    a = agent()
    with pytest.raises(ProviderCallError, match="safely inspected"):
        a.act(request())
    assert a.last_receipt["usage"]["total_tokens"] == 16
    assert a.last_receipt["provider_response_id"] is None


def test_credential_protection_preserves_explicit_safe_retry_receipts(monkeypatch, wire):
    payload, _ = wire
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429}},
                                  headers={"x-request-id": "rcai-fixture-credential"})
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    assert a.act(request()).action == 1
    assert len(calls) == len(a.attempt_receipts) == 2
    assert [r["attempt_index"] for r in a.attempt_receipts] == [1, 2]
    assert a.attempt_receipts[0]["request_id"] is None
    assert a.attempt_receipts[1]["provider_response_id"] == payload["id"]


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ReadError])
def test_private_transport_causes_are_not_exposed_in_tracebacks(monkeypatch, failure):
    primary, secondary = "PrimaryCredential12345", "SecondaryCredential67890"
    monkeypatch.setenv("ARCEE_API_KEY", primary)
    monkeypatch.setenv("ARCEE_SECONDARY_API_KEY", secondary)

    def post(*args, **kwargs):
        raise failure(f"{primary} {secondary}")

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = ModelProviderAgent("arcee-ai", MODEL, "ARCEE_SECONDARY_API_KEY")
    with pytest.raises((ProviderCallError, TimeoutError)) as error:
        a.act(request())
    public = "".join(traceback.format_exception(error.value)) + json.dumps(a.attempt_receipts)
    assert primary not in public and secondary not in public
