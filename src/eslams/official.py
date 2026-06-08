"""Official result merge helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eslams.artifacts import ArtifactValidator, extract_provider_usage, read_member
from eslams.contracts.versions import OFFICIAL_RESULT_SCHEMA_VERSION
from eslams.hashing import canonical_json


def merge_official_results(run_dir: Path, output_path: Path) -> Path:
    artifacts = _artifact_inputs(run_dir)
    rows: list[dict[str, Any]] = []
    aggregate_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    valid_count = 0
    signature_status_counts: dict[str, int] = {}
    for artifact in artifacts:
        validation = ArtifactValidator().validate_report(artifact, profile="auto")
        summary = _read_optional_json(artifact, "public/public_result_summary.json")
        if validation.valid:
            valid_count += 1
        signature_status_counts[validation.signature.status] = (
            signature_status_counts.get(validation.signature.status, 0) + 1
        )
        usage = extract_provider_usage(artifact)["usage"]
        for key in aggregate_usage:
            value = usage.get(key)
            if isinstance(value, int):
                aggregate_usage[key] += value
        rows.append(
            {
                "artifact": str(artifact),
                "artifact_id": validation.artifact_id,
                "run_id": validation.run_id,
                "arena_id": summary.get("arena_id") if summary else None,
                "winner": summary.get("winner") if summary else None,
                "valid_for_scoring": summary.get("valid_for_scoring") if summary else None,
                "validation_status": "valid" if validation.valid else "invalid",
                "runner_signature_status": validation.signature.status,
            }
        )
    payload = {
        "schema_version": OFFICIAL_RESULT_SCHEMA_VERSION,
        "case_counts": {
            "total": len(rows),
            "valid": valid_count,
            "invalid": len(rows) - valid_count,
        },
        "scoring_eligibility": {
            "eligible": sum(1 for row in rows if row["valid_for_scoring"] is True),
            "non_scoring": sum(1 for row in rows if row["valid_for_scoring"] is False),
        },
        "aggregate_usage": aggregate_usage,
        "aggregate_cost": _cost_unavailable(),
        "proof_counts": {
            "artifacts": len(rows),
            "validated_artifacts": valid_count,
        },
        "signature_status_counts": signature_status_counts,
        "rows": rows,
        "audit_links": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    return output_path


def _artifact_inputs(run_dir: Path) -> list[Path]:
    artifacts = []
    for path in sorted(run_dir.iterdir()):
        if path.name.startswith("latest.eslams"):
            continue
        if path.name.endswith(".eslams") or path.name.endswith(".eslams.d"):
            if path.name.endswith(".eslams.d") and path.with_suffix("").exists():
                continue
            artifacts.append(path.resolve())
    return artifacts


def _read_optional_json(artifact_path: Path, member: str) -> dict[str, Any] | None:
    try:
        value = json.loads(read_member(artifact_path, member).decode("utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _cost_unavailable() -> dict[str, Any]:
    return {
        "status": "cost_unavailable",
        "pricing_table_version": None,
        "currency": "USD",
        "billable_token_categories": [],
        "source": "not_configured",
        "unavailable_reason": "pricing_not_configured",
    }
