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
        preflight = provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True,
                                      strict_catalogue=True)
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
            "anthropic", "claude-haiku-4-5-20251001", "tic-tac-toe", live=True,
            strict_catalogue=True,
        )
        assert not result["ok"] and result["checks"]["account_model_visible"] is None
        assert result["error"]["error_class"] == "provider_response_schema_mismatch"
        assert len(calls) <= 2


def test_strict_catalogue_retired_models_fail_before_network_and_default_is_active(monkeypatch):
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get", lambda *a, **k: pytest.fail("must not discover")
    )
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("must not infer"))
    for live in (False, True):
        result = provider_preflight(
            "anthropic", "claude-sonnet-4-20250514", "tic-tac-toe", live=live,
            strict_catalogue=True,
        )
        assert not result["ok"] and result["lifecycle"] == "retired"
        assert not result["checks"]["model_lifecycle_available"]
        assert result["error"]["error_class"] == "provider_unavailable"
    agent = _provider_agent("anthropic")
    assert agent.model == "claude-sonnet-4-6"
    assert agent.capabilities.lifecycle == "active"
    assert provider_preflight("anthropic", agent.model, "tic-tac-toe")["ok"]


def test_gpt5_preflight_preserves_native_defaults_without_framework_caps(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    for model in ("gpt-5-mini", "gpt-5-nano"):
        monkeypatch.setattr(
            "eslams.provider_preflight.httpx.get",
            lambda *a, model=model, **k: httpx.Response(200, json={"data": [{"id": model}]}),
        )
        requests = []

        def post(*args, json, requests=requests, **kwargs):
            requests.append(json)
            assert "reasoning" not in json
            assert "max_output_tokens" not in json
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


@pytest.mark.parametrize("phase", ["discovery", "inference"])
@pytest.mark.parametrize(("status", "kind"), [
    (401, "provider_auth_failed"),
    (httpx.codes.ACCEPTED, "provider_pending"),
])
def test_preflight_uses_safe_public_messages_for_provider_failures(
    monkeypatch, capsys, phase, status, kind,
):
    from eslams.agents import ProviderCallError

    secret = "synthetic-preflight-password-953"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def fail(*args, **kwargs):
        raise ProviderCallError(secret, status_code=status, error_kind=kind)

    if phase == "discovery":
        monkeypatch.setattr("eslams.provider_preflight.provider_models_live", fail)
    else:
        monkeypatch.setattr("eslams.provider_preflight.provider_models_live", lambda _: None)
        monkeypatch.setattr("eslams.agents.ModelProviderAgent.act", fail)
    args = [
        "providers", "preflight", "--provider", "openai", "--model", "gpt-5-mini",
        "--arena", "tic-tac-toe", "--live",
    ]
    if phase == "discovery":
        args.append("--strict-catalogue")
    assert main(args) == 1
    output = capsys.readouterr().out
    error = json.loads(output)["error"]
    assert error["error_class"] == kind
    assert error["status_code"] == int(status)
    assert "Provider authentication failed" in error["message"] if status == 401 else (
        "still pending" in error["message"]
    )
    assert secret not in output


@pytest.mark.parametrize("encoding", ["plain", "percent"])
def test_discovery_never_publishes_a_credential_echo_as_a_model_id(monkeypatch, capsys, encoding):
    secret = "synthetic-preflight-password-953"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    echoed = secret if encoding == "plain" else "".join(f"%{ord(c):02x}" for c in secret)
    monkeypatch.setattr(
        "eslams.provider_preflight.httpx.get",
        lambda *a, **k: httpx.Response(200, json={"data": [{"id": f"gpt-5-mini-20{echoed}"}]}),
    )
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("must not infer"))
    assert main(["providers", "models", "--provider", "openai", "--live"]) == 1
    models_output = capsys.readouterr().out
    assert json.loads(models_output)["models"] == []
    assert secret not in models_output and echoed not in models_output
    assert main([
        "providers", "preflight", "--provider", "openai", "--model", "gpt-5-mini",
        "--arena", "tic-tac-toe", "--live", "--strict-catalogue",
    ]) == 1
    preflight_output = capsys.readouterr().out
    error = json.loads(preflight_output)["error"]
    assert error["error_class"] == "provider_response_schema_mismatch"
    assert "available_alternatives" not in error
    assert secret not in preflight_output and echoed not in preflight_output
