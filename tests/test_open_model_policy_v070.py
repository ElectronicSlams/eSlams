"""Catalogue-independent admission and exact caller-selected wire policy; no paid calls."""
from dataclasses import replace

import httpx
import pytest
from test_model_agents import _openai_wire, _request
from test_provider_wire_v06 import _fixture

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.provider_preflight import provider_preflight
from eslams.providers.capabilities import ModelCapabilities


def test_unknown_model_local_preflight_is_configuration_check_not_availability(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = provider_preflight("openai", "new-model-not-in-catalogue", "tic-tac-toe")
    assert result["ok"] is True
    assert result["checks"]["registry_entry"] is False
    assert result["model_availability"] == "unverified"
    assert result["strict_catalogue"] is False
    assert result.get("error") is None


@pytest.mark.parametrize("discovery", [[], ["other-model"], "failed"])
def test_explicit_live_preflight_uses_requested_model_despite_advisory_discovery(
    monkeypatch, discovery,
):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    def models(provider):
        if discovery == "failed":
            raise ProviderCallError("discovery unavailable", error_kind="provider_unavailable")
        return discovery
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live", models)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=_openai_wire('{"action":0}'))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = provider_preflight("openai", "new-model-not-in-catalogue", "tic-tac-toe",
                                live=True)
    assert result["ok"] is True
    assert result["model_availability"] == "inference_succeeded"
    assert len(calls) == 1 and calls[0]["model"] == "new-model-not-in-catalogue"
    assert "max_output_tokens" not in calls[0] and "reasoning" not in calls[0]
    assert result["warnings"]


def test_strict_catalogue_is_explicit_and_rejects_unknown_before_any_submission(monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    result = provider_preflight("openai", "new-model-not-in-catalogue", "tic-tac-toe",
                                strict_catalogue=True)
    assert result["ok"] is False
    assert result["error"]["error_class"] == "provider_request_rejected"


def test_advisory_catalogue_cannot_grant_adapter_or_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    assert provider_preflight("unsupported-api", "model", "tic-tac-toe")["ok"] is False
    missing = provider_preflight("openai", "model", "tic-tac-toe", live=True)
    assert missing["error"]["error_class"] == "provider_auth_failed"
    assert missing["readiness"]["inference"] == "not_attempted"


def test_successful_inference_does_not_require_optional_accounting(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live", lambda p: [])
    wire = _openai_wire('{"action":0}')
    wire.pop("usage", None)
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=wire))
    result = provider_preflight("openai", "new-model", "tic-tac-toe", live=True)
    assert result["ok"] is True
    assert result["checks"]["usage_extraction"] is False
    assert result["receipt_shape"]["usage_complete"] is False


@pytest.mark.parametrize("order", [(), ("fixture-provider",)])
def test_openrouter_forbidden_fallback_is_serialized_with_or_without_order(
    monkeypatch, order,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=_fixture("openrouter_chat_completions_success.json"))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openrouter", "requested-model", "OPENROUTER_API_KEY",
                              runtime_config=ProviderRuntimeConfig(
                                  openrouter_provider_order=order,
                                  openrouter_allow_fallbacks=False))
    response = agent.act(_request())
    expected = {"allow_fallbacks": False}
    if order:
        expected["order"] = list(order)
    assert len(calls) == 1 and calls[0]["provider"] == expected
    assert calls[0]["model"] == "requested-model"
    assert response.metadata["provider_receipt"]["model"] == "requested-model"
    # Preserve the actual returned identity; a route preference is not an
    # attestation of a pinned physical endpoint or a catalogue build alias.
    receipt = response.metadata["provider_receipt"]
    wire = _fixture("openrouter_chat_completions_success.json")
    assert receipt["locked_model_id"] == wire["model"]
    assert receipt["model_identity_source"] == "provider_response"


@pytest.mark.parametrize("value", [True, 1, "false", None])
def test_openrouter_fallback_cannot_be_enabled_or_smuggled(value):
    with pytest.raises(ValueError):
        ProviderRuntimeConfig(openrouter_allow_fallbacks=value)


@pytest.mark.parametrize("known", [False, True])
def test_explicit_openai_effort_does_not_depend_on_catalogue_name(monkeypatch, known):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=_openai_wire('{"action":0}'))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openai", "new-model", "OPENAI_API_KEY",
                              runtime_config=ProviderRuntimeConfig(reasoning_effort="high"))
    if known:
        agent.capabilities = replace(agent.capabilities, known=True, supports_reasoning=False,
                                     reasoning_efforts=["minimal"])
    agent.act(_request())
    assert len(calls) == 1 and calls[0]["reasoning"] == {"effort": "high"}


def test_unknown_gemini_forwards_explicit_endpoint_budget(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=_fixture("gemini_generate_content_success.json"))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("gemini", "new-model", "GEMINI_API_KEY",
                              runtime_config=ProviderRuntimeConfig(gemini_thinking_budget=-1))
    assert isinstance(agent.capabilities, ModelCapabilities)
    agent.act(_request())
    assert len(calls) == 1
    assert calls[0]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": -1}


def test_disabled_reasoning_cannot_silently_override_an_explicit_control():
    with pytest.raises(ValueError, match="disabled"):
        ProviderRuntimeConfig(reasoning="disabled", reasoning_effort="high")


def test_endpoint_rejects_explicit_control_without_core_substitution_or_replay(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(400, json={"error": {"code": "unsupported_reasoning_effort"}})
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = ModelProviderAgent("openai", "new-model", "OPENAI_API_KEY",
                              runtime_config=ProviderRuntimeConfig(
                                  reasoning_effort="high", max_retries=1))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == "provider_request_rejected"
    assert len(calls) == 1 and calls[0]["reasoning"] == {"effort": "high"}
    assert agent.last_receipt["status_code"] == 400


def test_unknown_anthropic_still_requires_a_real_output_parameter(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    agent = ModelProviderAgent("anthropic", "new-model", "ANTHROPIC_API_KEY")
    with pytest.raises(ProviderCallError, match="requires max_tokens"):
        agent.act(_request())
