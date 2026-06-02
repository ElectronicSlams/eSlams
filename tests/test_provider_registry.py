import json
from pathlib import Path

from eslams.providers.registry import (
    REQUESTED_PROVIDER_ORGANIZATIONS,
    load_provider_registry,
    load_provider_registry_from_paths,
)


def test_registry_includes_requested_provider_organizations():
    registry = load_provider_registry()

    for provider, name in REQUESTED_PROVIDER_ORGANIZATIONS:
        assert registry.organizations[provider] == name


def test_registry_resolves_known_and_unknown_models_safely():
    registry = load_provider_registry()

    known = registry.resolve("openai", "gpt-5.4-mini")
    unknown = registry.resolve("openai", "not-a-real-model")

    assert known.known is True
    assert known.reasoning_payload() == {"effort": "none"}
    assert unknown.known is False
    assert unknown.game_agent_supported is False
    assert unknown.reasoning_payload() is None
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
    assert record.sources == ["local-override"]
