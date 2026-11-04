"""Hostile wire regressions for the independent Sarvam draft review."""

from __future__ import annotations

import json
import traceback

import httpx
import pytest
from test_sarvam_provider import request, wire

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_result, provider_preflight

PRIMARY = "plainprimarycredential987654321"
SECONDARY = "plainsecondarycredential123456789"


def selected(monkeypatch, **kwargs):
    monkeypatch.setenv("CUSTOM_SARVAM_KEY", PRIMARY)
    monkeypatch.setenv("SARVAM_API_KEY", SECONDARY)
    return ModelProviderAgent(
        provider="sarvam", model="sarvam-105b", api_key_env="CUSTOM_SARVAM_KEY", **kwargs,
    )


@pytest.mark.parametrize("model", [None, "", " ", "\t\r\n"])
def test_empty_models_fail_in_constructor_preflight_and_mutated_agent(monkeypatch, model):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached transport")

    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", forbidden)
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent(provider="sarvam", model=model, api_key_env="SARVAM_API_KEY")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        provider_preflight("sarvam", model, "tic-tac-toe", live=True)
    current = selected(monkeypatch)
    current.model = model
    with pytest.raises(ValueError, match="explicit nonblank model"):
        current.act(request())


@pytest.mark.parametrize("prefix", ["sarvam", "sarvam-ai", "sarvam_ai"])
@pytest.mark.parametrize("suffix", ["", ":", ": ", ":\t\r\n"])
def test_cli_never_substitutes_missing_model(prefix, suffix):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(prefix + suffix)


@pytest.mark.parametrize("budget,value", [
    ("reasoning_budget_tokens", 0), ("reasoning_budget_tokens", 2048),
    ("gemini_thinking_budget", -1), ("gemini_thinking_budget", 0),
    ("gemini_thinking_budget", 2048),
])
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("prefix", ["sarvam", "sarvam-ai", "sarvam_ai"])
def test_unsupported_controls_fail_preflight_before_discovery_and_inference(
    monkeypatch, budget, value, live, prefix,
):
    def forbidden(*args, **kwargs):
        pytest.fail("unsupported control reached transport")

    monkeypatch.setattr("eslams.agents.bounded_post", forbidden)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", forbidden)
    runtime = ProviderRuntimeConfig(**{budget: value})
    report = provider_preflight(prefix, "sarvam-105b", "tic-tac-toe", live=live,
                                runtime_config=runtime)
    assert report["ok"] is False
    assert report["readiness"]["configuration_ready"] is False
    assert report["checks"]["minimal_inference"] is False
    assert report["error"]["error_class"] == "provider_request_rejected"
    current = selected(monkeypatch, runtime_config=runtime)
    with pytest.raises(ProviderCallError, match="thinking budget"):
        current.act(request())


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("case", ["success", "http-error", "body-error", "malformed", "partial"])
def test_credentials_never_escape_identifiers_or_error_receipts(monkeypatch, credential, case):
    current = selected(monkeypatch)
    payload = wire()
    payload.update(id=f"completion-{credential}", model=f"model-{credential}")
    headers = {"x-request-id": f"request-{credential}",
               "cf-aig-request-id": f"gateway-{credential}"}

    def post(url, **kwargs):
        assert kwargs["headers"]["api-subscription-key"] == PRIMARY
        if case == "partial":
            exc = httpx.ReadTimeout(f"partial response {credential}")
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                status_code=200, headers=tuple(headers.items()),
            )
            raise exc
        if case == "malformed":
            return httpx.Response(200, content=f"broken {credential}".encode(), headers=headers)
        if case in {"http-error", "body-error"}:
            payload["error"] = {"code": "invalid_request_error", "message": credential}
            return httpx.Response(400 if case == "http-error" else 200,
                                  json=payload, headers=headers)
        return httpx.Response(200, json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    if case == "success":
        result = current.act(request())
        assert result.action == 1
        assert current.last_receipt["locked_model_id"] is None
        assert current.last_receipt["model_identity_source"] is None
        public = json.dumps(result.to_dict())
    else:
        with pytest.raises(ProviderCallError) as caught:
            current.act(request())
        public = str(caught.value) + "".join(traceback.format_exception(caught.value))
        assert caught.value.__cause__ is None
    receipt = current.last_receipt
    assert receipt["request_id"] is None
    assert receipt["gateway_request_id"] is None
    assert receipt.get("provider_response_id") is None
    public += json.dumps(current.attempt_receipts)
    assert PRIMARY not in public
    assert SECONDARY not in public


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("fault", ["timeout", "connect", "protocol"])
def test_transport_error_strings_and_causes_are_scrubbed(monkeypatch, credential, fault):
    current = selected(monkeypatch)

    def post(url, **kwargs):
        if fault == "timeout":
            raise httpx.ReadTimeout(credential)
        if fault == "connect":
            raise httpx.ConnectError(credential)
        # Redaction must precede the shared error string's 500-character cap.
        raise ProtocolError("x" * 490 + credential)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        current.act(request())
    public = (
        "".join(traceback.format_exception(caught.value)) + json.dumps(current.attempt_receipts)
    )
    assert credential not in public
    assert credential[:12] not in public
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("case", ["explanation", "prefix", "json-escaped"])
def test_credential_action_text_is_rejected_before_parsing_or_repair(monkeypatch, credential, case):
    current = selected(monkeypatch, runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    payload = wire()
    content = json.dumps({"action": 1, "public_explanation": credential})
    if case == "prefix":
        content = credential + ' {"action": 1}'
    elif case == "json-escaped":
        escaped = "".join(f"\\u{ord(character):04x}" for character in credential)
        content = '{"action": 1, "public_explanation": "' + escaped + '"}'
    payload["choices"][0]["message"]["content"] = content
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    with pytest.raises(ProviderCallError, match="configured credential") as caught:
        current.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    assert current.last_receipt["usage"]["total_tokens"] == 16
    public = str(caught.value) + json.dumps(current.attempt_receipts)
    assert PRIMARY not in public and SECONDARY not in public


def test_discovery_has_no_network_or_credential_echo_surface(monkeypatch):
    selected(monkeypatch)

    def forbidden(*args, **kwargs):
        pytest.fail("V1 adapter has no discovery request")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", forbidden)
    report = provider_models_result("sarvam")
    assert report["ok"] is False
    assert report["error"]["error_class"] == "provider_discovery_unavailable"
    public = json.dumps(report)
    assert PRIMARY not in public and SECONDARY not in public


def test_redaction_scope_is_reset_between_calls(monkeypatch):
    current = selected(monkeypatch)
    payload = wire()
    payload["id"] = PRIMARY

    def post(url, **kwargs):
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert current.act(request()).metadata["provider_receipt"]["provider_response_id"] is None
    monkeypatch.setenv("CUSTOM_SARVAM_KEY", "differentprimarycredential")
    assert current.act(request()).metadata["provider_receipt"]["provider_response_id"] == PRIMARY
