"""Runner/container input and output contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import RUNNER_JOB_SCHEMA_VERSION
from eslams.hashing import sha256_json

FAILURE_CATEGORIES: tuple[str, ...] = (
    "provider_timeout",
    "runner_timeout",
    "artifact_validation_failed",
    "illegal_action",
    "no_action",
    "state_hash_invalid",
    "gateway_auth_failed",
    "runner_signature_missing",
)

RETRY_RECOMMENDATIONS: tuple[str, ...] = (
    "rerun_after_repair",
    "record_non_scoring_result",
    "retry_with_reviewed_policy",
    "do_not_retry",
)


@dataclass(frozen=True)
class RunnerJobRequest:
    job_id: str
    arena_id: str
    seed: int
    agents: dict[str, dict[str, Any]]
    artifact_output: dict[str, Any]
    suite_context: dict[str, Any] = field(default_factory=dict)
    case_id: str | None = None
    model_id: str | None = None
    time_budget_ms: int = 30_000
    shard_index: int | None = None
    shard_count: int | None = None
    policy_ids: list[str] = field(default_factory=list)
    schema_version: str = RUNNER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "arena_id": self.arena_id,
            "seed": self.seed,
            "agents": dict(self.agents),
            "artifact_output": dict(self.artifact_output),
            "suite_context": dict(self.suite_context),
            "case_id": self.case_id,
            "model_id": self.model_id,
            "time_budget_ms": self.time_budget_ms,
            "shard_index": self.shard_index,
            "shard_count": self.shard_count,
            "policy_ids": list(self.policy_ids),
        }


@dataclass(frozen=True)
class RunnerJobResult:
    job_id: str
    runner_completed: bool
    scoring_eligible: bool
    artifact_uri: str | None
    failure_category: str | None = None
    retry_recommendation: str | None = None
    artifact_key: str | None = None
    validation_status: str | None = None
    scoring_safety_reason: str | None = None
    runner_error: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUNNER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "runner_completed": self.runner_completed,
            "scoring_eligible": self.scoring_eligible,
            "artifact_uri": self.artifact_uri,
            "failure_category": self.failure_category,
            "retry_recommendation": self.retry_recommendation,
            "artifact_key": self.artifact_key,
            "validation_status": self.validation_status,
            "scoring_safety_reason": self.scoring_safety_reason,
            "runner_error": dict(self.runner_error),
        }


@dataclass(frozen=True)
class RunnerHealthPayload:
    core_commit: str | None
    core_version: str
    registry_hash: str
    game_count: int
    renderer_vocabulary_hash: str
    action_schema_hash: str
    schema_version: str = RUNNER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "core_commit": self.core_commit,
            "core_version": self.core_version,
            "registry_hash": self.registry_hash,
            "game_count": self.game_count,
            "renderer_vocabulary_hash": self.renderer_vocabulary_hash,
            "action_schema_hash": self.action_schema_hash,
        }


@dataclass(frozen=True)
class ArenaBrowserStartResponse:
    created: bool
    existing: bool
    session_id: str
    current_turn: int
    state_hash: str
    legal_action_count: int
    replay_readiness: str
    idempotency_key: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUNNER_JOB_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created": self.created,
            "existing": self.existing,
            "session_id": self.session_id,
            "current_turn": self.current_turn,
            "state_hash": self.state_hash,
            "legal_action_count": self.legal_action_count,
            "replay_readiness": self.replay_readiness,
            "idempotency_key": dict(self.idempotency_key),
        }


def validate_runner_job_result(result: RunnerJobResult) -> list[str]:
    errors: list[str] = []
    if result.runner_completed and not result.artifact_uri:
        errors.append("completed runner result without artifact_uri is invalid")
    if result.failure_category is not None and result.failure_category not in FAILURE_CATEGORIES:
        errors.append("failure_category is unsupported")
    if (
        result.retry_recommendation is not None
        and result.retry_recommendation not in RETRY_RECOMMENDATIONS
    ):
        errors.append("retry_recommendation is unsupported")
    return errors


def runner_health_payload(
    *,
    core_commit: str | None,
    core_version: str,
    registry_rows: list[dict[str, Any]],
    game_ids: list[str],
    renderer_vocabulary: list[str],
    action_schemas: list[dict[str, Any]],
) -> RunnerHealthPayload:
    return RunnerHealthPayload(
        core_commit=core_commit,
        core_version=core_version,
        registry_hash=sha256_json(registry_rows),
        game_count=len(game_ids),
        renderer_vocabulary_hash=sha256_json(sorted(renderer_vocabulary)),
        action_schema_hash=sha256_json(action_schemas),
    )


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        RUNNER_JOB_SCHEMA_VERSION: RunnerJobRequest(
            job_id="job_example",
            arena_id="tic-tac-toe",
            seed=1,
            agents={"player_1": {"kind": "builtin", "id": "first-legal"}},
            artifact_output={"kind": "local_path", "path": "runs/job_example.eslams"},
            case_id="case_example",
            model_id="builtin:first-legal",
            policy_ids=["public-smoke-v1"],
        ).to_dict()
    }
