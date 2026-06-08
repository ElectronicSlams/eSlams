"""Deterministic JSON schema export for public eSlams contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eslams.contracts.versions import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    CATALOGUE_GAME_SCHEMA_VERSION,
    CATALOGUE_MODEL_SCHEMA_VERSION,
    EVAL_PLAN_SCHEMA_VERSION,
    EVAL_PROGRESS_SCHEMA_VERSION,
    EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
    OFFICIAL_RESULT_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
    PUBLICATION_BUNDLE_SCHEMA_VERSION,
    PUBLICATION_VALIDATION_SCHEMA_VERSION,
    REPLAY_MANIFEST_SCHEMA_VERSION,
    REPLAY_PUBLIC_SCHEMA_VERSION,
    RUNNER_JOB_SCHEMA_VERSION,
    schema_versions,
)
from eslams.hashing import canonical_json


def export_schemas(output_dir: Path) -> list[Path]:
    """Write every known contract schema with deterministic bytes."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for version in schema_versions():
        path = output_dir / schema_filename(version)
        path.write_text(canonical_json(schema_for_version(version)) + "\n", encoding="utf-8")
        written.append(path)
    return written


def schema_filename(version: str) -> str:
    return f"{version}.schema.json"


def schema_for_version(version: str) -> dict[str, Any]:
    schemas = _schemas()
    if version not in schemas:
        raise KeyError(f"unknown schema version {version!r}")
    return schemas[version]


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
            required=["schema_version", "run_id", "arena_id", "valid_for_scoring"],
            properties={
                "schema_version": {"const": OFFICIAL_RESULT_SCHEMA_VERSION},
                "run_id": {"type": "string"},
                "arena_id": {"type": "string"},
                "winner": {"type": ["string", "null"]},
                "valid_for_scoring": {"type": "boolean"},
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
                "plan_hash": {"type": ["string", "null"]},
                "suite_fingerprint": {"type": ["string", "null"]},
                "object_manifest_hash": {"type": "string"},
                "statement_projection_hash": {"type": "string"},
                "completed_object_count": {"type": "integer"},
                "completed_projection_chunk_count": {"type": "integer"},
                "artifact_count": {"type": "integer"},
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
            },
        ),
    }


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
