"""Eval resume checkpoints and progress events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eslams.contracts.versions import (
    EVAL_PROGRESS_SCHEMA_VERSION,
    EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
)
from eslams.hashing import canonical_json, sha256_json

PROGRESS_SCHEMA_VERSION = EVAL_PROGRESS_SCHEMA_VERSION
RESUME_CHECKPOINT_SCHEMA_VERSION = EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION


@dataclass(frozen=True)
class ResumeInvariant:
    case_id: str
    artifact_digest: str
    model_id: str
    suite_fingerprint: str
    runner_version: str
    plan_hash: str

    @property
    def resume_key(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "artifact_digest": self.artifact_digest,
            "model_id": self.model_id,
            "suite_fingerprint": self.suite_fingerprint,
            "runner_version": self.runner_version,
            "plan_hash": self.plan_hash,
        }


@dataclass(frozen=True)
class ResumeCheckpointRecord:
    invariant: ResumeInvariant
    artifact_path: str
    status: str = "completed"
    validation_status: str = "valid"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resume_key": self.invariant.resume_key,
            "invariant": self.invariant.to_dict(),
            "artifact_path": self.artifact_path,
            "status": self.status,
            "validation_status": self.validation_status,
            "metadata": dict(self.metadata),
        }


def write_resume_checkpoint(path: Path, records: list[ResumeCheckpointRecord]) -> Path:
    payload = {
        "schema_version": RESUME_CHECKPOINT_SCHEMA_VERSION,
        "records": [
            record.to_dict()
            for record in sorted(records, key=lambda item: item.invariant.case_id)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return path


def load_resume_checkpoint(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("resume checkpoint must be a JSON object")
    if payload.get("schema_version") != RESUME_CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("resume checkpoint schema_version is unsupported")
    return payload


def should_skip_case(checkpoint: dict[str, Any], invariant: ResumeInvariant) -> bool:
    for record in checkpoint_records(checkpoint):
        if record.get("resume_key") != invariant.resume_key:
            continue
        if record.get("status") != "completed":
            return False
        if record.get("validation_status") != "valid":
            return False
        return record.get("invariant") == invariant.to_dict()
    return False


def checkpoint_records(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    records = checkpoint.get("records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def plan_case_ids(plan: dict[str, Any]) -> list[str]:
    case_ids: list[str] = []
    shards = plan.get("shards")
    if not isinstance(shards, list):
        return []
    for shard in shards:
        if not isinstance(shard, dict):
            continue
        values = shard.get("case_ids")
        if isinstance(values, list):
            case_ids.extend(str(value) for value in values)
    return sorted(case_ids)


def progress_event(
    *,
    plan: dict[str, Any],
    current_case: str | None,
    completed_cases: int,
    failed_cases: int,
    skipped_cases: int,
    elapsed_seconds: float,
    provider_latencies_ms: list[int] | None = None,
) -> dict[str, Any]:
    total_cases = int(plan.get("case_count_expected") or len(plan_case_ids(plan)))
    processed = completed_cases + failed_cases + skipped_cases
    case_rate = processed / elapsed_seconds if elapsed_seconds > 0 else None
    remaining = max(total_cases - processed, 0)
    estimated_remaining_time_seconds = (
        remaining / case_rate if case_rate and case_rate > 0 else None
    )
    latencies = provider_latencies_ms or []
    return {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "plan_hash": plan.get("plan_hash"),
        "current_case": current_case,
        "total_cases": total_cases,
        "completed_cases": completed_cases,
        "failed_cases": failed_cases,
        "skipped_cases": skipped_cases,
        "case_rate": case_rate,
        "provider_latency_rolling_stats": _latency_stats(latencies),
        "estimated_remaining_time_seconds": estimated_remaining_time_seconds,
    }


def append_progress_event(path: Path, event: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(event) + "\n")
    return path


def _latency_stats(latencies: list[int]) -> dict[str, Any]:
    if not latencies:
        return {
            "count": 0,
            "min_ms": None,
            "max_ms": None,
            "mean_ms": None,
        }
    return {
        "count": len(latencies),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "mean_ms": sum(latencies) / len(latencies),
    }
