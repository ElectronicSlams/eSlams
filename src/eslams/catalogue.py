"""Public catalogue exports for games, models, and availability."""

from __future__ import annotations

import logging
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry as arena_registry
from eslams.contracts.catalogue import (
    CapabilityFlag,
    GameCatalogueRecord,
    ModelCatalogueRecord,
)
from eslams.contracts.versions import CATALOGUE_AVAILABILITY_SCHEMA_VERSION
from eslams.game_metadata import core_0_5_metadata
from eslams.providers import load_provider_registry
from eslams.public_catalogue import PUBLIC_GAME_CATALOGUE_BY_ID
from eslams.rendering import renderer_vocabulary_rows

log = logging.getLogger(__name__)


def game_catalogue_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    renderer_rows = {
        row["game_id"]: row
        for row in renderer_vocabulary_rows()
    }
    for game_id in arena_registry.list():
        renderer_row = renderer_rows.get(game_id)
        if renderer_row is None:
            log.warning("arena %s has no renderer catalogue row; skipping", game_id)
            continue
        public = PUBLIC_GAME_CATALOGUE_BY_ID.get(game_id)
        if public is None:
            log.warning("arena %s has no public catalogue row; skipping", game_id)
            continue
        replay_availability = str(renderer_row["replay_availability"])
        metadata = core_0_5_metadata(
            public,
            renderer_family=str(renderer_row["renderer_family"]),
            replay_available=replay_availability == "playable",
        )
        topology = metadata["topology"]
        surface = metadata["surface"]
        help_payload = metadata["help"]
        rows.append(
            {
                **GameCatalogueRecord(
                    game_id=game_id,
                    display_name=public.name,
                    display_group=public.category_label,
                    renderer_family=str(renderer_row["renderer_family"]),
                    replay_availability=replay_availability,
                    official_eval_availability="not_evaluated",
                    coming_soon_reason=None
                    if replay_availability == "playable"
                    else "setup_only_replay",
                    topology=topology,
                    surface=surface,
                    result_contract=metadata["resultContract"],
                    help=help_payload,
                    render_spec=metadata["renderSpec"],
                    animation_spec=metadata["animationSpec"],
                ).to_dict(),
                "topology_mode": topology["mode"],
                "controlled_players": topology["controlledPlayers"],
                "environment_players": topology["environmentPlayers"],
                "min_players": topology["minPlayers"],
                "max_players": topology["maxPlayers"],
                "default_players": topology["defaultPlayers"],
                "evaluated_player": topology.get("evaluatedPlayer"),
                "arena_surface": surface["arena"],
                "battlefield_surface": surface["battlefield"],
                "benchmark_surface": surface["benchmark"],
                "playable_in_arena": surface["arena"] in {"main_arena", "advanced_arena"},
                "playable_in_battlefield": surface["battlefield"] != "disabled",
                "playable_as_benchmark": surface["benchmark"] == "enabled",
                "disabled_reason": surface["publicReason"]
                if surface["arena"] == "disabled"
                else None,
                "coming_soon_reason": surface["publicReason"]
                if surface["arena"] == "table_mode_pending"
                else None,
                "core_0_5_validation_errors": metadata["validationErrors"],
                "runtime_display_name": _display_name(game_id),
                "runtime_display_group": _display_group(game_id),
                "variant_token": public.variant,
                "variant_slug": public.variant,
                "variant_label": public.variant_label,
                "public_game_label": public.name,
                "public_display_name": public.name,
                "public_display_group": public.category_label,
                "public_category_label": public.category_label,
                "public_variant_label": public.variant_label,
                "public_short_description": public.short_description,
                "public_category_key": public.category,
                "difficulty": public.difficulty,
                "maturity": public.maturity,
                "player_count": topology["defaultPlayers"],
                "scenario_levels": ["default"],
                "action_schema_version": "action-schema-v1",
                "browser_play_availability": _browser_play_availability(surface),
                "public_rules": help_payload["objective"],
                "public_scoring_summary": help_payload["scoringSummary"],
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
                "supported_reasoning_modes": list(record.supported_reasoning_modes),
                "accepted_control_fields": list(record.accepted_control_fields),
                "default_reasoning_track": record.default_reasoning_track,
                "reasoning_track_kind": record.reasoning_track_kind,
                "unsupported_reasoning_control_reason": (
                    record.unsupported_reasoning_control_reason
                ),
                "http_agent_payload_guidance": dict(record.http_agent_payload_guidance),
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
                    "schema_version": CATALOGUE_AVAILABILITY_SCHEMA_VERSION,
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


def _browser_play_availability(surface: dict[str, Any]) -> str:
    arena_surface = surface.get("arena")
    if arena_surface in {"main_arena", "advanced_arena"}:
        return "ready"
    if arena_surface == "table_mode_pending":
        return "table_mode_pending"
    if surface.get("battlefield") == "solo_benchmark":
        return "benchmark_only"
    return "disabled"


def _reason(value: dict[str, bool | str | None]) -> str | None:
    reason = value.get("reason")
    return reason if isinstance(reason, str) else None
