"""Game result contracts and validators for Core 0.5."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_RESULT_SCHEMA_VERSION


@dataclass(frozen=True)
class GameResultContract:
    mode: str
    result_types: tuple[str, ...]
    score_type: str
    winner_required: bool
    draw_allowed: bool
    placements_allowed: bool
    evaluated_player: str | None = None
    schema_version: str = GAME_RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "mode": self.mode,
            "resultTypes": list(self.result_types),
            "scoreType": self.score_type,
            "winnerRequired": self.winner_required,
            "drawAllowed": self.draw_allowed,
            "placementsAllowed": self.placements_allowed,
        }
        if self.evaluated_player is not None:
            payload["evaluatedPlayer"] = self.evaluated_player
        return payload


def result_contract_for_topology(topology: dict[str, Any]) -> GameResultContract:
    mode = str(topology["mode"])
    if mode == "solo_score":
        return GameResultContract(
            mode=mode,
            result_types=("score",),
            score_type=str(topology.get("scoreType", "reward")),
            winner_required=False,
            draw_allowed=False,
            placements_allowed=False,
            evaluated_player="player_1",
        )
    if mode == "multi_seat":
        score_type = str(topology.get("scoreType", "placement"))
        result_types = ("winner", "placement", "points", "chips")
        return GameResultContract(
            mode=mode,
            result_types=result_types,
            score_type=score_type,
            winner_required=True,
            draw_allowed=topology.get("drawAllowed") is True,
            placements_allowed=topology.get("placementsAllowed") is True,
        )
    return GameResultContract(
        mode="head_to_head",
        result_types=("winner", "draw", "points"),
        score_type=str(topology.get("scoreType", "win_loss_draw")),
        winner_required=True,
        draw_allowed=topology.get("drawAllowed") is True,
        placements_allowed=False,
    )


def validate_result(payload: dict[str, Any], topology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = topology.get("mode")
    controlled = topology.get("controlledPlayers")
    controlled_players = [str(item) for item in controlled] if isinstance(controlled, list) else []
    if payload.get("schemaVersion") != GAME_RESULT_SCHEMA_VERSION:
        errors.append("result.schemaVersion is unsupported")
    if payload.get("mode") != mode:
        errors.append("result.mode must match topology.mode")
    if payload.get("terminal") is not True:
        errors.append("result.terminal must be true")

    scores = payload.get("scores")
    if not isinstance(scores, dict):
        errors.append("result.scores must be an object")
    else:
        for player in controlled_players:
            score = scores.get(player)
            if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                errors.append(f"result.scores.{player} must be finite")

    if mode == "solo_score":
        if payload.get("evaluatedPlayer") != topology.get("evaluatedPlayer"):
            errors.append("solo result evaluatedPlayer must match topology")
        if payload.get("winner") is not None:
            errors.append("solo result winner must be null")
        if payload.get("draw") is not False:
            errors.append("solo result draw must be false")
        primary_score = payload.get("primaryScore")
        if not isinstance(primary_score, (int, float)) or not math.isfinite(
            float(primary_score)
        ):
            errors.append("solo result primaryScore must be finite")
        if payload.get("resultType") != "score":
            errors.append("solo resultType must be score")
    elif mode == "head_to_head":
        winner = payload.get("winner")
        draw = payload.get("draw")
        if winner is not None and winner not in controlled_players:
            errors.append("head_to_head winner must be a controlled player")
        if winner is None and draw is not True:
            errors.append("head_to_head winner can be null only for draw")
        if draw is True and topology.get("drawAllowed") is not True:
            errors.append("head_to_head draw is not allowed by topology")
        if payload.get("resultType") not in {"winner", "draw", "points"}:
            errors.append("head_to_head resultType is unsupported")
    elif mode == "multi_seat":
        winner = payload.get("winner")
        if winner is not None and winner not in controlled_players:
            errors.append("multi_seat winner must be a controlled player")
        placements = payload.get("placements")
        if placements is not None and (
            not isinstance(placements, list) or sorted(placements) != sorted(controlled_players)
        ):
            errors.append("multi_seat placements must include each controlled player once")
        if payload.get("resultType") not in {"winner", "placement", "points", "chips"}:
            errors.append("multi_seat resultType is unsupported")
    else:
        errors.append("result topology mode is unsupported")
    return errors


def no_secret_example() -> dict[str, Any]:
    return {
        "schemaVersion": GAME_RESULT_SCHEMA_VERSION,
        "mode": "head_to_head",
        "terminal": True,
        "winner": "player_1",
        "draw": False,
        "scores": {"player_1": 1, "player_2": 0},
        "resultType": "winner",
        "reason": "four_in_a_row",
    }
