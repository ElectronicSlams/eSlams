"""MiniMax QA negatives use only synthetic wire responses and opaque keys."""
import json

import httpx
import pytest
from test_minimax_provider import agent, mock_wire, wire
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_preflight
from eslams.providers.minimax import API_KEY_ENV, DEFAULT_MODEL

PRIMARY = "OpaqueMiniMaxPrimaryNovember"
SECONDARY = "OpaqueMiniMaxSecondaryNovember"


@pytest.mark.parametrize("source", ["primary", "secondary"])
@pytest.mark.parametrize("encoded", [False, True])
def test_action_credentials_fail_before_parse_or_repair(monkeypatch, source, encoded):
    secret = PRIMARY if source == "primary" else SECONDARY
    echo = "".join(f"\\u{ord(c):04x}" for c in secret) if encoded else secret
    data = wire()
    data["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"' + echo + '"}')
    calls = mock_wire(monkeypatch, data)
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setenv("QA_GATEWAY_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.agents._parse_model_action",
                        lambda *a, **k: pytest.fail("credential reached action parsing"))
    current = agent(max_retries=2, action_repair_attempts=2)
    with pytest.raises(ProviderCallError):
        current.act(_request())
    assert len(calls) == 1 and current.last_receipt["usage"]["total_tokens"] == 16
    assert secret not in json.dumps(current.attempt_receipts)


@pytest.mark.parametrize("scenario", ["success", "http_error", "malformed", "partial", "protocol"])
@pytest.mark.parametrize("encoded", [False, True])
def test_primary_and_secondary_identifiers_and_errors_are_private(monkeypatch, scenario, encoded):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setenv("QA_GATEWAY_API_KEY", SECONDARY)
    data = wire()
    def echo(value):
        return "".join(f"\\u{ord(c):04x}" for c in value) if encoded else value
    data["id"] = echo(PRIMARY)
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        if scenario in {"partial", "protocol"}:
            from eslams.http_io import ResponseObservation
            error = ProtocolError("private diagnostic " + echo(SECONDARY))
            if scenario == "partial":
                error._eslams_response_observation = ResponseObservation(
                    200, (("x-request-id", echo(PRIMARY)),
                          ("x-gateway-request-id", echo(SECONDARY))))
            raise error
        return httpx.Response(401 if scenario == "http_error" else 200,
            content=b'{"broken"' if scenario == "malformed" else json.dumps(data).encode(),
            headers={"x-request-id": echo(SECONDARY), "x-gateway-request-id": echo(PRIMARY)})
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    current = agent(max_retries=2)
    if scenario == "success":
        result = current.act(_request())
        public = result.to_dict()
    else:
        with pytest.raises(ProviderCallError) as caught:
            current.act(_request())
        public = [str(caught.value), caught.value.receipt]
        assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert len(calls) == 1
    serialized = json.dumps([public, current.attempt_receipts])
    assert PRIMARY not in serialized and SECONDARY not in serialized
    assert echo(PRIMARY) not in serialized and echo(SECONDARY) not in serialized


@pytest.mark.parametrize("settings", [
    {"reasoning_effort": "none"}, {"reasoning_effort": "invented"},
    {"reasoning": "disabled"}, {"reasoning_budget_tokens": 0},
    {"reasoning_budget_tokens": 1024}, {"gemini_thinking_budget": -1},
])
def test_unsupported_controls_fail_before_discovery_and_transport(monkeypatch, settings):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live",
                        lambda *a, **k: pytest.fail("discovery"))
    runtime = ProviderRuntimeConfig(**settings)
    for live in (False, True):
        result = provider_preflight("minimax", DEFAULT_MODEL, "tic-tac-toe",
                                    runtime_config=runtime, live=live)
        assert not result["ok"] and not result["readiness"]["configuration_ready"]
    with pytest.raises(ProviderCallError):
        agent(**settings).act(_request())


@pytest.mark.parametrize("model", ["", " ", None])
def test_missing_model_never_selects_a_default(model):
    with pytest.raises(ValueError):
        ModelProviderAgent("minimax", model, API_KEY_ENV)
    if isinstance(model, str):
        with pytest.raises(ValueError):
            _provider_agent("minimax:" + model)
    result = provider_preflight("minimax", model, "tic-tac-toe")
    assert not result["ok"] and not result["readiness"]["configuration_ready"]


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_documented_efforts_reach_wire_unchanged(monkeypatch, effort):
    calls = mock_wire(monkeypatch, wire())
    assert agent(reasoning_effort=effort).act(_request()).action == 1
    assert calls[0][1]["json"]["reasoning_effort"] == effort


def test_m3_disable_is_supported_while_m31_disable_is_rejected(monkeypatch):
    data = wire()
    data["model"] = "MiniMax-M3"
    calls = mock_wire(monkeypatch, data)
    current = ModelProviderAgent("minimax", "MiniMax-M3", API_KEY_ENV,
                                runtime_config=ProviderRuntimeConfig(reasoning="disabled"))
    assert current.act(_request()).action == 1
    assert calls[0][1]["json"]["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("model", ["MiniMax-M3", "future-model"])
def test_unverified_or_ignored_effort_is_rejected_locally(monkeypatch, model):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    current = ModelProviderAgent("minimax", model, API_KEY_ENV,
                                runtime_config=ProviderRuntimeConfig(reasoning_effort="high"))
    with pytest.raises(ProviderCallError, match="reasoning_effort"):
        current.act(_request())
