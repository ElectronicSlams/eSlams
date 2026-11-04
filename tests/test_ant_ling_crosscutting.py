"""Cross-provider review regressions for the native Ant Ling boundary."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from test_ant_ling_adapter import SECRET, _agent, _respond, _wire
from test_model_agents import _request

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight

SECONDARY = "fixture-secondary-ant-credential"


@pytest.mark.parametrize("provider", ["ant-group", "bailing", "ANT_GROUP", " ant-group "])
@pytest.mark.parametrize("model", [None, "", " \t"])
@pytest.mark.parametrize("live", [False, True])
def test_missing_model_fails_preflight_before_network(monkeypatch, provider, model, live):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", _no_transport)
    monkeypatch.setattr("eslams.agents.bounded_post", _no_transport)
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight(provider, model, "tic-tac-toe", live=live)


def _no_transport(*args, **kwargs):
    pytest.fail("invalid config or undocumented discovery must not reach transport")


@pytest.mark.parametrize("provider", ["ant-group", "bailing", "ant_group", " ant-group "])
@pytest.mark.parametrize("controls", [
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 4096},
    {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 0},
    {"reasoning_effort": "high"},
])
@pytest.mark.parametrize("live", [False, True])
def test_reasoning_controls_fail_preflight(monkeypatch, provider, controls, live):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", _no_transport)
    monkeypatch.setattr("eslams.agents.bounded_post", _no_transport)
    with pytest.raises(ValueError, match="thinking.type"):
        provider_preflight(provider, "Ling-3.1-flash", "tic-tac-toe", live=live,
                           runtime_config=ProviderRuntimeConfig(**controls))


@pytest.mark.parametrize("controls", [
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 4096},
    {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 0},
])
def test_changed_runtime_is_revalidated_before_transport(monkeypatch, controls):
    _respond(monkeypatch, _wire())
    monkeypatch.setattr("eslams.agents.bounded_post", _no_transport)
    agent = _agent()
    agent.runtime_config = ProviderRuntimeConfig(**controls)
    with pytest.raises(ValueError, match="thinking.type"):
        agent.act(_request())


@pytest.mark.parametrize("environment", ["ANT_LING_API_KEY", "BAILING_API_KEY", "OPENAI_API_KEY"])
@pytest.mark.parametrize("field", ["id", "x-request-id", "cf-aig-request-id"])
def test_secondary_identifier_echo_is_removed(monkeypatch, environment, field):
    data = _wire()
    headers = {}
    if field == "id":
        data[field] = SECONDARY
    else:
        headers[field] = SECONDARY
    calls = _respond(monkeypatch, data, headers=headers)
    # A custom selected credential proves that the native name is also scrubbed
    # when it is secondary. None of these aliases selects fallback authentication.
    monkeypatch.setenv(environment, SECONDARY)
    monkeypatch.setenv("ANT_LING_SELECTED_TEST_KEY", SECRET)
    agent = _agent()
    agent.api_key_env = "ANT_LING_SELECTED_TEST_KEY"
    result = agent.act(_request())
    assert calls[0][1]["headers"]["Authorization"] == f"Bearer {SECRET}"
    for secret in (SECRET, SECONDARY):
        assert secret not in json.dumps(result.to_dict())
        assert secret not in json.dumps(agent.attempt_receipts)


@pytest.mark.parametrize("status", [200, 400, 401, 403, 429, 500])
def test_secondary_credential_in_http_error_is_removed(monkeypatch, status):
    calls = _respond(monkeypatch, {"error": {"code": status, "id": SECONDARY,
                                          "message": SECONDARY}}, status=status,
                     headers={"x-request-id": SECONDARY, "cf-aig-request-id": SECONDARY})
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert len(calls) == 1
    assert SECONDARY not in json.dumps(agent.attempt_receipts)
    assert SECONDARY not in json.dumps(failure.value.receipt)
    assert SECONDARY not in str(failure.value)


@pytest.mark.parametrize("content", [b"not-json", b'{"choices":', b"[]"])
def test_secondary_credential_in_malformed_response_headers_is_removed(monkeypatch, content):
    _respond(monkeypatch, content=content, headers={"x-request-id": SECONDARY})
    monkeypatch.setenv("OPENAI_API_KEY", SECONDARY)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert SECONDARY not in json.dumps(agent.attempt_receipts)
    assert SECONDARY not in json.dumps(failure.value.receipt)


@pytest.mark.parametrize("exception", [httpx.ReadError, httpx.ReadTimeout])
def test_secondary_credential_in_partial_response_is_removed(monkeypatch, exception):
    _respond(monkeypatch, _wire())
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        error = exception(SECONDARY)
        error._eslams_response_observation = ResponseObservation(
            status_code=200,
            headers=(("x-request-id", SECONDARY), ("cf-aig-request-id", SECRET)),
        )
        raise error

    monkeypatch.setattr("eslams.agents.bounded_post", fail)
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert len(calls) == 1
    for secret in (SECRET, SECONDARY):
        assert secret not in json.dumps(agent.attempt_receipts)
        assert secret not in json.dumps(failure.value.receipt)
        assert secret not in str(failure.value)


@pytest.mark.parametrize("escaped", [False, True])
@pytest.mark.parametrize("field", ["action", "public_explanation"])
def test_secondary_action_echo_is_rejected(monkeypatch, escaped, field):
    data = _wire()
    secret = ("".join(f"\\u{ord(character):04x}" for character in SECONDARY)
              if escaped else SECONDARY)
    text = ('{"action":"' + secret + '"}' if field == "action" else
            '{"action":1,"public_explanation":"' + secret + '"}')
    data["choices"][0]["message"]["content"] = text
    _respond(monkeypatch, data)
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert SECONDARY not in json.dumps(agent.attempt_receipts)


def test_percent_encoded_secondary_credential_is_rejected(monkeypatch):
    secret = "fixture-secondary-ant+/="
    data = _wire()
    data["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": quote(secret, safe=""),
    })
    _respond(monkeypatch, data)
    monkeypatch.setenv("BAILING_API_KEY", secret)
    with pytest.raises(ProviderCallError):
        _agent().act(_request())


def test_discovery_is_keyless_and_does_not_create_an_echo_surface(monkeypatch):
    monkeypatch.setenv("ANT_LING_API_KEY", SECRET)
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", _no_transport)
    for provider in ("ant-group", "bailing", "ANT_GROUP"):
        assert provider_models_live(provider) is None
        result = provider_preflight(provider, "Ling-3.1-flash", "tic-tac-toe")
        assert result["checks"]["account_model_visible"] is None
        for secret in (SECRET, SECONDARY):
            assert secret not in json.dumps(result)


@pytest.mark.parametrize("model", [None, "", " \t"])
def test_changed_model_is_revalidated_before_transport(monkeypatch, model):
    _respond(monkeypatch, _wire())
    monkeypatch.setattr("eslams.agents.bounded_post", _no_transport)
    agent = _agent()
    agent.model = model
    with pytest.raises(ValueError, match="explicit nonblank"):
        agent.act(_request())


def test_secondary_credential_does_not_supply_fallback_authentication(monkeypatch):
    monkeypatch.delenv("ANT_LING_API_KEY", raising=False)
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", _no_transport)
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert agent.last_receipt["usage"] == {}


def test_real_partial_transport_scrubs_both_credentials(monkeypatch):
    monkeypatch.setenv("ANT_LING_API_KEY", SECRET)
    monkeypatch.setenv("BAILING_API_KEY", SECONDARY)
    original = httpx.AsyncClient

    class PartialBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"choices":'
            raise httpx.ReadError(SECONDARY)

    def handle(request):
        return httpx.Response(200, headers={"x-request-id": SECONDARY,
                                           "cf-aig-request-id": SECRET}, stream=PartialBody())

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    agent = _agent()
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    for secret in (SECRET, SECONDARY):
        assert secret not in json.dumps(agent.attempt_receipts)
        assert secret not in json.dumps(failure.value.receipt)
        assert secret not in str(failure.value)


def test_ninety_seconds_is_only_an_upstream_constraint(monkeypatch):
    calls = _respond(monkeypatch, _wire())
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)})
    agent = _agent()
    agent.act(request)
    assert agent.runtime_config.timeout_ms is None
    assert agent.runtime_config.read_timeout_ms is None
    timeout = calls[0][1]["timeout"]
    assert timeout.read is None
    assert getattr(timeout, "deadline", None) is None
    assert "max_tokens" not in calls[0][1]["json"]
    guide = (Path(__file__).parents[1] / "docs/providers/ANT_LING.md").read_text()
    assert "provider-enforced 90-second" in guide
    assert "not a framework timeout setting" in guide
