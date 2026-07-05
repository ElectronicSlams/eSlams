"""Small deterministic matrix-game arenas."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState


class RockPaperScissorsArena(Arena):
    id = "rock-paper-scissors"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": ["rock", "paper", "scissors"],
        "description": "Choose rock, paper, or scissors.",
    }
    max_turns = 2

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(turn=0, active="player_1", seed=seed, pending=None, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "round": state.public_state["round"],
            "revealed_actions": state.public_state["revealed_actions"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal rock-paper-scissors action")
        if player_id == "player_1":
            return self._state(
                turn=state.turn + 1,
                active="player_2",
                seed=int(state.metadata["seed"]),
                pending=action,
                outcome=None,
            )
        pending = str(state.private_state_by_player["player_1"]["pending_action"])
        outcome = _rps_outcome(pending, action)
        return self._state(
            turn=state.turn + 1,
            active="player_1",
            seed=int(state.metadata["seed"]),
            pending=None,
            outcome=outcome,
            revealed={"player_1": pending, "player_2": action},
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        pending: str | None,
        outcome: dict[str, Any] | None,
        revealed: dict[str, str] | None = None,
    ) -> ArenaState:
        terminal = outcome is not None
        legal = [] if terminal else ["rock", "paper", "scissors"]
        private: dict[str, dict[str, Any]] = {player: {} for player in self.players}
        if pending is not None:
            private["player_1"]["pending_action"] = pending
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"round": 1, "revealed_actions": revealed or {}},
            private_state_by_player=private,
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"rock-paper-scissors:{seed}"),
            render_hints={"renderer": "matrix-game"},
            metadata={"seed": seed},
        )


class PrisonersDilemmaArena(Arena):
    id = "prisoners-dilemma"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": ["cooperate", "defect"],
        "description": "Choose cooperate or defect for a one-shot prisoner's dilemma.",
    }
    max_turns = 2

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(turn=0, active="player_1", seed=seed, pending=None, outcome=None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "payoff_matrix": {
                "both_cooperate": [3, 3],
                "player_1_defects": [5, 0],
                "player_2_defects": [0, 5],
                "both_defect": [1, 1],
            },
            "revealed_actions": state.public_state["revealed_actions"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal prisoner's dilemma action")
        if player_id == "player_1":
            return self._state(
                turn=state.turn + 1,
                active="player_2",
                seed=int(state.metadata["seed"]),
                pending=action,
                outcome=None,
            )
        pending = str(state.private_state_by_player["player_1"]["pending_action"])
        payoff = _dilemma_payoff(pending, action)
        winner = None
        if payoff["player_1"] > payoff["player_2"]:
            winner = "player_1"
        elif payoff["player_2"] > payoff["player_1"]:
            winner = "player_2"
        outcome = {
            "winner": winner,
            "reason": "payoff_matrix",
            "payoff": payoff,
            "actions": {"player_1": pending, "player_2": action},
        }
        return self._state(
            turn=state.turn + 1,
            active="player_1",
            seed=int(state.metadata["seed"]),
            pending=None,
            outcome=outcome,
            revealed={"player_1": pending, "player_2": action},
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        pending: str | None,
        outcome: dict[str, Any] | None,
        revealed: dict[str, str] | None = None,
    ) -> ArenaState:
        terminal = outcome is not None
        legal = [] if terminal else ["cooperate", "defect"]
        private: dict[str, dict[str, Any]] = {player: {} for player in self.players}
        if pending is not None:
            private["player_1"]["pending_action"] = pending
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"revealed_actions": revealed or {}},
            private_state_by_player=private,
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_dilemma_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"prisoners-dilemma:{seed}"),
            render_hints={"renderer": "matrix-game"},
            metadata={"seed": seed},
        )


def _rps_outcome(player_1: str, player_2: str) -> dict[str, Any]:
    if player_1 == player_2:
        winner = None
        reason = "draw"
    elif (player_1, player_2) in {
        ("rock", "scissors"),
        ("paper", "rock"),
        ("scissors", "paper"),
    }:
        winner = "player_1"
        reason = "beats"
    else:
        winner = "player_2"
        reason = "beats"
    return {
        "winner": winner,
        "reason": reason,
        "actions": {"player_1": player_1, "player_2": player_2},
    }


def _dilemma_payoff(player_1: str, player_2: str) -> dict[str, float]:
    if player_1 == "cooperate" and player_2 == "cooperate":
        return {"player_1": 3.0, "player_2": 3.0}
    if player_1 == "defect" and player_2 == "cooperate":
        return {"player_1": 5.0, "player_2": 0.0}
    if player_1 == "cooperate" and player_2 == "defect":
        return {"player_1": 0.0, "player_2": 5.0}
    return {"player_1": 1.0, "player_2": 1.0}


def _scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = "player_2" if winner == "player_1" else "player_1"
    return {winner: 1.0, loser: 0.0}


def _dilemma_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    payoff = outcome.get("payoff")
    if not isinstance(payoff, dict):
        return {"player_1": 0.0, "player_2": 0.0}
    max_payoff = 5.0
    return {
        "player_1": float(payoff["player_1"]) / max_payoff,
        "player_2": float(payoff["player_2"]) / max_payoff,
    }
