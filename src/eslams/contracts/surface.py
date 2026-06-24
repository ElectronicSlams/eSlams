"""Game surface contracts for Core 0.5 public catalogue exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_SURFACE_SCHEMA_VERSION

ARENA_SURFACES = {"main_arena", "advanced_arena", "table_mode_pending", "disabled"}
BATTLEFIELD_SURFACES = {"solo_benchmark", "head_to_head", "multi_seat", "disabled"}
BENCHMARK_SURFACES = {"enabled", "disabled"}
OFFICIAL_SURFACES = {"eligible", "not_eligible", "private_only"}


@dataclass(frozen=True)
class GameSurface:
    arena: str
    battlefield: str
    benchmark: str
    official: str
    public_reason: str | None = None
    schema_version: str = GAME_SURFACE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "arena": self.arena,
            "battlefield": self.battlefield,
            "benchmark": self.benchmark,
            "official": self.official,
            "publicReason": self.public_reason,
        }


def validate_surface(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("arena") not in ARENA_SURFACES:
        errors.append("surface.arena is unsupported")
    if payload.get("battlefield") not in BATTLEFIELD_SURFACES:
        errors.append("surface.battlefield is unsupported")
    if payload.get("benchmark") not in BENCHMARK_SURFACES:
        errors.append("surface.benchmark is unsupported")
    if payload.get("official") not in OFFICIAL_SURFACES:
        errors.append("surface.official is unsupported")
    if payload.get("arena") == "disabled" and not payload.get("publicReason"):
        errors.append("surface.publicReason is required when Arena is disabled")
    return errors


def no_secret_example() -> dict[str, Any]:
    return GameSurface(
        arena="main_arena",
        battlefield="head_to_head",
        benchmark="disabled",
        official="eligible",
    ).to_dict()
