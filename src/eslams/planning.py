"""Deterministic no-secret eval planning helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry as arena_registry
from eslams.contracts.eval_plan import EvalPlanEnvelope
from eslams.contracts.versions import CORE_PACKAGE_VERSION, EVAL_PLAN_SCHEMA_VERSION, RUNNER_VERSION
from eslams.hashing import sha256_json
from eslams.providers import load_provider_registry

CORE_VERSION = CORE_PACKAGE_VERSION
PLAN_GENERATED_AT = "1970-01-01T00:00:00Z"
MAX_PLAN_SHARDS = 1024


def official_plan(
    *,
    suite: str,
    providers: list[str],
    arenas: list[str],
    shard_count: int = 1,
) -> dict[str, Any]:
    if suite != "public-smoke":
        raise ValueError("unknown official planning suite; supported suite: public-smoke")
    provider_registry = load_provider_registry()
    unknown = sorted(
        set(providers) - {record.provider for record in provider_registry.list_models()}
    )
    if not providers or unknown:
        raise ValueError("official plan requires known provider namespaces")
    selected_models = [
        f"{record.provider}:{record.model}"
        for record in provider_registry.list_models()
        if record.provider in providers and record.capability_enabled("official_eval")
    ]
    selected_arenas = _selected_arenas(arenas)
    case_ids = [
        f"{suite}:{model}:{arena_id}" for model in selected_models for arena_id in selected_arenas
    ]
    return EvalPlanEnvelope(
        kind="official",
        generated_at=PLAN_GENERATED_AT,
        suite_fingerprint=sha256_json({"suite": suite, "arenas": selected_arenas}),
        core_version=CORE_VERSION,
        runner_version=RUNNER_VERSION,
        registry_hash=_registry_hash(),
        selected_providers=sorted(providers),
        selected_models=selected_models,
        selected_arenas=selected_arenas,
        case_count_expected=len(case_ids),
        shards=_shards(case_ids, shard_count),
        required_environment_names=_provider_env_names(providers),
        output_references=[{"kind": "artifact_directory", "path": "runs/official"}],
        policy_ids=["official-eval-v1"],
    ).to_dict()


def battlefield_plan(
    *,
    pairs: list[str],
    arenas: list[str],
    shard_count: int = 1,
) -> dict[str, Any]:
    selected_arenas = _selected_arenas(arenas)
    if not pairs or any(not _model_reference(pair) for pair in pairs):
        raise ValueError("battlefield pairs must contain provider:model references")
    normalized_pairs = sorted(set(pairs))
    case_ids = [
        f"battlefield:{pair}:{arena_id}"
        for pair in normalized_pairs
        for arena_id in selected_arenas
    ]
    providers = sorted({pair.split(":", 1)[0] for pair in normalized_pairs if ":" in pair})
    return EvalPlanEnvelope(
        kind="battlefield",
        generated_at=PLAN_GENERATED_AT,
        suite_fingerprint=sha256_json({"pairs": normalized_pairs, "arenas": selected_arenas}),
        core_version=CORE_VERSION,
        runner_version=RUNNER_VERSION,
        registry_hash=_registry_hash(),
        selected_providers=providers,
        selected_models=normalized_pairs,
        selected_arenas=selected_arenas,
        case_count_expected=len(case_ids),
        shards=_shards(case_ids, shard_count),
        required_environment_names=_provider_env_names(providers),
        output_references=[{"kind": "artifact_directory", "path": "runs/battlefield"}],
        policy_ids=["battlefield-smoke-v1"],
    ).to_dict()


def public_match_plan(*, request_path: Path, shard_count: int = 1) -> dict[str, Any]:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(request, dict) or not isinstance(request.get("arena_id"), str):
        raise ValueError("public match request requires an arena_id")
    arena_id = request["arena_id"]
    models = request.get("models", [])
    if not isinstance(models, list) or any(not _model_reference(item) for item in models):
        raise ValueError("public match models must be a list of provider:model references")
    models = sorted(set(models))
    case_ids = [f"public-match:{arena_id}:{model}" for model in sorted(models)] or [
        f"public-match:{arena_id}:local"
    ]
    providers = sorted({model.split(":", 1)[0] for model in models if ":" in model})
    return EvalPlanEnvelope(
        kind="public_match",
        generated_at=PLAN_GENERATED_AT,
        suite_fingerprint=sha256_json({"request": request}),
        core_version=CORE_VERSION,
        runner_version=RUNNER_VERSION,
        registry_hash=_registry_hash(),
        selected_providers=providers,
        selected_models=sorted(models),
        selected_arenas=_selected_arenas([arena_id]),
        case_count_expected=len(case_ids),
        shards=_shards(case_ids, shard_count),
        required_environment_names=_provider_env_names(providers),
        output_references=[{"kind": "artifact_directory", "path": "runs/public-match"}],
        policy_ids=["public-match-v1"],
    ).to_dict()


def _selected_arenas(arenas: list[str]) -> list[str]:
    available = set(arena_registry.list())
    if not arenas or any(arena_id not in available for arena_id in arenas):
        raise ValueError("plan requires known arena IDs; unknown arenas are not substituted")
    return sorted(set(arenas))


def _model_reference(value: Any) -> bool:
    return (
        isinstance(value, str)
        and ":" in value
        and all(part.strip() for part in value.split(":", 1))
    )


def validate_plan(value: Any) -> None:
    """Reject malformed or altered supplied plans before producing aggregate output."""
    if not isinstance(value, dict) or value.get("schema_version") != EVAL_PLAN_SCHEMA_VERSION:
        raise ValueError("plan must be an eslams.eval.plan.v1 object")
    if value.get("kind") not in {"official", "battlefield", "public_match"}:
        raise ValueError("plan has an unknown kind")
    count = value.get("case_count_expected")
    shards = value.get("shards")
    if type(count) is not int or count < 0 or not isinstance(shards, list) or not shards:
        raise ValueError("plan requires non-negative case count and non-empty shards")
    cases: list[str] = []
    for index, shard in enumerate(shards):
        if not isinstance(shard, dict):
            raise ValueError("plan shard must be an object")
        ids = shard.get("case_ids")
        if (
            not isinstance(ids, list)
            or any(not isinstance(item, str) or not item for item in ids)
            or type(shard.get("case_count")) is not int
            or shard["case_count"] != len(ids)
            or type(shard.get("shard_index")) is not int
            or shard["shard_index"] != index
            or type(shard.get("shard_count")) is not int
            or shard["shard_count"] != len(shards)
        ):
            raise ValueError("plan shard identity or case count is invalid")
        cases.extend(ids)
    if len(cases) != count or len(set(cases)) != count:
        raise ValueError("plan contains duplicate cases or inconsistent case totals")
    unhashed = {key: item for key, item in value.items() if key != "plan_hash"}
    if value.get("plan_hash") != sha256_json(unhashed):
        raise ValueError("plan_hash does not match plan contents")


def _registry_hash() -> str:
    provider_registry = load_provider_registry()
    return sha256_json([record.to_dict() for record in provider_registry.list_models()])


def _shards(case_ids: list[str], shard_count: int) -> list[dict[str, Any]]:
    maximum = min(MAX_PLAN_SHARDS, max(1, len(case_ids)))
    if (
        isinstance(shard_count, bool)
        or not isinstance(shard_count, int)
        or not 1 <= shard_count <= maximum
    ):
        raise ValueError(f"shard_count must be an integer between 1 and {maximum}")
    ordered_cases = sorted(case_ids)
    shards = []
    for shard_index in range(shard_count):
        shard_cases = ordered_cases[shard_index::shard_count]
        shards.append(
            {
                "shard_index": shard_index,
                "shard_count": shard_count,
                "case_count": len(shard_cases),
                "case_ids": shard_cases,
            }
        )
    return shards


def _provider_env_names(providers: list[str]) -> list[str]:
    names = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    return sorted({names[provider] for provider in providers if provider in names})
