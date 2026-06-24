"""Game topology contracts for Core 0.5 public catalogue exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import GAME_TOPOLOGY_SCHEMA_VERSION

TOPOLOGY_MODES = {"solo_score", "head_to_head", "multi_seat"}


@dataclass(frozen=True)
class GameTopology:
    mode: str
    controlled_players: tuple[str, ...]
    environment_players: tuple[str, ...]
    min_players: int
    max_players: int
    default_players: int
    winner_required: bool
    draw_allowed: bool
    placements_allowed: bool
    score_type: str
    evaluated_player: str | None = None
    schema_version: str = GAME_TOPOLOGY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "mode": self.mode,
            "controlledPlayers": list(self.controlled_players),
            "environmentPlayers": list(self.environment_players),
            "minPlayers": self.min_players,
            "maxPlayers": self.max_players,
            "defaultPlayers": self.default_players,
            "winnerRequired": self.winner_required,
            "drawAllowed": self.draw_allowed,
            "placementsAllowed": self.placements_allowed,
            "scoreType": self.score_type,
        }
        if self.evaluated_player is not None:
            payload["evaluatedPlayer"] = self.evaluated_player
        return payload


def solo_score_topology(*, score_type: str = "reward") -> GameTopology:
    return GameTopology(
        mode="solo_score",
        evaluated_player="player_1",
        controlled_players=("player_1",),
        environment_players=(),
        min_players=1,
        max_players=1,
        default_players=1,
        winner_required=False,
        draw_allowed=False,
        placements_allowed=False,
        score_type=score_type,
    )


def head_to_head_topology(
    *, draw_allowed: bool = True, score_type: str = "win_loss_draw"
) -> GameTopology:
    return GameTopology(
        mode="head_to_head",
        controlled_players=("player_1", "player_2"),
        environment_players=(),
        min_players=2,
        max_players=2,
        default_players=2,
        winner_required=True,
        draw_allowed=draw_allowed,
        placements_allowed=False,
        score_type=score_type,
    )


def multi_seat_topology(
    *,
    default_players: int,
    score_type: str = "placement",
    draw_allowed: bool = False,
    placements_allowed: bool = True,
) -> GameTopology:
    players = tuple(f"player_{index}" for index in range(1, default_players + 1))
    return GameTopology(
        mode="multi_seat",
        controlled_players=players,
        environment_players=(),
        min_players=default_players,
        max_players=default_players,
        default_players=default_players,
        winner_required=True,
        draw_allowed=draw_allowed,
        placements_allowed=placements_allowed,
        score_type=score_type,
    )


def validate_topology(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = payload.get("mode")
    controlled = payload.get("controlledPlayers")
    environment = payload.get("environmentPlayers")
    min_players = payload.get("minPlayers")
    max_players = payload.get("maxPlayers")
    default_players = payload.get("defaultPlayers")

    if mode not in TOPOLOGY_MODES:
        errors.append("topology.mode is unsupported")
    if not isinstance(controlled, list) or not all(isinstance(item, str) for item in controlled):
        errors.append("topology.controlledPlayers must be a string array")
    if not isinstance(environment, list) or not all(isinstance(item, str) for item in environment):
        errors.append("topology.environmentPlayers must be a string array")
    if not all(
        isinstance(value, int) and value >= 1
        for value in (min_players, max_players, default_players)
    ):
        errors.append("topology player counts must be positive integers")
    else:
        assert isinstance(min_players, int)
        assert isinstance(max_players, int)
        assert isinstance(default_players, int)
        if not (min_players <= default_players <= max_players):
            errors.append("topology player counts must satisfy min <= default <= max")

    if mode == "solo_score":
        if payload.get("evaluatedPlayer") != "player_1":
            errors.append("solo_score topology must evaluate player_1")
        if controlled != ["player_1"]:
            errors.append("solo_score topology must have exactly one controlled player")
        if payload.get("winnerRequired") is not False:
            errors.append("solo_score topology cannot require a winner")
    elif mode == "head_to_head":
        if controlled != ["player_1", "player_2"]:
            errors.append("head_to_head topology must control player_1 and player_2")
        if environment != []:
            errors.append("head_to_head topology cannot have environment players")
        if payload.get("winnerRequired") is not True:
            errors.append("head_to_head topology must require a winner or draw contract")
    elif mode == "multi_seat":
        if isinstance(controlled, list) and len(controlled) < 3:
            errors.append("multi_seat topology must have at least three controlled players")
        if payload.get("winnerRequired") is not True:
            errors.append("multi_seat topology must require a winner or placement contract")
    return errors


def no_secret_example() -> dict[str, Any]:
    return head_to_head_topology().to_dict()
