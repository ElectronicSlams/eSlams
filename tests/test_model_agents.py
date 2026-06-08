import threading
import time
from contextlib import suppress
from typing import Any

import httpx

from eslams.agents import MockProviderAgent, ModelProviderAgent
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_preflight


def _request() -> ActRequest:
    return ActRequest(
        protocol_version="eslams-act-v1",
        run_id="run_test",
        episode_id="episode_001",
        turn_id=1,
        arena=ArenaIdentity(id="connect-four", version="1.0.0"),
        agent=AgentIdentity(id="openai-test", version="gpt-test"),
        active_player="player_1",
        observation={"board": [], "you_are": "player_1"},
        legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[],
        time_budget_ms=1000,
        memory_policy="current_observation_plus_public_history",
    )


def test_openai_model_agent_parses_legal_json_action(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert url == "https://api.openai.com/v1/responses"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-test"
        assert "reasoning" not in json
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "output_text": (
                    '{"action": "2", "confidence": 0.9, '
                    '"public_explanation": "Creates a threat."}'
                ),
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            headers={"x-request-id": "req_123"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    response = ModelProviderAgent(
        provider="openai",
        model="gpt-test",
        api_key_env="OPENAI_API_KEY",
    ).act(_request())

    assert response.action == 2
    assert response.confidence == 0.9
    assert response.metadata["provider_receipt"]["provider_response_id"] == "resp_123"
    assert response.metadata["provider_receipt"]["schema_version"] == "eslams.provider.receipt.v1"
    assert response.metadata["provider_receipt"]["usage"]["input_tokens"] == 10
    assert response.metadata["provider_receipt"]["usage"]["total_tokens"] == 18
    assert response.metadata["provider_receipt"]["estimated_cost"]["status"] == "cost_unavailable"
    assert "raw_output_preview" not in response.metadata["provider_receipt"]
    assert "api_key_env" not in response.metadata["provider_receipt"]


def test_openai_gpt5_model_agent_limits_reasoning_budget(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert url == "https://api.openai.com/v1/responses"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-5-mini"
        assert json["reasoning"] == {"effort": "minimal"}
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "output_text": '{"action": 1, "confidence": 0.8}',
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            headers={"x-request-id": "req_123"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    response = ModelProviderAgent(
        provider="openai",
        model="gpt-5-mini",
        api_key_env="OPENAI_API_KEY",
    ).act(_request())

    assert response.action == 1


def test_openai_registry_can_select_none_reasoning_effort(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert url == "https://api.openai.com/v1/responses"
        assert json["model"] == "gpt-5.4-mini"
        assert json["reasoning"] == {"effort": "none"}
        return httpx.Response(
            200,
            json={"id": "resp_123", "output_text": '{"action": 1}'},
            headers={"x-request-id": "req_123"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    response = ModelProviderAgent(
        provider="openai",
        model="gpt-5.4-mini",
        api_key_env="OPENAI_API_KEY",
    ).act(_request())

    assert response.action == 1


def test_gemini_model_agent_receipt_does_not_include_key(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert "gemini-test:generateContent" in url
        assert headers["x-goog-api-key"] == "gemini-key"
        assert json["generationConfig"] == {"maxOutputTokens": 1024}
        return httpx.Response(
            200,
            json={
                "responseId": "gemini-response",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"action": 1, "confidence": 0.8, '
                                        '"public_explanation": "Takes center."}'
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7},
            },
        )

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    agent = ModelProviderAgent(
        provider="gemini",
        model="gemini-test",
        api_key_env="GEMINI_API_KEY",
    )
    response = agent.act(_request())

    assert response.action == 1
    assert agent.last_receipt is not None
    assert "gemini-key" not in str(agent.last_receipt)


def test_gemma_model_agent_omits_thinking_config(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert "gemma-3-27b-it:generateContent" in url
        assert json["generationConfig"] == {"maxOutputTokens": 1024, "temperature": 0.0}
        return httpx.Response(
            200,
            json={
                "responseId": "gemma-response",
                "candidates": [{"content": {"parts": [{"text": '{"action": 2}'}]}}],
            },
        )

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    response = ModelProviderAgent(
        provider="gemini",
        model="gemma-3-27b-it",
        api_key_env="GEMINI_API_KEY",
    ).act(_request())

    assert response.action == 2


def test_provider_agent_uses_generic_gateway_base_url(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert url == "https://gateway.example/v1/responses"
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.as_dict() == {"connect": 2.0, "read": 12.0, "write": 12.0, "pool": 2.0}
        return httpx.Response(
            200,
            json={"id": "resp_123", "output_text": '{"action": 1}'},
            headers={"x-gateway-request-id": "gw_123"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    agent = ModelProviderAgent(
        provider="openai",
        model="gpt-test",
        api_key_env="OPENAI_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            timeout_ms=12_000,
            connect_timeout_ms=2_000,
            read_timeout_ms=12_000,
            gateway_base_url="https://gateway.example",
            gateway_mode="generic_base_url",
        ),
    )
    response = agent.act(_request())

    assert response.action == 1
    assert agent.last_receipt is not None
    assert agent.last_receipt["gateway_mode"] == "generic_base_url"
    assert agent.last_receipt["gateway_request_id"] == "gw_123"


def test_provider_agent_retries_and_records_every_attempt(monkeypatch):
    calls = {"count": 0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, text="temporary provider failure")
        return httpx.Response(
            200,
            json={
                "id": "resp_retry",
                "output_text": '{"action": 1}',
                "usage": {"input_tokens": 4, "output_tokens": 1},
            },
            headers={"x-request-id": "req_retry"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    agent = ModelProviderAgent(
        provider="openai",
        model="gpt-test",
        api_key_env="OPENAI_API_KEY",
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0),
    )
    response = agent.act(_request())

    assert response.action == 1
    assert calls["count"] == 2
    assert [receipt["attempt"] for receipt in agent.attempt_receipts] == [1, 2]
    assert [receipt["outcome"] for receipt in agent.attempt_receipts] == [
        "provider_error",
        "ok",
    ]


def test_provider_agent_applies_rate_limit(monkeypatch):
    sleeps: list[float] = []
    now = {"value": 100.0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "resp_rate", "output_text": '{"action": 1}'},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("eslams.agents.time.monotonic", lambda: now["value"])
    monkeypatch.setattr("eslams.agents.time.sleep", lambda seconds: sleeps.append(seconds))

    agent = ModelProviderAgent(
        provider="openai",
        model="gpt-rate-test",
        api_key_env="OPENAI_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            rate_limit_per_minute=60,
            gateway_base_url="https://gateway-rate.example",
        ),
    )
    agent.act(_request())
    agent.act(_request())

    assert sleeps == [1.0]


def test_provider_agent_honors_concurrency_limit(monkeypatch):
    lock = threading.Lock()
    entered = {"current": 0, "max": 0}
    first_entered = threading.Event()
    release_first = threading.Event()

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        with lock:
            entered["current"] += 1
            entered["max"] = max(entered["max"], entered["current"])
            is_first = entered["current"] == 1 and not first_entered.is_set()
        first_entered.set()
        if is_first:
            release_first.wait(timeout=2)
        with lock:
            entered["current"] -= 1
        return httpx.Response(
            200,
            json={"id": "resp_concurrency", "output_text": '{"action": 1}'},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    runtime_config = ProviderRuntimeConfig(
        concurrency_limit=1,
        gateway_base_url="https://gateway-concurrency.example",
    )
    agents = [
        ModelProviderAgent(
            provider="openai",
            model="gpt-concurrency-test",
            api_key_env="OPENAI_API_KEY",
            runtime_config=runtime_config,
        )
        for _ in range(2)
    ]
    threads = [threading.Thread(target=agent.act, args=(_request(),)) for agent in agents]

    threads[0].start()
    assert first_entered.wait(timeout=2)
    threads[1].start()
    time.sleep(0.05)
    assert entered["max"] == 1
    release_first.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_provider_preflight_skips_api_check_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = provider_preflight("openai", "gpt-test", "tic-tac-toe")

    assert payload["ok"] is True
    assert payload["checks"]["arena_available"] is True
    assert payload["checks"]["api_key_configured"] is False
    assert payload["receipt_shape"]["schema_version"] == "eslams.provider.receipt.v1"


def test_mock_provider_scenarios_emit_safe_receipts():
    request = _request()
    scenarios = {
        "success": "ok",
        "missing_usage": "ok",
        "parse_error": "parse_error",
        "timeout": "provider_timeout",
        "provider_error": "provider_error",
        "gateway_auth_failed": "gateway_auth_failed",
    }

    for scenario, outcome in scenarios.items():
        agent = MockProviderAgent(scenario=scenario)
        with suppress(Exception):
            agent.act(request)

        assert agent.last_receipt is not None
        assert agent.last_receipt["schema_version"] == "eslams.provider.receipt.v1"
        assert agent.last_receipt["outcome"] == outcome
        assert agent.last_receipt["estimated_cost"]["status"] == "cost_unavailable"
        assert "raw_output_preview" not in agent.last_receipt
        assert "api_key_env" not in agent.last_receipt
