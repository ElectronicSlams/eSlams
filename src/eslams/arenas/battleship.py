"""Compact deterministic Battleship arena."""

from __future__ import annotations

import random
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

GRID_SIZE = 5
SHIP_COUNT = 3


class BattleshipArena(Arena):
    id = "battleship"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": r"^[0-4],[0-4]$",
        "description": "Fire at an unrevealed row,column cell on the opponent board.",
    }
    max_turns = GRID_SIZE * GRID_SIZE * 2

    def initial_state(self, seed: int) -> ArenaState:
        ships = _ship_layout(seed)
        return self._state(
            ships=ships,
            shots={"player_1": [], "player_2": []},
            turn=0,
            active="player_1",
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "grid_size": GRID_SIZE,
            "own_ships": state.private_state_by_player[player_id]["own_ships"],
            "shots": state.public_state["shots"],
            "hits": state.public_state["hits"],
            "legal_shots": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal battleship shot")
        ships = {
            player: list(private["own_ships"])
            for player, private in state.private_state_by_player.items()
        }
        shots = {
            player: [dict(shot) for shot in state.public_state["shots"][player]]
            for player in self.players
        }
        opponent = _opponent(player_id)
        hit = action in ships[opponent]
        shots[player_id].append({"cell": action, "hit": hit})
        hit_count = sum(1 for shot in shots[player_id] if shot["hit"])
        outcome = None
        if hit_count >= len(ships[opponent]):
            outcome = {
                "winner": player_id,
                "reason": "fleet_sunk",
                "final_shot": action,
                "hits": {
                    player: sum(1 for shot in shots[player] if shot["hit"])
                    for player in self.players
                },
            }
        return self._state(
            ships=ships,
            shots=shots,
            turn=state.turn + 1,
            active=opponent,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        ships: dict[str, list[str]],
        shots: dict[str, list[dict[str, Any]]],
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "shot_limit"}
        legal = [] if terminal else _available_shots(shots[active])
        hits = {
            player: sum(1 for shot in shots[player] if shot["hit"])
            for player in self.players
        }
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "grid_size": GRID_SIZE,
                "shots": shots,
                "hits": hits,
                "remaining_ship_counts": {
                    _opponent(player): max(0, len(ships[_opponent(player)]) - hits[player])
                    for player in self.players
                },
            },
            private_state_by_player={
                player: {"own_ships": ships[player]} for player in self.players
            },
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"battleship:{seed}"),
            render_hints={"renderer": "battleship", "rows": GRID_SIZE, "cols": GRID_SIZE},
            metadata={"seed": seed},
        )


def _ship_layout(seed: int) -> dict[str, list[str]]:
    cells = [f"{row},{col}" for row in range(GRID_SIZE) for col in range(GRID_SIZE)]
    rng = random.Random(seed)
    player_1 = sorted(rng.sample(cells, SHIP_COUNT))
    remaining = [cell for cell in cells if cell not in player_1]
    player_2 = sorted(rng.sample(remaining, SHIP_COUNT))
    return {"player_1": player_1, "player_2": player_2}


def _available_shots(previous: list[dict[str, Any]]) -> list[str]:
    fired = {str(shot["cell"]) for shot in previous}
    return [
        f"{row},{col}"
        for row in range(GRID_SIZE)
        for col in range(GRID_SIZE)
        if f"{row},{col}" not in fired
    ]


def _opponent(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _opponent(winner)
    return {winner: 1.0, loser: 0.0}
