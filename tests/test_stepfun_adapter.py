"""Keyless raw-wire tests; provenance: docs/providers/STEPFUN.md."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.runner import RunConfig, Runner

MODEL = "step-3.7-flash"
KEY = "stepfun-test-credential"
ENDPOINT = "https://api.stepfun.ai/v1/chat/completions"


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "stepfun_chat_completions_success.json").read_text())


def agent(**kwargs):
    return ModelProviderAgent("stepfun", MODEL, "STEPFUN_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("STEPFUN_API_KEY", KEY)


def install(monkeypatch, payload=None, status=200, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=wire() if payload is None else payload,
                              headers=headers or {"x-request-id": "stepfun-request"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_success_preserves_full_history_native_defaults_and_accounting(monkeypatch):
    calls = install(monkeypatch)
    native = agent()
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)},
                      history=[{"turn": i, "public": f"history-{i}"} for i in range(80)])
    response = native.act(request)
    assert response.action == 1
    url, sent = calls[0]
    assert url == ENDPOINT
    assert sent["headers"] == {"Authorization": f"Bearer {KEY}",
                               "Content-Type": "application/json"}
    payload = sent["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == MODEL and payload["stream"] is False
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    prompt_data = json.loads(payload["messages"][1]["content"].rsplit("\n", 1)[1])
    assert prompt_data["history"] == request.history
    assert sent["timeout"].read is None
    assert native.runtime_config.max_retries == 0
    receipt = response.metadata["provider_receipt"]
    assert receipt["provider"] == "stepfun" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "stepfun_chat_completions"
    assert receipt["parser_version"] == "stepfun-chat-completions-raw-v1"
    assert receipt["request_id"] == "stepfun-request"
    assert receipt["attempt_index"] == 1 and receipt["attempt_kind"] == "primary"
    usage = receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (12, 4, 16)
    assert usage["cached_input_tokens"] == usage["cache_read_input_tokens"] == 8
    assert usage["cached_input_is_subset"] is True
    assert usage["reasoning_tokens"] is None and usage["reasoning_included_in_output"] is None
    assert not usage["usage_validation_errors"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(native.attempt_receipts) == len(calls) == 1
    public = json.dumps(receipt)
    for private in (KEY, "Authorization", "private-reasoning-fixture", "history-79"):
        assert private not in public


@pytest.mark.parametrize("arena_id", ["tic-tac-toe", "chess", "connect-four"])
@pytest.mark.parametrize("reasoning", ["auto", "enabled", "disabled"])
def test_no_game_specific_reasoning_controls(monkeypatch, arena_id, reasoning):
    calls = install(monkeypatch)
    native = agent(runtime_config=ProviderRuntimeConfig(reasoning=reasoning))
    native.act(_request(arena_id=arena_id))
    assert set(calls[0][1]["json"]) == {"model", "messages", "stream"}


def test_explicit_controls_and_exact_unknown_model_are_forwarded(monkeypatch):
    calls = install(monkeypatch)
    native = ModelProviderAgent("stepfun", "Future/Exact-Model:version", "STEPFUN_API_KEY",
        temperature=0.3, max_output_tokens=2345,
        runtime_config=ProviderRuntimeConfig(reasoning_effort="operator-choice"))
    native.act(_request())
    payload = calls[0][1]["json"]
    assert payload["model"] == "Future/Exact-Model:version"
    assert payload["reasoning_effort"] == "operator-choice"
    assert payload["max_tokens"] == 2345 and payload["temperature"] == 0.3
    assert "provider" not in payload and "reasoning_budget" not in payload
    assert native.last_receipt["model"] == "Future/Exact-Model:version"
    assert native.last_receipt["locked_model_id"] == MODEL


@pytest.mark.parametrize("provider", ["stepfun-ai", "stepfun-cn", "stepfun-plan", "step-plan"])
def test_regional_plan_and_router_names_are_not_aliased(provider):
    assert _provider_agent(provider + ":" + MODEL) is None
    result = provider_preflight(provider, MODEL, "tic-tac-toe")
    assert result["checks"]["adapter_available"] is False


def test_cli_case_and_model_identity(monkeypatch, capsys):
    exact = _provider_agent("StepFun:Future/Model:Version")
    assert exact.provider == "stepfun" and exact.model == "Future/Model:Version"
    assert main(["providers", "preflight", "--provider", "StepFun", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True
    assert result["checks"]["minimal_inference"] is False
    assert main(["providers", "models", "--provider", "stepfun"]) == 0
    assert MODEL in json.dumps(json.loads(capsys.readouterr().out))


@pytest.mark.parametrize("selection", ["stepfun", "stepfun:", "stepfun: ", "StepFun:\t\n"])
def test_cli_rejects_missing_and_blank_models_without_transport(monkeypatch, tmp_path,
                                                               capsys, selection):
    calls = install(monkeypatch)
    with pytest.raises(ValueError, match="explicit nonblank model ID"):
        _provider_agent(selection)
    assert main(["run", "--agent", selection, "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank model ID" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize("model", [None, "", " ", "\t\n"])
def test_direct_and_preflight_reject_missing_model(monkeypatch, model):
    calls = install(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("invalid configuration must not discover"))
    with pytest.raises(ValueError, match="explicit nonblank model ID"):
        ModelProviderAgent("stepfun", model, "STEPFUN_API_KEY")
    for provider in ("stepfun", " StepFun "):
        for live in (False, True):
            with pytest.raises(ValueError, match="explicit nonblank model ID"):
                provider_preflight(provider, model, "tic-tac-toe", live=live)
    assert calls == []


@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_unsupported_budgets_fail_configuration_preflight_and_transport(monkeypatch, field):
    calls = install(monkeypatch)
    runtime = ProviderRuntimeConfig(**{field: 2048})
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("invalid controls must not discover"))
    with pytest.raises(ValueError, match="StepFun does not support"):
        agent(runtime_config=runtime)
    for provider in ("stepfun", " StepFun "):
        for live in (False, True):
            result = provider_preflight(provider, MODEL, "tic-tac-toe", live=live,
                                        runtime_config=runtime)
            assert not result["ok"] and not result["readiness"]["configuration_ready"]
            assert result["error"]["error_class"] == "provider_request_rejected"
            assert field in result["error"]["message"]
            assert not result["checks"]["minimal_inference"]
    native = agent()
    native.runtime_config = runtime
    with pytest.raises(ProviderCallError, match="StepFun does not support"):
        native.act(_request())
    assert calls == []
    assert native.last_receipt["outcome"] == "provider_request_rejected"


@pytest.mark.parametrize("secret_kind", ["primary", "secondary"])
@pytest.mark.parametrize("field", ["id", "model", "request_id", "gateway_request_id",
                                  "trace_id"])
def test_success_receipts_drop_literal_credential_echoes(monkeypatch, secret_kind, field):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    secret = KEY if secret_kind == "primary" else secondary
    echoed = "echo-prefix/" + secret + ":suffix"
    data = wire()
    headers = {}
    if field in {"id", "model"}:
        data[field] = echoed
    else:
        headers[{"request_id": "x-request-id", "gateway_request_id": "cf-aig-request-id",
                 "trace_id": "x-cloud-trace-context"}[field]] = echoed
    calls = install(monkeypatch, data, headers=headers)
    native = agent()
    response = native.act(_request())
    receipt = response.metadata["provider_receipt"]
    target = {"id": "provider_response_id", "model": "locked_model_id",
              "trace_id": "request_id"}.get(field, field)
    assert receipt[target] is None
    if field == "model":
        assert receipt["model_identity_source"] is None
    assert receipt["usage"]["total_tokens"] == 16 and len(calls) == 1
    for exposed in (response.to_dict(), native.last_receipt, native.attempt_receipts):
        assert KEY not in json.dumps(exposed) and secondary not in json.dumps(exposed)


@pytest.mark.parametrize("status", [400, 429, 451, 500])
def test_error_receipts_redact_both_credentials_without_authorizing_retry(monkeypatch, status):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    data = {"error": {"code": status, "message": KEY + secondary},
            "id": "echo-" + secondary,
            "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}}
    calls = install(monkeypatch, data, status=status,
                    headers={"x-request-id": "echo-" + KEY,
                             "cf-aig-request-id": "echo-" + secondary})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert not err.value.retry_permitted
    assert len(calls) == len(native.attempt_receipts) == 1
    receipt = native.last_receipt
    assert receipt["request_id"] is receipt["gateway_request_id"] is None
    assert receipt["provider_response_id"] is None
    assert receipt["pricing_provenance"]["work_observation_present"] is True
    assert receipt["usage"]["total_tokens"] == 16
    for exposed in (err.value.receipt, native.last_receipt, native.attempt_receipts):
        assert KEY not in json.dumps(exposed) and secondary not in json.dumps(exposed)
    assert KEY not in str(err.value) and secondary not in str(err.value)


@pytest.mark.parametrize("status", [200, 429])
def test_malformed_body_headers_do_not_echo_credentials(monkeypatch, status):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)

    def post(*args, **kwargs):
        return httpx.Response(status, text="malformed " + KEY + secondary,
                              headers={"x-request-id": "echo-" + KEY,
                                       "cf-aig-request-id": "echo-" + secondary})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent()
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert native.last_receipt["request_id"] is native.last_receipt["gateway_request_id"] is None
    assert native.last_receipt["usage"] == {}
    assert KEY not in json.dumps(err.value.receipt) + str(err.value)
    assert secondary not in json.dumps(native.attempt_receipts) + str(err.value)


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("failure_type", [httpx.ReadTimeout, ProtocolError])
def test_partial_response_observations_redact_credentials(monkeypatch, status, failure_type):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        failure = failure_type("partial " + KEY + secondary)
        failure.__dict__["_eslams_response_observation"] = ResponseObservation(
            status_code=status, headers=(("x-request-id", "echo-" + KEY),
                                         ("cf-aig-request-id", "echo-" + secondary)))
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert len(calls) == 1 and not err.value.retry_permitted
    assert native.last_receipt["status_code"] == status
    assert native.last_receipt["request_id"] is native.last_receipt["gateway_request_id"] is None
    assert native.last_receipt["locked_model_id"] is None and native.last_receipt["usage"] == {}
    assert KEY not in json.dumps(err.value.receipt) + str(err.value)
    assert secondary not in json.dumps(native.attempt_receipts) + str(err.value)


@pytest.mark.parametrize("secret", [KEY, "secondaryPlainValue8642"])
def test_action_explanations_cannot_echo_credentials(monkeypatch, secret):
    monkeypatch.setenv("SECONDARY_API_KEY", "secondaryPlainValue8642")
    data = wire()
    data["choices"][0]["message"]["content"] = json.dumps(
        {"action": 1, "public_explanation": "echo-" + secret})
    calls = install(monkeypatch, data)
    native = agent()
    with pytest.raises(ProviderCallError, match="credential material"):
        native.act(_request())
    assert len(calls) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 16
    assert secret not in json.dumps(native.attempt_receipts)


def test_redacted_request_ids_keep_definitive_rejection_retry_custody(monkeypatch):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429, "message": secondary}},
                                  headers={"Retry-After": "0", "x-request-id": "echo-" + KEY})
        return httpx.Response(200, json=wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    assert native.act(_request()).action == 1
    assert len(calls) == 2
    assert [r["attempt_index"] for r in native.attempt_receipts] == [1, 2]
    assert native.attempt_receipts[0]["request_id"] is None
    assert KEY not in json.dumps(native.attempt_receipts)
    assert secondary not in json.dumps(native.attempt_receipts)


def test_credential_echo_error_receipts_never_enter_runner_artifacts(monkeypatch, tmp_path):
    secondary = "secondaryPlainValue8642"
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    calls = install(monkeypatch, {"error": {"code": 429}, "id": "echo-" + secondary},
                    status=429, headers={"x-request-id": "echo-" + KEY,
                                         "cf-aig-request-id": "echo-" + secondary})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=native, output_dir=tmp_path))
    assert len(calls) == 1 and not result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            contents = path.read_bytes()
            assert KEY.encode() not in contents and secondary.encode() not in contents


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (402, "provider_request_rejected"), (403, "provider_permission_failed"),
    (404, "provider_unavailable"), (429, "provider_rate_limited"),
    (451, "provider_refused"), (500, "provider_unavailable"),
    (503, "provider_unavailable"), (504, "provider_unavailable"),
])
def test_http_errors_keep_one_sanitized_receipt_without_retry(monkeypatch, status, kind):
    calls = install(monkeypatch, {"error": {"code": status, "message": "private-error " + KEY}},
                    status=status, headers={"Retry-After": "17", "x-request-id": "stepfun-error"})
    native = agent()
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert err.value.error_kind == kind and err.value.status_code == status
    assert len(calls) == len(native.attempt_receipts) == 1
    receipt = native.last_receipt
    assert receipt["outcome"] == kind and receipt["request_id"] == "stepfun-error"
    assert receipt["locked_model_id"] is None and receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if status == 429:
        assert err.value.retry_after_seconds == 17 and receipt["retry_after_ms"] == 17000
    assert KEY not in str(err.value) + json.dumps(receipt)
    assert "private-error" not in str(err.value) + json.dumps(receipt)


@pytest.mark.parametrize(("reason", "kind"), [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"),
    ("future-private-reason", "provider_response_schema_mismatch"),
])
def test_finish_fields_reject_even_parseable_action_and_preserve_usage(monkeypatch, reason, kind):
    data = wire()
    data["choices"][0]["finish_reason"] = reason
    calls = install(monkeypatch, data)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert err.value.error_kind == kind
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 16
    assert "future-private-reason" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(object="chat.completion.chunk"),
    lambda d: d.update(choices=[]),
    lambda d: d["choices"].append(copy.deepcopy(d["choices"][0])),
    lambda d: d["choices"][0].pop("finish_reason"),
    lambda d: d["choices"][0].update(index=True),
    lambda d: d["choices"][0]["message"].update(role="user"),
    lambda d: d["choices"][0]["message"].update(content=None),
    lambda d: d["choices"][0]["message"].update(content=[{"text": '{"action":1}'}]),
    lambda d: d["choices"][0]["message"].update(tool_calls=[{"id": "tool-fixture"}]),
])
def test_rejects_malformed_envelopes_without_guessing_text(monkeypatch, mutate):
    data = wire()
    mutate(data)
    install(monkeypatch, data)
    native = agent()
    with pytest.raises(ProviderCallError, match="invalid Chat Completions"):
        native.act(_request())
    assert native.last_receipt["outcome"] == "provider_response_schema_mismatch"


@pytest.mark.parametrize("field", ["id", "model", "usage"])
def test_missing_identity_and_accounting_stay_unknown(monkeypatch, field):
    data = wire()
    data.pop(field)
    install(monkeypatch, data)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    if field == "usage":
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    else:
        assert receipt["provider_response_id" if field == "id" else "locked_model_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": -1, "completion_tokens": 4, "total_tokens": 3},
    {"prompt_tokens": 12, "completion_tokens": True, "total_tokens": 13},
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 17},
    {"prompt_tokens": 12, "cached_tokens": 13, "completion_tokens": 4, "total_tokens": 16},
])
def test_bad_usage_is_flagged_without_fabricating_cost(monkeypatch, usage):
    data = wire()
    data["usage"] = usage
    install(monkeypatch, data)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["usage_validation_errors"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_undocumented_accounting_extensions_cannot_attest_tokens_or_cost(monkeypatch):
    data = wire()
    data["usage"].update(reasoning_tokens=123, reasoning_included_in_output=True, cost=0.1)
    install(monkeypatch, data)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_step5_documented_inclusion_requires_returned_model_identity(monkeypatch):
    data = wire()
    data["model"] = "step-5-preview"
    install(monkeypatch, data)
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["total_tokens"] == 16
    data.pop("model")
    install(monkeypatch, data)
    native = ModelProviderAgent("stepfun", "step-5-preview", "STEPFUN_API_KEY")
    receipt = native.act(_request()).metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout("private-timeout"), httpx.ConnectError("private-network"),
    httpx.Response(200, text="private-malformed"),
    httpx.Response(200, text='{"choices":[],"choices":[]}'),
])
def test_transport_and_json_failures_keep_unknown_receipts(monkeypatch, failure):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        native.act(_request())
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["usage"] == {} and native.last_receipt["locked_model_id"] is None
    assert "private-" not in json.dumps(native.last_receipt)


def test_safe_explicit_retry_keeps_both_physical_attempts(monkeypatch):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429, "message": "limited"}},
                                  headers={"Retry-After": "0"})
        return httpx.Response(200, json=wire())

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    assert native.act(_request()).action == 1
    assert [r["attempt_index"] for r in native.attempt_receipts] == [1, 2]
    assert [r["outcome"] for r in native.attempt_receipts] == ["provider_rate_limited", "ok"]


@pytest.mark.parametrize("status", [200, 429])
def test_accepted_generation_observation_prevents_rate_limit_retry(monkeypatch, status):
    data = wire()
    data["error"] = {"code": 429, "message": "private-error"}
    calls = install(monkeypatch, data, status=status)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as err:
        native.act(_request())
    assert err.value.error_kind == "provider_rate_limited"
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 16


def test_models_and_live_preflight_are_mocked_and_preserve_native_defaults(monkeypatch):
    def get(url, *, headers, **kwargs):
        assert url == "https://api.stepfun.ai/v1/models"
        assert headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": MODEL, "object": "model", "created": 1789747200, "owned_by": "stepai"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("StepFun") == [MODEL]
    calls = install(monkeypatch)
    result = provider_preflight("stepfun", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"] is True
    assert result["checks"]["usage_extraction"] is True
    assert set(calls[0][1]["json"]) == {"model", "messages", "stream"}
    assert KEY not in json.dumps(result)


@pytest.mark.parametrize("model", ["step-1-32k", "step-2-16k"])
def test_retired_models_remain_exact_and_strict_catalogue_is_opt_in(monkeypatch, model):
    advisory = provider_preflight("stepfun", model, "tic-tac-toe")
    strict = provider_preflight("stepfun", model, "tic-tac-toe", strict_catalogue=True)
    assert advisory["ok"] and advisory["lifecycle"] == "retired"
    assert not strict["ok"] and strict["error"]["error_class"] == "provider_unavailable"
    calls = install(monkeypatch, {"error": {"code": 400}}, status=400)
    native = _provider_agent("stepfun:" + model)
    with pytest.raises(ProviderCallError):
        native.act(_request())
    assert calls[0][1]["json"]["model"] == model


def test_cli_run_dispatch_and_public_artifacts_with_mocked_wire(monkeypatch, tmp_path, capsys):
    calls = []

    def post(url, **kwargs):
        assert url == ENDPOINT
        prompt = json.loads(kwargs["json"]["messages"][1]["content"].rsplit("\n", 1)[1])
        data = wire()
        data["id"] = f"stepfun-cli-{len(calls)}"
        data["choices"][0]["message"]["content"] = json.dumps(
            {"action": prompt["legal_actions"][0]}
        )
        calls.append(kwargs["json"])
        return httpx.Response(200, json=data)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "stepfun:" + MODEL,
                 "--opponent", "first-legal", "--output-dir", str(tmp_path),
                 "--run-id", "stepfun-cli"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert len(calls) > 1
    assert output["summary"]["match_valid_for_scoring"] is True
    root = Path(output["expanded_artifact"])
    receipts = [json.loads(line) for line in (root / "receipts/provider_receipts.jsonl")
                .read_text().splitlines()]
    assert len(receipts) == len(calls)
    assert all(r["provider"] == "stepfun" and r["model"] == MODEL for r in receipts)
    assert ArtifactValidator().validate(root) == []
    for path in root.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes()
            assert b"private-reasoning-fixture" not in path.read_bytes()


def test_missing_key_never_submits_or_reads_another_provider_key(monkeypatch):
    monkeypatch.delenv("STEPFUN_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-key")
    calls = install(monkeypatch)
    native = agent()
    with pytest.raises(ProviderCallError, match="STEPFUN_API_KEY"):
        native.act(_request())
    assert calls == [] and native.last_receipt["outcome"] == "provider_auth_failed"


def test_registry_controls_are_documented_advisory_and_keep_distinct_variants():
    registry = load_provider_registry()
    assert registry.resolve("stepfun", "step-3.5-flash-2603").reasoning_efforts == ["low", "high"]
    for model in (MODEL, "step-5-preview"):
        record = registry.resolve("stepfun", model)
        assert record.accepted_control_fields == ["reasoning_effort"]
        assert record.reasoning_efforts == ["low", "medium", "high"]
        assert record.default_reasoning_track == "native-default"
        assert record.available_from_api is None
        assert record.pricing == {}


def test_runner_receipt_privacy_and_invalid_truncation(monkeypatch, tmp_path):
    data = wire()
    data["choices"][0]["finish_reason"] = "length"
    calls = install(monkeypatch, data)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(), output_dir=tmp_path))
    assert len(calls) == 1
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    receipts = (result.expanded_path / "receipts/provider_receipts.jsonl").read_text()
    assert json.loads(receipts.splitlines()[0])["outcome"] == "provider_output_truncated"
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            contents = path.read_bytes()
            assert KEY.encode() not in contents
            assert b"private-reasoning-fixture" not in contents
