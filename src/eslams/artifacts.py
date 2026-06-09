"""Artifact writer and validator for .eslams proof packages."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from eslams.contracts.artifact import (
    ARTIFACT_PROFILES,
    PublicArtifactManifest,
    PublicResultSummary,
)
from eslams.contracts.replay import PublicReasoningRow, PublicReplayManifest, ReplayParticipant
from eslams.contracts.safety import scan_public_payload
from eslams.contracts.versions import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    OFFICIAL_RESULT_SCHEMA_VERSION,
    REPLAY_MANIFEST_SCHEMA_VERSION,
)
from eslams.events import ReplayEvent, ScoreSummary, TraceEvent
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.policy import artifact_profile_label as policy_artifact_profile_label
from eslams.policy import policy_key, policy_label
from eslams.replay import render_replay_html
from eslams.replay_projection import display_frame_rows

ARTIFACT_VERSION = "eslams-artifact-v1"
RUNNER_SIGNATURE_VERSION = "eslams-runner-signature-v1"
RUNNER_SIGNATURE_ALGORITHM = "hmac-sha256"
RUNNER_SIGNATURE_PATH = "signatures/runner_signature.json"
RUNNER_SIGNING_KEY_ENV = "RUNNER_SIGNING_KEY"
RUNNER_SIGNING_KEY_ID_ENV = "RUNNER_SIGNING_KEY_ID"
DETERMINISTIC_REPLAY_VERSION = "eslams-deterministic-replay-v1"
REQUIRED_FILES = {
    "manifest.json",
    "traces/public_trace.jsonl",
    "traces/agent_visible_trace.jsonl",
    "traces/private_judge_trace.jsonl",
    "traces/auditor_trace.jsonl",
    "replay/replay_events.jsonl",
    "replay/display_frames.jsonl",
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
PUBLIC_REPLAY_PACKAGE_REQUIRED_FILES = {
    "manifest.json",
    "replay/replay_events.jsonl",
    "replay/display_frames.jsonl",
    "replay/replay_manifest.json",
}
PUBLIC_SUMMARY_FILES = {
    "public/public_manifest.json",
    "public/public_result_summary.json",
    "validation/validation_summary.json",
    "scores/official_result.json",
}
PROFILE_REQUIRED_FILES = {
    "runner_bundle": REQUIRED_FILES,
    "official_bundle": REQUIRED_FILES | {"scores/official_result.json"},
    "battlefield_bundle": REQUIRED_FILES
    | {"public/public_manifest.json", "public/public_result_summary.json"},
    "public_replay_package": PUBLIC_REPLAY_PACKAGE_REQUIRED_FILES,
}
PROFILE_ALIASES = {
    "runner-bundle": "runner_bundle",
    "official-bundle": "official_bundle",
    "battlefield-bundle": "battlefield_bundle",
    "public-replay-package": "public_replay_package",
    "auto": "auto",
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
    verification_level_key: str
    verification_level_label: str
    artifact_profile_key: str
    artifact_profile_label: str
    scoring_policy_key: str
    scoring_policy_label: str
    deterministic_replay: dict[str, Any]
    match_valid_for_scoring: bool
    invalid_reason: str | None
    per_case_run_valid: bool
    per_case_scoring_eligible: bool
    proof_row_publication_eligible: bool
    aggregate_leaderboard_eligible: bool
    aggregate_ineligibility_reason: str | None
    agent_error_count_by_player: dict[str, int]
    illegal_action_count_by_player: dict[str, int]
    fallback_action_count_by_player: dict[str, int]
    provider_status_by_player: dict[str, str]
    files: list[dict[str, Any]]
    hash_algorithm: str
    signature: dict[str, Any]
    manifest_schema_version: str = ARTIFACT_MANIFEST_SCHEMA_VERSION
    artifact_profile: str = "runner_bundle"
    artifact_kind: str = "local_match"
    model_identity_by_player: dict[str, Any] = field(default_factory=dict)
    run_metadata: dict[str, Any] = field(default_factory=dict)
    scoring_safety_reason: str | None = None
    runner_signature_status: str = "unsigned"
    public_exports: dict[str, Any] = field(default_factory=dict)
    validation_summary_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "artifact_version": self.artifact_version,
            "artifact_profile": self.artifact_profile,
            "artifact_kind": self.artifact_kind,
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "agent_version": self.agent_version,
            "arena_version": self.arena_version,
            "model_identity_by_player": self.model_identity_by_player,
            "run_metadata": self.run_metadata,
            "wrapper_version": self.wrapper_version,
            "eval_suite_version": self.eval_suite_version,
            "scoring_policy_version": self.scoring_policy_version,
            "runner_version": self.runner_version,
            "verification_level": self.verification_level,
            "verification_level_key": self.verification_level_key,
            "verification_level_label": self.verification_level_label,
            "artifact_profile_key": self.artifact_profile_key,
            "artifact_profile_label": self.artifact_profile_label,
            "scoring_policy_key": self.scoring_policy_key,
            "scoring_policy_label": self.scoring_policy_label,
            "deterministic_replay": self.deterministic_replay,
            "match_valid_for_scoring": self.match_valid_for_scoring,
            "invalid_reason": self.invalid_reason,
            "per_case_run_valid": self.per_case_run_valid,
            "per_case_scoring_eligible": self.per_case_scoring_eligible,
            "proof_row_publication_eligible": self.proof_row_publication_eligible,
            "aggregate_leaderboard_eligible": self.aggregate_leaderboard_eligible,
            "aggregate_ineligibility_reason": self.aggregate_ineligibility_reason,
            "agent_error_count_by_player": self.agent_error_count_by_player,
            "illegal_action_count_by_player": self.illegal_action_count_by_player,
            "fallback_action_count_by_player": self.fallback_action_count_by_player,
            "provider_status_by_player": self.provider_status_by_player,
            "scoring_safety_reason": self.scoring_safety_reason,
            "runner_signature_status": self.runner_signature_status,
            "public_exports": self.public_exports,
            "validation_summary_path": self.validation_summary_path,
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
    provider_receipts: list[dict[str, Any]] = field(default_factory=list)
    run_metadata: dict[str, Any] = field(default_factory=dict)
    wrapper_version: str = "legal_action_v1:1.0.0"
    eval_suite_version: str = "public-smoke:1.0.0"
    scoring_policy_version: str = "standard-score:1.0.0"
    runner_version: str = "eslams-runner:0.2.0"
    verification_level: str = "Local Artifact"


@dataclass(frozen=True)
class SignatureValidationStatus:
    status: str
    path: str | None = None
    algorithm: str | None = None
    key_id: str | None = None
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "verified": self.verified,
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.algorithm is not None:
            payload["algorithm"] = self.algorithm
        if self.key_id is not None:
            payload["key_id"] = self.key_id
        return payload


@dataclass(frozen=True)
class DeterministicReplayValidationStatus:
    status: str
    verified: bool = False
    arena_id: str | None = None
    action_event_count: int | None = None
    replay_event_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "verified": self.verified,
        }
        if self.arena_id is not None:
            payload["arena_id"] = self.arena_id
        if self.action_event_count is not None:
            payload["action_event_count"] = self.action_event_count
        if self.replay_event_count is not None:
            payload["replay_event_count"] = self.replay_event_count
        return payload


@dataclass(frozen=True)
class ArtifactValidationReport:
    errors: list[str]
    signature: SignatureValidationStatus
    deterministic_replay: DeterministicReplayValidationStatus
    profile: str = "runner_bundle"
    artifact: str | None = None
    artifact_id: str | None = None
    run_id: str | None = None
    verification_level: str | None = None
    scoring_eligible: bool | None = None
    archive_sha256: str | None = None
    artifact_size_bytes: int | None = None
    verification_level_key: str | None = None
    verification_level_label: str | None = None
    artifact_profile_key: str | None = None
    artifact_profile_label: str | None = None
    per_case_run_valid: bool | None = None
    per_case_scoring_eligible: bool | None = None
    proof_row_publication_eligible: bool | None = None
    aggregate_leaderboard_eligible: bool | None = None
    aggregate_ineligibility_reason: str | None = None
    schema_version: str = ARTIFACT_VALIDATION_SCHEMA_VERSION

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "valid": self.valid,
            "validation_status": "valid" if self.valid else "invalid",
            "profile": self.profile,
            "artifact": self.artifact,
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "verification_level": self.verification_level,
            "scoring_eligible": self.scoring_eligible,
            "archive_sha256": self.archive_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "verification_level_key": self.verification_level_key,
            "verification_level_label": self.verification_level_label,
            "artifact_profile_key": self.artifact_profile_key,
            "artifact_profile_label": self.artifact_profile_label,
            "per_case_run_valid": self.per_case_run_valid,
            "per_case_scoring_eligible": self.per_case_scoring_eligible,
            "proof_row_publication_eligible": self.proof_row_publication_eligible,
            "aggregate_leaderboard_eligible": self.aggregate_leaderboard_eligible,
            "aggregate_ineligibility_reason": self.aggregate_ineligibility_reason,
            "signature": self.signature.to_dict(),
            "runner_signature_status": self.signature.status,
            "deterministic_replay": self.deterministic_replay.to_dict(),
            "replay_status": self.deterministic_replay.status,
        }
        if self.errors:
            payload["errors"] = self.errors
        else:
            payload["errors"] = []
        return payload


def write_artifact(build: ArtifactBuildInput, output_path: Path, *, archive: bool = False) -> Path:
    """Write a directory artifact or zip-compatible .eslams archive."""

    output_path = output_path.resolve()
    artifact_dir = expanded_artifact_path(output_path)
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
    _write_jsonl(
        artifact_dir / "replay/display_frames.jsonl",
        display_frame_rows(build.replay_events),
    )
    arena_id = _arena_id_from_version(build.arena_version)
    replay_manifest = _public_replay_manifest(build, arena_id)
    _write_json(artifact_dir / "replay/replay_manifest.json", replay_manifest)
    _write_jsonl(
        artifact_dir / "public_reasoning/reasoning.jsonl",
        _public_reasoning_rows(build.replay_events),
    )
    render_replay_html(artifact_dir)
    _write_json(artifact_dir / "scores/score.json", build.score.to_dict())
    _write_json(
        artifact_dir / "scores/official_result.json",
        _official_result_summary(build.score, arena_id),
    )
    _write_json(artifact_dir / "scores/metrics.json", build.metrics)
    (artifact_dir / "logs/runner.log").write_text(build.runner_log, encoding="utf-8")
    _write_jsonl(artifact_dir / "logs/agent_io.jsonl", build.agent_io)
    _write_jsonl(artifact_dir / "logs/errors.jsonl", build.errors)
    _write_jsonl(artifact_dir / "receipts/provider_receipts.jsonl", build.provider_receipts)
    _write_json(
        artifact_dir / "environment/lockfile.json",
        {"python": ">=3.9", "package": "eslams-core"},
    )
    (artifact_dir / "environment/container_digest.txt").write_text(
        "local-development\n",
        encoding="utf-8",
    )
    _write_json(artifact_dir / "environment/package_versions.json", {"eslams-core": "0.2.0"})
    _write_json(
        artifact_dir / "broadcast/broadcast_manifest.json",
        {
            "broadcast_version": "eslams-broadcast-v1",
            "run_id": build.run_id,
            "vod_available": False,
            "broadcastVideoAvailable": False,
        },
    )
    _write_json(
        artifact_dir / "broadcast/vod_metadata.json",
        {
            "status": "not_requested",
            "failure_reason": "video_generation_not_owned_by_core",
        },
    )
    _write_json(
        artifact_dir / "public/public_result_summary.json",
        _public_result_summary(build.score, arena_id).to_dict(),
    )
    _write_json(
        artifact_dir / "public/public_manifest.json",
        PublicArtifactManifest(
            run_id=build.run_id,
            artifact_id="see-manifest",
            arena_id=arena_id,
            artifact_profile="runner_bundle",
            artifact_kind="local_match",
            replay_manifest_path="replay/replay_manifest.json",
            replay_events_path="replay/replay_events.jsonl",
            display_frames_path="replay/display_frames.jsonl",
            public_result_summary_path="public/public_result_summary.json",
            notes=["Artifact id is recorded in manifest.json to avoid recursive hashing."],
        ).to_dict(),
    )
    _write_json(
        artifact_dir / "validation/validation_summary.json",
        {
            "schema_version": ARTIFACT_VALIDATION_SCHEMA_VERSION,
            "artifact": str(output_path),
            "profile": "runner_bundle",
            "artifact_profile_key": "runner_bundle",
            "artifact_profile_label": "Runner Bundle",
            "valid": True,
            "validation_status": "not_validated_at_write_time",
            "errors": [],
            "run_id": build.run_id,
            "artifact_id": "see-manifest",
            "verification_level": build.verification_level,
            "verification_level_key": policy_key(
                build.verification_level,
                fallback="local_artifact",
            ),
            "verification_level_label": build.verification_level,
            "replay_status": "recorded",
            "scoring_eligible": build.score.match_valid_for_scoring,
            "per_case_run_valid": build.score.match_valid_for_scoring,
            "per_case_scoring_eligible": build.score.match_valid_for_scoring,
            "proof_row_publication_eligible": True,
            "aggregate_leaderboard_eligible": False,
            "aggregate_ineligibility_reason": "single_case_not_full_suite",
            "runner_signature_status": "pending",
        },
    )

    signing_key = _runner_signing_key()
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
        verification_level_key=policy_key(build.verification_level, fallback="local_artifact"),
        verification_level_label=build.verification_level,
        artifact_profile_key="runner_bundle",
        artifact_profile_label=policy_artifact_profile_label("runner_bundle"),
        scoring_policy_key=policy_key(build.scoring_policy_version, fallback="standard_score"),
        scoring_policy_label=policy_label(build.scoring_policy_version, fallback="Standard Score"),
        deterministic_replay={
            "version": DETERMINISTIC_REPLAY_VERSION,
            "status": "recorded",
            "source": "traces/auditor_trace.jsonl",
            "action_event_count": len(build.trace_events),
            "replay_event_count": len(build.replay_events),
            "checks": [
                "auditor_state_chain",
                "registered_arena_transition",
                "public_replay_snapshot",
            ],
        },
        match_valid_for_scoring=build.score.match_valid_for_scoring,
        invalid_reason=build.score.invalid_reason,
        per_case_run_valid=build.score.match_valid_for_scoring,
        per_case_scoring_eligible=build.score.match_valid_for_scoring,
        proof_row_publication_eligible=True,
        aggregate_leaderboard_eligible=False,
        aggregate_ineligibility_reason="single_case_not_full_suite",
        agent_error_count_by_player=build.score.agent_error_count_by_player,
        illegal_action_count_by_player=build.score.illegal_action_count_by_player,
        fallback_action_count_by_player=build.score.fallback_action_count_by_player,
        provider_status_by_player=build.score.provider_status_by_player,
        scoring_safety_reason=build.score.scoring_safety_reason,
        runner_signature_status="signed" if signing_key is not None else "unsigned",
        model_identity_by_player=_model_identity_by_player(build.agent_version),
        run_metadata={
            "time_source": "system_utc",
            "artifact_writer": "eslams-core",
            **build.run_metadata,
        },
        public_exports={
            "public_manifest": "public/public_manifest.json",
            "public_result_summary": "public/public_result_summary.json",
            "public_replay_manifest": "replay/replay_manifest.json",
            "public_replay_events": "replay/replay_events.jsonl",
            "public_display_frames": "replay/display_frames.jsonl",
            "public_reasoning": "public_reasoning/reasoning.jsonl",
        },
        validation_summary_path="validation/validation_summary.json",
        files=files,
        hash_algorithm="sha256",
        signature=_manifest_signature_metadata(signed=signing_key is not None),
    )
    manifest_dict = manifest.to_dict()
    manifest_path = artifact_dir / "manifest.json"
    _write_json(manifest_path, manifest_dict)
    if signing_key is not None:
        signature_path = artifact_dir / RUNNER_SIGNATURE_PATH
        signature_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(signature_path, _runner_signature(manifest_path, manifest_dict, signing_key))

    if archive:
        archive_path = archive_artifact_path(output_path)
        if archive_path.exists():
            archive_path.unlink()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(artifact_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(artifact_dir).as_posix())
        return archive_path
    return artifact_dir


def archive_artifact_path(path: Path) -> Path:
    """Return the canonical .eslams archive path for an artifact output path."""

    if path.suffix == ".eslams":
        return path
    if path.name.endswith(".eslams.d"):
        return path.with_suffix("")
    return path.with_suffix(".eslams")


def expanded_artifact_path(path: Path) -> Path:
    """Return the canonical expanded .eslams.d path for an artifact output path."""

    if path.name.endswith(".eslams.d"):
        return path
    return archive_artifact_path(path).with_suffix(".eslams.d")


@contextmanager
def open_artifact(path: Path) -> Iterator[Path]:
    """Materialize an artifact archive or directory for read-only inspection."""

    artifact_dir, cleanup = _materialize(path)
    try:
        yield artifact_dir
    finally:
        if cleanup:
            shutil.rmtree(artifact_dir, ignore_errors=True)


def read_member(path: Path, member: str) -> bytes:
    """Read a member from an expanded or archived artifact."""

    member_path = _safe_artifact_subpath(member)
    if member_path is None:
        raise ValueError(f"invalid artifact member path {member!r}")
    path = path.resolve()
    if path.is_dir():
        return (path / member_path).read_bytes()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return zf.read(member_path.as_posix())
    raise FileNotFoundError(path)


def extract_validation_summary(path: Path) -> dict[str, Any] | None:
    return _extract_json_member(path, "validation/validation_summary.json")


def extract_provider_usage(path: Path) -> dict[str, Any]:
    rows = _extract_jsonl_member(path, "receipts/provider_receipts.jsonl")
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    unavailable_reasons: list[str] = []
    for row in rows:
        usage = row.get("usage")
        if not isinstance(usage, dict):
            reason = row.get("usage_unavailable_reason")
            if isinstance(reason, str):
                unavailable_reasons.append(reason)
            continue
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return {
        "usage": totals,
        "usage_unavailable_reasons": sorted(set(unavailable_reasons)),
        "receipt_count": len(rows),
    }


def extract_public_manifest(path: Path) -> dict[str, Any] | None:
    return _extract_json_member(path, "public/public_manifest.json")


class ArtifactValidator:
    def validate(self, path: Path, *, profile: str = "runner_bundle") -> list[str]:
        return self.validate_report(path, profile=profile).errors

    def validate_report(
        self,
        path: Path,
        *,
        profile: str = "runner_bundle",
    ) -> ArtifactValidationReport:
        artifact_dir, cleanup = _materialize(path)
        try:
            normalized_profile = _normalize_validation_profile(profile, artifact_dir)
            return self._validate_dir(artifact_dir, normalized_profile, path.resolve())
        finally:
            if cleanup:
                shutil.rmtree(artifact_dir, ignore_errors=True)

    def _validate_dir(
        self,
        artifact_dir: Path,
        profile: str,
        source_path: Path,
    ) -> ArtifactValidationReport:
        errors: list[str] = []
        required_files = PROFILE_REQUIRED_FILES[profile]
        missing = sorted(rel for rel in required_files if not (artifact_dir / rel).exists())
        errors.extend(f"missing required file: {rel}" for rel in missing)
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            return _validation_report(
                errors=errors,
                signature=SignatureValidationStatus(status="not_checked"),
                deterministic_replay=DeterministicReplayValidationStatus(status="not_checked"),
                profile=profile,
                source_path=source_path,
                artifact_dir=artifact_dir,
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return _validation_report(
                errors=[*errors, f"manifest is invalid JSON: {exc}"],
                signature=SignatureValidationStatus(status="not_checked"),
                deterministic_replay=DeterministicReplayValidationStatus(status="not_checked"),
                profile=profile,
                source_path=source_path,
                artifact_dir=artifact_dir,
            )
        if manifest.get("artifact_version") != ARTIFACT_VERSION:
            errors.append("manifest.artifact_version is unsupported")
        manifest_schema_version = manifest.get("manifest_schema_version")
        if (
            manifest_schema_version is not None
            and manifest_schema_version != ARTIFACT_MANIFEST_SCHEMA_VERSION
        ):
            errors.append("manifest.manifest_schema_version is unsupported")
        file_entries = manifest.get("files")
        if not isinstance(file_entries, list):
            errors.append("manifest.files must be a list")
            signature_status, signature_errors = _validate_runner_signature(
                artifact_dir,
                manifest,
                manifest_path,
            )
            errors.extend(signature_errors)
            replay_status, replay_errors = _profile_replay_validation(
                artifact_dir,
                manifest,
                profile,
            )
            errors.extend(replay_errors)
            errors.extend(
                _profile_specific_errors(artifact_dir, manifest, profile, signature_status)
            )
            errors.extend(_public_safety_errors(artifact_dir, profile))
            return _validation_report(
                errors=errors,
                signature=signature_status,
                deterministic_replay=replay_status,
                profile=profile,
                source_path=source_path,
                artifact_dir=artifact_dir,
                manifest=manifest,
            )
        errors.extend(_validate_file_table(artifact_dir, manifest, file_entries))
        signature_status, signature_errors = _validate_runner_signature(
            artifact_dir,
            manifest,
            manifest_path,
        )
        errors.extend(signature_errors)
        replay_status, replay_errors = _profile_replay_validation(
            artifact_dir,
            manifest,
            profile,
        )
        errors.extend(replay_errors)
        errors.extend(_profile_specific_errors(artifact_dir, manifest, profile, signature_status))
        errors.extend(_public_safety_errors(artifact_dir, profile))
        return _validation_report(
            errors=errors,
            signature=signature_status,
            deterministic_replay=replay_status,
            profile=profile,
            source_path=source_path,
            artifact_dir=artifact_dir,
            manifest=manifest,
        )


def _normalize_validation_profile(profile: str, artifact_dir: Path) -> str:
    normalized = PROFILE_ALIASES.get(profile, profile).replace("-", "_")
    if normalized == "auto":
        manifest_path = artifact_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return "runner_bundle"
            artifact_profile = manifest.get("artifact_profile")
            if isinstance(artifact_profile, str):
                candidate = PROFILE_ALIASES.get(artifact_profile, artifact_profile).replace(
                    "-",
                    "_",
                )
                if candidate in PROFILE_REQUIRED_FILES:
                    return candidate
        return "runner_bundle"
    if normalized not in PROFILE_REQUIRED_FILES:
        valid = ", ".join(sorted((*ARTIFACT_PROFILES, "auto")))
        raise ValueError(f"validation profile must be one of: {valid}")
    return normalized


def _validate_file_table(
    artifact_dir: Path,
    manifest: dict[str, Any],
    file_entries: list[Any],
) -> list[str]:
    errors: list[str] = []
    valid_entries: list[dict[str, Any]] = []
    for entry in file_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append("manifest.files contains invalid entry")
            continue
        valid_entries.append(entry)
        file_path = artifact_dir / entry["path"]
        if not file_path.exists():
            errors.append(f"manifest file missing on disk: {entry['path']}")
            continue
        expected = entry.get("sha256")
        actual = sha256_file(file_path)
        if expected != actual:
            errors.append(f"hash mismatch for {entry['path']}")
    expected_artifact_id = sha256_json(sorted(valid_entries, key=lambda item: item["path"]))
    if manifest.get("artifact_id") != expected_artifact_id:
        errors.append("manifest.artifact_id does not match file table")
    return errors


def _profile_replay_validation(
    artifact_dir: Path,
    manifest: dict[str, Any],
    profile: str,
) -> tuple[DeterministicReplayValidationStatus, list[str]]:
    if profile == "public_replay_package":
        errors: list[str] = []
        replay_rows = _read_jsonl(artifact_dir / "replay/replay_events.jsonl", errors)
        replay_count = len(replay_rows) if replay_rows is not None else None
        replay_manifest_path = artifact_dir / "replay/replay_manifest.json"
        try:
            replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"replay/replay_manifest.json cannot be read: {exc}")
            replay_manifest = {}
        if (
            isinstance(replay_manifest, dict)
            and replay_manifest.get("schema_version") not in {None, REPLAY_MANIFEST_SCHEMA_VERSION}
        ):
            errors.append("replay manifest schema_version is unsupported")
        return (
            DeterministicReplayValidationStatus(
                status="not_required_for_public_profile" if not errors else "invalid",
                verified=not errors,
                replay_event_count=replay_count,
            ),
            errors,
        )
    return _validate_deterministic_replay(artifact_dir, manifest)


def _profile_specific_errors(
    artifact_dir: Path,
    manifest: dict[str, Any],
    profile: str,
    signature: SignatureValidationStatus,
) -> list[str]:
    errors: list[str] = []
    if profile == "official_bundle":
        if signature.status in {"unsigned", "missing", "not_checked"}:
            errors.append("runner_signature_missing")
        if not (artifact_dir / "scores/official_result.json").exists():
            errors.append("missing required file: scores/official_result.json")
    if profile == "public_replay_package":
        artifact_profile = manifest.get("artifact_profile")
        if artifact_profile not in {None, "public_replay_package", "uploaded_replay"}:
            errors.append("public replay package has incompatible artifact_profile")
    return errors


def _public_safety_errors(artifact_dir: Path, profile: str) -> list[str]:
    errors: list[str] = []
    candidates = [
        "replay/replay_events.jsonl",
        "replay/replay_manifest.json",
        "replay/display_frames.jsonl",
        "public/public_manifest.json",
        "public/public_result_summary.json",
        "public_reasoning/reasoning.jsonl",
    ]
    if profile == "public_replay_package":
        candidates.append("manifest.json")
    for rel in candidates:
        path = artifact_dir / rel
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            rows = _read_public_jsonl(path)
            for row_index, row in enumerate(rows):
                for issue in scan_public_payload(row, root=f"{rel}[{row_index}]"):
                    errors.append(
                        f"unsafe public payload key in {rel}: {issue.path} ({issue.key})"
                    )
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel} is invalid JSON: {exc}")
            continue
        for issue in scan_public_payload(payload, root=rel):
            errors.append(f"unsafe public payload key in {rel}: {issue.path} ({issue.key})")
    return errors


def _read_public_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"invalid_json_line": line_number})
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _extract_json_member(path: Path, member: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(read_member(path, member).decode("utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _extract_jsonl_member(path: Path, member: str) -> list[dict[str, Any]]:
    try:
        lines = read_member(path, member).decode("utf-8").splitlines()
    except (OSError, KeyError):
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _validation_report(
    *,
    errors: list[str],
    signature: SignatureValidationStatus,
    deterministic_replay: DeterministicReplayValidationStatus,
    profile: str,
    source_path: Path,
    artifact_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> ArtifactValidationReport:
    return ArtifactValidationReport(
        errors=errors,
        signature=signature,
        deterministic_replay=deterministic_replay,
        profile=profile,
        artifact=str(source_path),
        artifact_id=_optional_manifest_str(manifest, "artifact_id"),
        run_id=_optional_manifest_str(manifest, "run_id"),
        verification_level=_optional_manifest_str(manifest, "verification_level"),
        scoring_eligible=_optional_manifest_bool(manifest, "match_valid_for_scoring"),
        archive_sha256=_artifact_source_hash(source_path, artifact_dir),
        artifact_size_bytes=_artifact_source_size(source_path, artifact_dir),
        verification_level_key=_optional_manifest_str(manifest, "verification_level_key"),
        verification_level_label=_optional_manifest_str(manifest, "verification_level_label"),
        artifact_profile_key=_optional_manifest_str(manifest, "artifact_profile_key") or profile,
        artifact_profile_label=_optional_manifest_str(manifest, "artifact_profile_label")
        or policy_artifact_profile_label(profile),
        per_case_run_valid=_optional_manifest_bool(manifest, "per_case_run_valid"),
        per_case_scoring_eligible=_optional_manifest_bool(
            manifest,
            "per_case_scoring_eligible",
        ),
        proof_row_publication_eligible=_optional_manifest_bool(
            manifest,
            "proof_row_publication_eligible",
        ),
        aggregate_leaderboard_eligible=_optional_manifest_bool(
            manifest,
            "aggregate_leaderboard_eligible",
        ),
        aggregate_ineligibility_reason=_optional_manifest_str(
            manifest,
            "aggregate_ineligibility_reason",
        ),
    )


def _optional_manifest_str(manifest: dict[str, Any] | None, key: str) -> str | None:
    if manifest is None:
        return None
    value = manifest.get(key)
    return value if isinstance(value, str) else None


def _optional_manifest_bool(manifest: dict[str, Any] | None, key: str) -> bool | None:
    if manifest is None:
        return None
    value = manifest.get(key)
    return value if isinstance(value, bool) else None


def _artifact_source_hash(source_path: Path, artifact_dir: Path) -> str | None:
    if source_path.is_file():
        return sha256_file(source_path)
    if artifact_dir.is_dir():
        return sha256_json(_file_entries(artifact_dir))
    return None


def _artifact_source_size(source_path: Path, artifact_dir: Path) -> int | None:
    if source_path.is_file():
        return source_path.stat().st_size
    if artifact_dir.is_dir():
        return sum(path.stat().st_size for path in artifact_dir.rglob("*") if path.is_file())
    return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _arena_id_from_version(arena_version: str) -> str:
    return arena_version.split(":", 1)[0] if ":" in arena_version else arena_version


def _model_identity_by_player(agent_version: str) -> dict[str, dict[str, str]]:
    identities: dict[str, dict[str, str]] = {}
    for item in agent_version.split(";"):
        parts = item.split(":")
        if len(parts) < 3:
            continue
        player_id = parts[0]
        identities[player_id] = {
            "agent_id": parts[1],
            "agent_version": ":".join(parts[2:]),
        }
    return identities


def _public_replay_manifest(build: ArtifactBuildInput, arena_id: str) -> dict[str, Any]:
    event_count = len(build.replay_events)
    move_frame_count = sum(1 for event in build.replay_events if event.action is not None)
    state_frame_count = sum(1 for event in build.replay_events if event.public_state)
    visible_frame_count = sum(1 for event in build.replay_events if event.visibility == "public")
    setup_only = move_frame_count == 0
    timeline_completeness = "setup_only" if setup_only else "playable"
    reasoning_count = sum(1 for event in build.replay_events if event.public_reasoning_ref)
    participants = [
        ReplayParticipant(
            player_id=player_id,
            seat=player_id,
            label=player_id.replace("_", " ").title(),
            model_identity=_model_identity_by_player(build.agent_version).get(player_id, {}),
        )
        for player_id in sorted(build.score.scores_by_player)
    ]
    return PublicReplayManifest(
        replay_id=f"{build.run_id}:public-replay",
        run_id=build.run_id,
        arena_id=arena_id,
        variant_id="default",
        event_count=event_count,
        visible_frame_count=visible_frame_count,
        state_frame_count=state_frame_count,
        move_frame_count=move_frame_count,
        setup_only=setup_only,
        timeline_completeness=timeline_completeness,
        renderer_kind="eslams-html-v1",
        render_hints_version="render-hints-v1",
        public_state_shape_version="public-state-v1",
        has_public_state=state_frame_count > 0,
        state_hash_valid=True,
        participants=participants,
        showcase_ready=not setup_only and visible_frame_count >= 2,
        minimum_autoplay_frames=2,
        autoplay_ready=not setup_only and visible_frame_count >= 2,
        reasoning_frame_coverage=(
            reasoning_count / move_frame_count if move_frame_count else 0.0
        ),
    ).to_dict()


def _public_reasoning_rows(replay_events: list[ReplayEvent]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in replay_events:
        if event.action is None:
            continue
        rows.append(
            PublicReasoningRow(
                turn=event.turn_id,
                seat=event.seat,
                actor_player=event.actor_player,
                action=event.action,
                state_hash_before=event.state_hash_before,
                state_hash_after=event.state_hash_after,
                public_explanation=None,
                source_event_id=event.event_id,
            ).to_dict()
        )
    return rows


def _public_result_summary(score: ScoreSummary, arena_id: str) -> PublicResultSummary:
    reason = None
    if score.outcome and isinstance(score.outcome.get("reason"), str):
        reason = cast(str, score.outcome["reason"])
    return PublicResultSummary(
        run_id=score.run_id,
        arena_id=arena_id,
        winner=score.winner,
        outcome=score.outcome,
        score={
            "primary_score": score.primary_score,
            "scores_by_player": score.scores_by_player,
        },
        reason=reason,
        valid_for_scoring=score.match_valid_for_scoring,
        scoring_safety_reason=score.scoring_safety_reason,
        per_case_run_valid=score.match_valid_for_scoring,
        per_case_scoring_eligible=score.match_valid_for_scoring,
        proof_row_publication_eligible=True,
        aggregate_leaderboard_eligible=False,
        aggregate_ineligibility_reason="single_case_not_full_suite",
    )


def _official_result_summary(score: ScoreSummary, arena_id: str) -> dict[str, Any]:
    public_summary = _public_result_summary(score, arena_id).to_dict()
    return {
        **public_summary,
        "schema_version": OFFICIAL_RESULT_SCHEMA_VERSION,
        "case_counts": {
            "completed": 1,
            "failed": 0 if score.match_valid_for_scoring else 1,
            "non_scoring": 0 if score.match_valid_for_scoring else 1,
        },
        "aggregate_usage": score.aggregate_usage,
        "aggregate_cost": score.aggregate_cost,
        "proof_counts": {
            "artifact": 1,
            "public_replay": 1,
            "provider_receipt": 0,
        },
        "runner_signature_status": "pending",
        "audit_links": [],
    }


def _validate_deterministic_replay(
    artifact_dir: Path,
    manifest: dict[str, Any],
) -> tuple[DeterministicReplayValidationStatus, list[str]]:
    errors: list[str] = []
    deterministic_metadata_value = manifest.get("deterministic_replay")
    deterministic_metadata = (
        deterministic_metadata_value if isinstance(deterministic_metadata_value, dict) else None
    )
    required = (
        deterministic_metadata is not None
        and deterministic_metadata.get("status") == "recorded"
    )
    if (
        deterministic_metadata is not None
        and required
        and deterministic_metadata.get("version") != DETERMINISTIC_REPLAY_VERSION
    ):
        errors.append("deterministic replay version is unsupported")

    auditor_rows = _read_jsonl(artifact_dir / "traces/auditor_trace.jsonl", errors)
    replay_rows = _read_jsonl(artifact_dir / "replay/replay_events.jsonl", errors)
    if auditor_rows is None or replay_rows is None:
        return (
            DeterministicReplayValidationStatus(status="invalid"),
            errors,
        )

    action_rows = [row for row in auditor_rows if row.get("event_type") == "action"]
    has_state_snapshots = all(
        isinstance(row.get("state_before"), dict) and isinstance(row.get("state_after"), dict)
        for row in action_rows
    )
    if not action_rows and not required:
        return (
            DeterministicReplayValidationStatus(
                status="not_recorded",
                action_event_count=0,
                replay_event_count=len(replay_rows),
            ),
            errors,
        )
    if not has_state_snapshots:
        if required:
            errors.append("deterministic replay audit is missing auditor state snapshots")
            return (
                DeterministicReplayValidationStatus(
                    status="invalid",
                    action_event_count=len(action_rows),
                    replay_event_count=len(replay_rows),
                ),
                errors,
            )
        return (
            DeterministicReplayValidationStatus(
                status="not_recorded",
                action_event_count=len(action_rows),
                replay_event_count=len(replay_rows),
            ),
            errors,
        )

    arena_id = _artifact_arena_id(artifact_dir, manifest, errors)
    if arena_id is None:
        return (
            DeterministicReplayValidationStatus(
                status="invalid",
                action_event_count=len(action_rows),
                replay_event_count=len(replay_rows),
            ),
            errors,
        )

    from eslams.arenas import registry

    try:
        arena = registry.create(arena_id)
    except KeyError as exc:
        errors.append(f"deterministic replay arena is unavailable: {exc}")
        return (
            DeterministicReplayValidationStatus(
                status="invalid",
                arena_id=arena_id,
                action_event_count=len(action_rows),
                replay_event_count=len(replay_rows),
            ),
            errors,
        )

    _validate_deterministic_replay_counts(
        deterministic_metadata,
        action_rows,
        replay_rows,
        errors,
    )
    if len(replay_rows) != len(action_rows) + 1:
        errors.append("deterministic replay event count does not match action trace length")

    previous_state = None
    for index, row in enumerate(action_rows):
        state_before = _arena_state_from_payload(
            row.get("state_before"),
            f"auditor trace event {index} state_before",
            errors,
        )
        state_after = _arena_state_from_payload(
            row.get("state_after"),
            f"auditor trace event {index} state_after",
            errors,
        )
        if state_before is None or state_after is None:
            continue

        if previous_state is not None and state_before.state_hash != previous_state.state_hash:
            errors.append(
                f"auditor trace event {index} state_before does not continue prior state"
            )
        if row.get("turn_id") != state_before.turn:
            errors.append(f"auditor trace event {index} turn_id does not match state_before")
        if row.get("active_player") != state_before.active_player:
            errors.append(
                f"auditor trace event {index} active_player does not match state_before"
            )
        if row.get("state_hash_before") != state_before.state_hash:
            errors.append(
                f"auditor trace event {index} state_hash_before does not match state_before"
            )
        if row.get("state_hash_after") != state_after.state_hash:
            errors.append(
                f"auditor trace event {index} state_hash_after does not match state_after"
            )

        _compare_replay_snapshot(replay_rows, index, state_before, errors)
        recorded_action = row.get("action")
        action = _resolve_recorded_action(
            legal_actions=arena.legal_actions_for(state_before, state_before.active_player),
            recorded_action=recorded_action,
        )
        if not arena.is_legal(state_before, state_before.active_player, action):
            errors.append(f"auditor trace event {index} action is not legal for state_before")
            previous_state = state_after
            continue
        try:
            computed_state = arena.apply_action(state_before, state_before.active_player, action)
        except Exception as exc:  # pragma: no cover - defensive validation path
            errors.append(f"auditor trace event {index} action replay failed: {exc}")
            previous_state = state_after
            continue

        if computed_state.state_hash != state_after.state_hash:
            errors.append(
                f"auditor trace event {index} state_after does not match replayed action"
            )
        if not _canonical_equal(computed_state.to_dict(), state_after.to_dict()):
            errors.append(
                f"auditor trace event {index} state_after payload does not match replayed action"
            )
        _compare_replay_snapshot(replay_rows, index + 1, computed_state, errors)
        previous_state = state_after

    status = "verified" if not errors else "invalid"
    return (
        DeterministicReplayValidationStatus(
            status=status,
            verified=not errors,
            arena_id=arena_id,
            action_event_count=len(action_rows),
            replay_event_count=len(replay_rows),
        ),
        errors,
    )


def _read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]] | None:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"{path.relative_to(path.parents[2]).as_posix()} cannot be read: {exc}")
        return None
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name} line {line_number} is invalid JSON: {exc}")
            return None
        if not isinstance(row, dict):
            errors.append(f"{path.name} line {line_number} must be a JSON object")
            return None
        rows.append(row)
    return rows


def _artifact_arena_id(
    artifact_dir: Path,
    manifest: dict[str, Any],
    errors: list[str],
) -> str | None:
    score_path = artifact_dir / "scores/score.json"
    try:
        score = json.loads(score_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"scores/score.json cannot be read for deterministic replay: {exc}")
        return None
    if isinstance(score, dict) and isinstance(score.get("arena_id"), str):
        return cast(str, score["arena_id"])
    arena_version = manifest.get("arena_version")
    if isinstance(arena_version, str) and ":" in arena_version:
        return arena_version.split(":", 1)[0]
    errors.append("deterministic replay arena_id is missing")
    return None


def _validate_deterministic_replay_counts(
    deterministic_metadata: Any,
    action_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    errors: list[str],
) -> None:
    if not isinstance(deterministic_metadata, dict):
        return
    action_count = deterministic_metadata.get("action_event_count")
    replay_count = deterministic_metadata.get("replay_event_count")
    if isinstance(action_count, int) and action_count != len(action_rows):
        errors.append("deterministic replay action_event_count does not match auditor trace")
    if isinstance(replay_count, int) and replay_count != len(replay_rows):
        errors.append("deterministic replay replay_event_count does not match replay trace")


def _arena_state_from_payload(
    payload: Any,
    context: str,
    errors: list[str],
) -> Any | None:
    if not isinstance(payload, dict):
        errors.append(f"{context} must be a JSON object")
        return None
    try:
        from eslams.state import ArenaState

        return ArenaState(
            state_id=payload["state_id"],
            turn=payload["turn"],
            active_player=payload["active_player"],
            public_state=payload["public_state"],
            private_state_by_player=payload["private_state_by_player"],
            legal_actions_by_player=payload["legal_actions_by_player"],
            scores=payload["scores"],
            terminal=payload["terminal"],
            outcome=payload["outcome"],
            rng_commitment=payload["rng_commitment"],
            render_hints=payload["render_hints"],
            metadata=payload.get("metadata", {}),
            state_hash=payload.get("state_hash"),
        )
    except KeyError as exc:
        errors.append(f"{context} is missing field {exc}")
    except (TypeError, ValueError) as exc:
        errors.append(f"{context} is invalid: {exc}")
    return None


def _resolve_recorded_action(*, legal_actions: list[Any], recorded_action: Any) -> Any:
    recorded_json = json.loads(canonical_json(recorded_action))
    for action in legal_actions:
        if action == recorded_action:
            return action
        if json.loads(canonical_json(action)) == recorded_json:
            return action
    return recorded_action


def _canonical_equal(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def _compare_replay_snapshot(
    replay_rows: list[dict[str, Any]],
    index: int,
    state: Any,
    errors: list[str],
) -> None:
    if index >= len(replay_rows):
        errors.append(f"replay event {index} is missing")
        return
    replay = replay_rows[index]
    expected = {
        "state_hash": state.state_hash,
        "active_player": state.active_player,
        "public_state": state.public_state,
        "scores": state.scores,
        "terminal": state.terminal,
        "render_hints": state.render_hints,
    }
    for key, value in expected.items():
        if not _canonical_equal(replay.get(key), value):
            errors.append(f"replay event {index} {key} does not match deterministic state")
    if replay.get("turn_id") != state.turn:
        errors.append(f"replay event {index} turn_id does not match deterministic state")


def _file_entries(artifact_dir: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(artifact_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(artifact_dir).as_posix()
            if rel == "manifest.json" or rel.startswith("signatures/"):
                continue
            entries.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return sorted(entries, key=lambda item: item["path"])


def _manifest_signature_metadata(*, signed: bool) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "level": "Runner Signed" if signed else "Unsigned Local",
        "status": "signed" if signed else "unsigned",
        "covers": ["manifest_sha256", "artifact_id", "artifact_version", "run_id"],
    }
    if signed:
        metadata["algorithm"] = RUNNER_SIGNATURE_ALGORITHM
        metadata["signature_path"] = RUNNER_SIGNATURE_PATH
    return metadata


def _runner_signature(
    manifest_path: Path,
    manifest: dict[str, Any],
    signing_key: str,
) -> dict[str, Any]:
    signed_at = utc_now_iso()
    key_id = os.environ.get(RUNNER_SIGNING_KEY_ID_ENV, "runner-env-key")
    signed_payload = _signature_payload(
        manifest=manifest,
        manifest_sha256=sha256_file(manifest_path),
        signed_at=signed_at,
        key_id=key_id,
    )
    return {
        "signature_version": RUNNER_SIGNATURE_VERSION,
        "status": "signed",
        "algorithm": RUNNER_SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "signed_at": signed_at,
        "signed_payload": signed_payload,
        "signature": _hmac_sha256(signing_key, signed_payload),
    }


def _signature_payload(
    *,
    manifest: dict[str, Any],
    manifest_sha256: str,
    signed_at: str,
    key_id: str,
) -> dict[str, Any]:
    return {
        "signature_version": RUNNER_SIGNATURE_VERSION,
        "algorithm": RUNNER_SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "signed_at": signed_at,
        "artifact_version": manifest.get("artifact_version"),
        "artifact_id": manifest.get("artifact_id"),
        "run_id": manifest.get("run_id"),
        "manifest_sha256": manifest_sha256,
    }


def _runner_signing_key() -> str | None:
    value = os.environ.get(RUNNER_SIGNING_KEY_ENV)
    if value == "":
        return None
    return value


def _hmac_sha256(signing_key: str, payload: dict[str, Any]) -> str:
    digest = hmac.new(
        signing_key.encode("utf-8"),
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{RUNNER_SIGNATURE_ALGORITHM}:{digest}"


def _validate_runner_signature(
    artifact_dir: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> tuple[SignatureValidationStatus, list[str]]:
    signature_metadata = manifest.get("signature")
    manifest_signature_status = None
    signature_rel = RUNNER_SIGNATURE_PATH
    if isinstance(signature_metadata, dict):
        status = signature_metadata.get("status")
        if isinstance(status, str):
            manifest_signature_status = status
        manifest_path_value = signature_metadata.get("signature_path")
        if isinstance(manifest_path_value, str):
            signature_rel = manifest_path_value

    signature_subpath = _safe_artifact_subpath(signature_rel)
    if signature_subpath is None:
        return (
            SignatureValidationStatus(status="invalid", path=signature_rel),
            ["runner signature path is invalid"],
        )

    signature_path = artifact_dir / signature_subpath
    if not signature_path.exists():
        if manifest_signature_status == "signed":
            return (
                SignatureValidationStatus(status="missing", path=signature_rel),
                ["runner signature is declared signed but the signature file is missing"],
            )
        return SignatureValidationStatus(status="unsigned"), []

    try:
        signature_record = json.loads(signature_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            SignatureValidationStatus(status="invalid", path=signature_rel),
            [f"runner signature is invalid JSON: {exc}"],
        )
    if not isinstance(signature_record, dict):
        return (
            SignatureValidationStatus(status="invalid", path=signature_rel),
            ["runner signature must be a JSON object"],
        )

    record_status = signature_record.get("status")
    if record_status == "unsigned":
        if manifest_signature_status == "signed":
            return (
                SignatureValidationStatus(status="invalid", path=signature_rel),
                ["runner signature is declared signed but the signature file is unsigned"],
            )
        return SignatureValidationStatus(status="unsigned", path=signature_rel), []
    if record_status != "signed":
        return (
            SignatureValidationStatus(status="invalid", path=signature_rel),
            ["runner signature status is unsupported"],
        )

    return _validate_signed_runner_signature(
        signature_record=cast(dict[str, Any], signature_record),
        signature_rel=signature_rel,
        manifest=manifest,
        manifest_path=manifest_path,
    )


def _validate_signed_runner_signature(
    *,
    signature_record: dict[str, Any],
    signature_rel: str,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> tuple[SignatureValidationStatus, list[str]]:
    errors: list[str] = []
    signature_version = signature_record.get("signature_version")
    algorithm = signature_record.get("algorithm")
    key_id = signature_record.get("key_id")
    signed_at = signature_record.get("signed_at")
    signed_payload = signature_record.get("signed_payload")
    signature_value = signature_record.get("signature")

    if signature_version != RUNNER_SIGNATURE_VERSION:
        errors.append("runner signature version is unsupported")
    if algorithm != RUNNER_SIGNATURE_ALGORITHM:
        errors.append("runner signature algorithm is unsupported")
    if not isinstance(key_id, str) or not key_id:
        errors.append("runner signature key_id must be a non-empty string")
        key_id = None
    if not isinstance(signed_at, str) or not signed_at:
        errors.append("runner signature signed_at must be a non-empty string")
        signed_at = None
    if not isinstance(signed_payload, dict):
        errors.append("runner signature signed_payload must be a JSON object")
    if not isinstance(signature_value, str) or not signature_value.startswith(
        f"{RUNNER_SIGNATURE_ALGORITHM}:"
    ):
        errors.append("runner signature value is missing or unsupported")

    status = SignatureValidationStatus(
        status="invalid",
        path=signature_rel,
        algorithm=algorithm if isinstance(algorithm, str) else None,
        key_id=key_id if isinstance(key_id, str) else None,
    )
    if errors:
        return status, errors

    expected_payload = _signature_payload(
        manifest=manifest,
        manifest_sha256=sha256_file(manifest_path),
        signed_at=cast(str, signed_at),
        key_id=cast(str, key_id),
    )
    signed_payload_dict = cast(dict[str, Any], signed_payload)
    if signed_payload_dict != expected_payload:
        return status, ["runner signature payload does not match manifest"]

    signing_key = _runner_signing_key()
    if signing_key is None:
        return (
            SignatureValidationStatus(
                status="unverified_missing_key",
                path=signature_rel,
                algorithm=RUNNER_SIGNATURE_ALGORITHM,
                key_id=cast(str, key_id),
            ),
            [],
        )

    expected_signature = _hmac_sha256(signing_key, signed_payload_dict)
    if not hmac.compare_digest(cast(str, signature_value), expected_signature):
        return status, ["runner signature verification failed"]
    return (
        SignatureValidationStatus(
            status="verified",
            path=signature_rel,
            algorithm=RUNNER_SIGNATURE_ALGORITHM,
            key_id=cast(str, key_id),
            verified=True,
        ),
        [],
    )


def _safe_artifact_subpath(rel: str) -> Path | None:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or rel == "":
        return None
    return path


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
