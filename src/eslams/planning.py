"""Deterministic no-secret eval planning helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry as arena_registry
from eslams.contracts.eval_plan import EvalPlanEnvelope
from eslams.hashing import sha256_json
from eslams.providers import load_provider_registry

CORE_VERSION = "0.3.0"
RUNNER_VERSION = "eslams-runner:0.3.0"
PLAN_GENERATED_AT = "1970-01-01T00:00:00Z"


def official_plan(
    *,
    suite: str,
    providers: list[str],
    arenas: list[str],
    shard_count: int = 1,
) -> dict[str, Any]:
    provider_registry = load_provider_registry()
    selected_models = [
        f"{record.provider}:{record.model}"
        for record in provider_registry.list_models()
        if record.provider in providers and record.capability_enabled("official_eval")
    ]
    selected_arenas = _selected_arenas(arenas)
    case_ids = [
        f"{suite}:{model}:{arena_id}"
        for model in selected_models
        for arena_id in selected_arenas
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
    normalized_pairs = sorted(pair for pair in pairs if pair)
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
    if not isinstance(request, dict):
        request = {}
    arena_id = str(request.get("arena_id") or "tic-tac-toe")
    models = [str(item) for item in request.get("models", []) if item]
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
    selected = sorted(arena_id for arena_id in arenas if arena_id in available)
    return selected or ["tic-tac-toe"]


def _registry_hash() -> str:
    provider_registry = load_provider_registry()
    return sha256_json([record.to_dict() for record in provider_registry.list_models()])


def _shards(case_ids: list[str], shard_count: int) -> list[dict[str, Any]]:
    shard_count = max(1, shard_count)
    shards = []
    for shard_index in range(shard_count):
        shard_cases = [
            case_id
            for index, case_id in enumerate(sorted(case_ids))
            if index % shard_count == shard_index
        ]
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
