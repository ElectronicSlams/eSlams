"""Deterministic gridworld benchmark arenas."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

GridPos = tuple[int, int]

DIRECTIONS: dict[str, GridPos] = {
    "down": (1, 0),
    "right": (0, 1),
    "up": (-1, 0),
    "left": (0, -1),
}


class FrozenLakeArena(Arena):
    id = "frozen-lake"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": list(DIRECTIONS),
        "description": "Move the agent one tile on the deterministic frozen lake.",
    }
    max_turns = 32

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(position=(0, 0), turn=0, seed=seed, outcome=None, history=[])

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "position": state.public_state["position"],
            "grid": state.public_state["grid"],
            "goal": state.public_state["goal"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("frozen-lake is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal frozen-lake action")
        position = _move(tuple(state.metadata["position"]), action)
        history = [*state.public_state["history"], {"action": action, "position": list(position)}]
        outcome = _lake_outcome(position)
        return self._state(
            position=position,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
            history=history,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        position: GridPos,
        turn: int,
        seed: int,
        outcome: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "step_limit", "position": list(position)}
        legal = [] if terminal else _legal_moves(position, rows=4, cols=4)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "grid": [
                    ["S", "F", "F", "F"],
                    ["F", "H", "F", "H"],
                    ["F", "F", "F", "H"],
                    ["F", "F", "F", "G"],
                ],
                "position": list(position),
                "goal": [3, 3],
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"environment": "frozen-lake"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores=_single_agent_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"frozen-lake:{seed}"),
            render_hints={"renderer": "gridworld", "rows": 4, "cols": 4},
            metadata={"seed": seed, "position": position},
        )


class CliffWalkingArena(Arena):
    id = "cliff-walking"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": list(DIRECTIONS),
        "description": "Move the agent through the grid while avoiding the cliff.",
    }
    max_turns = 64

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            position=(3, 0),
            turn=0,
            seed=seed,
            reward=0.0,
            outcome=None,
            history=[],
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "position": state.public_state["position"],
            "start": state.public_state["start"],
            "goal": state.public_state["goal"],
            "cliff": state.public_state["cliff"],
            "cumulative_reward": state.public_state["cumulative_reward"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("cliff-walking is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal cliff-walking action")
        position = _move(tuple(state.metadata["position"]), action)
        reward = float(state.metadata["reward"]) - 1.0
        outcome = None
        if position in _cliff_cells():
            reward -= 99.0
            outcome = {
                "winner": "player_2",
                "reason": "fell_from_cliff",
                "position": list(position),
            }
        elif position == (3, 11):
            outcome = {"winner": "player_1", "reason": "reached_goal", "position": list(position)}
        history = [
            *state.public_state["history"],
            {"action": action, "position": list(position), "reward": reward},
        ]
        return self._state(
            position=position,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            reward=reward,
            outcome=outcome,
            history=history,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        position: GridPos,
        turn: int,
        seed: int,
        reward: float,
        outcome: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "step_limit", "position": list(position)}
        legal = [] if terminal else _legal_moves(position, rows=4, cols=12)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "rows": 4,
                "cols": 12,
                "start": [3, 0],
                "goal": [3, 11],
                "position": list(position),
                "cliff": [list(cell) for cell in sorted(_cliff_cells())],
                "cumulative_reward": reward,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"environment": "cliff-walking"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores=_single_agent_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"cliff-walking:{seed}"),
            render_hints={"renderer": "gridworld", "rows": 4, "cols": 12},
            metadata={"seed": seed, "position": position, "reward": reward},
        )


class TaxiArena(Arena):
    id = "taxi"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": ["down", "right", "up", "left", "pickup", "dropoff"],
        "description": "Move the taxi, pick up the passenger, and drop off at the destination.",
    }
    max_turns = 80

    def initial_state(self, seed: int) -> ArenaState:
        landmarks = _taxi_landmarks()
        passenger = landmarks[seed % len(landmarks)]
        destination = landmarks[(seed + 2) % len(landmarks)]
        if passenger == destination:
            destination = landmarks[(seed + 3) % len(landmarks)]
        return self._state(
            taxi=(2, 2),
            passenger=passenger,
            destination=destination,
            onboard=False,
            turn=0,
            seed=seed,
            outcome=None,
            history=[],
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "taxi": state.public_state["taxi"],
            "passenger": state.public_state["passenger"],
            "destination": state.public_state["destination"],
            "onboard": state.public_state["onboard"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("taxi is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal taxi action")
        taxi = tuple(state.metadata["taxi"])
        passenger = tuple(state.metadata["passenger"])
        destination = tuple(state.metadata["destination"])
        onboard = bool(state.metadata["onboard"])
        outcome = None
        if action in DIRECTIONS:
            taxi = _move(taxi, action)
        elif action == "pickup":
            onboard = True
        elif action == "dropoff":
            onboard = False
            outcome = {
                "winner": "player_1",
                "reason": "passenger_delivered",
                "destination": list(destination),
            }
        history = [
            *state.public_state["history"],
            {"action": action, "taxi": list(taxi), "onboard": onboard},
        ]
        return self._state(
            taxi=taxi,
            passenger=passenger,
            destination=destination,
            onboard=onboard,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
            history=history,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        taxi: GridPos,
        passenger: GridPos,
        destination: GridPos,
        onboard: bool,
        turn: int,
        seed: int,
        outcome: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "step_limit", "taxi": list(taxi)}
        legal = [] if terminal else _legal_moves(taxi, rows=5, cols=5)
        if not terminal and not onboard and taxi == passenger:
            legal.append("pickup")
        if not terminal and onboard and taxi == destination:
            legal.append("dropoff")
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "rows": 5,
                "cols": 5,
                "taxi": list(taxi),
                "passenger": "in_taxi" if onboard else list(passenger),
                "destination": list(destination),
                "landmarks": [list(cell) for cell in _taxi_landmarks()],
                "onboard": onboard,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"environment": "taxi"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores=_single_agent_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"taxi:{seed}"),
            render_hints={"renderer": "gridworld", "rows": 5, "cols": 5},
            metadata={
                "seed": seed,
                "taxi": taxi,
                "passenger": passenger,
                "destination": destination,
                "onboard": onboard,
            },
        )


def _lake_outcome(position: GridPos) -> dict[str, Any] | None:
    if position in {(1, 1), (1, 3), (2, 3)}:
        return {"winner": "player_2", "reason": "fell_in_hole", "position": list(position)}
    if position == (3, 3):
        return {"winner": "player_1", "reason": "reached_goal", "position": list(position)}
    return None


def _move(position: GridPos, action: str) -> GridPos:
    dr, dc = DIRECTIONS[action]
    return position[0] + dr, position[1] + dc


def _legal_moves(position: GridPos, *, rows: int, cols: int) -> list[str]:
    legal: list[str] = []
    for action, (dr, dc) in DIRECTIONS.items():
        row = position[0] + dr
        col = position[1] + dc
        if 0 <= row < rows and 0 <= col < cols:
            legal.append(action)
    return legal


def _single_agent_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") == "player_1":
        return {"player_1": 1.0, "player_2": 0.0}
    return {"player_1": 0.0, "player_2": 1.0}


def _cliff_cells() -> set[GridPos]:
    return {(3, col) for col in range(1, 11)}


def _taxi_landmarks() -> tuple[GridPos, ...]:
    return ((0, 0), (0, 4), (4, 0), (4, 3))
