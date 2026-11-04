"""Offline native REST fixtures; never call a paid Tencent endpoint."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.planning import _provider_env_names
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.tencent_hunyuan import ENDPOINT, HOST, signed_headers


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/provider" /
                       "tencent_hunyuan_chat_completions_success.json").read_text())


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "fixture-secret-id")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "fixture-secret-key")
    monkeypatch.delenv("TENCENTCLOUD_TOKEN", raising=False)
    monkeypatch.delenv("TENCENTCLOUD_REGION", raising=False)


def agent(provider="tencent-hunyuan", model="hunyuan-a13b", **kwargs):
    return ModelProviderAgent(provider, model, "TENCENTCLOUD_SECRET_ID", **kwargs)


def wire(monkeypatch, data=None, status=200, *, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=fixture() if data is None else data, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ["hunyuan", "tencent-hunyuan", "TENCENT_HUNYUAN"])
def test_aliases_cli_preflight_and_dispatch(monkeypatch, alias, capsys):
    calls = wire(monkeypatch)
    cli_agent = _provider_agent(f"{alias}:exact-unlisted-model")
    assert cli_agent.provider == "tencent-hunyuan"
    assert cli_agent.model == "exact-unlisted-model"
    result = provider_preflight(alias, cli_agent.model, "tic-tac-toe")
    assert result["checks"]["adapter_available"]
    assert result["checks"]["api_key_configured"]
    assert result["provider"] == "tencent-hunyuan"
    assert any("2026-12-21" in value for value in result["warnings"])
    assert not calls
    assert main(["providers", "preflight", "--provider", alias, "--model", cli_agent.model,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert cli_agent.act(_request()).action == 1
    assert calls[0][1]["json"]["Model"] == "exact-unlisted-model"
    assert load_provider_registry().resolve(alias, cli_agent.model).provider == "tencent-hunyuan"


@pytest.mark.parametrize("provider", ["tencent", "tencent-tokenhub", "tencent-coding-plan"])
def test_distinct_products_never_route_to_native(monkeypatch, provider):
    calls = wire(monkeypatch)
    assert _provider_agent(f"{provider}:hunyuan-a13b") is None
    result = provider_preflight(provider, "hunyuan-a13b", "tic-tac-toe", live=True)
    assert not result["checks"]["adapter_available"]
    with pytest.raises(ProviderCallError):
        agent(provider).act(_request())
    assert calls == []


def test_payload_history_native_defaults_and_unknown_identity_accounting(monkeypatch):
    calls = wire(monkeypatch)
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None, history=[
        {"turn": number, "public": "history-sentinel"} for number in range(100)
    ], metadata={"model_execution_policy": model_execution_policy(None)})
    current = agent(model="literal/case:Version")
    response = current.act(request)
    url, sent = calls[0]
    assert url == ENDPOINT
    assert sent["json"]["Model"] == "literal/case:Version"
    assert sent["json"]["Stream"] is False
    assert sent["json"]["EnableEnhancement"] is False
    assert len(sent["json"]["Messages"]) == 2
    assert '"turn": 0' in sent["json"]["Messages"][1]["Content"]
    assert '"turn": 99' in sent["json"]["Messages"][1]["Content"]
    assert set(sent["json"]) == {"Model", "Messages", "Stream", "EnableEnhancement"}
    assert sent["timeout"].read is None
    assert sent["headers"]["Host"] == HOST
    assert "X-TC-Region" not in sent["headers"]
    assert sent["headers"]["X-TC-Version"] == "2023-09-01"
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["endpoint_kind"] == "tencent_hunyuan_chat_completions"
    assert receipt["usage"]["input_tokens"] == 71
    assert receipt["usage"]["output_tokens"] == 42
    assert receipt["usage"]["total_tokens"] == 113
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["request_id"] == fixture()["Response"]["RequestId"]
    assert receipt["attempt_index"] == 1
    assert len(current.attempt_receipts) == 1
    assert "history-sentinel" not in json.dumps(receipt)


def test_tc3_signature_verifies_actual_httpx_body_through_safe_transport(monkeypatch):
    # Independent verification uses bytes observed by HTTPX MockTransport,
    # including non-ASCII prompt text, rather than reserializing the test payload.
    observed = []
    real_client = httpx.AsyncClient

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(fixture()).encode()

    def receive(request):
        observed.append(request)
        headers = request.headers
        date = headers["X-TC-Timestamp"]
        assert date == "1551113065"
        canonical = (
            "POST\n/\n\ncontent-type:application/json\n"
            f"host:{request.url.host}\nx-tc-action:chatcompletions\n\n"
            "content-type;host;x-tc-action\n" + hashlib.sha256(request.content).hexdigest()
        )
        scope = "2019-02-25/hunyuan/tc3_request"
        signing = ("TC3-HMAC-SHA256\n" + date + "\n" + scope + "\n" +
                   hashlib.sha256(canonical.encode()).hexdigest())
        key = b"TC3fixture-secret-key"
        for value in (b"2019-02-25", b"hunyuan", b"tc3_request"):
            key = hmac.digest(key, value, "sha256")
        signature = hmac.new(key, signing.encode(), hashlib.sha256).hexdigest()
        assert headers["Authorization"] == (
            f"TC3-HMAC-SHA256 Credential=fixture-secret-id/{scope}, "
            f"SignedHeaders=content-type;host;x-tc-action, Signature={signature}"
        )
        assert headers["X-TC-Token"] == "fixture-session-token"
        assert headers["X-TC-Region"] == "ap-guangzhou"
        assert "你好".encode() in request.content
        return httpx.Response(200, stream=Body(), headers={"X-TC-RequestId": "wire-request"})

    monkeypatch.setattr("eslams.providers.tencent_hunyuan.time.time", lambda: 1551113065)
    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(receive), **kwargs,
    ))
    monkeypatch.setenv("TENCENTCLOUD_TOKEN", "fixture-session-token")
    monkeypatch.setenv("TENCENTCLOUD_REGION", "ap-guangzhou")
    request = _request()
    request.observation["text"] = "你好"
    response = agent().act(request)
    assert response.action == 1
    assert response.metadata["provider_receipt"]["request_id"] == "wire-request"
    assert len(observed) == 1


def test_signature_changes_with_payload_and_utc_date():
    first = signed_headers({"text": "a"}, "id", "key", timestamp=1551113065)
    changed = signed_headers({"text": "b"}, "id", "key", timestamp=1551113065)
    later = signed_headers({"text": "a"}, "id", "key", timestamp=1551139200)
    assert first["Authorization"] != changed["Authorization"]
    assert "/2019-02-26/" in later["Authorization"]


@pytest.mark.parametrize("mode,expected", [("auto", None), ("enabled", True), ("disabled", False)])
def test_reasoning_is_explicit_and_answer_uses_content(monkeypatch, mode, expected):
    payload = fixture()
    payload["Response"]["Choices"][0]["Message"]["ReasoningContent"] = "private-thinking-sentinel"
    calls = wire(monkeypatch, payload)
    response = agent(runtime_config=ProviderRuntimeConfig(reasoning=mode)).act(_request())
    sent = calls[0][1]["json"]
    assert sent.get("EnableThinking") is expected
    assert ("EnableThinking" in sent) is (expected is not None)
    assert "private-thinking-sentinel" not in json.dumps(response.to_dict())
    assert response.action == 1


@pytest.mark.parametrize("config,max_tokens", [
    (ProviderRuntimeConfig(reasoning_effort="high"), None),
    (ProviderRuntimeConfig(reasoning_budget_tokens=2048), None),
    (ProviderRuntimeConfig(gemini_thinking_budget=0), None),
    (ProviderRuntimeConfig(gateway_base_url="https://example.invalid"), None),
    (ProviderRuntimeConfig(), 10),
])
def test_unsupported_controls_reject_before_network(monkeypatch, config, max_tokens):
    calls = wire(monkeypatch)
    current = agent(runtime_config=config, max_output_tokens=max_tokens)
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == "provider_request_rejected"
    assert current.last_receipt["usage"] == {}
    assert not calls
    result = provider_preflight("hunyuan", current.model, "tic-tac-toe",
                                runtime_config=config, max_output_tokens=max_tokens)
    assert result["error"]["error_class"] == "provider_request_rejected"


def test_unsupported_model_thinking_switch_rejects(monkeypatch):
    calls = wire(monkeypatch)
    with pytest.raises(ProviderCallError, match="only for exact model"):
        agent(model="hunyuan-a13b-other", runtime_config=ProviderRuntimeConfig(
            reasoning="disabled")).act(_request())
    assert not calls


@pytest.mark.parametrize("name,value", [
    ("TENCENTCLOUD_SECRET_ID", ""), ("TENCENTCLOUD_SECRET_KEY", ""),
    ("TENCENTCLOUD_SECRET_ID", "bad secret"), ("TENCENTCLOUD_SECRET_KEY", "bad\nsecret"),
    ("TENCENTCLOUD_TOKEN", "non-ascii-你好"), ("TENCENTCLOUD_REGION", "bad/region"),
])
def test_all_credentials_validated_without_network_or_secret_echo(monkeypatch, name, value):
    calls = wire(monkeypatch)
    monkeypatch.setenv(name, value)
    current = agent()
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == "provider_auth_failed"
    result = provider_preflight("hunyuan", current.model, "tic-tac-toe", live=True)
    assert result["error"]["error_class"] == "provider_auth_failed"
    if value:
        assert value not in str(error.value) + json.dumps(current.last_receipt) + json.dumps(result)
    assert not calls


@pytest.mark.parametrize("status,code,kind", [
    (400, "InvalidParameterValue", "provider_request_rejected"),
    (401, "AuthFailure.SignatureFailure", "provider_auth_failed"),
    (403, "UnauthorizedOperation", "provider_permission_failed"),
    (404, "ResourceNotFound", "provider_unavailable"),
    (429, "RequestLimitExceeded", "provider_rate_limited"),
    (503, "InternalError", "provider_unavailable"),
    (200, "AuthFailure.SecretIdNotFound", "provider_auth_failed"),
    (200, "FailedOperation.EngineRequestTimeout", "provider_timeout"),
    (200, "FailedOperation.EngineServerLimitExceeded", "provider_rate_limited"),
    (200, "ActionOffline", "provider_unavailable"),
    (200, "OperationDenied.TextIllegalDetected", "provider_refused"),
])
def test_native_error_envelopes_preserve_request_id_without_private_message(
    monkeypatch, status, code, kind,
):
    calls = wire(monkeypatch, {"Response": {
        "Error": {"Code": code, "Message": "private-error-sentinel fixture-secret-key"},
        "RequestId": "native-error-request",
    }}, status, headers={"Retry-After": "0"})
    current = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == kind
    assert current.last_receipt["request_id"] == "native-error-request"
    assert current.last_receipt["usage"] == {}
    assert current.last_receipt["locked_model_id"] is None
    assert "private-error-sentinel" not in str(error.value) + json.dumps(current.last_receipt)
    assert len(calls) == 1


@pytest.mark.parametrize("reason,kind", [
    ("sensitive", "provider_refused"), ("length", "provider_output_truncated"),
    ("max_tokens", "provider_output_truncated"),
    ("tool_calls", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"), ({}, "provider_response_schema_mismatch"),
    ("private-finish-sentinel", "provider_response_schema_mismatch"),
])
def test_refusal_truncation_unknown_finish_never_accepts_legal_partial_text(
    monkeypatch, reason, kind,
):
    payload = fixture()
    payload["Response"]["Choices"][0]["FinishReason"] = reason
    calls = wire(monkeypatch, payload)
    current = agent()
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == kind
    assert current.last_receipt["usage"]["total_tokens"] == 113
    assert "private-finish-sentinel" not in json.dumps(current.last_receipt)
    assert len(calls) == 1


@pytest.mark.parametrize("shape", ["unwrapped", "wrapped", "null-error"])
def test_documented_nonstream_envelopes(monkeypatch, shape):
    payload = fixture()
    if shape == "unwrapped":
        payload = payload["Response"]
    elif shape == "null-error":
        payload["Response"]["ErrorMsg"] = None
    wire(monkeypatch, payload)
    assert agent().act(_request()).action == 1


@pytest.mark.parametrize("data", [[], {"Response": []}, {"Choices": []},
                                   {"output_text": '{"action": 1}'}, {"Response": {}}])
def test_wrong_wire_shapes_fail_closed(monkeypatch, data):
    calls = wire(monkeypatch, data)
    current = agent()
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1


@pytest.mark.parametrize("content", [b"not JSON", b'{"Response":{},"Response":{}}', b'{"x":NaN}'])
def test_malformed_duplicate_and_nonfinite_json(monkeypatch, content):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, content=content,
    ))
    current = agent()
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("usage", [None, {}, {"PromptTokens": 71},
                                   {"PromptTokens": True, "CompletionTokens": -1},
                                   {"PromptTokens": 71, "CompletionTokens": 42}])
def test_missing_accounting_is_never_filled_in(monkeypatch, usage):
    payload = fixture()
    payload["Response"]["Usage"] = usage
    wire(monkeypatch, payload)
    current = agent()
    assert current.act(_request()).action == 1
    receipt = current.last_receipt
    assert receipt["usage"].get("total_tokens") is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["usage"].get("reasoning_tokens") is None


@pytest.mark.parametrize("failure,expected", [
    (httpx.ReadTimeout("private-timeout"), TimeoutError),
    (httpx.ConnectError("private-transport"), ProviderCallError),
])
def test_transport_errors_are_never_replayed(monkeypatch, failure, expected):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    current = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(expected):
        current.act(_request())
    assert calls == [1]
    assert current.last_receipt["usage"] == {}


def test_live_preflight_uses_one_native_call_and_no_discovery_guess(monkeypatch):
    calls = wire(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("no documented Models API"))
    result = provider_preflight("hunyuan", "hunyuan-a13b", "tic-tac-toe", live=True)
    assert result["ok"]
    assert result["checks"]["account_model_visible"] is None
    assert result["checks"]["usage_extraction"]
    assert provider_models_live("HUNYUAN") is None
    assert len(calls) == 1
    assert _provider_env_names(["hunyuan"]) == ["TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY"]


def test_reasoning_only_and_moderation_never_become_actions(monkeypatch):
    for moderation in (False, True):
        payload = copy.deepcopy(fixture())
        if moderation:
            payload["Response"]["ModerationLevel"] = "1"
        else:
            payload["Response"]["Choices"][0]["Message"] = {
                "Role": "assistant", "ReasoningContent": '{"action": 1}',
            }
        wire(monkeypatch, payload)
        with pytest.raises(ProviderCallError):
            agent().act(_request())


def test_error_with_generation_observations_never_replays_or_accepts_action(monkeypatch):
    data = fixture()
    data["Response"]["Error"] = {"Code": "RequestLimitExceeded", "Message": "private-error"}
    calls = wire(monkeypatch, data, 429)
    current = agent(runtime_config=ProviderRuntimeConfig(max_retries=5, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == "provider_rate_limited"
    assert len(calls) == 1
    receipt = current.last_receipt
    assert receipt["provider_response_id"] == data["Response"]["Id"]
    assert receipt["usage"]["total_tokens"] == 113
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "private-error" not in json.dumps(receipt)


def test_cached_count_keeps_unknown_breakdown_and_ignores_unattested_reasoning(monkeypatch):
    data = fixture()
    data["Response"]["Usage"].update({
        "PromptTokensDetails": {"CachedTokens": "12"},
        "reasoning_tokens": 20, "reasoning_included_in_output": True,
    })
    data["Response"]["Model"] = "unattested-model-extension"
    wire(monkeypatch, data)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["cached_input_tokens"] == 12
    assert receipt["usage"]["cache_read_input_tokens"] is None
    assert receipt["usage"]["cached_input_is_subset"] is None
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["locked_model_id"] is None


@pytest.mark.parametrize("mode", ["partial-read", "oversize", "compressed"])
def test_safe_transport_failure_custody_with_native_header_and_no_retry(monkeypatch, mode):
    calls = []
    real_client = httpx.AsyncClient

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"Response":{"Error":'
            raise httpx.ReadError("private-wire-sentinel")

    def receive(request):
        calls.append(request)
        headers = {"X-TC-RequestId": "native-partial-request"}
        if mode == "oversize":
            headers["Content-Length"] = "1048577"
        elif mode == "compressed":
            headers["Content-Encoding"] = "gzip"
        return httpx.Response(429, headers=headers, stream=BrokenBody())

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(receive), **kwargs,
    ))
    current = agent(runtime_config=ProviderRuntimeConfig(max_retries=5, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert len(calls) == 1
    receipt = current.last_receipt
    assert receipt["status_code"] == 429
    assert receipt["request_id"] == "native-partial-request"
    assert receipt["usage"] == {}
    assert receipt["usage_unavailable_reason"] == "provider_response_schema_mismatch" or (
        receipt["usage_unavailable_reason"] == "provider_transport_error"
    )
    assert "private-wire-sentinel" not in str(error.value) + json.dumps(receipt)


def test_illegal_or_non_json_model_output_never_falls_back(monkeypatch):
    for text in ('{"action": 999}', "private-output-sentinel"):
        data = fixture()
        data["Response"]["Choices"][0]["Message"]["Content"] = text
        calls = wire(monkeypatch, data)
        current = agent()
        with pytest.raises(ProviderCallError) as error:
            current.act(_request())
        assert error.value.error_kind == "action_response_unparseable"
        assert len(calls) == 1
        assert current.last_receipt["usage"]["total_tokens"] == 113
        assert "private-output-sentinel" not in str(error.value) + json.dumps(current.last_receipt)


@pytest.mark.parametrize("code,kind", [(4000, "provider_unavailable"), (4001, "provider_timeout")])
def test_native_runtime_error_msg_preserves_usage(monkeypatch, code, kind):
    data = fixture()
    data["Response"]["ErrorMsg"] = {"Code": code, "Msg": "private-runtime-error"}
    calls = wire(monkeypatch, data)
    current = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        current.act(_request())
    assert error.value.error_kind == kind
    assert current.last_receipt["usage"]["total_tokens"] == 113
    assert "private-runtime-error" not in str(error.value) + json.dumps(current.last_receipt)
    assert len(calls) == 1
