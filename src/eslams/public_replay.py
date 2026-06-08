"""Public replay package export and validation helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from eslams.artifacts import (
    ARTIFACT_VERSION,
    ArtifactValidator,
    open_artifact,
)
from eslams.contracts.versions import ARTIFACT_MANIFEST_SCHEMA_VERSION
from eslams.hashing import canonical_json, sha256_file, sha256_json

PUBLIC_EXPORT_MEMBERS: tuple[str, ...] = (
    "replay/replay_events.jsonl",
    "replay/replay_manifest.json",
    "public/public_manifest.json",
    "public/public_result_summary.json",
    "public_reasoning/reasoning.jsonl",
)


def export_public_replay(artifact_path: Path, output_dir: Path) -> Path:
    """Export a no-secret public replay package directory."""

    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    with open_artifact(artifact_path) as artifact_dir:
        manifest = _read_json(artifact_dir / "manifest.json")
        for member in PUBLIC_EXPORT_MEMBERS:
            source = artifact_dir / member
            if not source.exists():
                continue
            target = output_dir / member
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    files = _file_entries(output_dir)
    package_manifest = {
        "manifest_schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "artifact_profile": "public_replay_package",
        "artifact_kind": "uploaded_replay",
        "artifact_id": sha256_json(files),
        "source_artifact_id": _optional_str(manifest.get("artifact_id")),
        "run_id": _optional_str(manifest.get("run_id")) or "unknown-run",
        "created_at": _optional_str(manifest.get("created_at")),
        "files": files,
        "hash_algorithm": "sha256",
        "public_exports": {
            "public_replay_manifest": "replay/replay_manifest.json",
            "public_replay_events": "replay/replay_events.jsonl",
            "public_manifest": "public/public_manifest.json",
            "public_result_summary": "public/public_result_summary.json",
            "public_reasoning": "public_reasoning/reasoning.jsonl",
        },
    }
    _write_json(output_dir / "manifest.json", package_manifest)
    report = ArtifactValidator().validate_report(output_dir, profile="public_replay_package")
    if report.errors:
        raise ValueError("; ".join(report.errors))
    return output_dir


def validate_public_replay(path: Path) -> dict[str, Any]:
    return ArtifactValidator().validate_report(path, profile="public_replay_package").to_dict()


def create_uploaded_smoke_fixture(output_dir: Path) -> Path:
    """Create a minimal uploaded replay package fixture."""

    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "replay").mkdir(parents=True)
    replay_event = {
        "schema_version": "eslams.replay.public.v1",
        "event_id": "uploaded-smoke:replay:000000",
        "run_id": "uploaded-smoke",
        "episode_id": "episode_001",
        "turn_id": 0,
        "state_hash": "uploaded-smoke-state",
        "active_player": "player_1",
        "actor_player": None,
        "seat": None,
        "state_hash_before": None,
        "state_hash_after": "uploaded-smoke-state",
        "action": None,
        "action_label": None,
        "public_reasoning_ref": None,
        "visibility": "public",
        "public_safe": True,
        "state_hash_valid": None,
        "state_hash_invalid_reason": None,
        "public_state": {"status": "setup"},
        "scores": {"player_1": 0.0, "player_2": 0.0},
        "terminal": False,
        "render_hints": {"renderer_family": "metadata"},
        "markers": [],
    }
    _write_jsonl(output_dir / "replay/replay_events.jsonl", [replay_event])
    _write_json(
        output_dir / "replay/replay_manifest.json",
        {
            "schema_version": "eslams.replay.manifest.v1",
            "replay_id": "uploaded-smoke:public-replay",
            "run_id": "uploaded-smoke",
            "arena_id": "uploaded-smoke",
            "variant_id": "default",
            "event_count": 1,
            "visible_frame_count": 1,
            "state_frame_count": 1,
            "move_frame_count": 0,
            "setup_only": True,
            "timeline_completeness": "setup_only",
            "renderer_kind": "metadata",
            "render_hints_version": "render-hints-v1",
            "public_state_shape_version": "public-state-v1",
            "has_public_state": True,
            "state_hash_valid": None,
            "participants": [],
            "showcase_ready": False,
            "minimum_autoplay_frames": 2,
            "autoplay_ready": False,
            "reasoning_frame_coverage": 0.0,
        },
    )
    files = _file_entries(output_dir)
    _write_json(
        output_dir / "manifest.json",
        {
            "manifest_schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "artifact_profile": "public_replay_package",
            "artifact_kind": "uploaded_replay",
            "artifact_id": sha256_json(files),
            "run_id": "uploaded-smoke",
            "files": files,
            "hash_algorithm": "sha256",
        },
    )
    return output_dir


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _file_entries(root: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel == "manifest.json":
                continue
            entries.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return entries


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
