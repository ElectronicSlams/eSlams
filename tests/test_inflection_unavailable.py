"""Keep unverified Inflection transport selections from becoming broker calls."""

import json

import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry

SPELLINGS = ("inflection", "inflection-ai", "INFLECTION", "inflection_ai")
MODEL = "operator-selected/native-model"


@pytest.fixture
def no_network(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("unverified Inflection selection attempted network or fallback")

    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", unexpected)


@pytest.mark.parametrize("provider", SPELLINGS)
def test_inflection_alias_is_catalogue_identity_without_cli_transport(provider, no_network):
    record = load_provider_registry().resolve(provider, MODEL)
    assert record.provider == "inflection-ai"
    assert record.model == MODEL
    assert _provider_agent(f"{provider}:{MODEL}") is None


@pytest.mark.parametrize("provider", SPELLINGS)
@pytest.mark.parametrize("live", (False, True))
def test_inflection_preflight_never_claims_availability(provider, live, no_network):
    result = provider_preflight(provider, MODEL, "tic-tac-toe", live=live)
    assert not result["ok"]
    assert result["model"] == MODEL
    assert result["error"]["error_class"] == "provider_adapter_unavailable"
    assert result["checks"]["adapter_available"] is False
    assert result["checks"]["account_model_visible"] is None
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["readiness"]["usage_complete"] is False
    assert result["receipt_shape"]["outcome"] == "not_called"


@pytest.mark.parametrize("provider", SPELLINGS)
def test_inflection_cli_preflight_and_discovery_fail_without_fallback(provider, no_network, capsys):
    assert main([
        "providers", "preflight", "--provider", provider, "--model", MODEL, "--live",
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["error_class"] == "provider_adapter_unavailable"
    with pytest.raises(ProviderCallError) as error:
        provider_models_live(provider)
    assert error.value.error_kind == "provider_adapter_unavailable"
    assert main(["providers", "models", "--provider", provider, "--live"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["models"] == []
    assert result["error"]["error_class"] == "provider_adapter_unavailable"


@pytest.mark.parametrize("provider", SPELLINGS)
def test_inflection_direct_dispatch_cannot_fabricate_action_or_identity(
    provider, no_network, monkeypatch,
):
    monkeypatch.setenv("ESLAMS_TEST_INFLECTION_KEY", "test-secret-never-transmitted")
    agent = ModelProviderAgent(provider, MODEL, "ESLAMS_TEST_INFLECTION_KEY")
    request = _request()
    request.observation["private_marker"] = "private-observation-never-published"
    with pytest.raises(ProviderCallError) as error:
        agent.act(request)
    assert error.value.error_kind == "provider_unavailable"
    assert error.value.model == MODEL
    assert agent.model == MODEL
    assert len(agent.attempt_receipts) == 1
    receipt = agent.last_receipt
    assert receipt["locked_model_id"] is None
    assert receipt["usage"] == {}
    assert receipt["model_identity_source"] is None
    assert receipt["usage_unavailable_reason"] == "provider_unavailable"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    public = json.dumps(receipt) + str(error.value)
    assert "test-secret-never-transmitted" not in public
    assert "private-observation-never-published" not in public
