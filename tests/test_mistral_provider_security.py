"""Provider-specific rejection and known-credential echo regressions."""

import json
import traceback
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from test_mistral_provider import KEY, MODEL, _agent, _post, _success
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator, read_member
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight

PRIMARY = "opaquePrimaryMistralCredential9"
SECONDARY = "opaqueSecondaryGatewayCredential8"


@pytest.mark.parametrize("model", [None, "", " ", "\t\n", 42, [], {}])
def test_missing_or_blank_requested_ids_fail_at_construction_and_preflight(monkeypatch, model):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    with pytest.raises(ProviderCallError, match="explicit model ID") as error:
        ModelProviderAgent("mistral", model, KEY)
    assert error.value.error_kind == "provider_request_rejected"
    for live in (False, True):
        result = provider_preflight("mistral", model, "tic-tac-toe", live=live)
        assert result["ok"] is False and not result["readiness"]["configuration_ready"]
        assert result["error"]["error_class"] == "provider_request_rejected"
        assert not result["checks"]["minimal_inference"]


@pytest.mark.parametrize("returned", [
    None, "", " ", 12, [], {}, "other-model", "mistral-small-2603",
])
def test_missing_blank_or_conflicting_returned_model_fails_without_parsing_actions(
    monkeypatch, returned,
):
    payload = _success()
    payload["model"] = returned
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    expected = ("provider_request_rejected" if isinstance(returned, str) and returned.strip()
                else "provider_response_schema_mismatch")
    assert failure.value.error_kind == expected and len(calls) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert agent.last_receipt["locked_model_id"] == (
        returned if isinstance(returned, str) and returned.strip() else None
    )


def test_absent_returned_model_is_unknown_and_rejected_without_synthesizing_identity(monkeypatch):
    payload = _success()
    payload.pop("model")
    _post(monkeypatch, httpx.Response(200, json=payload))
    agent = _agent()
    with pytest.raises(ProviderCallError, match="nonblank model identity"):
        agent.act(_request())
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["model_identity_source"] is None
    assert agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
def test_credential_contaminated_returned_model_is_redacted_and_rejected(monkeypatch, secret):
    payload = _success()
    payload["model"] = f"wrong-model-{secret}"
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert len(calls) == 1 and failure.value.error_kind == "provider_request_rejected"
    assert agent.last_receipt["locked_model_id"] is None
    assert agent.last_receipt["model_identity_source"] is None
    _assert_scrubbed(agent.attempt_receipts)
    _assert_scrubbed(failure.value.__dict__)


@pytest.mark.parametrize("value", ["mistral", "mistral-ai", "mistral:", "mistral-ai:  "])
def test_cli_requires_an_explicit_nonblank_model(monkeypatch, capsys, value):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    with pytest.raises(ValueError, match="explicit model ID"):
        _provider_agent(value)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", value]) == 1
    assert "explicit model ID" in capsys.readouterr().err


@pytest.mark.parametrize("field,value", [
    ("reasoning_budget_tokens", 0), ("reasoning_budget_tokens", 1),
    ("reasoning_budget_tokens", 1024), ("gemini_thinking_budget", -1),
    ("gemini_thinking_budget", 0), ("gemini_thinking_budget", 1024),
])
def test_unsupported_budgets_fail_before_credentials_discovery_or_transport(
    monkeypatch, field, value,
):
    monkeypatch.delenv(KEY, raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    runtime = ProviderRuntimeConfig(**{field: value})
    agent = _agent(runtime_config=runtime)
    with pytest.raises(ProviderCallError, match="reasoning budgets") as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert agent.last_receipt is None and agent.attempt_receipts == []
    for live in (False, True):
        result = provider_preflight("mistral_ai", MODEL, "tic-tac-toe",
                                    live=live, runtime_config=runtime)
        assert not result["ok"] and not result["readiness"]["configuration_ready"]
        assert result["error"]["error_class"] == "provider_request_rejected"
        assert "reasoning budgets" in result["error"]["message"]


def _assert_scrubbed(value, secrets=(PRIMARY, SECONDARY)):
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    for secret in secrets:
        assert secret not in rendered
        assert quote(secret, safe="") not in rendered


@pytest.mark.parametrize("custom_primary", [False, True])
@pytest.mark.parametrize("secondary_env", [
    "OPENAI_API_KEY", "SECONDARY_KEY", "GATEWAY_AUTH_TOKEN", "AWS_ACCESS_KEY_ID",
])
def test_primary_and_secondary_ids_are_scrubbed_without_rewriting_clean_actions(
    monkeypatch, custom_primary, secondary_env,
):
    payload = _success()
    payload.update(id=f"cmpl-{PRIMARY}-{SECONDARY}")
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": "safe explanation",
    })
    calls = _post(monkeypatch, httpx.Response(200, json=payload, headers={
        "x-request-id": f"req-{PRIMARY}", "cf-aig-request-id": f"gw-{SECONDARY}",
    }))
    key_env = "CUSTOM_MISTRAL_VALUE" if custom_primary else KEY
    monkeypatch.setenv(key_env, PRIMARY)
    monkeypatch.setenv(secondary_env, SECONDARY)
    agent = ModelProviderAgent("mistral", MODEL, key_env)
    request = replace(_request(), history=[{"turn": i} for i in range(50)])
    response = agent.act(request)
    assert response.action == 1 and response.public_explanation == "safe explanation"
    assert response.metadata["raw_action_text"] == payload["choices"][0]["message"]["content"]
    _assert_scrubbed(json.loads(response.metadata["raw_action_text"]))
    _assert_scrubbed(response.public_explanation)
    _assert_scrubbed(response.to_dict())
    _assert_scrubbed(agent.last_receipt)
    _assert_scrubbed(agent.attempt_receipts)
    for field in ("request_id", "gateway_request_id", "provider_response_id"):
        assert agent.last_receipt[field] is None
    assert agent.last_receipt["locked_model_id"] == MODEL
    assert agent.last_receipt["model_identity_source"] == "provider_response"
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert calls[0][1]["headers"]["Authorization"] == f"Bearer {PRIMARY}"
    prompt = calls[0][1]["json"]["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request.history


@pytest.mark.parametrize("secret", [
    'key-with-"quotes', "key-with-\\slashes", "key/with?punctuation",
])
def test_escaped_credential_echoes_cannot_survive_in_raw_action_text(monkeypatch, secret):
    payload = _success()
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": f"{secret} {quote(secret, safe='')}",
    })
    _post(monkeypatch, httpx.Response(200, json=payload))
    monkeypatch.setenv(KEY, secret)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    _assert_scrubbed(failure.value.__dict__, (secret,))
    assert agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("valid_json", [False, True])
def test_invalid_action_text_does_not_leak_either_credential_or_trigger_retry(
    monkeypatch, valid_json,
):
    payload = _success()
    payload["choices"][0]["message"]["content"] = (
        json.dumps({"action": PRIMARY, "public_explanation": SECONDARY}) if valid_json
        else f"not JSON: {PRIMARY} {SECONDARY}"
    )
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected" and len(calls) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    _assert_scrubbed(agent.attempt_receipts)
    _assert_scrubbed(failure.value.__dict__)
    _assert_scrubbed("".join(traceback.format_exception(failure.value)))
    assert failure.value.__context__ is None and failure.value.__cause__ is None


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_discovery_transport_errors_discard_credential_containing_context(monkeypatch, error_type):
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)

    def get(*a, **k):
        raise error_type(f"echo {PRIMARY} {SECONDARY}")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("mistral")
    assert failure.value.__context__ is None and failure.value.__cause__ is None
    _assert_scrubbed(failure.value.__dict__)
    _assert_scrubbed("".join(traceback.format_exception(failure.value)))


@pytest.mark.parametrize("scenario", ["malformed", "truncated", "http200_error", "429", "503"])
def test_failure_ids_errors_and_quarantined_work_scrub_both_credentials_without_replay(
    monkeypatch, scenario,
):
    payload = _success()
    payload["id"] = f"observed-{PRIMARY}-{SECONDARY}"
    payload["choices"][0]["message"]["content"] = SECONDARY
    code = 200
    if scenario == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    else:
        payload["error"] = {"code": 429, "message": f"{PRIMARY} {SECONDARY}"}
    if scenario.isdigit():
        code = int(scenario)
    response = httpx.Response(code, json=payload, headers={
        "x-request-id": f"req-{PRIMARY}", "x-gateway-request-id": f"gw-{SECONDARY}",
    })
    if scenario == "malformed":
        response = httpx.Response(200, content=b'{"echo":"' + SECONDARY.encode(), headers={
            "x-request-id": PRIMARY, "cf-aig-request-id": SECONDARY,
        })
    calls = _post(monkeypatch, response)
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as error:
        agent.act(_request())
    assert len(calls) == 1
    _assert_scrubbed(error.value.__dict__)
    _assert_scrubbed(str(error.value))
    _assert_scrubbed(agent.attempt_receipts)
    _assert_scrubbed("".join(traceback.format_exception(error.value)))
    assert error.value.__context__ is None and error.value.__cause__ is None
    if scenario != "malformed":
        assert agent.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("kind", ["partial_timeout", "partial_protocol", "timeout", "connect"])
def test_transport_errors_and_partial_header_observations_do_not_retain_credentials(
    monkeypatch, kind,
):
    error_type = ProtocolError if kind == "partial_protocol" else (
        httpx.ConnectError if kind == "connect" else httpx.ReadTimeout
    )
    error = error_type(f"echo {PRIMARY} {SECONDARY}")
    if kind.startswith("partial_"):
        error.__dict__["_eslams_response_observation"] = ResponseObservation(
            200, (("x-request-id", PRIMARY), ("cf-aig-request-id", SECONDARY)),
        )
    calls = _post(monkeypatch, error)
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        agent.act(_request())
    assert len(calls) == 1
    _assert_scrubbed(failure.value.__dict__)
    _assert_scrubbed("".join(traceback.format_exception(failure.value)))
    assert failure.value.__context__ is None and failure.value.__cause__ is None
    _assert_scrubbed(agent.attempt_receipts)


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
def test_discovery_rejects_credential_contaminated_model_ids(monkeypatch, secret):
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": f"model-{secret}"}]},
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("mistral")
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    _assert_scrubbed(str(failure.value))


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
def test_discovery_retains_credential_redaction_across_environment_rotation(monkeypatch, secret):
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)

    def get(*a, **k):
        assert k["headers"]["Authorization"] == f"Bearer {PRIMARY}"
        monkeypatch.setenv(KEY, "rotatedPrimaryValue")
        monkeypatch.setenv("SECONDARY_API_KEY", "rotatedSecondaryValue")
        return httpx.Response(200, json={"data": [{"id": secret}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("mistral")
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    _assert_scrubbed(failure.value.__dict__)


@pytest.mark.parametrize("code", [200, 401, 429, 503])
def test_discovery_diagnostics_never_echo_credentials_from_malformed_or_error_bodies(
    monkeypatch, code,
):
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        code, content=f'{{"echo":"{PRIMARY} {SECONDARY}'.encode(), headers={
            "x-request-id": PRIMARY, "cf-aig-request-id": SECONDARY,
        },
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("mistral")
    _assert_scrubbed(failure.value.__dict__)
    _assert_scrubbed("".join(traceback.format_exception(failure.value)))


def test_definitive_rejection_keeps_explicit_safe_retry_after_credential_scrubbing(monkeypatch):
    calls = _post(monkeypatch, httpx.Response(429, json={"error": {
        "code": 429, "message": f"echo {PRIMARY} {SECONDARY}",
    }}, headers={"Retry-After": "0"}))
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(calls) == 2
    assert [r["attempt_index"] for r in agent.attempt_receipts] == [1, 2]
    _assert_scrubbed(agent.attempt_receipts)


def test_live_preflight_and_cli_discovery_do_not_expose_either_credential(monkeypatch, capsys):
    payload = _success()
    payload["id"] = PRIMARY
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": f"{PRIMARY} {SECONDARY}",
    })
    _post(monkeypatch, httpx.Response(200, json=payload, headers={"x-request-id": SECONDARY}))
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": PRIMARY}]},
    ))
    assert main(["providers", "models", "--provider", "mistral", "--live"]) == 1
    _assert_scrubbed(json.loads(capsys.readouterr().out))
    result = provider_preflight("mistral", MODEL, "tic-tac-toe", live=True)
    assert not result["ok"] and result["checks"]["account_model_visible"] is None
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert result["discovery_error"]["error_class"] == "provider_response_schema_mismatch"
    _assert_scrubbed(result)


def test_conflicting_identity_produces_a_valid_failure_artifact_and_no_scoring_valid_run(
    monkeypatch, tmp_path, capsys,
):
    payload = _success()
    payload["model"] = "unexpected-model"
    _post(monkeypatch, httpx.Response(200, json=payload))
    main(["run", "--arena", "tic-tac-toe", "--agent", f"mistral:{MODEL}",
          "--opponent", "first-legal", "--max-turns", "1", "--output-dir", str(tmp_path)])
    result = json.loads(capsys.readouterr().out)
    artifact = Path(result["artifact"])
    assert ArtifactValidator().validate_report(artifact).valid
    assert not result["score"]["match_valid_for_scoring"]
    receipts = [json.loads(line) for line in
                read_member(artifact, "receipts/provider_receipts.jsonl").decode().splitlines()]
    assert len(receipts) == 1
    assert receipts[0]["outcome"] == "provider_request_rejected"
    assert receipts[0]["locked_model_id"] == "unexpected-model"
    assert receipts[0]["usage"]["total_tokens"] == 16


def test_public_key_ids_and_short_secondary_secrets_do_not_corrupt_receipt_contracts(monkeypatch):
    payload = _success()
    payload["id"] = "response-stop"
    _post(monkeypatch, httpx.Response(200, json=payload))
    monkeypatch.setenv("ESLAMS_RUNNER_REQUEST_KEY_ID", "1")
    monkeypatch.setenv("SECONDARY_PASSWORD", "stop")
    agent = _agent()
    response = agent.act(_request())
    assert response.action == 1
    assert agent.last_receipt["provider_response_id"] is None
    assert agent.last_receipt["provider"] == "mistral-ai"
    assert agent.last_receipt["parser_version"] == "mistral-chat-completions-raw-v1"
    assert agent.last_receipt["finish_reason"] == "stop"
    assert agent.last_receipt["outcome"] == "ok"
