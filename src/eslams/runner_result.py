"""Runner job result construction from completed artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eslams.artifacts import ArtifactValidator, read_member
from eslams.contracts.runner_job import RunnerJobResult, validate_runner_job_result


def runner_job_result_from_artifact(
    *,
    artifact_path: Path,
    artifact_uri: str,
    job_id: str,
) -> RunnerJobResult:
    report = ArtifactValidator().validate_report(artifact_path, profile="auto")
    manifest = _read_manifest(artifact_path)
    scoring_eligible = report.valid and report.per_case_scoring_eligible is True
    failure_category = None
    retry_recommendation = None
    if not report.valid:
        failure_category = "artifact_validation_failed"
        retry_recommendation = "record_non_scoring_result"
    elif not scoring_eligible:
        retry_recommendation = "record_non_scoring_result"
    result = RunnerJobResult(
        job_id=job_id,
        runner_completed=True,
        scoring_eligible=scoring_eligible,
        artifact_uri=artifact_uri,
        failure_category=failure_category,
        retry_recommendation=retry_recommendation,
        artifact_key=report.artifact_id,
        validation_status="valid" if report.valid else "invalid",
        scoring_safety_reason=_optional_str(manifest.get("scoring_safety_reason"))
        or _optional_str(manifest.get("invalid_reason"))
        or report.aggregate_ineligibility_reason,
        runner_error={} if report.valid else {"validation_errors": list(report.errors)},
    )
    errors = validate_runner_job_result(result)
    if errors:
        raise ValueError("; ".join(errors))
    return result


def _read_manifest(artifact_path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_member(artifact_path, "manifest.json").decode("utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
