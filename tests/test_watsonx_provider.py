"""Deterministic IBM raw REST tests; never contact IAM or paid inference."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.watsonx import ALIASES, API_VERSION, IAM_ENDPOINT, REGIONS
from eslams.runner import RunConfig, Runner

MODEL = "ibm/granite-4-h-small"
FIXTURE = Path(__file__).parent / "fixtures/provider/watsonx_text_chat_success.json"


def wire():
    return json.loads(FIXTURE.read_text())


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)},
                   history=[{"turn": i, "public": f"history-{i}"} for i in range(100)])


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    for key in ("WATSONX_API_VERSION", "WATSONX_SPACE_ID", "WATSONX_DEPLOYMENT_ID"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WATSONX_API_KEY", "fixture-secret-never-persisted")
    monkeypatch.setenv("WATSONX_REGION", "eu-de")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "project-redacted")


def agent(**kwargs):
    return ModelProviderAgent("watsonx", MODEL, "WATSONX_API_KEY", **kwargs)


def stub(monkeypatch, payload=None, status=200, iam=None, iam_status=200,
         trace="trace-redacted"):
    calls = []

    def token(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(iam_status, json=iam if iam is not None else {
            "access_token": "private-IAM-token", "token_type": "Bearer", "expires_in": 3600,
        }, request=httpx.Request("POST", url))

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload if payload is not None else wire(),
                              headers={"X-Global-Transaction-Id": trace,
                                       "Retry-After": "2"}, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.providers.watsonx.bounded_post", token)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_success_exact_wire_iam_history_accounting_and_privacy(monkeypatch):
    calls = stub(monkeypatch)
    native = agent()
    assert native.act(request()).action == 0
    assert len(calls) == 2
    url, auth = calls[0]
    assert url == IAM_ENDPOINT
    assert auth["json"] is None
    assert auth["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert auth["data"] == {"apikey": "fixture-secret-never-persisted",
                            "grant_type": "urn:ibm:params:oauth:grant-type:apikey"}
    url, inference = calls[1]
    assert url == f"https://eu-de.ml.cloud.ibm.com/ml/v1/text/chat?version={API_VERSION}"
    assert inference["headers"]["Authorization"] == "Bearer private-IAM-token"
    body = inference["json"]
    assert body["model_id"] == MODEL and body["project_id"] == "project-redacted"
    assert set(body) == {"model_id", "project_id", "messages"}
    assert all(f'"public": "history-{i}"' in body["messages"][1]["content"] for i in range(100))
    assert inference["timeout"].read is None
    receipt = native.last_receipt
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "watsonx_text_chat"
    assert receipt["request_id"] == "trace-redacted"
    assert receipt["usage"]["input_tokens"] == 25
    assert receipt["usage"]["output_tokens"] == 12
    assert receipt["usage"]["total_tokens"] == 37
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(receipt)
    for secret in ("private-IAM-token", "fixture-secret-never-persisted",
                   "PRIVATE_REASONING_FIXTURE",
                   "messages", "history-99", "project-redacted"):
        assert secret not in public


@pytest.mark.parametrize("alias", sorted(ALIASES) + ["watsonx_ai"])
def test_aliases_cli_preflight_registry_dispatch(monkeypatch, capsys, tmp_path, alias):
    calls = stub(monkeypatch)
    native = _provider_agent(f"{alias}:{MODEL}")
    assert native.provider == "watsonx" and native.model == MODEL
    assert native.act(request()).action == 0
    assert ModelProviderAgent(alias, MODEL, "WATSONX_API_KEY").provider == "watsonx"
    assert load_provider_registry().resolve(alias, MODEL).provider == "watsonx"
    assert provider_preflight(alias, MODEL, "tic-tac-toe")["ok"]
    assert provider_models_live(alias) is None
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"]
    live = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert live["ok"] and live["checks"]["minimal_inference"]
    assert live["readiness"]["usage_complete"] is True  # numeric visibility only
    assert len(calls) == 4
    assert main(["run", "--arena", "tic-tac-toe", "--agent", f"{alias}:{MODEL}",
                 "--opponent", "first-legal", "--max-turns", "1",
                 "--output-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert json.loads(output[output.index("{"):])["summary"]["winner"] is None
    assert len(calls) == 6


def test_authors_do_not_silently_route_to_watsonx():
    assert _provider_agent(f"ibm:{MODEL}") is None
    assert _provider_agent(f"ibm-granite:{MODEL}") is None
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent("watsonx")


@pytest.mark.parametrize("region", REGIONS)
def test_explicit_regions_space_version_and_controls(monkeypatch, region):
    monkeypatch.setenv("WATSONX_REGION", region)
    monkeypatch.delenv("WATSONX_PROJECT_ID")
    monkeypatch.setenv("WATSONX_SPACE_ID", "space-redacted")
    monkeypatch.setenv("WATSONX_API_VERSION", "2026-01-01")
    calls = stub(monkeypatch)
    native = agent(max_output_tokens=789, temperature=0.3,
                   runtime_config=ProviderRuntimeConfig(reasoning="enabled",
                                                        reasoning_effort="high"))
    native.act(request())
    url, kwargs = calls[-1]
    assert url == f"{REGIONS[region]}/ml/v1/text/chat?version=2026-01-01"
    assert kwargs["json"]["space_id"] == "space-redacted"
    assert kwargs["json"]["max_completion_tokens"] == 789
    assert kwargs["json"]["chat_template_kwargs"] == {"thinking": True}
    assert kwargs["json"]["reasoning_effort"] == "high"
    assert kwargs["json"]["temperature"] == 0.3


def test_disable_thinking_is_explicit_not_include_reasoning(monkeypatch):
    calls = stub(monkeypatch)
    agent(runtime_config=ProviderRuntimeConfig(reasoning="disabled")).act(request())
    assert calls[-1][1]["json"]["chat_template_kwargs"] == {"thinking": False}
    assert "include_reasoning" not in calls[-1][1]["json"]


@pytest.mark.parametrize("key,value", [
    ("WATSONX_REGION", ""), ("WATSONX_REGION", "https://evil.test"),
    ("WATSONX_PROJECT_ID", ""), ("WATSONX_PROJECT_ID", "project?secret=private"),
    ("WATSONX_SPACE_ID", "space-conflicting"), ("WATSONX_API_VERSION", "2025-99-99"),
    ("WATSONX_API_VERSION", "2025-01-01&token=private"),
    ("WATSONX_DEPLOYMENT_ID", "deployment-is-not-model"),
])
def test_configuration_rejected_before_any_network(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    calls = stub(monkeypatch)
    with pytest.raises(ProviderCallError) as error:
        agent().act(request())
    assert error.value.error_kind == "provider_request_rejected" and not calls
    result = provider_preflight("watsonx", MODEL, "tic-tac-toe")
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert value not in json.dumps(result) if "private" in value else True


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(gateway_base_url="https://example.test"),
    ProviderRuntimeConfig(reasoning_budget_tokens=1000),
    ProviderRuntimeConfig(gemini_thinking_budget=1000),
    ProviderRuntimeConfig(reasoning_effort="invented"),
])
def test_unsupported_controls_fail_before_auth(monkeypatch, runtime):
    calls = stub(monkeypatch)
    with pytest.raises(ProviderCallError):
        agent(runtime_config=runtime).act(request())
    assert calls == []


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"), (503, "provider_unavailable"),
])
@pytest.mark.parametrize("retries", [0, 2])
def test_http_failures_no_ambiguous_replay_no_private_error(monkeypatch, status, kind, retries):
    calls = stub(monkeypatch, {"trace": "trace-redacted", "errors": [
        {"code": "rate_limit_reached", "message": "PRIVATE_ERROR fixture-secret-never-persisted"},
    ]}, status)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=retries))
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert error.value.error_kind == kind
    assert len(calls) == 2 and len(native.attempt_receipts) == 1
    assert native.last_receipt["status_code"] == status
    assert native.last_receipt["request_id"] == "trace-redacted"
    assert native.last_receipt["locked_model_id"] is None
    assert "PRIVATE_ERROR" not in json.dumps(native.last_receipt) + str(error.value)
    if status == 429:
        assert error.value.retry_after_seconds == 2


@pytest.mark.parametrize("reason,kind", [
    ("content_filter", "provider_refused"), ("length", "provider_output_truncated"),
    ("time_limit", "provider_interrupted"), ("TIME_LIMIT", "provider_interrupted"),
    ("tool_calls", "provider_request_rejected"), (None, "provider_pending"),
    ("cancelled", "provider_cancelled"), ("error", "provider_unavailable"),
    ("PRIVATE_UNKNOWN", "provider_response_schema_mismatch"),
])
def test_semantic_failures_preserve_usage_never_apply_partial_action(monkeypatch, reason, kind):
    payload = wire()
    payload["choices"][0]["finish_reason"] = reason
    calls = stub(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert error.value.error_kind == kind and len(calls) == 2
    assert native.last_receipt["usage"]["total_tokens"] == 37
    assert "PRIVATE_UNKNOWN" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("mutation", ["refusal", "reasoning_only", "two_choices", "wrong_role",
                                      "no_choices", "body_error", "bad_action"])
def test_invalid_raw_envelopes(monkeypatch, mutation):
    payload = wire()
    message = payload["choices"][0]["message"]
    if mutation == "refusal":
        message["refusal"] = "PRIVATE_REFUSAL"
    elif mutation == "reasoning_only":
        message["content"] = None
        message["reasoning_content"] = '{"action": 0}'
    elif mutation == "two_choices":
        payload["choices"].append(copy.deepcopy(payload["choices"][0]))
    elif mutation == "wrong_role":
        message["role"] = "user"
    elif mutation == "no_choices":
        del payload["choices"]
    elif mutation == "body_error":
        payload["errors"] = [{"code": "failed", "message": "PRIVATE_ERROR"}]
    else:
        message["content"] = "not an action"
    stub(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(request())
    assert native.last_receipt["outcome"] != "ok"
    assert "PRIVATE_REFUSAL" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("missing", ["usage", "total_tokens", "model_id"])
def test_missing_evidence_stays_unknown(monkeypatch, missing):
    payload = wire()
    if missing == "total_tokens":
        del payload["usage"]["total_tokens"]
    else:
        del payload[missing]
    payload["model"] = "invented-openai-shaped-identity"
    stub(monkeypatch, payload)
    native = agent()
    native.act(request())
    receipt = native.last_receipt
    if missing == "usage":
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    if missing == "total_tokens":
        assert receipt["usage"]["total_tokens"] is None
    if missing == "model_id":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("iam,status", [
    ({"errorMessage": "PRIVATE_AUTH"}, 401), ({"access_token": ""}, 200),
    ({"access_token": "private token", "token_type": "Bearer"}, 200),
    ({"access_token": "private", "token_type": "other"}, 200),
])
def test_iam_failures_do_not_submit_inference_or_leak_tokens(monkeypatch, iam, status):
    calls = stub(monkeypatch, iam=iam, iam_status=status)
    native = agent()
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert len(calls) == 1 and error.value.error_kind == "provider_auth_failed"
    assert "PRIVATE_AUTH" not in str(error.value) + json.dumps(native.last_receipt)


@pytest.mark.parametrize("stage", ["iam", "inference"])
@pytest.mark.parametrize("failure", [httpx.ReadTimeout("PRIVATE_TIMEOUT"),
                                     httpx.ConnectError("PRIVATE_TRANSPORT")])
def test_transport_failures_no_replay(monkeypatch, stage, failure):
    calls = stub(monkeypatch)

    def broken(*args, **kwargs):
        raise failure

    monkeypatch.setattr("eslams.providers.watsonx.bounded_post" if stage == "iam" else
                        "eslams.agents.bounded_post", broken)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)):
        native.act(request())
    assert len(calls) == (0 if stage == "iam" else 1)
    assert len(native.attempt_receipts) == 1
    assert "PRIVATE_" not in json.dumps(native.last_receipt)


def test_real_bounded_transport_encodes_form_and_json(monkeypatch):
    monkeypatch.setenv("WATSONX_API_KEY", "fixture+&=secret")
    requests = []

    class Stream(httpx.AsyncByteStream):
        def __init__(self, payload):
            self.body = json.dumps(payload).encode()

        async def __aiter__(self):
            yield self.body

    def handle(req):
        requests.append(req)
        if str(req.url) == IAM_ENDPOINT:
            assert parse_qs(req.content.decode()) == {
                "apikey": ["fixture+&=secret"],
                "grant_type": ["urn:ibm:params:oauth:grant-type:apikey"],
            }
            return httpx.Response(200, stream=Stream({
                "access_token": "test-token", "token_type": "Bearer"}))
        assert req.headers["Authorization"] == "Bearer test-token"
        assert json.loads(req.content)["model_id"] == MODEL
        return httpx.Response(200, stream=Stream(wire()))

    original = httpx.AsyncClient
    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs:
                        original(**kwargs, transport=httpx.MockTransport(handle)))
    assert agent().act(request()).action == 0
    assert len(requests) == 2


def test_runner_receipt_privacy_and_incomplete_accounting(monkeypatch, tmp_path):
    stub(monkeypatch)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(), max_turns=1,
                                   output_dir=tmp_path))
    rows = [json.loads(line) for line in (result.expanded_path /
            "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and not rows[0]["usage_complete"]
    assert rows[0]["model"] == rows[0]["locked_model_id"] == MODEL
    assert not rows[0]["cost_complete"]
    assert ArtifactValidator().validate(result.expanded_path) == []
    assert "PRIVATE_REASONING_FIXTURE" not in json.dumps(rows)


@pytest.mark.parametrize("stage", ["iam", "inference"])
@pytest.mark.parametrize("body", ['not-json', '[]', '{"id":1,"id":2}', 'null'])
def test_malformed_body_never_retries_or_applies(monkeypatch, stage, body):
    calls = stub(monkeypatch)

    def malformed(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, text=body, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.providers.watsonx.bounded_post" if stage == "iam" else
                        "eslams.agents.bounded_post", malformed)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        native.act(request())
    assert len(calls) == (1 if stage == "iam" else 2)
    assert len(native.attempt_receipts) == 1
    assert native.last_receipt["outcome"] != "ok"


def test_different_reported_model_is_not_a_silent_fallback(monkeypatch):
    payload = wire()
    payload["model_id"] = "different/model"
    calls = stub(monkeypatch, payload)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert error.value.error_kind == "provider_request_rejected"
    assert len(calls) == 2
    assert native.last_receipt["model"] == MODEL
    assert native.last_receipt["locked_model_id"] == "different/model"
    assert native.last_receipt["usage"]["total_tokens"] == 37


@pytest.mark.parametrize("field,value", [("prompt_tokens", True), ("completion_tokens", -1),
                                         ("total_tokens", 999), ("total_tokens", "37")])
def test_invalid_usage_is_reported_not_repaired(monkeypatch, field, value):
    payload = wire()
    payload["usage"][field] = value
    stub(monkeypatch, payload)
    native = agent()
    native.act(request())
    assert native.last_receipt["usage"]["usage_validation_errors"]
    if field == "total_tokens" and not isinstance(value, int):
        assert native.last_receipt["usage"]["total_tokens"] is None
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_undocumented_accounting_extensions_cannot_attest_completeness(monkeypatch):
    payload = wire()
    payload["usage"].update(reasoning_tokens=0, cached_input_tokens=0,
                           reasoning_included_in_output=True, cost=0.01)
    stub(monkeypatch, payload)
    native = agent()
    native.act(request())
    usage = native.last_receipt["usage"]
    assert usage["reasoning_tokens"] is None and usage["cached_input_tokens"] is None
    assert usage["reasoning_included_in_output"] is None
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_missing_credentials_and_cancellation_make_no_requests(monkeypatch):
    import threading

    from eslams.deadlines import ExecutionCancelled, cancellation_scope

    calls = stub(monkeypatch)
    monkeypatch.delenv("WATSONX_API_KEY")
    with pytest.raises(ProviderCallError) as error:
        agent().act(request())
    assert error.value.error_kind == "provider_auth_failed" and calls == []
    monkeypatch.setenv("WATSONX_API_KEY", "fixture-secret")
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ExecutionCancelled), cancellation_scope(cancelled):
        agent().act(request())
    assert calls == []


@pytest.mark.parametrize("status", [200, 400, 429])
def test_even_identifiers_cannot_echo_known_credentials(monkeypatch, status):
    payload = wire()
    payload["id"] = "fixture-secret-never-persisted"
    payload["model_id"] = "private-IAM-token"
    stub(monkeypatch, payload, status=status, trace="private-IAM-token")
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(request())
    public = json.dumps(native.last_receipt)
    assert "fixture-secret-never-persisted" not in public
    assert "private-IAM-token" not in public
    assert native.last_receipt.get("provider_response_id") is None
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("alias", sorted(ALIASES) + ["watsonx_ai"])
@pytest.mark.parametrize("model", [None, "", " ", "\t", " model", "model "])
def test_missing_or_blank_models_rejected_in_cli_preflight_and_agent(monkeypatch, alias, model):
    calls = stub(monkeypatch)
    value = alias if model is None else f"{alias}:{model}"
    with pytest.raises(ValueError, match="explicit model ID"):
        _provider_agent(value)
    with pytest.raises(ValueError, match="explicit model ID"):
        ModelProviderAgent(alias, model, "WATSONX_API_KEY")
    for live in (False, True):
        with pytest.raises(ValueError, match="explicit model ID"):
            provider_preflight(alias, model, "tic-tac-toe", live=live)
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("reasoning_budget_tokens", 0), ("reasoning_budget_tokens", 1000),
    ("gemini_thinking_budget", -1), ("gemini_thinking_budget", 0),
    ("gemini_thinking_budget", 1000),
])
def test_unsupported_budgets_rejected_in_all_preflight_modes_before_discovery(
    monkeypatch, field, value,
):
    calls = stub(monkeypatch)
    discoveries = []
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live",
                        lambda provider: discoveries.append(provider))
    runtime = ProviderRuntimeConfig(**{field: value})
    for live in (False, True):
        for strict in (False, True):
            result = provider_preflight("watsonx_ai", MODEL, "tic-tac-toe", live=live,
                                        strict_catalogue=strict, runtime_config=runtime)
            assert not result["ok"]
            assert result["error"]["error_class"] == "provider_request_rejected"
            assert "budget" in result["error"]["message"]
            assert not result["readiness"]["configuration_ready"]
            assert result["readiness"]["inference"] == "not_attempted"
    with pytest.raises(ProviderCallError, match="budget"):
        agent(runtime_config=runtime).act(request())
    assert calls == [] and discoveries == []


@pytest.mark.parametrize("secret", ["fixture-secret-never-persisted", "private-IAM-token"])
@pytest.mark.parametrize("scenario", ["success", "http400", "http429", "malformed",
                                      "partial_timeout", "partial_protocol",
                                      "refused", "truncated"])
def test_primary_and_secondary_credential_echoes_scrubbed_on_every_response_path(
    monkeypatch, secret, scenario,
):
    from eslams.http_io import ResponseObservation
    from eslams.protocol import ProtocolError

    calls = stub(monkeypatch)
    headers = {"x-global-transaction-id": f"{secret}-request",
               "x-request-id": f"{secret}-upstream", "cf-aig-request-id": f"{secret}-gateway"}
    payload = wire()
    payload["id"] = f"{secret}-response"
    payload["system"] = {"diagnostic": secret}  # Unused private extensions stay out of receipts.
    payload["choices"][0]["message"]["reasoning_content"] = secret
    if scenario == "refused":
        payload["choices"][0]["finish_reason"] = "content_filter"
    elif scenario == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    status = 400 if scenario == "http400" else 429 if scenario == "http429" else 200
    if status >= 400:
        payload["errors"] = [{"code": "failed", "message": secret}]

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if scenario.startswith("partial_"):
            exc = (httpx.ReadTimeout(secret) if scenario == "partial_timeout" else
                   ProtocolError(secret))
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                status_code=429, headers=tuple(headers.items()))
            raise exc
        return httpx.Response(status, headers=headers,
                              content=secret.encode() if scenario == "malformed" else
                              json.dumps(payload).encode(), request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    if scenario == "success":
        response = native.act(request())
        assert response.action == 0
        assert secret not in json.dumps(response.metadata)
    else:
        with pytest.raises(ProviderCallError) as error:
            native.act(request())
        assert secret not in str(error.value) + json.dumps(error.value.receipt)
    assert len(calls) == 2 and len(native.attempt_receipts) == 1
    assert secret not in json.dumps(native.attempt_receipts)
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["gateway_request_id"] is None
    assert native.last_receipt.get("provider_response_id") is None
    assert native.last_receipt["model"] == MODEL
    assert native.last_receipt.get("locked_model_id") == (MODEL if scenario in {
        "success", "refused", "truncated",
    } else None)


@pytest.mark.parametrize("secret", ["fixture-secret-never-persisted", "private-IAM-token"])
def test_generated_action_text_cannot_publish_credentials_or_trigger_action_repair(
    monkeypatch, secret,
):
    payload = wire()
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 0, "public_explanation": f"echo {secret}",
    })
    calls = stub(monkeypatch, payload)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 2 and len(native.attempt_receipts) == 1
    assert secret not in str(error.value) + json.dumps(native.attempt_receipts)
    assert native.last_receipt["usage"]["total_tokens"] == 37


def test_nested_receipt_extensions_cannot_publish_either_credential(monkeypatch):
    import eslams.agents as shared

    stub(monkeypatch)
    original = shared._receipt

    def extended(**kwargs):
        result = original(**kwargs)
        # Fault injection at the shared receipt boundary: no future diagnostic
        # extension may bypass the provider's final credential filter.
        result["diagnostic_extension"] = {
            "fixture-secret-never-persisted": ["prefix-private-IAM-token-suffix",
                                                {"detail": "fixture-secret-never-persisted"}],
        }
        return result

    monkeypatch.setattr(shared, "_receipt", extended)
    native = agent()
    response = native.act(request())
    encoded = json.dumps(response.metadata)
    assert "fixture-secret-never-persisted" not in encoded
    assert "private-IAM-token" not in encoded
    assert native.last_receipt["usage"]["total_tokens"] == 37
    assert native.last_receipt["locked_model_id"] == MODEL


@pytest.mark.parametrize("secret", ["fixture-secret-never-persisted", "private-IAM-token"])
def test_protocol_diagnostic_without_observed_headers_cannot_leak_credentials(monkeypatch, secret):
    from eslams.protocol import ProtocolError

    calls = stub(monkeypatch)

    def broken(url, **kwargs):
        calls.append((url, kwargs))
        raise ProtocolError(f"untrusted transport diagnostic: {secret}")

    monkeypatch.setattr("eslams.agents.bounded_post", broken)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as error:
        native.act(request())
    assert error.value.error_kind == "provider_response_schema_mismatch"
    assert secret not in str(error.value) + json.dumps(native.attempt_receipts)
    result = provider_preflight("watsonx", MODEL, "tic-tac-toe", live=True)
    assert not result["ok"] and secret not in json.dumps(result)
    assert len(calls) == 4  # One IAM exchange and inference attempt per explicit invocation.
