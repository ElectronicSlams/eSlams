"""Independent cross-provider privacy/admission review for the Krutrim draft."""

import json
import traceback
from dataclasses import replace

import httpx
import pytest
from test_krutrim_provider import MODEL, agent, install, request, wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers.krutrim import API_KEY_ENV

KEYS = ("opaquePrimaryKrutrimCredential123", "opaqueSecondaryKrutrimCredential456",
        "opaqueCustomKrutrimCredential789")
CUSTOM_ENV = "CUSTOM_KRUTRIM_AUTH"


@pytest.fixture(autouse=True)
def configured_keys(monkeypatch):
    for name, value in zip((API_KEY_ENV, "KRUTRIM_API_KEY", CUSTOM_ENV), KEYS, strict=True):
        monkeypatch.setenv(name, value)


def native():
    value = agent()
    value.api_key_env = CUSTOM_ENV
    return value


def assert_clean(*values):
    serialized = json.dumps(values, default=str)
    assert all(key not in serialized for key in KEYS)


@pytest.mark.parametrize("secret", KEYS)
def test_all_configured_credentials_are_removed_from_success_ids(monkeypatch, secret):
    payload = wire()
    payload.update(id=secret, model="prefix-" + secret)
    install(monkeypatch, payload, headers={"x-request-id": secret,
                                           "x-gateway-request-id": secret})
    value = native()
    response = value.act(request())
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None and receipt["request_id"] is None
    assert receipt["gateway_request_id"] is None
    assert_clean(response.to_dict(), value.last_receipt, value.attempt_receipts)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 503])
def test_secondary_echo_in_http_errors_is_scrubbed_without_replay(monkeypatch, status):
    secret = KEYS[1]
    calls = install(monkeypatch, {"error": {"id": secret, "message": secret,
        "code": "rate_limit_exceeded", "metadata": {"id": secret}}}, status=status,
        headers={"request-id": secret, "x-gateway-request-id": secret})
    value = native()
    value.runtime_config = ProviderRuntimeConfig(max_retries=3, retry_backoff_ms=0)
    with pytest.raises(ProviderCallError) as caught:
        value.act(request())
    assert len(calls) == 1 and caught.value.retry_permitted is False
    assert value.last_receipt["request_id"] is None
    assert_clean(caught.value.receipt, str(caught.value),
                 value.last_receipt, value.attempt_receipts)


def test_secondary_echo_in_malformed_body_and_headers_is_scrubbed(monkeypatch):
    secret = KEYS[1]
    install(monkeypatch, content=('{"private":"' + secret).encode(),
            headers={"x-request-id": secret, "x-gateway-request-id": secret})
    value = native()
    with pytest.raises(ProviderCallError) as caught:
        value.act(request())
    assert value.last_receipt["request_id"] is None
    assert_clean(str(caught.value), caught.value.receipt, value.attempt_receipts)


@pytest.mark.parametrize("failure_type", [ProtocolError, httpx.ReadError, httpx.ReadTimeout])
@pytest.mark.parametrize("partial", [False, True])
def test_secondary_echo_in_partial_response_and_errors_is_scrubbed(
    monkeypatch, failure_type, partial,
):
    secret = KEYS[1]
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        failure = failure_type(secret)
        if partial:
            failure._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", secret), ("x-gateway-request-id", secret)))
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    value = native()
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        value.act(request())
    assert len(calls) == 1
    assert value.last_receipt["request_id"] is None
    assert value.last_receipt["status_code"] == (200 if partial else None)
    assert_clean(str(caught.value), getattr(caught.value, "receipt", None),
                 traceback.format_exception(caught.value), value.attempt_receipts)


@pytest.mark.parametrize("secret", KEYS)
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("field", ["action", "public_explanation", "unused"])
def test_credentials_cannot_enter_any_action_text_field(monkeypatch, secret, encoded, field):
    payload = wire()
    text = json.dumps({"action": 1, field: secret})
    if encoded:
        text = text.replace(secret, "".join(f"\\u{ord(char):04x}" for char in secret))
    payload["choices"][0]["message"]["content"] = text
    install(monkeypatch, payload)
    value = native()
    current = request()
    if field == "action":
        current = replace(current, legal_actions=[secret], action_schema={"type": "string"})
    with pytest.raises(ProviderCallError) as caught:
        value.act(current)
    assert_clean(str(caught.value), caught.value.receipt, value.attempt_receipts)


def test_credential_snapshot_survives_secondary_key_rotation_during_transport(monkeypatch):
    secret = KEYS[1]

    def post(url, **kwargs):
        monkeypatch.delenv("KRUTRIM_API_KEY")
        payload = wire()
        payload["id"] = secret
        payload["model"] = secret
        return httpx.Response(200, json=payload, headers={"x-request-id": secret})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    value = native()
    response = value.act(request())
    assert response.metadata["provider_receipt"]["locked_model_id"] is None
    assert_clean(response.to_dict(), value.attempt_receipts)


def test_no_discovery_endpoint_is_guessed_or_credential_bearing_response_exposed(monkeypatch):
    def network(*args, **kwargs):
        pytest.fail("Krutrim has no verified Models API")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", network)
    assert provider_models_live("krutrim") is None
    result = provider_models_result("krutrim")
    assert result["ok"] is False and result["models"] == []
    assert result["error"]["error_class"] == "provider_discovery_unavailable"
    assert_clean(result)


@pytest.mark.parametrize("model", [None, "", " ", "\t\n"])
@pytest.mark.parametrize("live", [False, True])
def test_blank_models_fail_before_preflight_can_call_transport(monkeypatch, model, live):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    with pytest.raises(ValueError, match="nonblank model"):
        provider_preflight("krutrim", model, "tic-tac-toe", live=live)
    value = native()
    value.model = model
    with pytest.raises(ValueError, match="nonblank model"):
        value._call_provider(KEYS[2], "public request")
    with pytest.raises(ValueError, match="nonblank model"):
        value.act(request())


@pytest.mark.parametrize("config", [{"reasoning_budget_tokens": 0},
    {"reasoning_budget_tokens": 1024}, {"gemini_thinking_budget": 0},
    {"reasoning_effort": "high"}, {"reasoning": "enabled"}, {"reasoning": "disabled"}])
@pytest.mark.parametrize("live", [False, True])
def test_reasoning_controls_fail_in_preflight_and_before_transport(monkeypatch, config, live):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    runtime = ProviderRuntimeConfig(**config)
    with pytest.raises(ValueError, match="reasoning"):
        provider_preflight("krutrim", MODEL, "tic-tac-toe", runtime_config=runtime, live=live)
    value = native()
    value.runtime_config = runtime
    with pytest.raises(ValueError, match="reasoning"):
        value._call_provider(KEYS[2], "public request")
    with pytest.raises(ValueError, match="reasoning"):
        value.act(request())
