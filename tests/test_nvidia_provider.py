"""Offline NVIDIA hosted contract tests; no account or paid API is contacted."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.nvidia import CHAT_COMPLETIONS_ENDPOINT, REFERENCE_MODEL
from eslams.runner import RunConfig, Runner

ALIASES = ("nvidia", "nvidia-nim", "nvidia-hosted")
FIXTURE = Path(__file__).parent / "fixtures/provider/nvidia/chat_success.json"


def wire():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def transport(monkeypatch):
    """Exercise the actual bounded reader with a deterministic raw HTTP transport."""
    calls = []
    responses = []
    original = httpx.AsyncClient

    def respond(request):
        calls.append(request)
        assert str(request.url) == CHAT_COMPLETIONS_ENDPOINT
        assert request.headers["Authorization"] == "Bearer synthetic-nvidia-primary"
        response = responses.pop(0) if responses else httpx.Response(200, json=wire())
        if response.is_stream_consumed:
            content = response.content

            class Bytes(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield content

            return httpx.Response(response.status_code, headers=response.headers, stream=Bytes())
        return response

    monkeypatch.setenv("NVIDIA_API_KEY", "synthetic-nvidia-primary")
    monkeypatch.setenv("SECONDARY_API_KEY", "synthetic-nvidia-secondary")
    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kw: original(
        transport=httpx.MockTransport(respond), **kw,
    ))
    return calls, responses


def agent(provider="nvidia", model=REFERENCE_MODEL, **kwargs):
    return ModelProviderAgent(provider, model, "NVIDIA_API_KEY", **kwargs)


@pytest.mark.parametrize("provider", ALIASES)
def test_aliases_cli_preflight_and_dispatch_keep_exact_model_and_full_history(
    provider, transport, capsys,
):
    calls, _ = transport
    configured = _provider_agent(f"{provider}:{REFERENCE_MODEL}")
    assert configured.provider == "nvidia" and configured.model == REFERENCE_MODEL
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None)},
        history=[{"turn": turn, "action": turn % 3} for turn in range(200)])
    result = configured.act(request)
    assert result.action == 0
    payload = json.loads(calls[0].content)
    assert payload["model"] == REFERENCE_MODEL and payload["stream"] is False
    assert [item["role"] for item in payload["messages"]] == ["system", "user"]
    assert all(json.dumps(row, sort_keys=True) in payload["messages"][1]["content"]
               for row in request.history)
    assert set(payload) == {"model", "messages", "stream"}
    assert calls[0].extensions["timeout"]["read"] is None
    receipt = configured.last_receipt
    assert receipt["provider"] == "nvidia" and receipt["locked_model_id"] == REFERENCE_MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "nvidia_chat_completions"
    assert receipt["parser_version"] == "nvidia-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 140
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "synthetic-private-reasoning" not in json.dumps(result.to_dict())
    assert provider_models_live(provider) is None
    assert main(["providers", "preflight", "--provider", provider, "--model", REFERENCE_MODEL,
                 "--arena", "tic-tac-toe", "--live"]) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["checks"]["account_model_visible"] is None
    assert preflight["checks"]["response_parsing"]
    assert preflight["checks"]["usage_extraction"]


@pytest.mark.parametrize("provider", ALIASES)
@pytest.mark.parametrize("model", ["", " ", "\t"])
def test_blank_model_rejected_by_cli_constructor_and_preflight(provider, model, transport):
    calls, _ = transport
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(f"{provider}:{model}")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        agent(provider, model)
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(provider)
    result = provider_preflight(provider, model, "tic-tac-toe", live=True)
    assert not result["ok"] and result["error"]["error_class"] == "provider_request_rejected"
    assert not calls


@pytest.mark.parametrize("model,options", [
    (REFERENCE_MODEL, {"reasoning_effort": "high"}),
    (REFERENCE_MODEL, {"gemini_thinking_budget": 100}),
    (REFERENCE_MODEL, {"reasoning_budget_tokens": 32769}),
    ("nvidia/nemotron-3.5-bolt-e4b", {"reasoning_budget_tokens": 100}),
    ("nvidia/unknown-exact-id", {"reasoning_budget_tokens": 100}),
    ("nvidia/unknown-exact-id", {"reasoning": "enabled"}),
    ("nvidia/unknown-exact-id", {"reasoning": "disabled"}),
])
@pytest.mark.parametrize("provider", ALIASES)
def test_unsupported_reasoning_rejected_in_preflight_and_transport(
    model, options, provider, transport,
):
    calls, _ = transport
    runtime = ProviderRuntimeConfig(**options)
    result = provider_preflight(provider, model, "tic-tac-toe", live=True, runtime_config=runtime)
    assert not result["ok"] and result["error"]["error_class"] == "provider_request_rejected"
    assert not result["readiness"]["configuration_ready"]
    configured = agent(provider, model, runtime_config=runtime)
    with pytest.raises(ProviderCallError) as caught:
        configured.act(_request())
    assert caught.value.error_kind == "provider_request_rejected" and not calls


@pytest.mark.parametrize("mode", ["enabled", "disabled"])
def test_explicit_controls_and_unknown_exact_id_are_never_rewritten(mode, transport):
    calls, _ = transport
    runtime = ProviderRuntimeConfig(reasoning=mode,
        reasoning_budget_tokens=800 if mode == "enabled" else None)
    agent(runtime_config=runtime, max_output_tokens=40000, temperature=0.3).act(_request())
    payload = json.loads(calls[0].content)
    assert payload["chat_template_kwargs"] == {"enable_thinking": mode == "enabled"}
    assert payload["max_tokens"] == 40000 and payload["temperature"] == 0.3
    assert payload.get("reasoning_budget") == (800 if mode == "enabled" else None)
    exact = "other-author/Future-Model:revision"
    agent(model=exact).act(_request())
    assert json.loads(calls[1].content)["model"] == exact
    assert "provider" not in payload


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (403, "provider_permission_failed"),
    (402, "provider_request_rejected"), (404, "provider_unavailable"),
    (422, "provider_request_rejected"), (429, "provider_rate_limited"),
    (500, "provider_unavailable"), (503, "provider_unavailable"),
])
def test_http_errors_keep_receipts_without_retries_or_body_prose(status, kind, transport):
    calls, responses = transport
    responses.append(httpx.Response(status, json={"error": {"code": status,
        "message": "private-error-text"}}, headers={"Retry-After": "4"}))
    configured = agent()
    with pytest.raises(ProviderCallError) as caught:
        configured.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert configured.last_receipt["outcome"] == kind
    assert configured.last_receipt["status_code"] == status
    assert configured.last_receipt["usage"] == {}
    assert "private-error-text" not in json.dumps(configured.last_receipt)
    if status == 429:
        assert caught.value.retry_after_seconds == 4


@pytest.mark.parametrize("finish,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("unrecognized", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"),
])
def test_noncomplete_parseable_action_never_accepted_or_repaired(finish, kind, transport):
    calls, responses = transport
    body = wire()
    body["choices"][0]["finish_reason"] = finish
    responses.append(httpx.Response(200, json=body))
    configured = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        configured.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert configured.last_receipt["usage"]["total_tokens"] == 140


@pytest.mark.parametrize("case", [
    "refusal", "reasoning_only", "body_error", "pending", "empty_pending",
    "malformed_json", "duplicate_json", "two_choices",
])
def test_refusal_pending_malformed_and_embedded_error_receipts(case, transport):
    calls, responses = transport
    body = wire()
    status = 200
    kind = "provider_response_schema_mismatch"
    if case == "refusal":
        body["choices"][0]["message"]["refusal"] = "private-refusal"
        kind = "provider_refused"
    elif case == "reasoning_only":
        body["choices"][0]["message"]["content"] = None
    elif case == "body_error":
        body["error"] = {"code": 429, "message": "private-error"}
        kind = "provider_rate_limited"
    elif case in {"pending", "empty_pending"}:
        status, kind = 202, "provider_pending"
    elif case == "two_choices":
        body["choices"].append(copy.deepcopy(body["choices"][0]))
    if case == "empty_pending":
        responses.append(httpx.Response(status, content=b""))
    elif case in {"malformed_json", "duplicate_json"}:
        responses.append(httpx.Response(200, content=(b'not-json' if case == "malformed_json"
                                                    else b'{"id":1,"id":2}')))
    else:
        responses.append(httpx.Response(status, json=body))
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        configured.act(_request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert "private-refusal" not in json.dumps(configured.last_receipt)


@pytest.mark.parametrize("missing", ["model", "usage", "total", "invalid_total", "reasoning"])
def test_missing_identity_and_accounting_stay_unknown(missing, transport):
    _, responses = transport
    body = wire()
    if missing in {"model", "usage"}:
        del body[missing]
    elif missing == "total":
        del body["usage"]["total_tokens"]
    elif missing == "invalid_total":
        body["usage"]["total_tokens"] = "not-a-measurement"
    else:
        body["usage"]["completion_tokens_details"] = {"reasoning_tokens": 12}
    responses.append(httpx.Response(200, json=body))
    configured = agent()
    configured.act(_request())
    receipt = configured.last_receipt
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if missing == "model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    if missing == "usage":
        assert receipt["usage"] == {}
    if missing in {"total", "invalid_total"}:
        assert receipt["usage"]["total_tokens"] is None
    if missing == "reasoning":
        assert receipt["usage"]["reasoning_tokens"] == 12
        assert receipt["usage"]["reasoning_included_in_output"] is None


@pytest.mark.parametrize("case", ["success", "http_error", "malformed", "partial", "refusal"])
@pytest.mark.parametrize("secret", ["synthetic-nvidia-primary", "synthetic-nvidia-secondary"])
def test_echoed_credentials_never_enter_receipts_artifacts_or_identifiers(
    case, secret, transport, tmp_path,
):
    calls, responses = transport
    body = wire()
    body.update(id=f"id-{secret}", model=secret)
    headers = {"x-request-id": f"request-{secret}", "cf-aig-request-id": secret}
    status = 200
    if case == "http_error":
        status = 429
        body["error"] = {"code": 429, "message": secret}
    if case == "refusal":
        body["choices"][0]["message"]["refusal"] = secret
    if case == "malformed":
        responses.append(httpx.Response(status, content=b'{', headers=headers))
    elif case == "partial":
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield json.dumps(body).encode()[:40]
                raise httpx.ReadError(secret)
        responses.append(httpx.Response(status, stream=Stream(), headers=headers))
    else:
        responses.append(httpx.Response(status, json=body, headers=headers))
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=configured,
        on_agent_error="forfeit", max_turns=1, output_dir=tmp_path))
    assert len(calls) == 1
    receipt = configured.last_receipt
    assert receipt["request_id"] is None and receipt["gateway_request_id"] is None
    assert receipt.get("locked_model_id") is None
    assert receipt.get("model_identity_source") is None
    assert secret not in json.dumps(receipt)
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes()


def test_optional_safe_retry_requires_definitive_rejection_without_work(transport):
    calls, responses = transport
    responses.append(httpx.Response(429, json={"error": {"code": 429}},
                                    headers={"Retry-After": "0"}))
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    assert configured.act(_request()).action == 0
    assert len(calls) == len(configured.attempt_receipts) == 2
    assert configured.attempt_receipts[0]["outcome"] == "provider_rate_limited"


@pytest.mark.parametrize("key", ["", " ", "synthetic bad key", "synthetic-🔑"])
def test_missing_or_invalid_key_fails_without_network_or_echo(key, transport, monkeypatch):
    calls, _ = transport
    monkeypatch.setenv("NVIDIA_API_KEY", key)
    configured = agent()
    with pytest.raises(ProviderCallError) as caught:
        configured.act(_request())
    assert caught.value.error_kind == "provider_auth_failed" and not calls
    assert configured.last_receipt["outcome"] == "provider_auth_failed"
    if key.strip():
        assert key not in str(caught.value) + json.dumps(configured.last_receipt)


def test_ambiguous_timeout_never_retries_even_if_enabled(transport, monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("synthetic-nvidia-primary")

    monkeypatch.setattr("eslams.agents.bounded_post", timeout)
    configured = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(TimeoutError):
        configured.act(_request())
    assert calls == [1] and len(configured.attempt_receipts) == 1
    assert configured.last_receipt["outcome"] == "provider_timeout"
    assert "synthetic-nvidia-primary" not in json.dumps(configured.last_receipt)


def test_catalogue_prices_cannot_manufacture_hosted_billing(transport):
    configured = agent()
    configured.capabilities = replace(configured.capabilities, pricing={
        "input_cost_per_token": 0.0, "output_cost_per_token": 0.0,
        "source": "synthetic-external-catalogue",
    })
    configured.act(_request())
    assert configured.last_receipt["usage"]["total_tokens"] == 140
    assert configured.last_receipt["pricing"]["status"] == "cost_unavailable"
    assert configured.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert configured.last_receipt["rate_card_reference"] is None
