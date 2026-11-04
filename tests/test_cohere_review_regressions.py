"""Provider-specific regression checks from the 0.7.1 adapter review."""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
from test_cohere_provider import agent, fixture, offline, wire  # noqa: F401
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers import cohere


@pytest.mark.parametrize("model", [None, "", " ", "\t\r\n", False, 0])
def test_missing_or_blank_model_fails_construction_and_preflight(model):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent("cohere-ai", model, "COHERE_API_KEY")
    for live in (False, True):
        with pytest.raises(ValueError, match="explicit nonblank model"):
            provider_preflight("cohere-ai", model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("value", ["cohere", "cohere:", "cohere:   ", "cohere-ai", "COHERE_AI:"])
def test_cli_does_not_select_a_model_when_one_is_missing(value, capsys, tmp_path):
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent(value)
    assert main(["run", "--agent", value, "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank model" in capsys.readouterr().err


@pytest.mark.parametrize("model", ["command-a-03-2025", "unknown-model"])
@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning_budget_tokens=500),
    ProviderRuntimeConfig(reasoning="enabled"),
    ProviderRuntimeConfig(reasoning="disabled"),
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(gemini_thinking_budget=500),
])
def test_unsupported_thinking_fails_preflight_and_before_transport(model, config):
    for live in (False, True):
        result = provider_preflight("cohere-ai", model, "tic-tac-toe", live=live,
                                    runtime_config=config)
        assert result["ok"] is False
        assert result["readiness"]["configuration_ready"] is False
        assert result["readiness"]["inference"] == "not_attempted"
        assert result["error"]["error_class"] == "provider_request_rejected"
    selected = agent(model=model, runtime_config=config)
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert len(selected.attempt_receipts) == 1


@pytest.mark.parametrize("model", sorted(cohere.THINKING_MODELS))
def test_verified_native_budget_is_consistent_in_preflight_and_execution(monkeypatch, model):
    config = ProviderRuntimeConfig(reasoning_budget_tokens=500)
    result = provider_preflight("cohere", model, "tic-tac-toe", runtime_config=config)
    assert result["ok"] and result["readiness"]["configuration_ready"]
    calls = wire(monkeypatch)
    assert agent(model=model, runtime_config=config).act(_request()).action == 1
    assert calls[0][1]["json"]["thinking"] == {"type": "enabled", "token_budget": 500}


@pytest.mark.parametrize("model", sorted(cohere.THINKING_MODELS))
def test_zero_budget_fails_both_preflight_modes_and_transport(model):
    config = ProviderRuntimeConfig(reasoning_budget_tokens=0)
    for live in (False, True):
        assert not provider_preflight("cohere", model, "tic-tac-toe", live=live,
                                      runtime_config=config)["ok"]
    with pytest.raises(ProviderCallError):
        agent(model=model, runtime_config=config).act(_request())


@pytest.fixture
def credentials(monkeypatch):
    values = ("fixture-cohere-key", "sdk-secondary-credential", "custom-agent-credential")
    for name, value in zip(("COHERE_API_KEY", "CO_API_KEY", "CUSTOM_COHERE_KEY"), values,
                           strict=True):
        monkeypatch.setenv(name, value)
    return values


def custom_agent():
    return ModelProviderAgent("cohere", "command-a-03-2025", "CUSTOM_COHERE_KEY",
                              runtime_config=ProviderRuntimeConfig(max_retries=2))


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("status", [200, 401, 429, 503])
def test_all_known_credentials_are_removed_from_ids_and_errors(monkeypatch, credentials, index,
                                                              status):
    value = credentials[index]
    payload = fixture()
    payload["id"] = f"prefix-{value}"
    if status != 200:
        payload["message"] = f"provider echoed {value}"
    calls = wire(monkeypatch, payload, status=status, headers={
        "x-request-id": value, "cf-aig-request-id": value,
    })
    selected = custom_agent()
    if status == 200:
        result = selected.act(_request()).to_dict()
    else:
        with pytest.raises(ProviderCallError) as failure:
            selected.act(_request())
        result = str(failure.value)
    serialized = json.dumps([result, selected.last_receipt, selected.attempt_receipts])
    assert all(credential not in serialized for credential in credentials)
    assert len(calls) == 1
    assert selected.last_receipt["provider_response_id"] is None
    assert selected.last_receipt["request_id"] is None
    assert selected.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("kind", ["malformed", "partial", "timeout", "transport"])
def test_all_credentials_are_removed_from_failed_response_paths(monkeypatch, credentials, index,
                                                                kind):
    value = credentials[index]
    if kind == "malformed":
        wire(monkeypatch, content=f'{{"broken":"{value}', headers={"x-request-id": value})
    else:
        def post(*args, **kwargs):
            if kind == "partial":
                error = ProtocolError(f"private partial response {value}")
            elif kind == "timeout":
                error = httpx.ReadTimeout(f"private timeout {value}")
            else:
                error = httpx.ConnectError(f"private transport {value}")
            error._eslams_response_observation = ResponseObservation(
                status_code=200, headers=(("x-request-id", value), ("cf-aig-request-id", value)),
            )
            raise error
        monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = custom_agent()
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        selected.act(_request())
    serialized = str(failure.value) + json.dumps(selected.attempt_receipts)
    assert all(credential not in serialized for credential in credentials)
    assert len(selected.attempt_receipts) == 1


def test_all_credentials_are_scrubbed_before_action_parsing_and_metadata(monkeypatch, credentials):
    payload = fixture()
    payload["message"]["content"][0]["text"] = json.dumps({
        "action": 1, "public_explanation": " ".join(credentials),
    })
    wire(monkeypatch, payload)
    selected = custom_agent()
    result = selected.act(_request())
    assert result.action == 1
    serialized = json.dumps([result.to_dict(), selected.attempt_receipts])
    assert all(credential not in serialized for credential in credentials)
    assert result.public_explanation == "[REDACTED] [REDACTED] [REDACTED]"


def test_json_escaped_and_url_encoded_secondary_keys_are_scrubbed(monkeypatch):
    secondary = 'sdk-quote"slash\\credential'
    monkeypatch.setenv("CO_API_KEY", secondary)
    payload = fixture()
    payload["message"]["content"][0]["text"] = json.dumps({
        "action": 1, "public_explanation": secondary + " " + quote(secondary, safe=""),
    })
    wire(monkeypatch, payload)
    result = agent().act(_request()).to_dict()
    assert "credential" not in json.dumps(result)
    assert result["public_explanation"] == "[REDACTED] [REDACTED]"


@pytest.mark.parametrize("field", ["name", "cursor", "error", "malformed", "transport"])
@pytest.mark.parametrize("index", [0, 1])
def test_discovery_does_not_publish_primary_or_sdk_secondary_credentials(monkeypatch, credentials,
                                                                      field, index):
    value = credentials[index]

    def get(*args, **kwargs):
        if field == "transport":
            raise httpx.ConnectError(value)
        if field == "malformed":
            return httpx.Response(200, content=f'{{"models":"{value}')
        if field == "error":
            return httpx.Response(401, json={"message": value})
        data = {"models": [{"name": value if field == "name" else "command-a-03-2025"}]}
        if field == "cursor":
            data["next_page_token"] = value
        return httpx.Response(200, json=data)

    monkeypatch.setattr(httpx, "get", get)
    result = provider_models_result("cohere-ai")
    assert not result["ok"] and result["models"] == []
    assert all(credential not in json.dumps(result) for credential in credentials)
