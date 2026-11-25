"""Keyless raw-wire Krutrim checks; provenance: docs/providers/KRUTRIM.md."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_preflight
from eslams.providers.krutrim import API_KEY_ENV, CHAT_COMPLETIONS_ENDPOINT
from eslams.runner import RunConfig, Runner

SECRET = "syntheticCredentialForKrutrim123"
MODEL = "Krutrim-spectre-v2"
FIXTURE = Path(__file__).parent / "fixtures/provider/krutrim_chat_completions_success.json"


def wire():
    return json.loads(FIXTURE.read_text())


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   history=[{"turn": turn, "public": f"history-{turn}"} for turn in range(30)],
                   metadata={"model_execution_policy": model_execution_policy(None)})


def agent(runtime=None, model=MODEL):
    return ModelProviderAgent("krutrim", model, API_KEY_ENV, runtime_config=runtime)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)


def install(monkeypatch, payload=None, status=200, headers=None, content=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", url),
                              **({"content": content} if content is not None
                                 else {"json": wire() if payload is None else payload}))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def assert_private(value):
    text = json.dumps(value, default=str)
    assert SECRET not in text
    assert "private-provider-prose" not in text


def test_direct_dispatch_exact_model_full_history_and_no_implicit_caps(monkeypatch):
    calls = install(monkeypatch)
    native = agent(model="Explicit-Case-Sensitive-ID")
    result = native.act(request())
    url, kwargs = calls[0]
    assert len(calls) == 1 and url == CHAT_COMPLETIONS_ENDPOINT
    assert kwargs["headers"] == {"Authorization": f"Bearer {SECRET}",
                                 "Content-Type": "application/json"}
    payload = kwargs["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == "Explicit-Case-Sensitive-ID" and payload["stream"] is False
    assert len(payload["messages"]) == 2
    for turn in range(30):
        assert f'"public": "history-{turn}"' in payload["messages"][1]["content"]
    assert kwargs["timeout"].read is None
    receipt = result.metadata["provider_receipt"]
    assert result.action == 1
    assert receipt["provider"] == "krutrim"
    assert receipt["model"] == "Explicit-Case-Sensitive-ID"
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "krutrim_chat_completions"
    assert receipt["parser_version"] == "krutrim-chat-completions-raw-v1"
    assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert_private(result.to_dict())


def test_explicit_output_temperature_and_timeout_are_forwarded(monkeypatch):
    calls = install(monkeypatch)
    native = agent(ProviderRuntimeConfig(timeout_ms=4500))
    native.temperature = 0.25
    native.max_output_tokens = 345
    native.act(request())
    assert calls[0][1]["json"]["max_tokens"] == 345
    assert calls[0][1]["json"]["temperature"] == 0.25
    assert calls[0][1]["timeout"].read <= 4.5


@pytest.mark.parametrize("model", [None, "", " ", "\n\t"])
def test_missing_or_blank_model_rejected_every_entrypoint(model):
    with pytest.raises(ValueError, match="nonblank model"):
        agent(model=model)
    with pytest.raises(ValueError, match="nonblank model"):
        provider_preflight("krutrim", model, "tic-tac-toe")
    if isinstance(model, str):
        with pytest.raises(ValueError, match="nonblank model"):
            _provider_agent("krutrim:" + model)


@pytest.mark.parametrize("config", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 1024}, {"gemini_thinking_budget": 0},
    {"gateway_base_url": "https://example.invalid"}, {"gateway_mode": "disabled"},
    {"openrouter_provider_order": ("some-route",)},
])
def test_unsupported_controls_rejected_by_adapter_and_offline_preflight(config):
    runtime = ProviderRuntimeConfig(**config)
    with pytest.raises(ValueError, match="Krutrim"):
        agent(runtime)
    with pytest.raises(ValueError, match="Krutrim"):
        provider_preflight("krutrim", MODEL, "tic-tac-toe", runtime_config=runtime)


def test_cli_dispatch_and_configuration_preflight_are_keyless(monkeypatch, capsys):
    monkeypatch.delenv(API_KEY_ENV)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    native = _provider_agent(f"krutrim:{MODEL}")
    assert native.provider == "krutrim" and native.api_key_env == API_KEY_ENV
    with pytest.raises(ValueError, match="nonblank model"):
        _provider_agent("krutrim")
    assert main(["providers", "preflight", "--provider", "krutrim", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["checks"]["adapter_available"] is True
    assert output["checks"]["api_key_configured"] is False
    assert output["checks"]["account_model_visible"] is None
    assert output["checks"]["minimal_inference"] is False


def test_live_preflight_fixture_does_not_invent_models_discovery(monkeypatch):
    calls = install(monkeypatch)
    result = provider_preflight("krutrim", MODEL, "tic-tac-toe", live=True)
    assert len(calls) == 1
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["minimal_inference"] is True
    assert result["checks"]["usage_extraction"] is False
    assert_private(result)


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable")])
def test_http_errors_no_automatic_retry_or_credential_echo(monkeypatch, status, kind):
    calls = install(monkeypatch, status=status, headers={"x-request-id": SECRET,
        "x-gateway-request-id": "prefix-" + SECRET, "retry-after": "1"},
        payload={"error": {"message": SECRET + "private-provider-prose", "id": SECRET,
                            "code": "rate_limit_exceeded", "model": SECRET}})
    native = agent(ProviderRuntimeConfig(max_retries=3, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert len(calls) == 1 and caught.value.error_kind == kind
    assert native.last_receipt["status_code"] == status
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["gateway_request_id"] is None
    assert native.last_receipt["locked_model_id"] is None
    assert_private([str(caught.value), caught.value.receipt, native.attempt_receipts])


@pytest.mark.parametrize("content", [b'not json', b'[]', b'{"id":"a","id":"b"}',
                                    b'{"choices":NaN}', b'{"choices":'])
def test_malformed_bodies_keep_sanitized_headers_and_unknown_accounting(monkeypatch, content):
    install(monkeypatch, content=content, headers={"x-request-id": SECRET})
    native = agent()
    with pytest.raises(ProviderCallError, match="provider response body") as caught:
        native.act(request())
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["usage"] == {}
    assert_private([native.attempt_receipts, caught.value.receipt])


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("kind", ["timeout", "transport", "oversized"])
def test_transport_failures_preserve_partial_status_without_replay(monkeypatch, partial, kind):
    from eslams.protocol import ProtocolError

    calls = []

    def post(url, **kwargs):
        calls.append(url)
        failure = {"timeout": httpx.ReadTimeout("private-provider-prose"),
                   "transport": httpx.ReadError("private-provider-prose"),
                   "oversized": ProtocolError("agent/provider response exceeds 1 MiB limit")}[kind]
        if partial:
            failure._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", SECRET), ("x-gateway-request-id", SECRET)))
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        native.act(request())
    assert len(calls) == 1
    assert native.last_receipt["status_code"] == (200 if partial else None)
    assert native.last_receipt["usage"] == {} and native.last_receipt["locked_model_id"] is None
    assert_private([native.attempt_receipts, str(caught.value)])


@pytest.mark.parametrize("mutation,kind", [
    ({"index": False}, "provider_response_schema_mismatch"),
    ({"finish_reason": "length"}, "provider_output_truncated"),
    ({"finish_reason": "content_filter"}, "provider_refused"),
    ({"finish_reason": None}, "provider_response_schema_mismatch"),
    ({"finish_reason": SECRET}, "provider_response_schema_mismatch"),
    ({"finish_reason": {"secret": SECRET}}, "provider_response_schema_mismatch"),
    ({"finish_reason": "tool_calls"}, "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "content": "{\"action\":1}", "tool_calls": [{}]}},
     "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "content": None}}, "provider_response_schema_mismatch"),
    ({"message": {"role": "assistant", "content": [{"text": "{\"action\":1}"}]}},
     "provider_response_schema_mismatch"),
    ({"message": {"role": "tool", "content": "{\"action\":1}"}},
     "provider_response_schema_mismatch"),
])
def test_partial_semantic_or_wrong_envelopes_never_accept_legal_looking_text(
    monkeypatch, mutation, kind,
):
    payload = wire()
    payload["choices"][0].update(mutation)
    install(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert caught.value.error_kind == kind
    assert_private([native.attempt_receipts, caught.value.receipt])


@pytest.mark.parametrize("shape", ["empty", "multiple", "body-error", "choice-error",
                                   "invalid-action", "malformed-secret"])
def test_invalid_envelopes_and_actions_keep_receipts_and_never_fallback(monkeypatch, shape):
    payload = wire()
    if shape == "empty":
        payload["choices"] = []
    elif shape == "multiple":
        payload["choices"] *= 2
    elif shape == "body-error":
        payload["error"] = {"message": SECRET, "code": 429}
    elif shape == "choice-error":
        payload["choices"][0]["error"] = {"message": SECRET}
    elif shape == "invalid-action":
        payload["choices"][0]["message"]["content"] = '{"action":999}'
    calls = install(monkeypatch, payload, content=(
        ('{"private-provider-prose":"' + SECRET).encode() if shape == "malformed-secret"
        else None))
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["outcome"] != "ok"
    assert_private([str(caught.value), caught.value.receipt, native.attempt_receipts])


@pytest.mark.parametrize("model", [None, "", SECRET, "prefix-" + SECRET])
def test_response_identity_is_never_invented_and_ids_cannot_echo_credentials(monkeypatch, model):
    payload = wire()
    payload.update(model=model, id=SECRET)
    install(monkeypatch, payload, headers={"x-request-id": SECRET})
    native = agent()
    result = native.act(request())
    receipt = result.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["request_id"] is None and receipt["provider_response_id"] is None
    assert_private(result.to_dict())


@pytest.mark.parametrize("encoded", [False, True])
def test_generated_explanation_cannot_echo_credentials_even_json_escaped(monkeypatch, encoded):
    payload = wire()
    text = json.dumps({"action": 1, "public_explanation": SECRET})
    if encoded:
        text = text.replace(SECRET, "".join(f"\\u{ord(c):04x}" for c in SECRET))
    payload["choices"][0]["message"]["content"] = text
    install(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_private([native.attempt_receipts, str(caught.value)])


def test_json_escaped_credential_action_is_rejected_even_if_legal(monkeypatch):
    payload = wire()
    text = json.dumps({"action": SECRET})
    payload["choices"][0]["message"]["content"] = text.replace(
        SECRET, "".join(f"\\u{ord(c):04x}" for c in SECRET))
    install(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(replace(request(), legal_actions=[SECRET], action_schema={"type": "string"}))
    assert_private(native.attempt_receipts)


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}, (12, 4, 16)),
    ({"prompt_tokens": 12, "completion_tokens": 4}, (12, 4, None)),
    ({"prompt_tokens": True, "completion_tokens": SECRET}, (None, None, None)),
    ({"total_tokens": 16, "completion_tokens_details": {"reasoning_tokens": 4}},
     (None, None, 16)),
])
def test_usage_is_observed_without_inventing_missing_totals_or_reasoning(
    monkeypatch, usage, expected,
):
    payload = wire()
    payload["usage"] = usage
    install(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    normalized = receipt["usage"]
    if normalized:
        keys = ("input_tokens", "output_tokens", "total_tokens")
        assert tuple(normalized[k] for k in keys) == expected
        assert normalized["reasoning_included_in_output"] is None
        assert normalized["reasoning_tokens"] is None and normalized["cached_input_tokens"] is None
    else:
        assert expected == (None, None, None)
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert_private(receipt)


@pytest.mark.parametrize("usage", [None,
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}])
def test_runner_artifact_dispatch_and_receipts_validate_without_live_inference(
    monkeypatch, tmp_path, usage,
):
    payload = wire()
    if usage is not None:
        payload["usage"] = usage
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        prompt = kwargs["json"]["messages"][1]["content"]
        # Select only from the actual complete request, without game logic.
        body = json.loads(prompt.split("\n")[-1])
        current = copy.deepcopy(payload)
        current["choices"][0]["message"]["content"] = json.dumps(
            {"action": body["legal_actions"][0]})
        return httpx.Response(200, json=current, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig(
        "tic-tac-toe", agent_1=agent(), agent_2=agent(), output_dir=tmp_path))
    assert calls and all(url == CHAT_COMPLETIONS_ENDPOINT for url in calls)
    assert ArtifactValidator().validate(result.expanded_path) == []
    receipts = [json.loads(line) for line in (result.expanded_path /
        "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(receipts) == len(calls)
    assert all(row["provider"] == "krutrim" and row["locked_model_id"] == MODEL for row in receipts)
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert result.score.aggregate_usage["totalTokens"] is None
    if usage is not None:
        assert all(row["usage"]["total_tokens"] == 16 for row in receipts)
    assert_private(receipts)
