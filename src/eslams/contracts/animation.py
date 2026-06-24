"""Game animation spec contract for Core 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_ANIMATION_SCHEMA_VERSION


@dataclass(frozen=True)
class GameAnimationSpec:
    family: str
    default_move_ms: int = 220
    default_reveal_ms: int = 220
    default_result_ms: int = 520
    reduced_motion_behavior: str = "static_final_state"
    events: dict[str, dict[str, Any]] | None = None
    schema_version: str = GAME_ANIMATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "family": self.family,
            "defaultMoveMs": self.default_move_ms,
            "defaultRevealMs": self.default_reveal_ms,
            "defaultResultMs": self.default_result_ms,
            "reducedMotionBehavior": self.reduced_motion_behavior,
            "events": dict(self.events or {"move": {"kind": self.family}}),
        }


def validate_animation_spec(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("family"), str) or not payload.get("family"):
        errors.append("animation.family is required")
    if payload.get("reducedMotionBehavior") not in {"static_final_state", "fade_only"}:
        errors.append("animation.reducedMotionBehavior is unsupported")
    for key in ("defaultMoveMs", "defaultRevealMs", "defaultResultMs"):
        value = payload.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"animation.{key} must be a non-negative integer")
    if not isinstance(payload.get("events"), dict):
        errors.append("animation.events must be an object")
    return errors


def no_secret_example() -> dict[str, Any]:
    return GameAnimationSpec(family="connect_four_drop").to_dict()
