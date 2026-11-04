"""Cross-cutting xAI input validation and credential echo regressions."""

import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import httpx
import pytest
from test_provider_wire_v06 import _request
from test_xai_provider import agent
from test_xai_provider import wire as wire

from eslams.agents import ModelProviderAgent, ProviderCallError, _http_error_identifier
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers import xai
from eslams.runner import RunConfig, Runner

PRIMARY = "primaryOpaque42"
SECONDARY = "secondaryOpaque73"


@pytest.mark.parametrize("provider", ["xai", "x-ai"])
@pytest.mark.parametrize("model", [None, "", " \t "])
def test_missing_requested_model_fails_in_agent_and_preflight(monkeypatch, provider, model):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid configuration must not discover or submit")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", unexpected)
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent(provider, model, "XAI_API_KEY")
    for live in (False, True):
        with pytest.raises(ValueError, match="explicit nonblank model"):
            provider_preflight(provider, model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("value", ["xai", "x-ai", "xai:", "x-ai: \t"])
def test_cli_does_not_replace_a_missing_model_with_a_default(value, monkeypatch, tmp_path, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid CLI model must not submit")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(value)
    assert main(["run", "--agent", value, "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank model" in capsys.readouterr().err


@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
@pytest.mark.parametrize("live", [False, True])
def test_unsupported_budgets_fail_configuration_preflight_before_discovery(
    monkeypatch, field, live,
):
    def unexpected(*args, **kwargs):
        pytest.fail("unsupported controls must not discover or submit")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", unexpected)
    runtime = ProviderRuntimeConfig(**{field: 0})
    result = provider_preflight("x-ai", "grok-4.7", "tic-tac-toe", live=live,
                                runtime_config=runtime)
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert result["readiness"]["configuration_ready"] is False
    assert result["readiness"]["inference"] == "not_attempted"


@pytest.fixture
def credentials(monkeypatch, wire):
    monkeypatch.setenv("XAI_API_KEY", PRIMARY)
    monkeypatch.setenv("GATEWAY_API_KEY", SECONDARY)
    return wire


def assert_private_values_absent(value):
    public = json.dumps(value, default=str)
    assert PRIMARY not in public and SECONDARY not in public


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("status", [200, 429, 503])
def test_credential_ids_and_error_body_observations_are_scrubbed_without_replay(
    monkeypatch, credentials, secret, status,
):
    payload = copy.deepcopy(credentials[0])
    payload.update(id=f"resp_{secret}", model=f"grok_{secret}")
    if status != 200:
        payload["error"] = {"code": "rate_limit_exceeded", "message": PRIMARY + SECONDARY}
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(status, json=payload, headers={
            "x-request-id": f"req_{secret}", "cf-aig-request-id": f"gateway_{secret}",
        })

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(max_retries=2)
    if status == 200:
        result = a.act(_request())
        assert_private_values_absent(result.to_dict())
        assert a.last_receipt["locked_model_id"] is None
        assert a.last_receipt["model_identity_source"] is None
    else:
        with pytest.raises(ProviderCallError) as failure:
            a.act(_request())
        assert_private_values_absent(vars(failure.value))
    assert calls == [1]
    assert a.last_receipt.get("provider_response_id") is None
    assert a.last_receipt["request_id"] is None and a.last_receipt["gateway_request_id"] is None
    assert_private_values_absent(a.attempt_receipts)


@pytest.mark.parametrize("body", ["malformed", "refusal", "truncated", "http200_error"])
def test_failures_scrub_identifiers_receipts_and_exception_chains(monkeypatch, credentials, body):
    payload = copy.deepcopy(credentials[0])
    payload["id"] = PRIMARY
    if body == "refusal":
        payload["output"][1]["content"] = [{"type": "refusal", "refusal": SECONDARY}]
    elif body == "truncated":
        payload.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
    else:
        payload["error"] = {"code": "server_error", "message": SECONDARY}
    response = httpx.Response(200, headers={"x-request-id": PRIMARY,
                                           "cf-aig-request-id": SECONDARY},
                              text='{"private":"' + SECONDARY if body == "malformed" else None,
                              json=payload if body != "malformed" else None)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: response)
    a = agent(max_retries=2)
    with pytest.raises(ProviderCallError) as failure:
        a.act(_request())
    assert_private_values_absent(traceback.format_exception(failure.value))
    assert_private_values_absent(vars(failure.value))
    assert_private_values_absent(a.attempt_receipts)
    assert a.last_receipt["request_id"] is None and a.last_receipt["gateway_request_id"] is None
    assert len(a.attempt_receipts) == 1


@pytest.mark.parametrize("failure_type", [httpx.ReadTimeout, httpx.ConnectError, ProtocolError])
@pytest.mark.parametrize("observed", [False, True])
def test_partial_response_headers_and_transport_errors_are_scrubbed(
    monkeypatch, credentials, failure_type, observed,
):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        failure = failure_type(PRIMARY + SECONDARY)
        if observed:
            failure._eslams_response_observation = ResponseObservation(
                status_code=200, headers=(("x-request-id", PRIMARY),
                                          ("cf-aig-request-id", SECONDARY)),
            )
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(max_retries=2)
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        a.act(_request())
    assert_private_values_absent(traceback.format_exception(failure.value))
    assert_private_values_absent(vars(failure.value))
    assert_private_values_absent(a.attempt_receipts)
    assert a.last_receipt.get("request_id") is None
    assert a.last_receipt.get("gateway_request_id") is None
    assert calls == [1] and a.last_receipt["status_code"] == (200 if observed else None)


@pytest.mark.parametrize("escaped", [False, True])
def test_action_explanations_and_raw_text_scrub_both_credentials(credentials, escaped):
    text = json.dumps({"action": 1, "public_explanation": PRIMARY + " / " + SECONDARY})
    if escaped:
        text = text.replace(PRIMARY, "".join(f"\\u{ord(c):04x}" for c in PRIMARY))
        text = text.replace(SECONDARY, "".join(f"\\u{ord(c):04x}" for c in SECONDARY))
    credentials[0]["output"][1]["content"][0]["text"] = text
    a = agent()
    result = a.act(_request())
    assert result.action == 1 and result.public_explanation == "[REDACTED] / [REDACTED]"
    assert_private_values_absent(result.to_dict())
    assert_private_values_absent(a.attempt_receipts)


def test_credentials_in_selected_action_are_rejected_with_receipt(credentials):
    credentials[0]["output"][1]["content"][0]["text"] = json.dumps({"action": PRIMARY})
    a = agent()
    with pytest.raises(ProviderCallError) as failure:
        a.act(replace(_request(), legal_actions=[PRIMARY]))
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert_private_values_absent(a.attempt_receipts)


def test_credentials_never_enter_completed_run_artifacts(monkeypatch, credentials, tmp_path):
    def post(*args, **kwargs):
        prompt = json.loads(kwargs["json"]["input"][1]["content"].splitlines()[-1])
        payload = copy.deepcopy(credentials[0])
        payload["id"] = PRIMARY
        payload["model"] = SECONDARY
        payload["output"][1]["content"][0]["text"] = json.dumps({
            "action": prompt["legal_actions"][0],
            "public_explanation": PRIMARY + SECONDARY,
        })
        return httpx.Response(200, json=payload, headers={"x-request-id": PRIMARY})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, output_dir=tmp_path,
    ))
    for path in result.artifact_path.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl"}:
            assert_private_values_absent(path.read_text())
    assert ArtifactValidator().validate(result.artifact_path) == []


@pytest.mark.parametrize("status", [200, 401, 429, 503])
def test_discovery_does_not_return_credential_model_ids_or_error_text(
    monkeypatch, credentials, status,
):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        status, json={"data": [{"id": PRIMARY}, {"id": "grok-" + SECONDARY}],
                      "error": PRIMARY + SECONDARY},
    ))
    result = provider_models_result("x-ai")
    assert result["ok"] is False and result["models"] == []
    assert_private_values_absent(result)


@pytest.mark.parametrize("fault", ["malformed", "timeout", "transport"])
def test_discovery_malformed_and_transport_errors_suppress_private_context(
    monkeypatch, credentials, fault,
):
    def get(*args, **kwargs):
        if fault == "malformed":
            return httpx.Response(200, text='{"data":"' + PRIMARY + SECONDARY)
        kind = httpx.ReadTimeout if fault == "timeout" else httpx.ConnectError
        raise kind(PRIMARY + SECONDARY)

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("xai")
    assert_private_values_absent(traceback.format_exception(failure.value))


def test_custom_primary_environment_and_secondary_credentials_are_both_scoped(
    monkeypatch, credentials,
):
    monkeypatch.setenv("CUSTOM_AUTH", PRIMARY)
    credentials[0]["id"] = SECONDARY
    credentials[0]["output"][1]["content"][0]["text"] = json.dumps({
        "action": 1, "public_explanation": PRIMARY + SECONDARY,
    })
    a = ModelProviderAgent("xai", "grok-4.7", "CUSTOM_AUTH")
    result = a.act(_request())
    assert_private_values_absent(result.to_dict())
    assert a.last_receipt.get("provider_response_id") is None


@pytest.mark.parametrize("name", [
    "XAI_API_KEY_SECONDARY", "GATEWAY_SECRET_KEY", "AWS_SECRET_ACCESS_KEY",
])
def test_secondary_and_rotated_credential_names_are_recognized(monkeypatch, credentials, name):
    monkeypatch.delenv("GATEWAY_API_KEY")
    monkeypatch.setenv(name, SECONDARY)
    credentials[0]["id"] = SECONDARY
    credentials[0]["output"][1]["content"][0]["text"] = json.dumps({
        "action": 1, "public_explanation": SECONDARY,
    })
    a = agent()
    result = a.act(_request())
    assert a.last_receipt.get("provider_response_id") is None
    assert result.public_explanation == "[REDACTED]"
    assert_private_values_absent(result.to_dict())


def test_credential_context_is_isolated_and_reset_after_each_invocation():
    barrier = Barrier(2)

    def scoped(own, other):
        with xai.credential_scope(own):
            barrier.wait(timeout=5)
            assert _http_error_identifier(own) is None
            assert _http_error_identifier(other) == other
        assert _http_error_identifier(own) == own

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(scoped, "opaque_thread_a", "opaque_thread_b"),
                   pool.submit(scoped, "opaque_thread_b", "opaque_thread_a")]
        for future in futures:
            future.result(timeout=10)
