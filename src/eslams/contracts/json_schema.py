"""Deterministic JSON schema export for public eSlams contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from eslams.contracts.versions import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    CATALOGUE_AVAILABILITY_SCHEMA_VERSION,
    CATALOGUE_GAME_SCHEMA_VERSION,
    CATALOGUE_MODEL_SCHEMA_VERSION,
    CATALOGUE_RENDERER_SCHEMA_VERSION,
    CORE_PACKAGE_VERSION,
    EVAL_PLAN_SCHEMA_VERSION,
    EVAL_PROGRESS_SCHEMA_VERSION,
    EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
    OFFICIAL_RESULT_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
    PUBLICATION_BUNDLE_SCHEMA_VERSION,
    PUBLICATION_VALIDATION_SCHEMA_VERSION,
    REPLAY_DISPLAY_FRAME_SCHEMA_VERSION,
    REPLAY_MANIFEST_SCHEMA_VERSION,
    REPLAY_PUBLIC_SCHEMA_VERSION,
    RUNNER_JOB_SCHEMA_VERSION,
    SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION,
    SCHEMA_BUNDLE_VERSION,
    schema_versions,
)
from eslams.hashing import canonical_json, sha256_file, sha256_json

SCHEMA_BUNDLE_MANIFEST_FILENAME = "schema_bundle_manifest.json"
SCHEMA_BUNDLE_BUILD_ID = "1970-01-01T00:00:00Z"


def export_schemas(output_dir: Path) -> list[Path]:
    """Write every known contract schema with deterministic bytes."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for version in schema_versions():
        path = output_dir / schema_filename(version)
        path.write_text(canonical_json(schema_for_version(version)) + "\n", encoding="utf-8")
        written.append(path)
    manifest_path = output_dir / SCHEMA_BUNDLE_MANIFEST_FILENAME
    manifest_path.write_text(
        canonical_json(schema_bundle_manifest(written)) + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written


def schema_filename(version: str) -> str:
    return f"{version}.schema.json"


def schema_for_version(version: str) -> dict[str, Any]:
    schemas = _schemas()
    if version not in schemas:
        raise KeyError(f"unknown schema version {version!r}")
    return schemas[version]


def schema_bundle_manifest(schema_paths: list[Path]) -> dict[str, Any]:
    schema_rows = []
    for path in sorted(schema_paths, key=lambda item: item.name):
        if path.name == SCHEMA_BUNDLE_MANIFEST_FILENAME:
            continue
        version = path.name.removesuffix(".schema.json")
        schema_rows.append(
            {
                "name": path.name,
                "schema_version": version,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION,
        "core_package_version": CORE_PACKAGE_VERSION,
        "core_commit": _git_commit(),
        "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
        "deterministic_build_id": sha256_json(
            {
                "core_package_version": CORE_PACKAGE_VERSION,
                "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
                "schemas": schema_rows,
            }
        ),
        "generated_at": SCHEMA_BUNDLE_BUILD_ID,
        "schemas": schema_rows,
    }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION: {
            "schema_version": SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION,
            "core_package_version": CORE_PACKAGE_VERSION,
            "core_commit": "abcdef1234567890",
            "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
            "deterministic_build_id": "sha256:example",
            "generated_at": SCHEMA_BUNDLE_BUILD_ID,
            "schemas": [
                {
                    "name": "eslams.artifact.validation.v1.schema.json",
                    "schema_version": ARTIFACT_VALIDATION_SCHEMA_VERSION,
                    "sha256": "sha256:example",
                    "bytes": 123,
                }
            ],
        }
    }


def _schemas() -> dict[str, dict[str, Any]]:
    return {
        ARTIFACT_MANIFEST_SCHEMA_VERSION: _object_schema(
            ARTIFACT_MANIFEST_SCHEMA_VERSION,
            required=["manifest_schema_version", "artifact_profile", "artifact_kind", "run_id"],
            properties={
                "manifest_schema_version": {"const": ARTIFACT_MANIFEST_SCHEMA_VERSION},
                "artifact_profile": {"type": "string"},
                "artifact_kind": {"type": "string"},
                "run_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "verification_level_key": {"type": "string"},
                "verification_level_label": {"type": "string"},
                "artifact_profile_key": {"type": "string"},
                "artifact_profile_label": {"type": "string"},
                "scoring_policy_key": {"type": "string"},
                "scoring_policy_label": {"type": "string"},
                "per_case_run_valid": {"type": "boolean"},
                "per_case_scoring_eligible": {"type": "boolean"},
                "proof_row_publication_eligible": {"type": "boolean"},
                "aggregate_leaderboard_eligible": {"type": "boolean"},
                "aggregate_ineligibility_reason": {"type": ["string", "null"]},
                "files": {"type": "array"},
            },
        ),
        ARTIFACT_VALIDATION_SCHEMA_VERSION: _object_schema(
            ARTIFACT_VALIDATION_SCHEMA_VERSION,
            required=["schema_version", "artifact", "profile", "valid", "validation_status"],
            properties={
                "schema_version": {"const": ARTIFACT_VALIDATION_SCHEMA_VERSION},
                "artifact": {"type": "string"},
                "profile": {"type": "string"},
                "valid": {"type": "boolean"},
                "validation_status": {"type": "string"},
                "errors": {"type": "array", "items": {"type": "string"}},
                "signature": {"type": "object"},
                "deterministic_replay": {"type": "object"},
                "per_case_run_valid": {"type": ["boolean", "null"]},
                "per_case_scoring_eligible": {"type": ["boolean", "null"]},
                "proof_row_publication_eligible": {"type": ["boolean", "null"]},
                "aggregate_leaderboard_eligible": {"type": ["boolean", "null"]},
                "aggregate_ineligibility_reason": {"type": ["string", "null"]},
            },
        ),
        REPLAY_PUBLIC_SCHEMA_VERSION: _object_schema(
            REPLAY_PUBLIC_SCHEMA_VERSION,
            required=["schema_version", "event_id", "run_id", "turn_id", "public_safe"],
            properties={
                "schema_version": {"const": REPLAY_PUBLIC_SCHEMA_VERSION},
                "event_id": {"type": "string"},
                "run_id": {"type": "string"},
                "turn_id": {"type": "integer"},
                "actor_player": {"type": ["string", "null"]},
                "seat": {"type": ["string", "null"]},
                "public_safe": {"type": "boolean"},
            },
        ),
        REPLAY_MANIFEST_SCHEMA_VERSION: _object_schema(
            REPLAY_MANIFEST_SCHEMA_VERSION,
            required=["schema_version", "replay_id", "run_id", "event_count"],
            properties={
                "schema_version": {"const": REPLAY_MANIFEST_SCHEMA_VERSION},
                "replay_id": {"type": "string"},
                "run_id": {"type": "string"},
                "arena_id": {"type": "string"},
                "event_count": {"type": "integer"},
                "timeline_completeness": {"type": "string"},
                "participants": {"type": "array"},
            },
        ),
        REPLAY_DISPLAY_FRAME_SCHEMA_VERSION: _object_schema(
            REPLAY_DISPLAY_FRAME_SCHEMA_VERSION,
            required=[
                "schema_version",
                "frame_id",
                "renderer_family",
                "visibility",
                "source_replay_event_id",
            ],
            properties={
                "schema_version": {"const": REPLAY_DISPLAY_FRAME_SCHEMA_VERSION},
                "frame_id": {"type": "string"},
                "renderer_family": {"type": "string"},
                "visibility": {"type": "string"},
                "actor_player": {"type": ["string", "null"]},
                "action_label": {"type": ["string", "null"]},
                "display_cells": {"type": "array"},
                "summary": {"type": "object"},
                "source_replay_event_id": {"type": "string"},
            },
        ),
        PROVIDER_RECEIPT_SCHEMA_VERSION: _object_schema(
            PROVIDER_RECEIPT_SCHEMA_VERSION,
            required=["schema_version", "provider", "model", "outcome", "redaction_version"],
            properties={
                "schema_version": {"const": PROVIDER_RECEIPT_SCHEMA_VERSION},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "outcome": {"type": "string"},
                "usage": {"type": "object"},
                "estimated_cost": {"type": "object"},
                "redaction_version": {"type": "string"},
            },
        ),
        EVAL_PLAN_SCHEMA_VERSION: _object_schema(
            EVAL_PLAN_SCHEMA_VERSION,
            required=["schema_version", "kind", "plan_hash", "case_count_expected", "shards"],
            properties={
                "schema_version": {"const": EVAL_PLAN_SCHEMA_VERSION},
                "kind": {"type": "string"},
                "plan_hash": {"type": "string"},
                "case_count_expected": {"type": "integer"},
                "shards": {"type": "array"},
            },
        ),
        EVAL_PROGRESS_SCHEMA_VERSION: _object_schema(
            EVAL_PROGRESS_SCHEMA_VERSION,
            required=[
                "schema_version",
                "plan_hash",
                "total_cases",
                "completed_cases",
                "failed_cases",
                "skipped_cases",
            ],
            properties={
                "schema_version": {"const": EVAL_PROGRESS_SCHEMA_VERSION},
                "plan_hash": {"type": ["string", "null"]},
                "current_case": {"type": ["string", "null"]},
                "total_cases": {"type": "integer"},
                "completed_cases": {"type": "integer"},
                "failed_cases": {"type": "integer"},
                "skipped_cases": {"type": "integer"},
                "case_rate": {"type": ["number", "null"]},
                "provider_latency_rolling_stats": {"type": "object"},
                "estimated_remaining_time_seconds": {"type": ["number", "null"]},
            },
        ),
        EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION: _object_schema(
            EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
            required=["schema_version", "records"],
            properties={
                "schema_version": {"const": EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION},
                "records": {"type": "array"},
            },
        ),
        OFFICIAL_RESULT_SCHEMA_VERSION: _object_schema(
            OFFICIAL_RESULT_SCHEMA_VERSION,
            required=["schema_version"],
            properties={
                "schema_version": {"const": OFFICIAL_RESULT_SCHEMA_VERSION},
                "run_id": {"type": "string"},
                "arena_id": {"type": "string"},
                "winner": {"type": ["string", "null"]},
                "valid_for_scoring": {"type": "boolean"},
                "per_case_run_valid": {"type": "boolean"},
                "per_case_scoring_eligible": {"type": "boolean"},
                "proof_row_publication_eligible": {"type": "boolean"},
                "aggregate_leaderboard_eligible": {"type": "boolean"},
                "aggregate_ineligibility_reason": {"type": ["string", "null"]},
            },
        ),
        PUBLICATION_BUNDLE_SCHEMA_VERSION: _object_schema(
            PUBLICATION_BUNDLE_SCHEMA_VERSION,
            required=[
                "schema_version",
                "kind",
                "object_manifest_hash",
                "completed_object_count",
                "completed_projection_chunk_count",
            ],
            properties={
                "schema_version": {"const": PUBLICATION_BUNDLE_SCHEMA_VERSION},
                "kind": {"type": "string"},
                "publication_kind_key": {"type": "string"},
                "publication_kind_label": {"type": "string"},
                "plan_hash": {"type": ["string", "null"]},
                "suite_fingerprint": {"type": ["string", "null"]},
                "object_manifest_hash": {"type": "string"},
                "statement_projection_hash": {"type": "string"},
                "completed_object_count": {"type": "integer"},
                "completed_projection_chunk_count": {"type": "integer"},
                "artifact_count": {"type": "integer"},
                "aggregate_leaderboard_eligible": {"type": "boolean"},
                "aggregate_ineligibility_reason": {"type": ["string", "null"]},
            },
        ),
        PUBLICATION_VALIDATION_SCHEMA_VERSION: _object_schema(
            PUBLICATION_VALIDATION_SCHEMA_VERSION,
            required=["schema_version", "bundle_dir", "valid", "status", "errors"],
            properties={
                "schema_version": {"const": PUBLICATION_VALIDATION_SCHEMA_VERSION},
                "bundle_dir": {"type": "string"},
                "kind": {"type": ["string", "null"]},
                "valid": {"type": "boolean"},
                "status": {"type": "string"},
                "object_count": {"type": "integer"},
                "projection_chunk_count": {"type": "integer"},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
        ),
        RUNNER_JOB_SCHEMA_VERSION: _object_schema(
            RUNNER_JOB_SCHEMA_VERSION,
            required=["schema_version", "job_id", "arena_id", "artifact_output"],
            properties={
                "schema_version": {"const": RUNNER_JOB_SCHEMA_VERSION},
                "job_id": {"type": "string"},
                "arena_id": {"type": "string"},
                "artifact_output": {"type": "object"},
                "runner_completed": {"type": "boolean"},
                "scoring_eligible": {"type": "boolean"},
                "artifact_uri": {"type": ["string", "null"]},
                "validation_status": {"type": ["string", "null"]},
            },
        ),
        CATALOGUE_RENDERER_SCHEMA_VERSION: _object_schema(
            CATALOGUE_RENDERER_SCHEMA_VERSION,
            required=[
                "schema_version",
                "game_id",
                "renderer_family",
                "timeline_completeness",
                "public_safe",
            ],
            properties={
                "schema_version": {"const": CATALOGUE_RENDERER_SCHEMA_VERSION},
                "game_id": {"type": "string"},
                "renderer_family": {"type": "string"},
                "renderer_kind": {"type": "string"},
                "timeline_completeness": {"type": "string"},
                "replay_availability": {"type": "string"},
                "visible_frame_count": {"type": "integer"},
                "state_frame_count": {"type": "integer"},
                "move_frame_count": {"type": "integer"},
                "public_safe": {"type": "boolean"},
                "state_hash_valid": {"type": ["boolean", "null"]},
            },
        ),
        CATALOGUE_AVAILABILITY_SCHEMA_VERSION: _object_schema(
            CATALOGUE_AVAILABILITY_SCHEMA_VERSION,
            required=["schema_version", "provider", "model", "game_id", "status", "reason"],
            properties={
                "schema_version": {"const": CATALOGUE_AVAILABILITY_SCHEMA_VERSION},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "game_id": {"type": "string"},
                "status": {"type": "string"},
                "reason": {"type": ["string", "null"]},
            },
        ),
        SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION: _object_schema(
            SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION,
            required=[
                "schema_version",
                "core_package_version",
                "schema_bundle_version",
                "schemas",
            ],
            properties={
                "schema_version": {"const": SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION},
                "core_package_version": {"type": "string"},
                "core_commit": {"type": ["string", "null"]},
                "schema_bundle_version": {"type": "string"},
                "deterministic_build_id": {"type": "string"},
                "generated_at": {"type": "string"},
                "schemas": {"type": "array"},
            },
        ),
        CATALOGUE_GAME_SCHEMA_VERSION: _object_schema(
            CATALOGUE_GAME_SCHEMA_VERSION,
            required=["schema_version", "game_id", "display_name", "replay_availability"],
            properties={
                "schema_version": {"const": CATALOGUE_GAME_SCHEMA_VERSION},
                "game_id": {"type": "string"},
                "display_name": {"type": "string"},
                "replay_availability": {"type": "string"},
            },
        ),
        CATALOGUE_MODEL_SCHEMA_VERSION: _object_schema(
            CATALOGUE_MODEL_SCHEMA_VERSION,
            required=["schema_version", "provider", "model", "launch_status"],
            properties={
                "schema_version": {"const": CATALOGUE_MODEL_SCHEMA_VERSION},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "launch_status": {"type": "string"},
                "supported_reasoning_modes": {"type": "array"},
                "accepted_control_fields": {"type": "array"},
                "default_reasoning_track": {"type": ["string", "null"]},
                "reasoning_track_kind": {"type": "string"},
                "unsupported_reasoning_control_reason": {"type": ["string", "null"]},
                "http_agent_payload_guidance": {"type": "object"},
            },
        ),
    }


def _git_commit() -> str | None:
    root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def _object_schema(
    schema_id: str,
    *,
    required: list[str],
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://schemas.eslams.dev/{schema_id}.json",
        "title": schema_id,
        "type": "object",
        "additionalProperties": True,
        "required": required,
        "properties": properties,
    }
