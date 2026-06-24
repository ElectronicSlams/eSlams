"""Public game help contract for Core 0.5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_HELP_SCHEMA_VERSION


@dataclass(frozen=True)
class GameHelp:
    objective: str
    turn_rules: tuple[str, ...]
    legal_action_summary: str
    scoring_summary: str
    win_loss_draw_summary: str
    hidden_info_summary: str | None
    first_move_tip: str | None
    example_actions: tuple[dict[str, str], ...]
    detail_sections: tuple[dict[str, str], ...] = ()
    schema_version: str = GAME_HELP_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "objective": self.objective,
            "turnRules": list(self.turn_rules),
            "legalActionSummary": self.legal_action_summary,
            "scoringSummary": self.scoring_summary,
            "winLossDrawSummary": self.win_loss_draw_summary,
            "hiddenInfoSummary": self.hidden_info_summary,
            "firstMoveTip": self.first_move_tip,
            "exampleActions": [dict(row) for row in self.example_actions],
            "detailSections": [dict(row) for row in self.detail_sections],
        }


def validate_help(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("objective", "legalActionSummary", "scoringSummary", "winLossDrawSummary"):
        if not isinstance(payload.get(key), str) or not payload.get(key):
            errors.append(f"help.{key} is required")
    turn_rules = payload.get("turnRules")
    if not isinstance(turn_rules, list) or not turn_rules:
        errors.append("help.turnRules must be a non-empty array")
    examples = payload.get("exampleActions")
    if not isinstance(examples, list) or not examples:
        errors.append("help.exampleActions must include at least one example")
    return errors


def no_secret_example() -> dict[str, Any]:
    return GameHelp(
        objective="Connect four discs in a row before the opponent does.",
        turn_rules=("Players alternate turns.",),
        legal_action_summary="Choose a non-full column.",
        scoring_summary="First four-in-a-row wins; a full board without four is a draw.",
        win_loss_draw_summary="Winner, draw, and final score are reported by the result contract.",
        hidden_info_summary=None,
        first_move_tip="Center columns usually create more threats.",
        example_actions=(
            {
                "token": "3",
                "label": "Drop in column 4",
                "explanation": "Places your disc in the lowest empty slot of the fourth column.",
            },
        ),
    ).to_dict()
