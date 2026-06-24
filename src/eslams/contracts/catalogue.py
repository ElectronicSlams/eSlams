"""Public catalogue records for games and models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import (
    CATALOGUE_AVAILABILITY_SCHEMA_VERSION,
    CATALOGUE_GAME_SCHEMA_VERSION,
    CATALOGUE_MODEL_SCHEMA_VERSION,
    CATALOGUE_RENDERER_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class CapabilityFlag:
    enabled: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "reason": self.reason}


@dataclass(frozen=True)
class GameCatalogueRecord:
    game_id: str
    display_name: str
    display_group: str
    renderer_family: str
    replay_availability: str
    official_eval_availability: str
    coming_soon_reason: str | None = None
    topology: dict[str, Any] | None = None
    surface: dict[str, Any] | None = None
    result_contract: dict[str, Any] | None = None
    help: dict[str, Any] | None = None
    render_spec: dict[str, Any] | None = None
    animation_spec: dict[str, Any] | None = None
    schema_version: str = CATALOGUE_GAME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "display_name": self.display_name,
            "display_group": self.display_group,
            "renderer_family": self.renderer_family,
            "replay_availability": self.replay_availability,
            "official_eval_availability": self.official_eval_availability,
            "coming_soon_reason": self.coming_soon_reason,
        }
        if self.topology is not None:
            payload["topology"] = self.topology
        if self.surface is not None:
            payload["surface"] = self.surface
        if self.result_contract is not None:
            payload["resultContract"] = self.result_contract
        if self.help is not None:
            payload["help"] = self.help
        if self.render_spec is not None:
            payload["renderSpec"] = self.render_spec
        if self.animation_spec is not None:
            payload["animationSpec"] = self.animation_spec
        return payload


@dataclass(frozen=True)
class ModelCatalogueRecord:
    provider: str
    model: str
    public_slug: str
    display_name: str
    launch_status: str
    capability_flags: dict[str, CapabilityFlag] = field(default_factory=dict)
    absence_reasons: list[str] = field(default_factory=list)
    schema_version: str = CATALOGUE_MODEL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "public_slug": self.public_slug,
            "display_name": self.display_name,
            "launch_status": self.launch_status,
            "capability_flags": {
                key: value.to_dict() for key, value in sorted(self.capability_flags.items())
            },
            "absence_reasons": list(self.absence_reasons),
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        CATALOGUE_GAME_SCHEMA_VERSION: GameCatalogueRecord(
            game_id="tic-tac-toe",
            display_name="Tic-Tac-Toe",
            display_group="Board",
            renderer_family="grid",
            replay_availability="playable",
            official_eval_availability="ready",
            topology={
                "schemaVersion": "eslams.game.topology.v1",
                "mode": "head_to_head",
                "controlledPlayers": ["player_1", "player_2"],
                "environmentPlayers": [],
                "minPlayers": 2,
                "maxPlayers": 2,
                "defaultPlayers": 2,
                "winnerRequired": True,
                "drawAllowed": True,
                "placementsAllowed": False,
                "scoreType": "win_loss_draw",
            },
            surface={
                "schemaVersion": "eslams.game.surface.v1",
                "arena": "main_arena",
                "battlefield": "head_to_head",
                "benchmark": "disabled",
                "official": "eligible",
                "publicReason": None,
            },
            result_contract={
                "schemaVersion": "eslams.game.result.v1",
                "mode": "head_to_head",
                "resultTypes": ["winner", "draw", "points"],
                "scoreType": "win_loss_draw",
                "winnerRequired": True,
                "drawAllowed": True,
                "placementsAllowed": False,
            },
        ).to_dict(),
        CATALOGUE_MODEL_SCHEMA_VERSION: ModelCatalogueRecord(
            provider="mock",
            model="legal-action",
            public_slug="mock-legal-action",
            display_name="Mock Legal Action",
            launch_status="ready",
            capability_flags={
                "arena": CapabilityFlag(True),
                "battlefield": CapabilityFlag(True),
                "official_eval": CapabilityFlag(False, "not_evaluated"),
            },
        ).to_dict(),
        CATALOGUE_RENDERER_SCHEMA_VERSION: {
            "schema_version": CATALOGUE_RENDERER_SCHEMA_VERSION,
            "game_id": "tic-tac-toe",
            "renderer_family": "grid",
            "renderer_kind": "grid",
            "timeline_completeness": "playable",
            "replay_availability": "playable",
            "visible_frame_count": 2,
            "state_frame_count": 2,
            "move_frame_count": 1,
            "public_safe": True,
            "state_hash_valid": True,
        },
        CATALOGUE_AVAILABILITY_SCHEMA_VERSION: {
            "schema_version": CATALOGUE_AVAILABILITY_SCHEMA_VERSION,
            "provider": "mock",
            "model": "legal-action",
            "game_id": "tic-tac-toe",
            "status": "ready",
            "reason": None,
        },
        "eslams.game.topology.v1": {
            "schemaVersion": "eslams.game.topology.v1",
            "mode": "head_to_head",
            "controlledPlayers": ["player_1", "player_2"],
            "environmentPlayers": [],
            "minPlayers": 2,
            "maxPlayers": 2,
            "defaultPlayers": 2,
            "winnerRequired": True,
            "drawAllowed": True,
            "placementsAllowed": False,
            "scoreType": "win_loss_draw",
        },
        "eslams.game.surface.v1": {
            "schemaVersion": "eslams.game.surface.v1",
            "arena": "main_arena",
            "battlefield": "head_to_head",
            "benchmark": "disabled",
            "official": "eligible",
            "publicReason": None,
        },
        "eslams.game.result.v1": {
            "schemaVersion": "eslams.game.result.v1",
            "mode": "head_to_head",
            "terminal": True,
            "winner": "player_1",
            "draw": False,
            "scores": {"player_1": 1, "player_2": 0},
            "resultType": "winner",
        },
        "eslams.game.help.v1": {
            "schemaVersion": "eslams.game.help.v1",
            "objective": "Place three marks in a row before the opponent does.",
            "turnRules": ["Players alternate turns."],
            "legalActionSummary": "Choose any empty cell.",
            "scoringSummary": "Three in a row wins; a full board without three is a draw.",
            "winLossDrawSummary": "The result is a win, loss, or draw.",
            "hiddenInfoSummary": None,
            "firstMoveTip": "The center and corners give the most future lines.",
            "exampleActions": [
                {
                    "token": "4",
                    "label": "Center cell",
                    "explanation": "Places your mark in the center cell.",
                }
            ],
            "detailSections": [],
        },
        "eslams.game.render.v1": {
            "schemaVersion": "eslams.game.render.v1",
            "rendererFamily": "grid_3x3",
            "boardSize": {"rows": 3, "cols": 3},
            "seatLayout": "two_sides",
            "hiddenInfo": False,
            "supportsReplay": True,
            "supportsLiveFrame": True,
        },
        "eslams.game.animation.v1": {
            "schemaVersion": "eslams.game.animation.v1",
            "family": "tic_tac_toe_mark",
            "defaultMoveMs": 220,
            "defaultRevealMs": 180,
            "defaultResultMs": 520,
            "reducedMotionBehavior": "static_final_state",
            "events": {"move": {"kind": "tic_tac_toe_mark"}},
        },
        "eslams.usage.v1": {
            "schemaVersion": "eslams.usage.summary.v1",
            "totalInputTokens": 10,
            "totalOutputTokens": 5,
            "totalTokens": 15,
            "totalCostUsd": None,
            "usageComplete": True,
            "costComplete": False,
            "bySeat": {"player_1": {"totalTokens": 15, "costUsd": None}},
            "byAgent": {},
            "byModel": {},
        },
    }
