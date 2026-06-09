"""Deterministic official and showcase evaluation plan contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import (
    EVAL_PLAN_SCHEMA_VERSION,
    EVAL_PROGRESS_SCHEMA_VERSION,
    EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
)
from eslams.hashing import sha256_json


@dataclass(frozen=True)
class EvalPlanEnvelope:
    kind: str
    generated_at: str
    suite_fingerprint: str
    core_version: str
    runner_version: str
    registry_hash: str
    selected_providers: list[str]
    selected_models: list[str]
    selected_arenas: list[str]
    case_count_expected: int
    shards: list[dict[str, Any]]
    required_environment_names: list[str] = field(default_factory=list)
    output_references: list[dict[str, Any]] = field(default_factory=list)
    policy_ids: list[str] = field(default_factory=list)
    schema_version: str = EVAL_PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "generated_at": self.generated_at,
            "suite_fingerprint": self.suite_fingerprint,
            "core_version": self.core_version,
            "runner_version": self.runner_version,
            "registry_hash": self.registry_hash,
            "selected_providers": list(self.selected_providers),
            "selected_models": list(self.selected_models),
            "selected_arenas": list(self.selected_arenas),
            "case_count_expected": self.case_count_expected,
            "shards": list(self.shards),
            "required_environment_names": list(self.required_environment_names),
            "output_references": list(self.output_references),
            "policy_ids": list(self.policy_ids),
        }
        payload["plan_hash"] = sha256_json(payload)
        return payload


def no_secret_examples() -> dict[str, dict[str, Any]]:
    plan = EvalPlanEnvelope(
        kind="official",
        generated_at="1970-01-01T00:00:00Z",
        suite_fingerprint="suite-example",
        core_version="0.3.0",
        runner_version="eslams-runner:0.3.0",
        registry_hash="registry-example",
        selected_providers=["mock"],
        selected_models=["mock:legal-action"],
        selected_arenas=["tic-tac-toe"],
        case_count_expected=1,
        shards=[{"shard_index": 0, "shard_count": 1, "case_count": 1}],
    ).to_dict()
    progress = {
        "schema_version": EVAL_PROGRESS_SCHEMA_VERSION,
        "plan_hash": plan["plan_hash"],
        "current_case": "case-example",
        "total_cases": 1,
        "completed_cases": 1,
        "failed_cases": 0,
        "skipped_cases": 0,
        "case_rate": 1.0,
        "provider_latency_rolling_stats": {
            "count": 1,
            "min_ms": 10,
            "max_ms": 10,
            "mean_ms": 10.0,
        },
        "estimated_remaining_time_seconds": 0.0,
    }
    resume = {
        "schema_version": EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION,
        "records": [
            {
                "resume_key": "resume-key-example",
                "invariant": {
                    "case_id": "case-example",
                    "artifact_digest": "artifact-digest-example",
                    "model_id": "mock:legal-action",
                    "suite_fingerprint": "suite-example",
                    "runner_version": "eslams-runner:0.3.0",
                    "plan_hash": plan["plan_hash"],
                },
                "artifact_path": "runs/case-example.eslams",
                "status": "completed",
                "validation_status": "valid",
                "metadata": {},
            }
        ],
    }
    return {
        EVAL_PLAN_SCHEMA_VERSION: plan,
        EVAL_PROGRESS_SCHEMA_VERSION: progress,
        EVAL_RESUME_CHECKPOINT_SCHEMA_VERSION: resume,
    }
