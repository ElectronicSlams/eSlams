"""Game render spec contract for Core 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_RENDER_SCHEMA_VERSION


@dataclass(frozen=True)
class GameRenderSpec:
    renderer_family: str
    seat_layout: str
    hidden_info: bool
    supports_replay: bool
    supports_live_frame: bool
    board_size: dict[str, int] | None = None
    schema_version: str = GAME_RENDER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "rendererFamily": self.renderer_family,
            "boardSize": self.board_size,
            "seatLayout": self.seat_layout,
            "hiddenInfo": self.hidden_info,
            "supportsReplay": self.supports_replay,
            "supportsLiveFrame": self.supports_live_frame,
        }


def validate_render_spec(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload.get("rendererFamily"), str) or not payload.get("rendererFamily"):
        errors.append("renderSpec.rendererFamily is required")
    if payload.get("seatLayout") not in {"two_sides", "compass", "table_ring", "solo_panel"}:
        errors.append("renderSpec.seatLayout is unsupported")
    for key in ("hiddenInfo", "supportsReplay", "supportsLiveFrame"):
        if not isinstance(payload.get(key), bool):
            errors.append(f"renderSpec.{key} must be boolean")
    return errors


def no_secret_example() -> dict[str, Any]:
    return GameRenderSpec(
        renderer_family="connect_four",
        board_size={"rows": 6, "cols": 7},
        seat_layout="two_sides",
        hidden_info=False,
        supports_replay=True,
        supports_live_frame=True,
    ).to_dict()
