"""Manifest path confinement and fail-closed validation echoes."""

from __future__ import annotations

import json
from pathlib import Path

from eslams.artifacts import ARTIFACT_VERSION, ArtifactValidator
from eslams.hashing import sha256_file, sha256_json


def test_validation_confines_manifest_paths_and_clears_official_echo(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("hidden-eval-material", encoding="utf-8")
    inside = artifact / "ok.txt"
    inside.write_text("ok", encoding="utf-8")
    link = artifact / "leak.txt"
    link.symlink_to(outside)
    files = [
        {"path": "ok.txt", "sha256": sha256_file(inside)},
        {"path": "/etc/passwd", "sha256": "sha256:" + ("0" * 64)},
        {"path": "../secret.txt", "sha256": sha256_file(outside)},
        {"path": "leak.txt", "sha256": sha256_file(outside)},
    ]
    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "files": files,
        "artifact_id": sha256_json(sorted(files, key=lambda item: str(item["path"]))),
        "unhashed_files": [{"path": "../secret.txt"}],
        "verification_level": "Official",
        "verification_level_key": "official",
        "verification_level_label": "Grand Slam",
        "match_valid_for_scoring": True,
        "per_case_run_valid": True,
        "per_case_scoring_eligible": True,
        "proof_row_publication_eligible": True,
        "aggregate_leaderboard_eligible": True,
    }
    (artifact / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = ArtifactValidator().validate_report(artifact, profile="runner_bundle")
    errors = "\n".join(report.errors)

    assert "manifest path escapes artifact root: /etc/passwd" in errors
    assert "manifest path escapes artifact root: ../secret.txt" in errors
    assert "refusing symlink: leak.txt" in errors
    assert "hash mismatch for /etc/passwd" not in errors
    assert "hash mismatch for ../secret.txt" not in errors
    assert "hash mismatch for leak.txt" not in errors
    assert "hidden-eval-material" not in errors
    assert report.valid is False
    assert report.scoring_eligible is False
    assert report.per_case_run_valid is False
    assert report.per_case_scoring_eligible is False
    assert report.proof_row_publication_eligible is False
    assert report.aggregate_leaderboard_eligible is False
    assert report.verification_level == "Untrusted"
    assert report.verification_level_key == "untrusted"
    assert report.verification_level_label == "Untrusted"
