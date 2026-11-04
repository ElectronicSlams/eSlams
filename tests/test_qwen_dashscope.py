"""Native REST fixtures only: no credentials, SDK, network or billable calls."""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.qwen import generation_endpoint
from eslams.runner import RunConfig, Runner

FIXTURES = Path(__file__).parent / "fixtures" / "provider"
REQUESTED = "Exact-Caller-Model-2026-11-04"
SECRET = "fixture-secret-never-persisted"


def fixture(name="success"):
    return json.loads((FIXTURES / f"qwen_dashscope_{name}.json").read_text())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_REGION", raising=False)
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("unmocked POST"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("unmocked GET"))


def agent(**kwargs):
    return ModelProviderAgent("qwen", REQUESTED, "DASHSCOPE_API_KEY", **kwargs)


def request():
    return replace(
        _request(), protocol_version="eslams-act-v2", time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def wire(monkeypatch, payload=None, status=200, **headers):
    calls = []
    payload = fixture() if payload is None else payload

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_native_request_history_and_unknown_identity_cost(monkeypatch):
    payload = fixture()
    payload["model"] = "undocumented-model-extension"
    payload["usage"]["cost"] = 123
    payload["output"]["choices"][0]["message"]["reasoning_content"] = "PRIVATE-REASONING"
    calls = wire(monkeypatch, payload)
    wrapped = agent()
    # Even a catalogue price must not be mistaken for a regional DashScope rate.
    wrapped.capabilities = replace(wrapped.capabilities, pricing={
        "input_cost_per_million": 1, "output_cost_per_million": 2, "currency": "USD",
    })
    history = [{"turn": i, "public_state": f"public-turn-{i}"} for i in range(64)]
    result = wrapped.act(replace(request(), history=history))
    assert result.action == 1
    url, sent = calls[0]
    assert url == "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    assert sent["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    assert sent["json"]["model"] == REQUESTED
    assert sent["json"]["parameters"] == {"result_format": "message"}
    messages = sent["json"]["input"]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    encoded_request = json.loads(messages[1]["content"].split("\n")[-1])
    assert encoded_request["history"] == history
    assert sent["timeout"].read is None
    assert wrapped.runtime_config.max_retries == 0
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "qwen" and receipt["model"] == REQUESTED
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["endpoint_kind"] == "dashscope_text_generation"
    assert receipt["parser_version"] == "dashscope-text-generation-raw-v1"
    assert receipt["request_id"] == payload["request_id"]
    assert receipt["provider_response_id"] == payload["request_id"]
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["finish_reason"] == "stop" and receipt["finish_status"] == "completed"
    assert receipt["attempt"] == 1 and receipt["attempt_kind"] == "primary"
    assert len(wrapped.attempt_receipts) == 1
    public = json.dumps(receipt)
    for private in (SECRET, "PRIVATE-REASONING", "public-turn-", "Authorization", "Fixture action"):
        assert private not in public


@pytest.mark.parametrize("alias", ["qwen", "alibaba", "dashscope", "alibaba-cn", " ALIBABA_CN "])
def test_alias_registry_cli_preflight_and_execution(monkeypatch, alias):
    calls = wire(monkeypatch)
    record = load_provider_registry().resolve(alias, "qwen-plus")
    assert record.provider == "qwen" and record.known
    wrapped = _provider_agent(f"{alias}:{REQUESTED}")
    assert wrapped.provider == "qwen" and wrapped.api_key_env == "DASHSCOPE_API_KEY"
    assert wrapped.act(request()).action == 1
    assert wrapped.last_receipt["provider"] == "qwen"
    local = provider_preflight(alias, REQUESTED, "tic-tac-toe")
    assert local["provider"] == "qwen" and local["ok"]
    assert local["checks"]["adapter_available"] and not local["checks"]["registry_entry"]
    live = provider_preflight(alias, REQUESTED, "tic-tac-toe", live=True)
    assert live["ok"] and live["checks"]["account_model_visible"] is None
    assert live["model_availability"] == "inference_succeeded"
    assert provider_models_live(alias) is None
    assert len(calls) == 2 and all(c[1]["json"]["model"] == REQUESTED for c in calls)


def test_cli_preflight_is_keyless_and_canonical(monkeypatch, capsys):
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    assert main(["providers", "preflight", "--provider", "dashscope", "--model", REQUESTED,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider"] == "qwen" and result["ok"]
    assert result["readiness"]["inference"] == "not_attempted"
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent("dashscope")


def test_cli_run_dispatches_alias_to_native_provider(monkeypatch, tmp_path, capsys):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]["model"]))
        prompt = kwargs["json"]["input"]["messages"][1]["content"]
        payload = fixture()
        action = json.loads(prompt.split("\n")[-1])["legal_actions"][0]
        payload["output"]["choices"][0]["message"]["content"] = json.dumps({"action": action})
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", f"dashscope:{REQUESTED}",
                 "--expanded", "--output-dir", str(tmp_path), "--runner-result-json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result and calls and all(model == REQUESTED for _, model in calls)
    assert all("/services/aigc/text-generation/generation" in url for url, _ in calls)


def test_strict_catalogue_remains_opt_in_and_cannot_enable_unknown_model():
    result = provider_preflight("dashscope", REQUESTED, "tic-tac-toe", live=True,
                                strict_catalogue=True)
    assert not result["ok"] and result["error"]["error_class"] == "provider_request_rejected"
    assert result["readiness"]["inference"] == "not_attempted"


@pytest.mark.parametrize("region,host", [
    ("ap-southeast-1", "dashscope-intl.aliyuncs.com"),
    ("cn-beijing", "dashscope.aliyuncs.com"),
    ("cn-hongkong", "cn-hongkong.dashscope.aliyuncs.com"),
])
def test_legacy_regions(monkeypatch, region, host):
    monkeypatch.setenv("DASHSCOPE_REGION", region)
    calls = wire(monkeypatch)
    agent().act(request())
    assert calls[0][0] == f"https://{host}/api/v1/services/aigc/text-generation/generation"


@pytest.mark.parametrize("region", [
    "ap-southeast-1", "cn-beijing", "cn-hongkong", "us-east-1", "eu-central-1", "ap-northeast-1",
])
def test_workspace_regions_and_gateway(monkeypatch, region):
    monkeypatch.setenv("DASHSCOPE_REGION", region)
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", "ws-example")
    assert generation_endpoint().startswith(f"https://ws-example.{region}.maas.aliyuncs.com/")
    calls = wire(monkeypatch)
    agent(runtime_config=ProviderRuntimeConfig(
        gateway_base_url="https://gateway.example.test/qwen", gateway_mode="generic_base_url",
    )).act(request())
    assert calls[0][0] == (
        "https://gateway.example.test/qwen/api/v1/services/aigc/text-generation/generation"
    )


@pytest.mark.parametrize("region,workspace", [
    ("unsupported-region", None), ("", None), ("us-east-1", None),
    ("cn-beijing", ""), ("ap-southeast-1", "private.example.test"),
    ("ap-southeast-1", "user@host"), ("ap-southeast-1", "host/path"),
])
def test_invalid_endpoint_configuration_fails_before_submission(monkeypatch, region, workspace):
    monkeypatch.setenv("DASHSCOPE_REGION", region)
    if workspace is not None:
        monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID", workspace)
    result = provider_preflight("dashscope", REQUESTED, "tic-tac-toe", live=True)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ProviderCallError) as failure:
        agent().act(request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert "private.example.test" not in str(failure.value)


@pytest.mark.parametrize("mode,expected", [("auto", None), ("enabled", True), ("disabled", False)])
def test_explicit_controls_do_not_depend_on_model_or_arena(monkeypatch, mode, expected):
    calls = wire(monkeypatch)
    wrapped = agent(max_output_tokens=123, temperature=0.5, runtime_config=ProviderRuntimeConfig(
        reasoning=mode, timeout_ms=7890, history_window_turns=1,
    ))
    wrapped.act(replace(request(), history=[{"turn": 0}, {"turn": 1}]))
    parameters = calls[0][1]["json"]["parameters"]
    assert parameters["max_tokens"] == 123 and parameters["temperature"] == 0.5
    if expected is None:
        assert "enable_thinking" not in parameters
    else:
        assert parameters["enable_thinking"] is expected
    prompt = calls[0][1]["json"]["input"]["messages"][1]["content"]
    assert json.loads(prompt.split("\n")[-1])["history"] == [{"turn": 1}]


@pytest.mark.parametrize("runtime,field,value", [
    (ProviderRuntimeConfig(reasoning_budget_tokens=512), "thinking_budget", 512),
    (ProviderRuntimeConfig(reasoning_effort="low"), "reasoning_effort", "low"),
])
def test_explicit_native_reasoning_controls(monkeypatch, runtime, field, value):
    calls = wire(monkeypatch)
    agent(runtime_config=runtime).act(request())
    assert calls[0][1]["json"]["parameters"][field] == value
    assert "enable_thinking" not in calls[0][1]["json"]["parameters"]


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(gemini_thinking_budget=512),
    ProviderRuntimeConfig(reasoning_effort="low", reasoning_budget_tokens=512),
])
def test_unrepresentable_reasoning_controls_fail_closed(runtime):
    wrapped = agent(runtime_config=runtime)
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert wrapped.last_receipt["outcome"] == "provider_request_rejected"


@pytest.mark.parametrize("alias", ["qwen", "alibaba", "dashscope", "alibaba-cn"])
@pytest.mark.parametrize("suffix", ["", ":", ":   ", ":\t"])
def test_cli_missing_or_blank_model_cannot_select_a_default(alias, suffix, tmp_path, capsys):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(alias + suffix)
    assert main(["run", "--agent", alias + suffix, "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank model" in capsys.readouterr().err


@pytest.mark.parametrize("model", [None, "", "   ", "\t\n"])
def test_direct_execution_and_preflight_reject_blank_model(model):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent("dashscope", model, "DASHSCOPE_API_KEY")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        provider_preflight("alibaba", model, "tic-tac-toe", live=True)


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(gemini_thinking_budget=-1),
    ProviderRuntimeConfig(gemini_thinking_budget=0),
    ProviderRuntimeConfig(gemini_thinking_budget=512),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(reasoning_effort="low", reasoning_budget_tokens=512),
])
def test_preflight_and_transport_reject_unrepresentable_budgets(runtime, live):
    result = provider_preflight("dashscope", REQUESTED, "tic-tac-toe", live=live,
                                runtime_config=runtime)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["error"]["error_class"] == "provider_request_rejected"
    wrapped = agent(runtime_config=runtime)
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert wrapped.last_receipt["status_code"] is None


@pytest.mark.parametrize("status,code,kind", [
    (400, "InvalidParameter", "provider_request_rejected"),
    (401, "InvalidApiKey", "provider_auth_failed"),
    (403, "AccessDenied", "provider_permission_failed"),
    (404, "ModelNotFound", "provider_unavailable"),
    (429, "Throttling.RateQuota", "provider_rate_limited"),
    (500, "InternalError", "provider_unavailable"),
    (503, "ServiceUnavailable", "provider_unavailable"),
    (400, "DataInspectionFailed", "provider_refused"),
])
@pytest.mark.parametrize("retries", [0, 2])
def test_native_http_failures_never_replay_or_leak(monkeypatch, status, code, kind, retries):
    payload = fixture("error")
    payload.update(code=code, message=f"PRIVATE-PROMPT Authorization: Bearer {SECRET}")
    calls = wire(monkeypatch, payload, status, **{"Retry-After": "3"})
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=retries))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert len(calls) == 1 and len(wrapped.attempt_receipts) == 1
    assert failure.value.error_kind == kind and failure.value.status_code == status
    receipt = wrapped.last_receipt
    assert receipt["outcome"] == kind and receipt["request_id"] == payload["request_id"]
    assert failure.value.retry_after_seconds == 3
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(receipt) + str(failure.value)
    assert SECRET not in public and "PRIVATE-PROMPT" not in public


@pytest.mark.parametrize("code,kind", [
    ("InvalidApiKey", "provider_auth_failed"), ("AccessDenied", "provider_permission_failed"),
    ("Throttling.RateQuota", "provider_rate_limited"),
    ("InternalError", "provider_unavailable"), ("DataInspectionFailed", "provider_refused"),
    ("UnknownProviderError", "provider_unavailable"),
])
def test_http200_flat_error_with_legal_looking_output_is_rejected(monkeypatch, code, kind):
    payload = fixture()
    payload.update(code=code, message=f"PRIVATE-ERROR {SECRET}")
    calls = wire(monkeypatch, payload)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert wrapped.last_receipt["usage"]["total_tokens"] == 16
    assert "PRIVATE-ERROR" not in json.dumps(wrapped.last_receipt) + str(failure.value)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("tool_calls", "provider_request_rejected"),
    ("content_filter", "provider_refused"), (None, "provider_response_schema_mismatch"),
    ("future-private-finish-reason", "provider_response_schema_mismatch"),
    ({"private": "data"}, "provider_response_schema_mismatch"),
])
def test_incomplete_response_rejects_parseable_action(monkeypatch, reason, kind):
    payload = fixture()
    payload["output"]["choices"][0]["finish_reason"] = reason
    calls = wire(monkeypatch, payload)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert wrapped.last_receipt["usage"]["total_tokens"] == 16
    assert "future-private" not in json.dumps(wrapped.last_receipt)


@pytest.mark.parametrize("key,value,kind", [
    ("refusal", "PRIVATE-REFUSAL", "provider_refused"),
    ("tool_calls", [{"function": {"arguments": '{"action": 1}'}}], "provider_request_rejected"),
    ("function_call", {"arguments": '{"action": 1}'}, "provider_request_rejected"),
    ("content", [{"text": '{"action": 1}'}], "provider_response_schema_mismatch"),
    ("content", None, "provider_response_schema_mismatch"),
    ("content", "", "provider_response_schema_mismatch"),
    ("role", "user", "provider_response_schema_mismatch"),
])
def test_message_errors_are_not_accepted(monkeypatch, key, value, kind):
    payload = fixture()
    payload["output"]["choices"][0]["message"][key] = value
    wire(monkeypatch, payload)
    wrapped = agent()
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == kind
    assert "PRIVATE-REFUSAL" not in json.dumps(wrapped.last_receipt)


@pytest.mark.parametrize("body", [
    b'{"output":', b'[]', b'null', b'not JSON', b'{"output":{},"output":{}}',
    b'{"output":{"text":"{\\"action\\":1}","finish_reason":"stop"}}',
    b'{"choices":[{"message":{"content":"{\\"action\\":1}"}}]}',
])
def test_malformed_or_sdk_compatible_envelopes_fail_with_receipt(monkeypatch, body):
    calls = []

    def post(*a, **k):
        calls.append(1)
        return httpx.Response(200, content=body, headers={"x-request-id": "req-malformed"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == "provider_response_schema_mismatch" and calls == [1]
    assert wrapped.last_receipt["status_code"] == 200
    assert wrapped.last_receipt["request_id"] == "req-malformed"
    assert wrapped.last_receipt["usage"] == {}


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": 12},
    {"input_tokens": True, "output_tokens": -1, "total_tokens": "16"}])
def test_usage_gaps_are_not_zero_or_fabricated_cost(monkeypatch, usage):
    payload = fixture()
    payload["usage"] = usage
    payload.pop("request_id")
    wire(monkeypatch, payload)
    wrapped = agent()
    assert wrapped.act(request()).action == 1
    receipt = wrapped.last_receipt
    assert receipt["locked_model_id"] is None and receipt["request_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "cost_usd" not in receipt["estimated_cost"]
    if usage == {"input_tokens": 12}:
        assert receipt["usage"]["input_tokens"] == 12
        assert receipt["usage"]["output_tokens"] is None
        assert receipt["usage"]["total_tokens"] is None
    else:
        assert receipt["usage"] == {}


def test_reasoning_cache_subsets_and_total_validation(monkeypatch):
    payload = fixture()
    payload["usage"].update(
        output_tokens_details={"reasoning_tokens": 2},
        prompt_tokens_details={"cached_tokens": 3, "cache_creation_input_tokens": 2},
    )
    wire(monkeypatch, payload)
    wrapped = agent()
    wrapped.act(request())
    usage = wrapped.last_receipt["usage"]
    assert usage["reasoning_tokens"] == 2 and usage["output_tokens"] == 4
    assert usage["cached_input_tokens"] == 5 and usage["cache_write_input_tokens"] == 2
    assert usage["total_tokens"] == 16 and usage["usage_validation_errors"] == []
    payload["usage"]["total_tokens"] = 18
    wire(monkeypatch, payload)
    wrapped.act(request())
    assert wrapped.last_receipt["usage"]["usage_validation_errors"]


def test_undocumented_top_level_cache_creation_is_not_native_accounting(monkeypatch):
    payload = fixture()
    payload["usage"]["cache_creation_input_tokens"] = 7
    wire(monkeypatch, payload)
    wrapped = agent()
    wrapped.act(request())
    assert wrapped.last_receipt["usage"]["cache_write_input_tokens"] is None


@pytest.mark.parametrize("error,kind", [
    (httpx.ReadTimeout("PRIVATE-TRANSPORT"), "provider_timeout"),
    (httpx.ConnectError("PRIVATE-TRANSPORT"), "provider_transport_error"),
])
def test_transport_failure_is_ambiguous_and_never_replayed(monkeypatch, error, kind):
    calls = []

    def post(*a, **k):
        calls.append(1)
        raise error

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)):
        wrapped.act(request())
    assert calls == [1] and wrapped.last_receipt["outcome"] == kind
    assert wrapped.last_receipt["usage"] == {}
    assert "PRIVATE-TRANSPORT" not in json.dumps(wrapped.last_receipt)


@pytest.mark.parametrize("key", [None, "", "bad key\nvalue"])
def test_missing_or_invalid_credentials_are_never_sent(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("DASHSCOPE_API_KEY")
    else:
        monkeypatch.setenv("DASHSCOPE_API_KEY", key)
    wrapped = agent()
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert wrapped.last_receipt["status_code"] is None
    result = provider_preflight("alibaba", REQUESTED, "tic-tac-toe", live=True)
    assert not result["ok"] and result["readiness"]["inference"] == "not_attempted"


def test_repair_is_opt_in_and_receipt_attempts_stay_distinct(monkeypatch):
    calls = []

    def post(*a, **k):
        calls.append(k["json"])
        payload = fixture()
        if len(calls) == 1:
            payload["output"]["choices"][0]["message"]["content"] = "unparseable"
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=1))
    assert wrapped.act(request()).action == 1
    assert len(calls) == 2 and calls[0]["model"] == calls[1]["model"] == REQUESTED
    assert [r["attempt"] for r in wrapped.attempt_receipts] == [1, 2]
    assert [r["attempt_kind"] for r in wrapped.attempt_receipts] == ["primary", "action_repair"]
    assert wrapped.attempt_receipts[0]["outcome"] == "action_response_unparseable"
    assert wrapped.attempt_receipts[0]["usage"]["total_tokens"] == 16


def test_non2xx_usage_is_quarantined_without_cost_or_identity(monkeypatch):
    payload = fixture("error")
    payload.update(usage=copy.deepcopy(fixture()["usage"]), model="unverified", cost=9)
    calls = wire(monkeypatch, payload, 429)
    wrapped = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        wrapped.act(request())
    receipt = wrapped.last_receipt
    assert len(calls) == 1 and receipt["usage"]["total_tokens"] == 16
    assert receipt["locked_model_id"] is None
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_native_receipts_survive_runner_without_claiming_complete_cost(monkeypatch, tmp_path):
    def post(url, **kwargs):
        prompt = kwargs["json"]["input"]["messages"][1]["content"]
        act_request = json.loads(prompt.split("\n")[-1])
        payload = fixture()
        payload["output"]["choices"][0]["message"]["content"] = json.dumps({
            "action": act_request["legal_actions"][0],
        })
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig(
        "tic-tac-toe", agent_1=agent(), output_dir=tmp_path,
    ))
    receipt_path = result.expanded_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert receipts and all(r["provider"] == "qwen" for r in receipts)
    assert all(r["usage_complete"] and not r["cost_complete"] for r in receipts)
    assert all(r["locked_model_id"] is None for r in receipts)
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


@pytest.mark.parametrize("status,failure,kind", [
    (200, "timeout", "provider_timeout"),
    (429, "reset", "provider_transport_error"),
    (503, "resource", "provider_response_schema_mismatch"),
])
@pytest.mark.parametrize("echo_index", [None, 0, 1])
def test_actual_bounded_reader_keeps_header_custody_after_partial_body(
    monkeypatch, tmp_path, status, failure, kind, echo_index,
):
    calls = []
    original_client = httpx.AsyncClient
    secrets = echo_credentials(monkeypatch) if echo_index is not None else ()
    request_id = secrets[echo_index] if echo_index is not None else "safe-native-header-id"

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"private_prompt":"PRIVATE-PARTIAL-BODY",'
            if failure == "timeout":
                raise httpx.ReadTimeout("PRIVATE-TRANSPORT")
            if failure == "reset":
                raise httpx.ReadError("PRIVATE-TRANSPORT")
            yield b"x" * (1024 * 1024 + 1)

    def respond(request):
        calls.append(1)
        return httpx.Response(status, stream=Stream(), request=request,
                              headers={"x-request-id": request_id, "cf-aig-request-id": request_id})

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
    monkeypatch.setattr("eslams.agents.bounded_post", http_io.bounded_post)
    wrapped = ModelProviderAgent(
        "qwen", REQUESTED,
        "QWEN_CUSTOM_AUTH" if echo_index is not None else "DASHSCOPE_API_KEY",
        runtime_config=ProviderRuntimeConfig(max_retries=2),
    )
    result = Runner().run(RunConfig(
        "tic-tac-toe", agent_1=wrapped, on_agent_error="forfeit", output_dir=tmp_path,
    ))
    receipt_path = result.expanded_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert calls == [1] and len(receipts) == 1
    receipt = receipts[0]
    assert receipt["outcome"] == kind and receipt["status_code"] == status
    expected_id = None if echo_index is not None else "safe-native-header-id"
    assert receipt["request_id"] == expected_id and receipt["gateway_request_id"] == expected_id
    assert not receipt["usage"] and not receipt["action_applied"]
    assert result.score.winner is None and not result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert b"PRIVATE-" not in path.read_bytes()
            assert SECRET.encode() not in path.read_bytes()
            assert all(secret.encode() not in path.read_bytes() for secret in secrets)


def echo_credentials(monkeypatch):
    # Neither credential matches pattern-based sk-/token-/key- redaction.
    primary, secondary = "OpaquePrimaryCredential123", "OpaqueSecondaryCredential456"
    monkeypatch.setenv("QWEN_CUSTOM_AUTH", primary)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", secondary)
    return primary, secondary


@pytest.mark.parametrize("echo_index", [0, 1])
def test_credential_echoes_are_removed_from_success_and_receipt_snapshots(monkeypatch, echo_index):
    secrets = echo_credentials(monkeypatch)
    echo = secrets[echo_index]
    payload = fixture()
    payload["request_id"] = f"native-{echo}-response"
    payload["model"] = echo
    payload["output"]["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": " ".join(secrets),
    })
    wire(monkeypatch, payload, **{
        "x-request-id": f"header-{echo}", "cf-aig-request-id": f"gateway-{echo}",
    })
    wrapped = ModelProviderAgent("qwen", REQUESTED, "QWEN_CUSTOM_AUTH")
    result = wrapped.act(request())
    receipt = wrapped.last_receipt
    assert result.action == 1
    assert receipt["provider_response_id"] is None
    assert receipt["request_id"] is None and receipt["gateway_request_id"] is None
    assert receipt["locked_model_id"] is None
    assert receipt["usage"]["total_tokens"] == 16
    snapshot = wrapped._receipt_snapshot(wrapped._receipt_batch[0])
    exported = json.dumps([result.to_dict(), receipt, wrapped.attempt_receipts, snapshot])
    assert all(secret not in exported for secret in secrets)
    # Context cleanup does not change other providers' identifier semantics.
    from eslams.agents import _http_error_identifier
    assert _http_error_identifier(echo) == echo


def test_credential_redaction_precedes_diagnostic_snippet_truncation(monkeypatch):
    primary, secondary = echo_credentials(monkeypatch)
    payload = fixture()
    payload["output"]["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": "x" * 440 + primary + secondary,
    })
    wire(monkeypatch, payload)
    wrapped = ModelProviderAgent("qwen", REQUESTED, "QWEN_CUSTOM_AUTH")
    result = wrapped.act(request())
    assert result.action == 1
    exported = json.dumps(result.to_dict())
    assert primary[:12] not in exported and secondary[:12] not in exported


def test_json_and_url_encoded_secondary_credential_echoes_are_redacted(monkeypatch):
    from urllib.parse import quote

    secondary = 'OpaqueSecondary/With+Special="Characters'
    monkeypatch.setenv("OPENAI_API_KEY", secondary)
    payload = fixture()
    payload["output"]["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": secondary + " " + quote(secondary, safe=""),
    })
    wire(monkeypatch, payload)
    result = agent().act(request())
    assert result.action == 1
    assert result.public_explanation == "[REDACTED] [REDACTED]"
    assert "OpaqueSecondary" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("echo_index", [0, 1])
@pytest.mark.parametrize("status,body_kind", [
    (429, "native_error"), (500, "native_error"), (200, "native_error"),
    (200, "malformed"), (401, "malformed"),
])
def test_credential_echoes_are_removed_from_failure_receipts(
    monkeypatch, echo_index, status, body_kind,
):
    secrets = echo_credentials(monkeypatch)
    echo = secrets[echo_index]
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        headers = {"x-request-id": f"header-{echo}", "cf-aig-request-id": echo}
        if body_kind == "malformed":
            return httpx.Response(status, content=b'{"private":"' + echo.encode(), headers=headers)
        payload = fixture("error")
        payload.update(request_id=echo, id=echo, message=" ".join(secrets),
                       usage=fixture()["usage"])
        return httpx.Response(status, json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = ModelProviderAgent("dashscope", REQUESTED, "QWEN_CUSTOM_AUTH",
                                 runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert calls == [1] and len(wrapped.attempt_receipts) == 1
    assert wrapped.last_receipt["request_id"] is None
    assert wrapped.last_receipt["gateway_request_id"] is None
    assert wrapped.last_receipt.get("provider_response_id") is None
    exported = json.dumps([wrapped.last_receipt, wrapped.attempt_receipts, failure.value.receipt])
    assert all(secret not in exported + str(failure.value) for secret in secrets)


@pytest.mark.parametrize("echo_index", [0, 1])
@pytest.mark.parametrize("kind", ["provider_timeout", "provider_transport_error"])
def test_credential_echoes_are_removed_from_partial_response_custody(
    monkeypatch, echo_index, kind,
):
    secrets = echo_credentials(monkeypatch)
    echo = secrets[echo_index]
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        exc = (httpx.ReadTimeout(echo) if kind == "provider_timeout" else httpx.ReadError(echo))
        # Match the bounded reader's actual partial-response observation object.
        exc.__dict__["_eslams_response_observation"] = http_io.ResponseObservation(
            status_code=200,
            headers=(("x-request-id", echo), ("cf-aig-request-id", f"prefix-{echo}")),
        )
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = ModelProviderAgent("qwen", REQUESTED, "QWEN_CUSTOM_AUTH",
                                 runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        wrapped.act(request())
    assert calls == [1] and wrapped.last_receipt["outcome"] == kind
    assert wrapped.last_receipt["request_id"] is None
    assert wrapped.last_receipt["gateway_request_id"] is None
    assert not wrapped.last_receipt["usage"]
    exported = json.dumps([wrapped.last_receipt, wrapped.attempt_receipts, failure.value.receipt])
    assert all(secret not in exported + str(failure.value) for secret in secrets)


def test_timeout_exception_chain_cannot_print_echoed_credentials(monkeypatch):
    import traceback

    secrets = echo_credentials(monkeypatch)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout(" ".join(secrets))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    wrapped = ModelProviderAgent("qwen", REQUESTED, "QWEN_CUSTOM_AUTH",
                                 runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(TimeoutError) as failure:
        wrapped.act(request())
    assert calls == [1] and wrapped.last_receipt["outcome"] == "provider_timeout"
    printed = "".join(traceback.format_exception(failure.value))
    assert all(secret not in printed + json.dumps(wrapped.last_receipt) for secret in secrets)


@pytest.mark.parametrize("name,value", [
    ("TOKENIZERS_PARALLELISM", "false"), ("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1"),
    ("HF_TOKEN_TYPE", "1"),
    ("ESLAMS_MAX_TOKENS", "1"), ("DASHSCOPE_TOKEN_MODE", "stop"),
    ("ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET", "1"),
])
def test_nonsecret_token_and_secret_configuration_flags_do_not_corrupt_actions(
    monkeypatch, name, value,
):
    monkeypatch.setenv(name, value)
    payload = fixture()
    payload["output"]["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "confidence": 1.0, "public_explanation": "false stop",
    })
    wire(monkeypatch, payload)
    result = agent().act(request())
    assert result.action == 1 and result.public_explanation == "false stop"
    assert result.metadata["provider_receipt"]["finish_reason"] == "stop"


@pytest.mark.parametrize("name", ["QWEN_SECONDARY_KEY", "QWEN_MAX_API_KEY"])
def test_secondary_key_settings_are_still_private(monkeypatch, name):
    secret = "OpaqueBackupCredential789"
    monkeypatch.setenv(name, secret)
    payload = fixture()
    payload["request_id"] = secret
    wire(monkeypatch, payload)
    result = agent().act(request())
    assert result.metadata["provider_receipt"]["request_id"] is None
    assert result.metadata["provider_receipt"]["provider_response_id"] is None
    assert secret not in json.dumps(result.to_dict())
