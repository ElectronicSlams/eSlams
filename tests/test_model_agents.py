from typing import Any

import httpx

from eslams.agents import ModelProviderAgent
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity


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
        timeout: int,
    ) -> httpx.Response:
        assert url == "https://api.openai.com/v1/responses"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-test"
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


def test_gemini_model_agent_receipt_does_not_include_key(monkeypatch):
    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: int,
    ) -> httpx.Response:
        assert "gemini-test:generateContent" in url
        assert headers["x-goog-api-key"] == "gemini-key"
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
