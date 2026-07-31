from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.providers.capabilities import ModelCapabilities
from eslams.runner import RunConfig, Runner

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "provider"

PROVIDER_CASES = (
    (
        "openai",
        "gpt-5-mini",
        "OPENAI_API_KEY",
        "openai_responses_success.json",
    ),
    (
        "anthropic",
        "claude-sonnet-4-20250514",
        "ANTHROPIC_API_KEY",
        "anthropic_messages_success.json",
    ),
    (
        "gemini",
        "gemini-2.5-flash",
        "GEMINI_API_KEY",
        "gemini_generate_content_success.json",
    ),
    (
        "openrouter",
        "openai/gpt-5-mini",
        "OPENROUTER_API_KEY",
        "openrouter_chat_completions_success.json",
    ),
    (
        "bedrock",
        "amazon.nova-micro-v1:0",
        "AWS_BEARER_TOKEN_BEDROCK",
        "bedrock_converse_success.json",
    ),
)


def _request(*, arena_id: str = "tic-tac-toe") -> ActRequest:
    return ActRequest(
        protocol_version="eslams-act-v1",
        run_id="run_wire_fixture",
        episode_id="episode_001",
        turn_id=0,
        arena=ArenaIdentity(id=arena_id, version="1.0.0"),
        agent=AgentIdentity(id="provider-wire-agent", version="fixture-v1"),
        active_player="player_1",
        observation={"board": [], "you_are": "player_1"},
        legal_actions=[0, 1, 2],
        action_schema={"type": "integer"},
        history=[],
        time_budget_ms=10_000,
        memory_policy="current_observation_plus_public_history",
    )


def _fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _agent(
    provider: str,
    model: str,
    env_name: str,
    *,
    runtime_config: ProviderRuntimeConfig | None = None,
) -> ModelProviderAgent:
    return ModelProviderAgent(
        provider=provider,
        model=model,
        api_key_env=env_name,
        runtime_config=runtime_config or ProviderRuntimeConfig(reasoning="disabled"),
    )


def test_all_five_adapters_parse_documented_raw_wire_fixtures(monkeypatch):
    for provider, model, env_name, fixture_name in PROVIDER_CASES:
        monkeypatch.setenv(env_name, "fixture-secret-never-persisted")
        payload = _fixture(fixture_name)

        def fake_post(
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: Any,
            provider_case: str = provider,
            payload_case: dict[str, Any] = payload,
        ) -> httpx.Response:
            if provider_case == "bedrock":
                assert "/model/amazon.nova-micro-v1:0/converse" in url
            return httpx.Response(
                200,
                json=payload_case,
                headers={"x-amzn-requestid": "bedrock-wire-request"},
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        response = _agent(provider, model, env_name).act(_request())
        receipt = response.metadata["provider_receipt"]

        assert response.action == 1
        assert receipt["schema_version"] == "eslams.provider.receipt.v2"
        assert receipt["usage"]["input_tokens"] == 12
        assert receipt["usage"]["output_tokens"] == 4
        assert receipt["usage"]["total_tokens"] == 16
        assert "fixture-secret-never-persisted" not in json.dumps(receipt)


def test_openai_raw_wire_requires_output_array_and_scans_message_parts(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "sdk-convenience-shape",
                "output_text": '{"action": 1}',
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            },
            headers={"x-request-id": "req-wrong-wire-shape"},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = _agent("openai", "gpt-5-mini", "OPENAI_API_KEY")

    with pytest.raises(ProviderCallError) as caught:
        agent.act(_request())

    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert agent.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert agent.last_receipt["status_code"] == 200
    assert agent.last_receipt["request_id"] == "req-wrong-wire-shape"
    assert agent.last_receipt["usage"]["total_tokens"] == 2


def test_openrouter_provider_pin_is_explicit_and_fallback_stays_disabled(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-key")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        assert json["provider"] == {
            "order": ["Amazon Bedrock"],
            "allow_fallbacks": False,
        }
        return httpx.Response(
            200,
            json=_fixture("openrouter_chat_completions_success.json"),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = _agent(
        "openrouter",
        "openai/gpt-5-mini",
        "OPENROUTER_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            reasoning="disabled",
            openrouter_provider_order=("Amazon Bedrock",),
            openrouter_allow_fallbacks=False,
        ),
    )

    response = agent.act(_request())

    assert response.metadata["provider_receipt"]["estimated_cost"]["cost_usd"] == 0.000012
    assert response.metadata["provider_receipt"]["rate_card_id"] == (
        "openrouter:provider-native-reported-cost:v1"
    )


def test_complete_openrouter_case_is_publication_eligible(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-key")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=_fixture("openrouter_chat_completions_success.json"),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": _agent(
                    "openrouter",
                    "openai/gpt-5-mini",
                    "OPENROUTER_API_KEY",
                )
            },
            case_id="case_openrouter_complete_001",
            model_id_by_player={"player_1": "openai/gpt-5-mini"},
            max_turns=1,
            output_dir=tmp_path,
        )
    )
    receipt = json.loads(
        (result.artifact_path / "receipts/provider_receipts.jsonl").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (result.artifact_path / "manifest.json").read_text(encoding="utf-8")
    )

    assert receipt["case_valid_for_scoring"] is True
    assert receipt["usage_complete"] is True
    assert receipt["cost_complete"] is True
    assert result.score.integrity_status == "valid"
    assert manifest["per_case_run_valid"] is True
    assert manifest["per_case_scoring_eligible"] is True
    assert manifest["proof_row_publication_eligible"] is True


def test_provider_runtime_rejects_unobservable_openrouter_fallback():
    with pytest.raises(ValueError, match="provider fallback is unsupported"):
        ProviderRuntimeConfig(openrouter_allow_fallbacks=True)


def test_anthropic_reasoning_temperature_matrix(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    sent_payloads: list[dict[str, Any]] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        sent_payloads.append(json)
        return httpx.Response(200, json=_fixture("anthropic_messages_success.json"))

    monkeypatch.setattr(httpx, "post", fake_post)

    enabled = _agent(
        "anthropic",
        "claude-reasoning",
        "ANTHROPIC_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            reasoning="enabled",
            reasoning_budget_tokens=1024,
        ),
    )
    enabled.temperature = 0.25
    enabled.capabilities = ModelCapabilities(
        provider="anthropic",
        model="claude-reasoning",
        game_agent_supported=True,
        supports_temperature=True,
        supports_reasoning=True,
    )
    enabled.act(_request())

    disabled = _agent(
        "anthropic",
        "claude-reasoning",
        "ANTHROPIC_API_KEY",
        runtime_config=ProviderRuntimeConfig(reasoning="disabled"),
    )
    disabled.temperature = 0.25
    disabled.capabilities = enabled.capabilities
    disabled.act(_request())

    automatic = _agent(
        "anthropic",
        "claude-reasoning",
        "ANTHROPIC_API_KEY",
        runtime_config=ProviderRuntimeConfig(reasoning="auto"),
    )
    automatic.temperature = 0.25
    automatic.capabilities = enabled.capabilities
    automatic.act(_request(arena_id="connect-four"))

    assert sent_payloads[0]["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert sent_payloads[0]["temperature"] == 1.0
    assert "thinking" not in sent_payloads[1]
    assert sent_payloads[1]["temperature"] == 0.25
    assert "thinking" not in sent_payloads[2]
    assert sent_payloads[2]["temperature"] == 0.25


def test_anthropic_adaptive_and_manual_budget_contracts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    sent_payloads: list[dict[str, Any]] = []

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        sent_payloads.append(json)
        return httpx.Response(200, json=_fixture("anthropic_messages_success.json"))

    monkeypatch.setattr(httpx, "post", fake_post)
    adaptive = _agent(
        "anthropic",
        "claude-sonnet-5",
        "ANTHROPIC_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            reasoning="enabled",
            reasoning_budget_tokens=512,
        ),
    )
    adaptive.temperature = 0.25
    adaptive.capabilities = ModelCapabilities(
        provider="anthropic",
        model="claude-sonnet-5",
        game_agent_supported=True,
        supports_temperature=True,
        supports_reasoning=True,
    )

    response = adaptive.act(_request())

    assert response.action == 1
    assert sent_payloads[0]["thinking"] == {"type": "adaptive"}
    assert "temperature" not in sent_payloads[0]
    assert "budget_tokens" not in sent_payloads[0]["thinking"]

    invalid_manual = _agent(
        "anthropic",
        "claude-sonnet-4-20250514",
        "ANTHROPIC_API_KEY",
        runtime_config=ProviderRuntimeConfig(
            reasoning="enabled",
            reasoning_budget_tokens=512,
        ),
    )
    invalid_manual.capabilities = ModelCapabilities(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        game_agent_supported=True,
        supports_temperature=True,
        supports_reasoning=True,
        max_output_tokens=4096,
    )

    with pytest.raises(ProviderCallError) as caught:
        invalid_manual.act(_request())

    assert caught.value.error_kind == "provider_request_rejected"
    assert "at least 1024" in str(caught.value)
    assert len(sent_payloads) == 1


def test_action_repair_is_a_distinct_physical_attempt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    calls = 0

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = _fixture("openai_responses_success.json")
        if calls == 1:
            payload["output"][1]["content"] = [
                {"type": "output_text", "text": "not-json", "annotations": []}
            ]
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx, "post", fake_post)
    agent = _agent("openai", "gpt-5-mini", "OPENAI_API_KEY")

    response = agent.act(_request())

    assert response.action == 1
    assert calls == 2
    assert [row["attempt_index"] for row in agent.attempt_receipts] == [1, 2]
    assert [row["attempt_kind"] for row in agent.attempt_receipts] == [
        "primary",
        "action_repair",
    ]
    assert [row["outcome"] for row in agent.attempt_receipts] == [
        "action_response_unparseable",
        "ok",
    ]


def test_fault_matrix_is_typed_and_unscoreable_for_every_adapter(tmp_path: Path, monkeypatch):
    status_faults = (
        (400, "provider_request_rejected"),
        (401, "provider_auth_failed"),
        (403, "provider_permission_failed"),
        (404, "provider_unavailable"),
        (429, "provider_rate_limited"),
        (500, "provider_unavailable"),
    )
    for provider, model, env_name, fixture_name in PROVIDER_CASES:
        monkeypatch.setenv(env_name, "fixture-key")
        for status_code, expected_class in status_faults:

            def fake_status(
                url: str,
                *,
                headers: dict[str, str],
                json: dict[str, Any],
                timeout: Any,
                status_code_case: int = status_code,
            ) -> httpx.Response:
                return httpx.Response(status_code_case, text="sanitized fixture failure")

            monkeypatch.setattr(httpx, "post", fake_status)
            result = Runner().run(
                RunConfig(
                    arena_id="tic-tac-toe",
                    agents={"player_1": _agent(provider, model, env_name)},
                    max_turns=1,
                    output_dir=tmp_path / provider / str(status_code),
                    execution_profile="official_eval",
                )
            )

            assert result.score.match_valid_for_scoring is False
            assert expected_class in result.score.invalid_reason_codes
            assert result.score.fallback_action_count_by_player["player_1"] == 0
            assert result.trace_events == []

        def fake_timeout(
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: Any,
        ) -> httpx.Response:
            raise httpx.ReadTimeout("fixture timeout")

        monkeypatch.setattr(httpx, "post", fake_timeout)
        timeout_result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                agents={"player_1": _agent(provider, model, env_name)},
                max_turns=1,
                output_dir=tmp_path / provider / "timeout",
                execution_profile="official_eval",
            )
        )
        assert timeout_result.score.match_valid_for_scoring is False
        assert "provider_timeout" in timeout_result.score.invalid_reason_codes

        def fake_malformed(
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: Any,
        ) -> httpx.Response:
            return httpx.Response(200, content=b"{not-json")

        monkeypatch.setattr(httpx, "post", fake_malformed)
        malformed_result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                agents={"player_1": _agent(provider, model, env_name)},
                max_turns=1,
                output_dir=tmp_path / provider / "malformed",
                execution_profile="official_eval",
            )
        )
        assert malformed_result.score.match_valid_for_scoring is False
        assert "provider_response_schema_mismatch" in malformed_result.score.invalid_reason_codes

        missing_usage_payload = copy.deepcopy(_fixture(fixture_name))
        missing_usage_payload.pop("usage", None)
        missing_usage_payload.pop("usageMetadata", None)

        def fake_missing_usage(
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
            timeout: Any,
            payload_case: dict[str, Any] = missing_usage_payload,
        ) -> httpx.Response:
            return httpx.Response(200, json=payload_case)

        monkeypatch.setattr(httpx, "post", fake_missing_usage)
        missing_usage_result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                agents={"player_1": _agent(provider, model, env_name)},
                max_turns=1,
                output_dir=tmp_path / provider / "missing-usage",
                execution_profile="official_eval",
            )
        )
        report = ArtifactValidator().validate_report(
            missing_usage_result.artifact_path,
            profile="official_case",
        )

        assert missing_usage_result.score.usage_complete is False
        assert "usage_incomplete" in report.errors
        assert report.valid is False
