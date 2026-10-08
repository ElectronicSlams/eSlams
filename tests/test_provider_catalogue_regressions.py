import importlib.util
import json
import re
from pathlib import Path

import pytest

from eslams.catalogue import model_catalogue_rows
from eslams.cli import main
from eslams.providers import load_provider_registry
from eslams.providers.capabilities import ModelCapabilities
from eslams.providers.registry import load_provider_registry_from_paths


def test_non_game_tasks_cannot_be_promoted_by_text_modalities_or_capability_overrides():
    registry = load_provider_registry()
    for record in registry.list_models():
        if re.search(r"embed|rerank|moderation", record.model, re.I):
            assert not record.allows_text_game_agent(), (record.provider, record.model)
            assert record.launch_status == "not_evaluated"
            assert all(
                not record.capability_enabled(key)
                for key in ("arena", "battlefield", "official_eval")
            )
    for task in ("embedding", "rerank", "moderation", "transcription"):
        record = ModelCapabilities.from_mapping(
            {
                "provider": "broker",
                "model": "opaque-model-id",
                "mode": task,
                "game_agent_supported": True,
                "launch_status": "ready",
                "modalities": {"input": ["text"], "output": ["text"]},
                "capability_flags": {"arena": True, "battlefield": True, "official_eval": True},
            }
        )
        assert not record.allows_text_game_agent() and record.launch_status == "not_evaluated"
        assert not record.capability_enabled("official_eval")
    assert registry.resolve("openai", "gpt-5-mini").allows_text_game_agent()
    assert (
        registry.resolve("azure-cognitive-services", "text-embedding-3-large").game_agent_supported
        is False
    )


def test_all_catalogue_slugs_are_unique_safe_and_deterministic_across_input_order(tmp_path):
    rows = model_catalogue_rows()
    assert len({row["public_slug"] for row in rows}) == len(rows)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", row["public_slug"]) for row in rows)
    assert (
        load_provider_registry().resolve("openai", "gpt-5-mini").public_slug == "openai-gpt-5-mini"
    )
    models = [
        {"provider": "broker", "model": model}
        for model in ("MODEL", "model", "bad@id", "bad*id", "☃")
    ]
    snapshots = []
    for index, ordered in enumerate((models, list(reversed(models)))):
        path = tmp_path / f"registry-{index}.json"
        path.write_text(json.dumps({"models": ordered}))
        registry = load_provider_registry_from_paths(path)
        snapshots.append({key: row.public_slug for key, row in registry.models.items()})
    assert snapshots[0] == snapshots[1]
    assert len(set(snapshots[0].values())) == len(models)
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", slug) for slug in snapshots[0].values())


def test_registry_refresh_requires_an_explicit_new_snapshot_and_does_not_infer_task_from_listing(
    tmp_path,
    monkeypatch,
):
    source = Path(__file__).resolve().parents[1] / "scripts/update_provider_registry.py"
    spec = importlib.util.spec_from_file_location("registry_update_fixture", source)
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    tracked = source.parents[1] / "src/eslams/providers/data/models.generated.json"
    original = tracked.read_bytes()
    with pytest.raises(SystemExit):
        main(["models", "update", "--providers", "openai"])
    existing = tmp_path / "existing.json"
    existing.write_text("preserve-existing")
    with pytest.raises(SystemExit):
        updater.main(["--output", str(existing), "--skip-public"])
    assert existing.read_text() == "preserve-existing"
    monkeypatch.setattr(
        updater,
        "_records_from_provider_apis",
        lambda: [updater._api_availability_record("openai", "unknown-listed-model")],
    )
    output = tmp_path / "snapshot.json"
    assert updater.main(["--output", str(output), "--skip-public", "--providers", "openai"]) == 0
    registry = load_provider_registry_from_paths(output)
    assert not registry.resolve("openai", "unknown-listed-model").allows_text_game_agent()
    assert registry.resolve("openai", "gpt-5-mini").supports_reasoning
    assert tracked.read_bytes() == original
    monkeypatch.setattr(
        updater,
        "_fetch_json",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("fixture source failure")),
    )
    with pytest.raises(ValueError, match="source failure"):
        updater.main(["--output", str(tmp_path / "failed-snapshot.json")])
    assert not (tmp_path / "failed-snapshot.json").exists()
