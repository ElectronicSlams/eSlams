"""Public catalogue exports for games, models, and availability."""

from __future__ import annotations

from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry as arena_registry
from eslams.contracts.catalogue import (
    CapabilityFlag,
    GameCatalogueRecord,
    ModelCatalogueRecord,
)
from eslams.providers import load_provider_registry
from eslams.rendering import renderer_vocabulary_rows


def game_catalogue_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    renderer_rows = {
        row["game_id"]: row
        for row in renderer_vocabulary_rows()
    }
    for game_id in arena_registry.list():
        renderer_row = renderer_rows[game_id]
        replay_availability = str(renderer_row["replay_availability"])
        rows.append(
            {
                **GameCatalogueRecord(
                    game_id=game_id,
                    display_name=_display_name(game_id),
                    display_group=_display_group(game_id),
                    renderer_family=str(renderer_row["renderer_family"]),
                    replay_availability=replay_availability,
                    official_eval_availability="not_evaluated",
                    coming_soon_reason=None
                    if replay_availability == "playable"
                    else "setup_only_replay",
                ).to_dict(),
                "variant_token": "default",
                "scenario_levels": ["default"],
                "action_schema_version": "action-schema-v1",
                "browser_play_availability": "ready",
                "public_rules": f"Play {_display_name(game_id)} using legal actions only.",
                "public_scoring_summary": "Scores are reported by the arena state.",
                "timeline_completeness": renderer_row["timeline_completeness"],
                "render_hints_version": renderer_row["render_hints_version"],
                "public_state_shape_version": renderer_row["public_state_shape_version"],
                "showcase_ready": renderer_row["showcase_ready"],
                "autoplay_ready": renderer_row["autoplay_ready"],
                "public_safe": renderer_row["public_safe"],
                "state_hash_valid": renderer_row["state_hash_valid"],
            }
        )
    return rows


def model_catalogue_rows() -> list[dict[str, Any]]:
    provider_registry = load_provider_registry()
    rows: list[dict[str, Any]] = []
    for record in provider_registry.list_models():
        capability_flags = {
            key: CapabilityFlag(
                enabled=value.get("enabled") is True,
                reason=_reason(value),
            )
            for key, value in record.capability_flags.items()
        }
        rows.append(
            ModelCatalogueRecord(
                provider=record.provider,
                model=record.model,
                public_slug=record.public_slug or _display_name(record.model),
                display_name=record.display_name or record.model,
                launch_status=record.launch_status,
                capability_flags=capability_flags,
                absence_reasons=_absence_reasons(record.to_dict()),
            ).to_dict()
            | {
                "source_model_id": record.source_model_id,
                "modality_summary": record.modality_summary,
                "provider_label": provider_registry.organizations.get(
                    record.provider,
                    record.provider,
                ),
            }
        )
    return rows


def availability_rows() -> list[dict[str, Any]]:
    games = game_catalogue_rows()
    models = model_catalogue_rows()
    rows: list[dict[str, Any]] = []
    for model in models:
        arena_flag = _capability_flag(model, "arena")
        for game in games:
            allowed = arena_flag.get("enabled") is True
            rows.append(
                {
                    "model": model["model"],
                    "provider": model["provider"],
                    "game_id": game["game_id"],
                    "status": "ready" if allowed else "not_evaluated",
                    "reason": None if allowed else arena_flag.get("reason") or "not_evaluated",
                }
            )
    return rows


def _display_name(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-"))


def _display_group(game_id: str) -> str:
    if any(token in game_id for token in ("poker", "card", "hearts", "euchre")):
        return "Cards"
    if any(token in game_id for token in ("grid", "maze", "taxi", "cliff")):
        return "Control"
    return "Board"


def _absence_reasons(record: dict[str, Any]) -> list[str]:
    reasons = list(record.get("eligibility_reasons") or [])
    flags = record.get("capability_flags")
    if isinstance(flags, dict):
        for value in flags.values():
            if isinstance(value, dict) and isinstance(value.get("reason"), str):
                reasons.append(value["reason"])
    return sorted({str(reason) for reason in reasons if reason})


def _capability_flag(model: dict[str, Any], capability: str) -> dict[str, Any]:
    flags = model.get("capability_flags")
    if isinstance(flags, dict):
        value = flags.get(capability)
        if isinstance(value, dict):
            return value
    return {"enabled": False, "reason": "not_evaluated"}


def _reason(value: dict[str, bool | str | None]) -> str | None:
    reason = value.get("reason")
    return reason if isinstance(reason, str) else None
