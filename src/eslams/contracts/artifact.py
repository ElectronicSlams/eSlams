"""Artifact-facing contracts shared by runner, validator, and Platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    OFFICIAL_RESULT_SCHEMA_VERSION,
)

ARTIFACT_PROFILES: tuple[str, ...] = (
    "runner_bundle",
    "public_replay_package",
    "official_bundle",
    "battlefield_bundle",
)
ARTIFACT_KINDS: tuple[str, ...] = (
    "local_match",
    "official_eval_case",
    "battlefield_match",
    "arena_session",
    "uploaded_replay",
)

VALIDATION_PROFILES: tuple[str, ...] = (*ARTIFACT_PROFILES, "auto")

ARTIFACT_COMPATIBILITY_MAP: dict[str, str] = {
    "artifact_version": "manifest_schema_version",
    "match_valid_for_scoring": "scoring.valid_for_scoring",
    "invalid_reason": "scoring.invalid_reason",
    "verification_level": "verification.level",
    "deterministic_replay.status": "replay.deterministic_status",
    "signature.status": "runner_signature_status",
    "arena_version": "arena.id_and_version",
    "agent_version": "model_identity_by_player",
}


@dataclass(frozen=True)
class PublicResultSummary:
    run_id: str
    arena_id: str
    winner: str | None
    outcome: dict[str, Any] | None
    score: dict[str, Any]
    reason: str | None
    valid_for_scoring: bool
    scoring_safety_reason: str | None
    schema_version: str = OFFICIAL_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "arena_id": self.arena_id,
            "winner": self.winner,
            "outcome": self.outcome,
            "score": self.score,
            "reason": self.reason,
            "valid_for_scoring": self.valid_for_scoring,
            "scoring_safety_reason": self.scoring_safety_reason,
        }


@dataclass(frozen=True)
class PublicArtifactManifest:
    run_id: str
    artifact_id: str
    arena_id: str
    artifact_profile: str
    artifact_kind: str
    replay_manifest_path: str
    replay_events_path: str
    public_result_summary_path: str
    receipts_public: bool = False
    schema_version: str = ARTIFACT_MANIFEST_SCHEMA_VERSION
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "arena_id": self.arena_id,
            "artifact_profile": self.artifact_profile,
            "artifact_kind": self.artifact_kind,
            "replay_manifest_path": self.replay_manifest_path,
            "replay_events_path": self.replay_events_path,
            "public_result_summary_path": self.public_result_summary_path,
            "receipts_public": self.receipts_public,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ArtifactValidationSummary:
    artifact: str
    profile: str
    valid: bool
    validation_status: str
    errors: list[str]
    run_id: str | None = None
    artifact_id: str | None = None
    verification_level: str | None = None
    replay_status: str | None = None
    scoring_eligible: bool | None = None
    runner_signature_status: str | None = None
    archive_sha256: str | None = None
    artifact_size_bytes: int | None = None
    schema_version: str = ARTIFACT_VALIDATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact": self.artifact,
            "profile": self.profile,
            "valid": self.valid,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "verification_level": self.verification_level,
            "replay_status": self.replay_status,
            "scoring_eligible": self.scoring_eligible,
            "runner_signature_status": self.runner_signature_status,
            "archive_sha256": self.archive_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    """Return small public fixtures used by schema/export tests."""

    return {
        ARTIFACT_MANIFEST_SCHEMA_VERSION: {
            "manifest_schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "artifact_profile": "runner_bundle",
            "artifact_kind": "local_match",
            "run_id": "run_example",
            "artifact_id": "sha256-example",
            "files": [],
        },
        ARTIFACT_VALIDATION_SCHEMA_VERSION: ArtifactValidationSummary(
            artifact="example.eslams",
            profile="runner_bundle",
            valid=True,
            validation_status="valid",
            errors=[],
            run_id="run_example",
            artifact_id="sha256-example",
            verification_level="Local Artifact",
            replay_status="verified",
            scoring_eligible=True,
            runner_signature_status="unsigned",
        ).to_dict(),
        OFFICIAL_RESULT_SCHEMA_VERSION: PublicResultSummary(
            run_id="run_example",
            arena_id="tic-tac-toe",
            winner="player_1",
            outcome={"winner": "player_1", "reason": "three_in_a_row"},
            score={
                "primary_score": 1.0,
                "scores_by_player": {"player_1": 1.0, "player_2": 0.0},
            },
            reason="three_in_a_row",
            valid_for_scoring=True,
            scoring_safety_reason=None,
        ).to_dict(),
    }
