"""Deterministic Kalah-style Mancala arena."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PITS = 6
STARTING_STONES = 4


class MancalaArena(Arena):
    id = "mancala"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": PITS - 1,
        "description": "Choose one of your six pits, indexed from left to right.",
    }
    max_turns = 200

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            pits={
                "player_1": [STARTING_STONES] * PITS,
                "player_2": [STARTING_STONES] * PITS,
            },
            stores={"player_1": 0, "player_2": 0},
            turn=0,
            active="player_1",
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "pits": state.public_state["pits"],
            "stores": state.public_state["stores"],
            "you_are": player_id,
            "legal_pits": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int):
            raise ValueError("mancala action must be an integer pit")
        if not self.is_legal(state, player_id, action):
            raise ValueError("illegal mancala pit")
        pits = {player: list(values) for player, values in state.public_state["pits"].items()}
        stores = {player: int(value) for player, value in state.public_state["stores"].items()}
        active = player_id
        stones = pits[player_id][action]
        pits[player_id][action] = 0
        position: tuple[str, int | str] = (player_id, action)
        while stones:
            position = _next_position(position, player_id)
            owner, slot = position
            if slot == "store":
                stores[owner] += 1
            else:
                pits[owner][int(slot)] += 1
            stones -= 1

        owner, slot = position
        if owner == player_id and slot == "store":
            active = player_id
        else:
            active = _other(player_id)
            if owner == player_id and isinstance(slot, int) and pits[player_id][slot] == 1:
                opposite = PITS - 1 - slot
                captured = pits[_other(player_id)][opposite]
                if captured:
                    pits[_other(player_id)][opposite] = 0
                    pits[player_id][slot] = 0
                    stores[player_id] += captured + 1

        outcome = _outcome(pits, stores)
        if outcome is not None:
            for player in ("player_1", "player_2"):
                stores[player] += sum(pits[player])
                pits[player] = [0] * PITS
            outcome = _final_outcome(stores, outcome["reason"])

        return self._state(
            pits=pits,
            stores=stores,
            turn=state.turn + 1,
            active=active,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        pits: dict[str, list[int]],
        stores: dict[str, int],
        turn: int,
        active: str,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        if outcome is None and turn >= self.max_turns:
            outcome = _final_outcome(stores, "max_turns")
        terminal = outcome is not None
        legal = [
            index for index, stones in enumerate(pits[active]) if stones > 0
        ] if not terminal else []
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"pits": pits, "stores": stores, "pits_per_side": PITS},
            private_state_by_player={player: {} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"mancala:{seed}"),
            render_hints={"renderer": "mancala-board"},
            metadata={"seed": seed},
        )


def _next_position(position: tuple[str, int | str], active_player: str) -> tuple[str, int | str]:
    owner, slot = position
    opponent = _other(owner)
    if slot == "store":
        return opponent, 0
    pit = int(slot)
    if pit < PITS - 1:
        return owner, pit + 1
    if owner == active_player:
        return owner, "store"
    return _other(owner), 0


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"


def _outcome(pits: dict[str, list[int]], stores: dict[str, int]) -> dict[str, Any] | None:
    if sum(pits["player_1"]) == 0 or sum(pits["player_2"]) == 0:
        return _final_outcome(stores, "side_empty")
    return None


def _final_outcome(stores: dict[str, int], reason: str) -> dict[str, Any]:
    winner = None
    if stores["player_1"] > stores["player_2"]:
        winner = "player_1"
    elif stores["player_2"] > stores["player_1"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "stores": dict(stores)}


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    stores = outcome.get("stores")
    if isinstance(stores, dict):
        total = float(stores["player_1"]) + float(stores["player_2"])
        if total > 0:
            return {
                "player_1": float(stores["player_1"]) / total,
                "player_2": float(stores["player_2"]) / total,
            }
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}
