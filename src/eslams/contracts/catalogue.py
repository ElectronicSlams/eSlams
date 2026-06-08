"""Public catalogue records for games and models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import CATALOGUE_GAME_SCHEMA_VERSION, CATALOGUE_MODEL_SCHEMA_VERSION


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
    schema_version: str = CATALOGUE_GAME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "display_name": self.display_name,
            "display_group": self.display_group,
            "renderer_family": self.renderer_family,
            "replay_availability": self.replay_availability,
            "official_eval_availability": self.official_eval_availability,
            "coming_soon_reason": self.coming_soon_reason,
        }


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
    }
