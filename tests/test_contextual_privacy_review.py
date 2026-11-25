"""Cross-cutting validation and secondary-credential regressions for PR #273."""

from __future__ import annotations

import json
from dataclasses import replace
from urllib.parse import quote

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.contextual import API_KEY_ENV

PRIMARY = "sentPrimaryContextualCredential12345"
SECONDARY = "alternateContextualCredential67890"
CUSTOM_ENV = "CONTEXTUAL_REVIEW_TRANSPORT_KEY"
SUCCESS = {"response": '{"action":1}'}


@pytest.mark.parametrize("provider", [
    "contextual-ai", "contextual", "contextual_ai", " CONTEXTUAL_AI ",
])
@pytest.mark.parametrize("model", [None, "", " \t"])
@pytest.mark.parametrize("live", [False, True])
def test_preflight_rejects_blank_ids_for_every_registry_spelling(
    monkeypatch, provider, model, live,
):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("discovery"),
    )
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight(provider, model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("provider", ["contextual-ai", "contextual_ai", " contextual "])
@pytest.mark.parametrize("control", [
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 4096},
    {"gemini_thinking_budget": -1}, {"reasoning_effort": "high"},
])
@pytest.mark.parametrize("live", [False, True])
def test_preflight_rejects_explicit_reasoning_before_any_io(monkeypatch, provider, control, live):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("discovery"),
    )
    with pytest.raises(ValueError, match="no reasoning controls"):
        provider_preflight(provider, "v2", "tic-tac-toe", live=live,
                           runtime_config=ProviderRuntimeConfig(**control))


def test_reconfigured_agent_revalidates_budget_before_transport(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    agent = _provider_agent("contextual-ai:v2")
    agent.runtime_config = ProviderRuntimeConfig(reasoning_budget_tokens=0)
    with pytest.raises(ValueError, match="no reasoning controls"):
        agent.act(_request())


@pytest.mark.parametrize("value", ["contextual-ai", "contextual-ai:", "contextual-ai: \t"])
def test_cli_does_not_substitute_a_model(monkeypatch, tmp_path, capsys, value):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    assert main(["run", "--arena", "tic-tac-toe", "--agent", value,
                 "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank" in capsys.readouterr().err


@pytest.mark.parametrize("source", ["sent", "canonical", "langchain", "gateway", "gateway_user"])
@pytest.mark.parametrize("outcome", [
    "success", "http_error", "malformed", "extended", "partial", "action", "escaped_action",
    "url_encoded_action",
])
def test_all_configured_credentials_are_protected_in_every_response_path(
    monkeypatch, source, outcome,
):
    monkeypatch.setenv(CUSTOM_ENV, PRIMARY)
    monkeypatch.setenv(API_KEY_ENV, SECONDARY)
    monkeypatch.setenv("CONTEXTUAL_AI_API_KEY", "langchainCredentialNotUsed12345")
    gateway_secret = "gatewayCredential%/67890"
    gateway_user = "gatewayUserCredential12345"
    runtime = ProviderRuntimeConfig(
        max_retries=2,
        gateway_base_url=f"https://{gateway_user}:{quote(gateway_secret, safe='')}@gateway.example",
    )
    echoed = {
        "sent": PRIMARY, "canonical": SECONDARY,
        "langchain": "langchainCredentialNotUsed12345", "gateway": gateway_secret,
        "gateway_user": gateway_user,
    }[source]
    calls = []

    def post(url, *, headers, json, **kwargs):
        calls.append(1)
        assert headers["Authorization"] == f"Bearer {PRIMARY}"
        assert json["knowledge"] == [""]
        assert set(json) == {"model", "messages", "knowledge", "system_prompt"}
        response_headers = {"x-request-id": echoed, "cf-aig-request-id": echoed}
        if outcome == "partial":
            error = httpx.ReadError(echoed)
            error.__dict__["_eslams_response_observation"] = ResponseObservation(
                200, tuple(response_headers.items()),
            )
            raise error
        if outcome == "http_error":
            return httpx.Response(429, json={
                "error": {"type": "rate_limit_error", "message": echoed},
                "id": echoed, "response_id": echoed,
            }, headers=response_headers)
        if outcome == "malformed":
            return httpx.Response(200, text='{"response":' + echoed, headers=response_headers)
        payload = dict(SUCCESS)
        if outcome == "extended":
            payload["id"] = echoed
        if outcome in {"action", "escaped_action", "url_encoded_action"}:
            text = echoed if outcome != "escaped_action" else "".join(
                f"\\u{ord(char):04x}" for char in echoed
            )
            if outcome == "url_encoded_action":
                text = quote(echoed, safe="").replace("%2F", "%2f")
            payload["response"] = '{"action":1,"public_explanation":"' + text + '"}'
        return httpx.Response(200, json=payload, headers=response_headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("contextual-ai", "v2", CUSTOM_ENV, runtime_config=runtime)
    if outcome == "success":
        response = agent.act(_request())
        public = response.to_dict()
        assert response.action == 1
    else:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        public = {"error": str(failure.value), "receipt": failure.value.receipt}
        assert failure.value.retry_permitted is False
    assert calls == [1]
    assert agent.last_receipt["request_id"] is None
    assert agent.last_receipt["gateway_request_id"] is None
    assert agent.last_receipt.get("provider_response_id") is None
    assert agent.last_receipt["locked_model_id"] is None
    assert not agent.last_receipt["usage"]
    serialized = json.dumps({"public": public, "receipts": agent.attempt_receipts})
    for credential in (
        PRIMARY, SECONDARY, "langchainCredentialNotUsed12345", gateway_secret, gateway_user,
    ):
        assert credential not in serialized and quote(credential, safe="") not in serialized


def test_gateway_query_credentials_are_also_protected(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, json=SUCCESS, headers={"x-request-id": SECONDARY},
    ))
    agent = ModelProviderAgent(
        "contextual-ai", "v2", API_KEY_ENV, runtime_config=ProviderRuntimeConfig(
            gateway_base_url=f"https://gateway.example?api_key={SECONDARY}",
        ),
    )
    assert agent.act(_request()).metadata["provider_receipt"]["request_id"] is None


def test_discovery_is_offline_and_secondary_key_is_never_auth_fallback(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv("CONTEXTUAL_AI_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("discovery"),
    )
    assert provider_models_live("contextual-ai") is None
    result = provider_preflight("contextual-ai", "v2", "tic-tac-toe", live=True)
    assert result["checks"]["account_model_visible"] is None
    assert result["error"]["error_class"] == "provider_auth_failed"
    assert SECONDARY not in json.dumps(result)
    agent = ModelProviderAgent("contextual-ai", "v2", API_KEY_ENV)
    with pytest.raises(ProviderCallError):
        agent.act(replace(_request(), history=[{"event": "retained"}]))
    assert SECONDARY not in json.dumps(agent.attempt_receipts)
