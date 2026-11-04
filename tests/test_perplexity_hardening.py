"""Cross-cutting regression checks using synthetic credentials only."""

import json
from dataclasses import replace

import httpx
import pytest
from test_model_agents import _request
from test_perplexity_adapter import API_KEY_ENV, MODEL, PRIMARY, SECONDARY, _agent, _safe, _wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.contracts.usage import aggregate_provider_receipts
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers.perplexity import discover_models


def _mixed(value):
    return "".join(f"\\u{ord(char):04x}" if i % 2 else char for i, char in enumerate(value))


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("field", ["public_explanation", "nested", "extra_key"])
def test_mixed_unicode_action_echo_is_rejected_before_shared_decode(monkeypatch, credential, field):
    data = _wire()
    escaped = _mixed(credential)
    text = ('{"action":1,"public_explanation":"' + escaped + '"}' if field == "public_explanation"
            else '{"action":1,"extra":{"value":"' + escaped + '"}}' if field == "nested"
            else '{"action":1,"' + escaped + '":"extra"}')
    assert credential not in text
    data["output"][0]["content"][0]["text"] = text
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch)
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    _safe(agent, failure.value)


@pytest.mark.parametrize("encoded", [False, True])
def test_public_discovery_never_returns_a_credential_as_model_id(monkeypatch, encoded):
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    value = _mixed(SECONDARY) if encoded else SECONDARY
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": MODEL}, {"id": "provider/" + value}]}))
    result = provider_models_result("perplexity")
    assert not result["ok"] and result["models"] == []
    assert result["error"]["error_class"] == "provider_response_schema_mismatch"
    assert SECONDARY not in json.dumps(result) and value not in json.dumps(result)


@pytest.mark.parametrize("usage", [
    {"input_tokens": 100, "output_tokens": 20, "total_tokens": 5},
    {"input_tokens": 100, "output_tokens": 20, "total_tokens": 999},
    {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
     "input_tokens_details": {"cache_read_input_tokens": 101}},
    {"input_tokens": True, "output_tokens": 20, "total_tokens": 120},
])
def test_incoherent_usage_stays_incomplete_in_preflight_and_aggregate(monkeypatch, usage):
    data = _wire()
    data["usage"] = usage
    data["output"][0]["content"][0]["text"] = '{"action":0}'
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": MODEL}]}))
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    result = provider_preflight("perplexity", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["minimal_inference"]
    assert not result["checks"]["usage_extraction"]
    assert not result["readiness"]["usage_complete"]
    assert not result["receipt_shape"]["usage_complete"]
    agent = _agent(monkeypatch)
    agent.act(_request())
    usage_summary, _ = aggregate_provider_receipts([agent.last_receipt])
    assert not usage_summary["usageComplete"]


@pytest.mark.parametrize("model", [None, "", " ", "\t"])
def test_preflight_blank_model_fails_without_network(monkeypatch, model):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("GET"))
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("POST"))
    with pytest.raises(ValueError, match="Perplexity"):
        provider_preflight("perplexity", model, "tic-tac-toe", live=True)


@pytest.mark.parametrize("setting", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_unsupported_budget_fails_preflight_and_even_after_agent_config_replacement(
    monkeypatch, setting,
):
    agent = _agent(monkeypatch)
    agent.runtime_config = replace(ProviderRuntimeConfig(), **{setting: 2048})
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("GET"))
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("POST"))
    with pytest.raises(ValueError, match="budgets"):
        agent.act(_request())
    with pytest.raises(ValueError, match="budgets"):
        provider_preflight("perplexity", MODEL, "tic-tac-toe", live=True,
                           runtime_config=agent.runtime_config)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("mode", ["success", "error", "malformed", "partial"])
def test_id_and_failure_custody_scrubs_primary_and_secondary(
    monkeypatch, credential, encoded, mode,
):
    value = _mixed(credential) if encoded else credential
    headers = {"x-request-id": value, "cf-aig-request-id": value}

    def post(*args, **kwargs):
        if mode == "partial":
            error = ProtocolError(value)
            error.__dict__["_eslams_response_observation"] = ResponseObservation(
                200, tuple(headers.items()))
            raise error
        if mode == "malformed":
            return httpx.Response(200, text='{"id":"' + value, headers=headers)
        if mode == "error":
            return httpx.Response(429, json={"id": value,
                "error": {"type": "rate_limit_error", "message": value}}, headers=headers)
        data = _wire()
        data["id"] = value
        return httpx.Response(200, json=data, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=1))
    if mode == "success":
        response = agent.act(_request())
        assert credential not in json.dumps(response.to_dict())
        assert agent.last_receipt["provider_response_id"] is None
    else:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        _safe(agent, failure.value)
    assert len(agent.attempt_receipts) == 1
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None
    _safe(agent)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("encoded", [False, True])
def test_custom_primary_and_canonical_secondary_discovery_guard(monkeypatch, credential, encoded):
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    value = _mixed(credential) if encoded else credential

    def get(url, *, headers, **kwargs):
        assert headers == {"Accept": "application/json"}  # Public list needs no credential.
        return httpx.Response(200, json={"data": [{"id": MODEL}, {"id": "provider/" + value}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        discover_models(PRIMARY)
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert PRIMARY not in str(failure.value) and SECONDARY not in str(failure.value)


@pytest.mark.parametrize("mode", ["error", "malformed", "duplicate", "partial"])
def test_discovery_errors_never_expose_bodies_or_transport_details(monkeypatch, mode):
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)

    def get(*args, **kwargs):
        if mode == "partial":
            raise httpx.ReadError(_mixed(SECONDARY))
        if mode == "error":
            return httpx.Response(503, text=f"{PRIMARY} {SECONDARY}")
        if mode == "duplicate":
            return httpx.Response(200, text='{"data":[],"data":[{"id":"' + SECONDARY + '"}]}')
        return httpx.Response(200, text=PRIMARY + _mixed(SECONDARY))

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        discover_models(PRIMARY)
    assert PRIMARY not in str(failure.value) and SECONDARY not in str(failure.value)
    assert _mixed(SECONDARY) not in str(failure.value)


@pytest.mark.parametrize("field,value", [
    ("profile", {"id": "server-profile"}), ("models", [MODEL, "other/model"]),
    ("skills", [{"type": "builtin", "name": "office"}]),
    ("previous_response_id", "other-session"), ("tool_choice", "auto"),
])
def test_reflected_tools_or_fallback_configuration_is_rejected(monkeypatch, field, value):
    data = _wire()
    data[field] = value
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    agent = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(agent.attempt_receipts) == 1
