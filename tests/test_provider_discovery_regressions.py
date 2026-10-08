import json

import httpx
import pytest
from test_model_agents import _openai_wire

from eslams.cli import _provider_agent, main
from eslams.provider_preflight import provider_models_live, provider_preflight


def test_live_discovery_diagnoses_failures_and_preserves_a_real_empty_result(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["providers", "models", "--provider", "openai", "--live"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["error_class"] == "provider_auth_failed"
    assert "OPENAI_API_KEY" in result["error"]["message"]

    monkeypatch.setenv("OPENAI_API_KEY", "discovery-secret-test-key")
    cases = [
        (
            httpx.ConnectError("URL includes discovery-secret-test-key"),
            "provider_transport_error",
            None,
        ),
        (httpx.ReadTimeout("discovery-secret-test-key"), "provider_timeout", None),
        (httpx.Response(401, text="discovery-secret-test-key"), "provider_auth_failed", 401),
        (httpx.Response(429, text="discovery-secret-test-key"), "provider_rate_limited", 429),
        (httpx.Response(503), "provider_unavailable", 503),
        (
            httpx.Response(200, json={"data": [{"id": 42}]}),
            "provider_response_schema_mismatch",
            None,
        ),
        (
            httpx.Response(200, text="invalid discovery-secret-test-key"),
            "provider_response_schema_mismatch",
            None,
        ),
    ]
    for response, kind, status in cases:

        def get(*args, response=response, **kwargs):
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
        assert main(["providers", "models", "--provider", "openai", "--live"]) == 1
        result = json.loads(capsys.readouterr().out)
        assert result["error"]["error_class"] == kind
        assert result["error"]["status_code"] == status
        assert "discovery-secret-test-key" not in json.dumps(result)
        monkeypatch.setattr(
            "eslams.agents.bounded_post",
            lambda *a, **k: pytest.fail("discovery failure must stop inference"),
        )
        preflight = provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True)
        assert not preflight["ok"] and preflight["checks"]["account_model_visible"] is None
        assert preflight["error"]["error_class"] == kind
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get",
        lambda *a, **k: httpx.Response(200, json={"data": []}),
    )
    assert main(["providers", "models", "--provider", "openai", "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["models"] == []


def test_discovery_follows_anthropic_and_gemini_pages_before_testing_visibility(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    calls = []

    def get(url, *, headers, params, **kwargs):
        calls.append((url, headers, params))
        if "anthropic" in url:
            assert params["limit"] == "1000"
            if "after_id" not in params:
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "model-first"}],
                        "has_more": True,
                        "last_id": "model-first",
                    },
                )
            assert params["after_id"] == "model-first"
            return httpx.Response(
                200, json={"data": [{"id": "claude-haiku-4-5-20251001"}], "has_more": False}
            )
        assert headers["x-goog-api-key"] == "fake-gemini-key" and "key" not in params
        if "pageToken" not in params:
            return httpx.Response(
                200, json={"models": [{"name": "models/model-first"}], "nextPageToken": "second"}
            )
        assert params["pageToken"] == "second"
        return httpx.Response(
            200,
            json={"models": [{"name": "models/gemini-2.5-flash"}, {"name": "models/model-first"}]},
        )

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live("anthropic") == ["claude-haiku-4-5-20251001", "model-first"]
    assert provider_models_live("gemini") == ["gemini-2.5-flash", "model-first"]
    assert len(calls) == 4
    inference = []

    def post(url, **kwargs):
        inference.append(url)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "content": [{"type": "text", "text": '{"action": 0}'}],
                "usage": {"input_tokens": 20, "output_tokens": 5},
            },
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = provider_preflight("anthropic", "claude-haiku-4-5-20251001", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"] and len(inference) == 1


def test_broken_pagination_never_turns_partial_results_into_false_invisibility(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("must not infer"))
    for page in (
        {"data": [{"id": "first"}], "has_more": True},
        {"data": [{"id": "first"}], "has_more": "true", "last_id": "first"},
        {"data": [{"id": "first"}], "has_more": True, "last_id": "first"},
    ):
        calls = []

        def get(*args, calls=calls, page=page, **kwargs):
            calls.append(1)
            return httpx.Response(200, json=page)

        monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
        result = provider_preflight(
            "anthropic", "claude-haiku-4-5-20251001", "tic-tac-toe", live=True
        )
        assert not result["ok"] and result["checks"]["account_model_visible"] is None
        assert result["error"]["error_class"] == "provider_response_schema_mismatch"
        assert len(calls) <= 2


def test_retired_models_fail_offline_and_live_without_network_and_default_is_active(monkeypatch):
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("must not discover")
    )
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("must not infer"))
    for live in (False, True):
        result = provider_preflight(
            "anthropic", "claude-sonnet-4-20250514", "tic-tac-toe", live=live
        )
        assert not result["ok"] and result["lifecycle"] == "retired"
        assert not result["checks"]["model_lifecycle_available"]
        assert result["error"]["error_class"] == "provider_unavailable"
    agent = _provider_agent("anthropic")
    assert agent.model == "claude-sonnet-4-6"
    assert agent.capabilities.lifecycle == "active"
    assert provider_preflight("anthropic", agent.model, "tic-tac-toe")["ok"]


def test_gpt5_preflight_sends_minimal_effort_with_a_reasoning_and_action_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    for model in ("gpt-5-mini", "gpt-5-nano"):
        monkeypatch.setattr(
            "eslams.provider_preflight.httpx.get",
            lambda *a, model=model, **k: httpx.Response(200, json={"data": [{"id": model}]}),
        )
        requests = []

        def post(*args, json, requests=requests, **kwargs):
            requests.append(json)
            assert json["reasoning"] == {"effort": "minimal"}
            assert json["max_output_tokens"] >= 4096
            return httpx.Response(
                200,
                json=_openai_wire(
                    '{"action": 0}',
                    usage={
                        "input_tokens": 20,
                        "output_tokens": 130,
                        "total_tokens": 150,
                        "output_tokens_details": {"reasoning_tokens": 125},
                    },
                ),
            )

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        result = provider_preflight("openai", model, "tic-tac-toe", live=True)
        assert result["ok"] and result["checks"]["usage_extraction"] and len(requests) == 1
