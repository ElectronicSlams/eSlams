"""Artifact writer and validator for .eslams proof packages."""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eslams.events import ReplayEvent, ScoreSummary, TraceEvent
from eslams.hashing import canonical_json, sha256_file, sha256_json

ARTIFACT_VERSION = "eslams-artifact-v1"
REQUIRED_FILES = {
    "manifest.json",
    "signatures/runner.sig",
    "traces/public_trace.jsonl",
    "traces/agent_visible_trace.jsonl",
    "traces/private_judge_trace.jsonl",
    "traces/auditor_trace.jsonl",
    "replay/replay_events.jsonl",
    "replay/replay_manifest.json",
    "scores/score.json",
    "scores/metrics.json",
    "logs/runner.log",
    "logs/agent_io.jsonl",
    "logs/errors.jsonl",
    "receipts/provider_receipts.jsonl",
    "environment/lockfile.json",
    "environment/container_digest.txt",
    "environment/package_versions.json",
    "broadcast/broadcast_manifest.json",
    "broadcast/vod_metadata.json",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ArtifactManifest:
    artifact_version: str
    artifact_id: str
    run_id: str
    created_at: str
    agent_version: str
    arena_version: str
    wrapper_version: str
    eval_suite_version: str
    scoring_policy_version: str
    runner_version: str
    verification_level: str
    files: list[dict[str, Any]]
    hash_algorithm: str
    signature: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_version": self.artifact_version,
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "agent_version": self.agent_version,
            "arena_version": self.arena_version,
            "wrapper_version": self.wrapper_version,
            "eval_suite_version": self.eval_suite_version,
            "scoring_policy_version": self.scoring_policy_version,
            "runner_version": self.runner_version,
            "verification_level": self.verification_level,
            "files": self.files,
            "hash_algorithm": self.hash_algorithm,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class ArtifactBuildInput:
    run_id: str
    arena_version: str
    agent_version: str
    score: ScoreSummary
    trace_events: list[TraceEvent]
    replay_events: list[ReplayEvent]
    metrics: dict[str, Any]
    runner_log: str
    agent_io: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    wrapper_version: str = "legal_action_v1:1.0.0"
    eval_suite_version: str = "public-smoke:1.0.0"
    scoring_policy_version: str = "standard-score:1.0.0"
    runner_version: str = "eslams-runner:0.1.0"
    verification_level: str = "Local Artifact"


def write_artifact(build: ArtifactBuildInput, output_path: Path, *, archive: bool = False) -> Path:
    """Write a directory artifact or zip-compatible .eslams archive."""

    output_path = output_path.resolve()
    artifact_dir = output_path if not archive else output_path.with_suffix("")
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    required_dirs = {
        str(Path(item).parent) for item in REQUIRED_FILES if Path(item).parent != Path(".")
    }
    for rel in sorted(required_dirs):
        (artifact_dir / rel).mkdir(parents=True, exist_ok=True)

    _write_jsonl(
        artifact_dir / "traces/public_trace.jsonl",
        (event.view("public") for event in build.trace_events),
    )
    _write_jsonl(
        artifact_dir / "traces/agent_visible_trace.jsonl",
        (event.view("agent_visible") for event in build.trace_events),
    )
    _write_jsonl(
        artifact_dir / "traces/private_judge_trace.jsonl",
        (event.view("private_judge") for event in build.trace_events),
    )
    _write_jsonl(
        artifact_dir / "traces/auditor_trace.jsonl",
        (event.view("auditor") for event in build.trace_events),
    )
    _write_jsonl(
        artifact_dir / "replay/replay_events.jsonl",
        (event.to_dict() for event in build.replay_events),
    )
    _write_json(
        artifact_dir / "replay/replay_manifest.json",
        {
            "replay_version": "eslams-replay-v1",
            "run_id": build.run_id,
            "event_count": len(build.replay_events),
            "privacy": "public",
            "renderer": "eslams-html-v1",
        },
    )
    _write_json(artifact_dir / "scores/score.json", build.score.to_dict())
    _write_json(artifact_dir / "scores/metrics.json", build.metrics)
    (artifact_dir / "logs/runner.log").write_text(build.runner_log, encoding="utf-8")
    _write_jsonl(artifact_dir / "logs/agent_io.jsonl", build.agent_io)
    _write_jsonl(artifact_dir / "logs/errors.jsonl", build.errors)
    _write_jsonl(artifact_dir / "receipts/provider_receipts.jsonl", [])
    _write_json(
        artifact_dir / "environment/lockfile.json",
        {"python": ">=3.9", "package": "eslams-core"},
    )
    (artifact_dir / "environment/container_digest.txt").write_text(
        "local-development\n",
        encoding="utf-8",
    )
    _write_json(artifact_dir / "environment/package_versions.json", {"eslams-core": "0.1.0"})
    _write_json(
        artifact_dir / "broadcast/broadcast_manifest.json",
        {
            "broadcast_version": "eslams-broadcast-v1",
            "run_id": build.run_id,
            "vod_available": False,
        },
    )
    _write_json(artifact_dir / "broadcast/vod_metadata.json", {"status": "not_requested"})
    (artifact_dir / "signatures/runner.sig").write_text("unsigned-local\n", encoding="utf-8")

    files = _file_entries(artifact_dir)
    artifact_id = sha256_json(files)
    manifest = ArtifactManifest(
        artifact_version=ARTIFACT_VERSION,
        artifact_id=artifact_id,
        run_id=build.run_id,
        created_at=utc_now_iso(),
        agent_version=build.agent_version,
        arena_version=build.arena_version,
        wrapper_version=build.wrapper_version,
        eval_suite_version=build.eval_suite_version,
        scoring_policy_version=build.scoring_policy_version,
        runner_version=build.runner_version,
        verification_level=build.verification_level,
        files=files,
        hash_algorithm="sha256",
        signature={
            "level": "Unsigned Local",
            "covers": ["manifest", "file_hashes", "score", "trace_references"],
        },
    )
    _write_json(artifact_dir / "manifest.json", manifest.to_dict())

    if archive:
        archive_path = (
            output_path if output_path.suffix == ".eslams" else output_path.with_suffix(".eslams")
        )
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(artifact_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(artifact_dir).as_posix())
        return archive_path
    return artifact_dir


class ArtifactValidator:
    def validate(self, path: Path) -> list[str]:
        artifact_dir, cleanup = _materialize(path)
        try:
            return self._validate_dir(artifact_dir)
        finally:
            if cleanup:
                shutil.rmtree(artifact_dir, ignore_errors=True)

    def _validate_dir(self, artifact_dir: Path) -> list[str]:
        errors: list[str] = []
        missing = sorted(rel for rel in REQUIRED_FILES if not (artifact_dir / rel).exists())
        errors.extend(f"missing required file: {rel}" for rel in missing)
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            return errors
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [*errors, f"manifest is invalid JSON: {exc}"]
        if manifest.get("artifact_version") != ARTIFACT_VERSION:
            errors.append("manifest.artifact_version is unsupported")
        file_entries = manifest.get("files")
        if not isinstance(file_entries, list):
            errors.append("manifest.files must be a list")
            return errors
        for entry in file_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                errors.append("manifest.files contains invalid entry")
                continue
            file_path = artifact_dir / entry["path"]
            if not file_path.exists():
                errors.append(f"manifest file missing on disk: {entry['path']}")
                continue
            expected = entry.get("sha256")
            actual = sha256_file(file_path)
            if expected != actual:
                errors.append(f"hash mismatch for {entry['path']}")
        expected_artifact_id = sha256_json(sorted(file_entries, key=lambda item: item["path"]))
        if manifest.get("artifact_id") != expected_artifact_id:
            errors.append("manifest.artifact_id does not match file table")
        return errors


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _file_entries(artifact_dir: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            rel = path.relative_to(artifact_dir).as_posix()
            entries.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return sorted(entries, key=lambda item: item["path"])


def _materialize(path: Path) -> tuple[Path, bool]:
    path = path.resolve()
    if path.is_dir():
        return path, False
    if zipfile.is_zipfile(path):
        tmp = path.parent / f".{path.stem}.validate"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        return tmp, True
    raise FileNotFoundError(path)
