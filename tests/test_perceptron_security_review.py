"""Cross-draft configuration/privacy regressions, using only synthetic credentials."""

from __future__ import annotations

import json

import httpx
import pytest
from test_perceptron_adapter import MODEL, payload, request, respond

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_preflight

SELECTED = "opaqueSelectedCredential772834"
DEFAULT = "opaqueDefaultCredential662834"
SECONDARY = "opaqueSecondaryCredential552834"
SECRETS = (SELECTED, DEFAULT, SECONDARY)


@pytest.fixture(autouse=True)
def credentials_and_no_network(monkeypatch):
    monkeypatch.setenv("PERCEPTRON_SELECTED_CREDENTIAL", SELECTED)
    monkeypatch.setenv("PERCEPTRON_API_KEY", DEFAULT)
    monkeypatch.setenv("PERCEPTRON_SECONDARY_TOKEN", SECONDARY)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("unexpected IO"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("unexpected discovery"))


def agent():
    return ModelProviderAgent(provider="perceptron", model=MODEL,
                              api_key_env="PERCEPTRON_SELECTED_CREDENTIAL")


def assert_safe(value):
    rendered = json.dumps(value)
    assert all(secret not in rendered for secret in SECRETS)


@pytest.mark.parametrize("provider", ["perceptron", "PERCEPTRON", " Perceptron "])
@pytest.mark.parametrize("model", [None, "", " \t "])
def test_missing_ids_fail_in_preflight_and_adapter(provider, model):
    with pytest.raises(ValueError, match="model ID"):
        provider_preflight(provider, model, "tic-tac-toe")
    with pytest.raises(ValueError, match="model ID"):
        ModelProviderAgent("perceptron", model, "PERCEPTRON_SELECTED_CREDENTIAL")


@pytest.mark.parametrize("field", ["reasoning_budget_tokens", "gemini_thinking_budget"])
@pytest.mark.parametrize("budget", [0, 1, 1024])
@pytest.mark.parametrize("provider", ["perceptron", " Perceptron "])
def test_unsupported_budgets_fail_in_preflight_and_before_transport(field, budget, provider):
    runtime = ProviderRuntimeConfig(**{field: budget})
    with pytest.raises(ValueError, match="reasoning token budget"):
        provider_preflight(provider, MODEL, "tic-tac-toe", live=True, runtime_config=runtime)
    instance = agent()
    instance.runtime_config = runtime
    with pytest.raises(ValueError, match="reasoning token budget"):
        instance.act(request())


@pytest.mark.parametrize("secret", SECRETS)
@pytest.mark.parametrize("field", ["id", "model", "request_id", "gateway_request_id",
                                  "action", "explanation", "escaped_explanation"])
def test_all_configured_credentials_are_excluded_from_receipts_and_actions(
    monkeypatch, secret, field,
):
    data = payload()
    headers = {}
    if field in {"id", "model"}:
        data[field] = "prefix-" + secret
    elif field in {"request_id", "gateway_request_id"}:
        headers["x-trace-id" if field == "request_id" else "cf-aig-request-id"] = secret
    else:
        text = json.dumps({"action": secret if field == "action" else 1,
                           "public_explanation": secret})
        if field == "escaped_explanation":
            text = text.replace(secret, "".join(f"\\u{ord(char):04x}" for char in secret))
        data["choices"][0]["message"]["content"] = text
    calls = respond(monkeypatch, data, headers=headers)
    instance = agent()
    if field in {"action", "explanation", "escaped_explanation"}:
        with pytest.raises(ProviderCallError) as caught:
            instance.act(request())
        assert_safe(str(caught.value))
    else:
        result = instance.act(request())
        assert_safe(result.to_dict())
    assert len(calls) == 1
    assert calls[0][1]["headers"]["Authorization"] == "Bearer " + SELECTED
    assert_safe(calls[0][1]["json"])
    assert_safe(instance.attempt_receipts)
    if field == "model":
        assert instance.last_receipt["locked_model_id"] is None
        assert instance.last_receipt["model_identity_source"] is None


@pytest.mark.parametrize("status", [200, 400, 429, 503])
def test_error_echoes_keep_safe_retry_and_accounting_policy(monkeypatch, status):
    data = {"id": SELECTED, "model": DEFAULT, "usage": payload()["usage"],
            "error": {"type": "rate_limit_error", "code": "rate_limit_error",
                      "message": " ".join(SECRETS)}}
    calls = respond(monkeypatch, data, status=status,
                    headers={"x-request-id": DEFAULT, "x-trace-id": SELECTED,
                             "cf-aig-request-id": SECONDARY})
    instance = agent()
    instance.runtime_config = ProviderRuntimeConfig(max_retries=2, retry_backoff_ms=0)
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert len(calls) == 1  # Reported work never becomes a safe rate rejection.
    assert instance.last_receipt["usage"]["total_tokens"] == 16
    assert_safe(instance.attempt_receipts)
    assert_safe(str(caught.value))


@pytest.mark.parametrize("partial", [False, True])
def test_malformed_and_partial_responses_remove_secondary_header_echoes(monkeypatch, partial):
    if partial:
        def post(*args, **kwargs):
            error = httpx.ReadError(" ".join(SECRETS))
            error._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", DEFAULT), ("x-trace-id", SELECTED),
                      ("cf-aig-request-id", SECONDARY)))
            raise error

        monkeypatch.setattr("eslams.agents.bounded_post", post)
    else:
        respond(monkeypatch, content=("invalid " + " ".join(SECRETS)).encode(),
                headers={"x-request-id": DEFAULT, "cf-aig-request-id": SECONDARY})
    instance = agent()
    with pytest.raises(ProviderCallError) as caught:
        instance.act(request())
    assert_safe(str(caught.value))
    assert_safe(instance.attempt_receipts)
    assert instance.last_receipt["usage"] == {}


@pytest.mark.parametrize("secret", SECRETS)
@pytest.mark.parametrize("mode", ["model_id", "error", "malformed", "partial"])
def test_discovery_never_returns_credential_echoes(monkeypatch, capsys, secret, mode):
    def get(*args, **kwargs):
        if mode == "partial":
            raise httpx.ReadError(secret)
        if mode == "error":
            return httpx.Response(400, json={"error": {"message": secret}})
        if mode == "malformed":
            return httpx.Response(200, content=("invalid " + secret).encode())
        return httpx.Response(200, json={"data": [{"id": MODEL}, {"id": "echo-" + secret}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert main(["providers", "models", "--provider", "perceptron", "--live"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"] and result["models"] == []
    assert_safe(result)
