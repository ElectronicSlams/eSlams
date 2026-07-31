import json
from pathlib import Path

from eslams.providers.registry import (
    FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS,
    PLATFORM_API_DISCOVERED_PROVIDER_KEYS,
    REQUESTED_PROVIDER_ORGANIZATIONS,
    load_provider_registry,
    load_provider_registry_from_paths,
)


def test_registry_includes_requested_provider_organizations():
    registry = load_provider_registry()

    provider_keys = {provider for provider, _ in REQUESTED_PROVIDER_ORGANIZATIONS}
    discovered_keys = {
        *FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS,
        *PLATFORM_API_DISCOVERED_PROVIDER_KEYS,
    }

    assert len(REQUESTED_PROVIDER_ORGANIZATIONS) == 90
    assert len(provider_keys) == 90
    assert len(FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS) == 20
    assert len(PLATFORM_API_DISCOVERED_PROVIDER_KEYS) == 1
    assert discovered_keys <= provider_keys
    assert len(provider_keys - discovered_keys) == 69

    for provider, name in REQUESTED_PROVIDER_ORGANIZATIONS:
        assert registry.organizations[provider] == name


def test_registry_resolves_known_and_unknown_models_safely():
    registry = load_provider_registry()

    known = registry.resolve("openai", "gpt-5.4-mini")
    unknown = registry.resolve("openai", "not-a-real-model")

    assert known.known is True
    assert known.reasoning_payload() == {"effort": "none"}
    assert known.accepted_control_fields == ["reasoning_effort"]
    assert known.default_reasoning_track == "none"
    assert known.reasoning_track_kind == "provider_controlled"
    assert unknown.known is False
    assert unknown.game_agent_supported is False
    assert unknown.reasoning_payload() is None
    assert unknown.default_reasoning_track == "native-default"
    assert unknown.supports_temperature is False
    assert unknown.supports_google_thinking_config is False


def test_registry_merges_local_overrides(tmp_path: Path):
    generated = {
        "generated_at": "2026-06-02T00:00:00Z",
        "sources": ["test-generated"],
        "organizations": [{"provider": "openai", "name": "OpenAI"}],
        "models": [
            {
                "provider": "openai",
                "model": "model-a",
                "available_from_api": True,
                "game_agent_supported": False,
                "endpoints": ["responses"],
                "modalities": {"input": ["text"], "output": ["text"]},
                "supports_temperature": False,
                "supports_reasoning": False,
                "reasoning_efforts": [],
                "default_reasoning_effort": None,
                "supports_google_thinking_config": False,
                "max_output_tokens": None,
                "context_window": None,
                "last_verified_at": None,
                "sources": ["test-generated"],
            }
        ],
    }
    overrides = {
        "models": [
            {
                "provider": "openai",
                "model": "model-a",
                "game_agent_supported": True,
                "supports_reasoning": True,
                "reasoning_efforts": ["none"],
                "default_reasoning_effort": "none",
                "sources": ["local-override"],
            }
        ]
    }
    generated_path = tmp_path / "models.generated.json"
    overrides_path = tmp_path / "overrides.json"
    generated_path.write_text(json.dumps(generated), encoding="utf-8")
    overrides_path.write_text(json.dumps(overrides), encoding="utf-8")

    registry = load_provider_registry_from_paths(generated_path, overrides_path)
    record = registry.resolve("openai", "model-a")

    assert record.game_agent_supported is True
    assert record.reasoning_payload() == {"effort": "none"}
    assert record.supported_reasoning_modes == ["none"]
    assert record.accepted_control_fields == ["reasoning_effort"]
    assert record.sources == ["local-override"]


def test_registry_distinguishes_provider_controlled_and_native_reasoning():
    registry = load_provider_registry()
    gpt5 = registry.resolve("openai", "gpt-5-mini")
    gpt41 = registry.resolve("openai", "gpt-4.1")

    assert gpt5.accepted_control_fields == ["reasoning_effort"]
    assert gpt5.supported_reasoning_modes == ["minimal", "low", "medium", "high"]
    assert gpt5.reasoning_track_kind == "provider_controlled"
    assert gpt5.http_agent_payload_guidance["accepted_control_fields"] == ["reasoning_effort"]
    assert gpt41.supported_reasoning_modes == ["native-default"]
    assert gpt41.accepted_control_fields == []
    assert gpt41.reasoning_track_kind == "provider_native"
    assert gpt41.unsupported_reasoning_control_reason == "provider_control_not_supported"


def test_direct_bedrock_and_openrouter_routes_are_first_class_registry_entries():
    registry = load_provider_registry()

    bedrock = registry.resolve("amazon-bedrock", "amazon.nova-micro-v1:0")
    openrouter = registry.resolve("openrouter", "openai/gpt-5-mini")

    assert bedrock.known is True
    assert bedrock.provider == "bedrock"
    assert bedrock.endpoints == ["converse"]
    assert bedrock.lifecycle == "account-dependent"
    assert openrouter.known is True
    assert openrouter.provider == "openrouter"
    assert openrouter.endpoints == ["chat-completions"]
    assert openrouter.lifecycle == "account-dependent"


def test_anthropic_registry_exposes_only_the_supported_thinking_control():
    registry = load_provider_registry()

    manual = registry.resolve("anthropic", "claude-sonnet-4-20250514")

    assert manual.anthropic_reasoning_mode() == "manual"
    assert manual.accepted_control_fields == ["thinking_budget_tokens"]
