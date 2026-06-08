"""Deterministic publication bundle exports without storage/database execution."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from eslams.artifacts import (
    ArtifactValidator,
    extract_provider_usage,
    extract_public_manifest,
    read_member,
)
from eslams.contracts.versions import (
    PUBLICATION_BUNDLE_SCHEMA_VERSION,
    PUBLICATION_VALIDATION_SCHEMA_VERSION,
)
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.public_replay import export_public_replay, validate_public_replay

PUBLICATION_KINDS = ("official-proof", "battlefield-sample", "uploaded-replay")
REQUIRED_BUNDLE_FILES: tuple[str, ...] = (
    "aggregate_usage.json",
    "bundle_manifest.json",
    "checkpoint_manifest.json",
    "leaderboard_rows.jsonl",
    "object_manifest.json",
    "proof_index.jsonl",
    "provider_model_rows.jsonl",
    "public_manifest.jsonl",
    "signature_readback_manifest.json",
)


def export_publication_bundle(
    *,
    kind: str,
    output_dir: Path,
    artifacts_dir: Path | None = None,
    artifact: Path | None = None,
    plan_path: Path | None = None,
) -> Path:
    if kind not in PUBLICATION_KINDS:
        valid = ", ".join(PUBLICATION_KINDS)
        raise ValueError(f"publication kind must be one of: {valid}")
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    artifacts = _artifact_inputs(artifacts_dir=artifacts_dir, artifact=artifact)
    plan_payload = _read_plan(plan_path)
    plan_hash = _plan_hash(plan_payload)
    suite_fingerprint = (
        plan_payload.get("suite_fingerprint") if isinstance(plan_payload, dict) else None
    )
    proof_rows: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    public_manifest_rows: list[dict[str, Any]] = []
    provider_model_rows: list[dict[str, Any]] = []
    aggregate_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }

    for index, artifact_path in enumerate(artifacts):
        public_dir = output_dir / "public_replays" / f"{index:05d}_{artifact_path.stem}"
        export_public_replay(artifact_path, public_dir)
        validation = ArtifactValidator().validate_report(artifact_path, profile="auto")
        public_manifest = extract_public_manifest(artifact_path)
        if public_manifest:
            public_manifest_rows.append(public_manifest)
        summary = _read_optional_json(artifact_path, "public/public_result_summary.json")
        if summary:
            leaderboard_rows.append(
                {
                    "run_id": summary.get("run_id"),
                    "arena_id": summary.get("arena_id"),
                    "winner": summary.get("winner"),
                    "valid_for_scoring": summary.get("valid_for_scoring"),
                    "source": "artifact_public_summary",
                    "proof_row": False,
                }
            )
        usage = extract_provider_usage(artifact_path)["usage"]
        for key in aggregate_usage:
            value = usage.get(key)
            if isinstance(value, int):
                aggregate_usage[key] += value
        proof_rows.append(
            {
                "artifact": str(artifact_path),
                "artifact_id": validation.artifact_id,
                "run_id": validation.run_id,
                "validation_status": "valid" if validation.valid else "invalid",
                "public_replay_path": public_dir.relative_to(output_dir).as_posix(),
                "evidence_row": True,
                "leaderboard_predicate": False,
            }
        )

    _write_jsonl(output_dir / "public_manifest.jsonl", public_manifest_rows)
    _write_jsonl(output_dir / "proof_index.jsonl", proof_rows)
    _write_jsonl(output_dir / "leaderboard_rows.jsonl", leaderboard_rows)
    _write_jsonl(output_dir / "provider_model_rows.jsonl", provider_model_rows)
    statement_projection_hash = sha256_json(
        {
            "public_manifest_rows": public_manifest_rows,
            "proof_rows": proof_rows,
            "leaderboard_rows": leaderboard_rows,
            "provider_model_rows": provider_model_rows,
        }
    )
    _write_json(
        output_dir / "aggregate_usage.json",
        {
            "usage": aggregate_usage,
            "pricing": _cost_unavailable(),
        },
    )
    object_manifest = _object_manifest(output_dir)
    _write_json(output_dir / "object_manifest.json", {"objects": object_manifest})
    checkpoint = {
        "completed_object_count": len(object_manifest),
        "completed_projection_chunk_count": 4,
        "object_manifest_hash": sha256_json(object_manifest),
        "statement_projection_hash": statement_projection_hash,
    }
    _write_json(output_dir / "checkpoint_manifest.json", checkpoint)
    _write_json(output_dir / "signature_readback_manifest.json", {"status": "not_signed_by_core"})
    bundle_manifest = {
        "schema_version": PUBLICATION_BUNDLE_SCHEMA_VERSION,
        "kind": kind,
        "plan_hash": plan_hash,
        "suite_fingerprint": suite_fingerprint,
        "object_manifest_hash": checkpoint["object_manifest_hash"],
        "statement_projection_hash": statement_projection_hash,
        "completed_object_count": checkpoint["completed_object_count"],
        "completed_projection_chunk_count": checkpoint["completed_projection_chunk_count"],
        "artifact_count": len(artifacts),
    }
    _write_json(output_dir / "bundle_manifest.json", bundle_manifest)
    return output_dir


def validate_publication_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Validate a deterministic publication bundle without storage credentials."""

    bundle_dir = bundle_dir.resolve()
    errors: list[str] = []
    for required in REQUIRED_BUNDLE_FILES:
        if not (bundle_dir / required).is_file():
            errors.append(f"missing required file: {required}")

    bundle_manifest = _read_bundle_json(bundle_dir / "bundle_manifest.json", errors)
    object_payload = _read_bundle_json(bundle_dir / "object_manifest.json", errors)
    checkpoint = _read_bundle_json(bundle_dir / "checkpoint_manifest.json", errors)
    signature_readback = _read_bundle_json(
        bundle_dir / "signature_readback_manifest.json",
        errors,
    )
    aggregate_usage = _read_bundle_json(bundle_dir / "aggregate_usage.json", errors)
    objects = object_payload.get("objects") if isinstance(object_payload, dict) else None
    object_rows = objects if isinstance(objects, list) else []
    if not isinstance(objects, list):
        errors.append("object_manifest.json must contain an objects array")

    kind = bundle_manifest.get("kind") if isinstance(bundle_manifest, dict) else None
    if bundle_manifest.get("schema_version") != PUBLICATION_BUNDLE_SCHEMA_VERSION:
        errors.append("bundle_manifest.json schema_version mismatch")
    if kind not in PUBLICATION_KINDS:
        errors.append("bundle_manifest.json has unknown publication kind")

    validated_object_count = 0
    for index, row in enumerate(object_rows):
        if not isinstance(row, dict):
            errors.append(f"object manifest row {index} is not an object")
            continue
        rel_path = row.get("path")
        expected_sha = row.get("sha256")
        expected_bytes = row.get("bytes")
        if not isinstance(rel_path, str) or not isinstance(expected_sha, str):
            errors.append(f"object manifest row {index} is missing path or sha256")
            continue
        path = _safe_bundle_path(bundle_dir, rel_path, errors)
        if path is None:
            continue
        if not path.is_file():
            errors.append(f"object missing from bundle: {rel_path}")
            continue
        if sha256_file(path) != expected_sha:
            errors.append(f"object hash mismatch: {rel_path}")
        if not isinstance(expected_bytes, int) or path.stat().st_size != expected_bytes:
            errors.append(f"object size mismatch: {rel_path}")
        validated_object_count += 1

    object_manifest_hash = sha256_json(object_rows)
    _compare_field(
        checkpoint,
        "object_manifest_hash",
        object_manifest_hash,
        "checkpoint_manifest.json",
        errors,
    )
    _compare_field(
        bundle_manifest,
        "object_manifest_hash",
        object_manifest_hash,
        "bundle_manifest.json",
        errors,
    )
    _compare_field(
        checkpoint,
        "completed_object_count",
        len(object_rows),
        "checkpoint_manifest.json",
        errors,
    )
    _compare_field(
        bundle_manifest,
        "completed_object_count",
        len(object_rows),
        "bundle_manifest.json",
        errors,
    )

    projection_rows = {
        "public_manifest_rows": _read_bundle_jsonl(bundle_dir / "public_manifest.jsonl", errors),
        "proof_rows": _read_bundle_jsonl(bundle_dir / "proof_index.jsonl", errors),
        "leaderboard_rows": _read_bundle_jsonl(bundle_dir / "leaderboard_rows.jsonl", errors),
        "provider_model_rows": _read_bundle_jsonl(
            bundle_dir / "provider_model_rows.jsonl",
            errors,
        ),
    }
    statement_projection_hash = sha256_json(projection_rows)
    _compare_field(
        checkpoint,
        "statement_projection_hash",
        statement_projection_hash,
        "checkpoint_manifest.json",
        errors,
    )
    _compare_field(
        bundle_manifest,
        "statement_projection_hash",
        statement_projection_hash,
        "bundle_manifest.json",
        errors,
    )
    _validate_proof_rows(bundle_dir, projection_rows["proof_rows"], errors)
    _validate_aggregate_usage(aggregate_usage, errors)
    if signature_readback and "status" not in signature_readback:
        errors.append("signature_readback_manifest.json missing status")

    return {
        "schema_version": PUBLICATION_VALIDATION_SCHEMA_VERSION,
        "bundle_dir": str(bundle_dir),
        "kind": kind,
        "valid": not errors,
        "status": "valid" if not errors else "invalid",
        "object_count": validated_object_count,
        "projection_chunk_count": 4,
        "object_manifest_hash": object_manifest_hash,
        "statement_projection_hash": statement_projection_hash,
        "errors": errors,
    }


def _artifact_inputs(*, artifacts_dir: Path | None, artifact: Path | None) -> list[Path]:
    if artifact is not None:
        return [artifact.resolve()]
    if artifacts_dir is None:
        raise ValueError("either artifact or artifacts_dir is required")
    candidates = []
    for path in sorted(artifacts_dir.iterdir()):
        if path.name.endswith(".eslams") or path.name.endswith(".eslams.d"):
            if path.name.endswith(".eslams.d") and path.with_suffix("").exists():
                continue
            candidates.append(path.resolve())
    return candidates


def _read_plan(plan_path: Path | None) -> dict[str, Any] | None:
    if plan_path is None or not plan_path.exists():
        return None
    try:
        value = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _plan_hash(plan_payload: dict[str, Any] | None) -> str | None:
    if plan_payload is None:
        return None
    value = plan_payload.get("plan_hash")
    return value if isinstance(value, str) else sha256_json(plan_payload)


def _read_optional_json(artifact_path: Path, member: str) -> dict[str, Any] | None:
    try:
        value = json.loads(read_member(artifact_path, member).decode("utf-8"))
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _object_manifest(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "object_manifest.json":
            continue
        rows.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _read_bundle_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"invalid JSON: {path.name}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} must contain a JSON object")
        return {}
    return value


def _read_bundle_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"invalid JSONL row: {path.name}:{line_number}")
            continue
        if not isinstance(value, dict):
            errors.append(f"JSONL row must be an object: {path.name}:{line_number}")
            continue
        rows.append(value)
    return rows


def _safe_bundle_path(bundle_dir: Path, rel_path: str, errors: list[str]) -> Path | None:
    path = (bundle_dir / rel_path).resolve()
    try:
        path.relative_to(bundle_dir)
    except ValueError:
        errors.append(f"object path escapes bundle: {rel_path}")
        return None
    return path


def _compare_field(
    payload: dict[str, Any],
    field: str,
    expected: Any,
    label: str,
    errors: list[str],
) -> None:
    if payload.get(field) != expected:
        errors.append(f"{label} {field} mismatch")


def _validate_proof_rows(
    bundle_dir: Path,
    proof_rows: list[dict[str, Any]],
    errors: list[str],
) -> None:
    for index, row in enumerate(proof_rows):
        if row.get("evidence_row") is not True:
            errors.append(f"proof row {index} must be marked as evidence_row")
        if row.get("leaderboard_predicate") is True and row.get(
            "leaderboard_predicate_configured"
        ) is not True:
            errors.append(f"proof row {index} cannot be a leaderboard predicate by default")
        public_replay_path = row.get("public_replay_path")
        if not isinstance(public_replay_path, str):
            errors.append(f"proof row {index} missing public_replay_path")
            continue
        replay_path = _safe_bundle_path(bundle_dir, public_replay_path, errors)
        if replay_path is None or not replay_path.exists():
            errors.append(f"proof row {index} public replay is missing")
            continue
        replay_report = validate_public_replay(replay_path)
        if replay_report.get("valid") is not True:
            errors.append(f"proof row {index} public replay failed validation")


def _validate_aggregate_usage(payload: dict[str, Any], errors: list[str]) -> None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        errors.append("aggregate_usage.json missing usage object")
        return
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "total_tokens",
    ):
        if not isinstance(usage.get(key), int):
            errors.append(f"aggregate_usage.json usage.{key} must be an integer")
    pricing = payload.get("pricing")
    if not isinstance(pricing, dict):
        errors.append("aggregate_usage.json missing pricing object")
        return
    if pricing.get("status") == "ok" and pricing.get("source") is None:
        errors.append("aggregate_usage.json pricing.source is required when pricing is available")


def _cost_unavailable() -> dict[str, Any]:
    return {
        "status": "cost_unavailable",
        "pricing_table_version": None,
        "currency": "USD",
        "billable_token_categories": [],
        "source": "not_configured",
        "unavailable_reason": "pricing_not_configured",
    }
