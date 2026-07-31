"""Runner health payload helpers."""

from __future__ import annotations

import time
from typing import Any

import eslams.arenas  # noqa: F401
from eslams._build_provenance import core_source_commit
from eslams.arena import registry as arena_registry
from eslams.contracts.runner_job import runner_health_payload
from eslams.contracts.versions import CORE_PACKAGE_VERSION
from eslams.hashing import canonical_json
from eslams.providers import load_provider_registry
from eslams.rendering import renderer_vocabulary_rows

CORE_VERSION = CORE_PACKAGE_VERSION
_STARTED_AT = time.monotonic()


def current_runner_health() -> dict[str, Any]:
    game_ids = arena_registry.list()
    action_schemas = [
        arena_registry.create(arena_id).action_schema
        for arena_id in game_ids
    ]
    renderer_vocabulary = renderer_vocabulary_rows()
    registry_rows = [
        record.to_dict()
        for record in load_provider_registry().list_models()
    ]
    payload = runner_health_payload(
        core_commit=core_source_commit(),
        core_version=CORE_VERSION,
        registry_rows=registry_rows,
        game_ids=game_ids,
        renderer_vocabulary=[canonical_json(row) for row in renderer_vocabulary],
        action_schemas=action_schemas,
    ).to_dict()
    payload.update(
        {
            "ok": True,
            "loadedGames": len(game_ids),
            "warm": True,
            "uptimeMs": int((time.monotonic() - _STARTED_AT) * 1000),
        }
    )
    return payload
