"""Deterministic modern control benchmark arenas."""

from __future__ import annotations

import math
import random
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")


class LunarLanderArena(Arena):
    id = "lunar-lander"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["idle", "left", "right", "main"],
        "description": "Fire no engine, side thrusters, or main engine.",
    }
    max_turns = 220

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        return self._state(
            x=rng.uniform(-0.18, 0.18),
            y=1.0,
            vx=rng.uniform(-0.015, 0.015),
            vy=0.0,
            angle=rng.uniform(-0.08, 0.08),
            angular_velocity=0.0,
            fuel=100.0,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "lander": state.public_state["lander"],
            "fuel": state.public_state["fuel"],
            "landing_pad": state.public_state["landing_pad"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("lunar-lander is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal lunar-lander action")
        x = float(state.metadata["x"])
        y = float(state.metadata["y"])
        vx = float(state.metadata["vx"])
        vy = float(state.metadata["vy"])
        angle = float(state.metadata["angle"])
        angular_velocity = float(state.metadata["angular_velocity"])
        fuel = float(state.public_state["fuel"])
        if action == "main" and fuel >= 2.0:
            vy += 0.045 * math.cos(angle)
            vx += 0.018 * math.sin(angle)
            fuel -= 2.0
        elif action == "left" and fuel >= 1.0:
            vx -= 0.012
            angular_velocity -= 0.035
            fuel -= 1.0
        elif action == "right" and fuel >= 1.0:
            vx += 0.012
            angular_velocity += 0.035
            fuel -= 1.0
        vy -= 0.028
        x += vx
        y += vy
        angle += angular_velocity
        angular_velocity *= 0.96
        turn = state.turn + 1
        outcome = _lander_outcome(x, y, vx, vy, angle, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "x": _round(x), "y": _round(y), "fuel": _round(fuel)},
        ]
        return self._state(
            x=x,
            y=y,
            vx=vx,
            vy=vy,
            angle=angle,
            angular_velocity=angular_velocity,
            fuel=fuel,
            turn=turn,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        x: float,
        y: float,
        vx: float,
        vy: float,
        angle: float,
        angular_velocity: float,
        fuel: float,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "time_limit"}
        legal = [] if terminal else list(self.action_schema["enum"])
        stability = _clip(1.0 - (abs(x) + abs(vy) * 4.0 + abs(angle)), 0.0, 1.0)
        score = 1.0 if outcome and outcome.get("winner") == "player_1" else stability * 0.6
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "lander": {
                    "x": _round(x),
                    "y": _round(max(0.0, y)),
                    "vx": _round(vx),
                    "vy": _round(vy),
                    "angle": _round(angle),
                },
                "fuel": _round(fuel),
                "landing_pad": {"x_min": -0.2, "x_max": 0.2, "y": 0.0},
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"role": "environment"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": score, "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"lunar-lander:{seed}"),
            render_hints={"renderer": "lunar-lander"},
            metadata={
                "seed": seed,
                "x": x,
                "y": y,
                "vx": vx,
                "vy": vy,
                "angle": angle,
                "angular_velocity": angular_velocity,
            },
        )


class CarRacingArena(Arena):
    id = "car-racing"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["accelerate", "brake", "left", "right", "coast"],
        "description": "Control throttle, braking, or steering on a profiled track.",
    }
    max_turns = 180

    def initial_state(self, seed: int) -> ArenaState:
        track = _track_profile(seed)
        return self._state(
            progress=0.0,
            speed=0.08,
            lane=0.0,
            heading=0.0,
            offtrack_ticks=0,
            track=track,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "car": state.public_state["car"],
            "track_window": state.public_state["track_window"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("car-racing is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal car-racing action")
        progress = float(state.metadata["progress"])
        speed = float(state.metadata["speed"])
        lane = float(state.metadata["lane"])
        heading = float(state.metadata["heading"])
        track = list(state.metadata["track"])
        if action == "accelerate":
            speed += 0.025
        elif action == "brake":
            speed -= 0.035
        elif action == "left":
            heading -= 0.05
        elif action == "right":
            heading += 0.05
        speed = _clip(speed, 0.02, 0.18)
        desired_curve = _curve_at(track, progress)
        lane += heading - desired_curve
        heading *= 0.82
        offtrack_ticks = int(state.public_state["offtrack_ticks"])
        if abs(lane) > 1.0:
            offtrack_ticks += 1
            speed *= 0.65
        else:
            offtrack_ticks = max(0, offtrack_ticks - 1)
        progress += speed * max(0.2, 1.0 - abs(lane) * 0.3)
        turn = state.turn + 1
        outcome = _racing_outcome(progress, offtrack_ticks, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "progress": _round(progress), "lane": _round(lane)},
        ]
        return self._state(
            progress=progress,
            speed=speed,
            lane=lane,
            heading=heading,
            offtrack_ticks=offtrack_ticks,
            track=track,
            turn=turn,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        progress: float,
        speed: float,
        lane: float,
        heading: float,
        offtrack_ticks: int,
        track: list[float],
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "lap_timeout"}
        legal = [] if terminal else list(self.action_schema["enum"])
        score = (
            1.0
            if outcome and outcome.get("winner") == "player_1"
            else _clip(progress, 0.0, 1.0)
        )
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "car": {
                    "progress": _round(min(progress, 1.0)),
                    "speed": _round(speed),
                    "lane": _round(lane),
                    "heading": _round(heading),
                },
                "track_window": _track_window(track, progress),
                "offtrack_ticks": offtrack_ticks,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"track": track}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": score, "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"car-racing:{seed}"),
            render_hints={"renderer": "car-racing"},
            metadata={
                "seed": seed,
                "progress": progress,
                "speed": speed,
                "lane": lane,
                "heading": heading,
                "track": track,
            },
        )


class BipedalWalkerArena(Arena):
    id = "bipedal-walker"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["left-step", "right-step", "balance", "jump"],
        "description": "Coordinate stepping and balance across uneven terrain.",
    }
    max_turns = 220

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            distance=0.0,
            velocity=0.08,
            torso_angle=0.0,
            next_foot="left",
            energy=100.0,
            terrain=_terrain_profile(seed),
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "walker": state.public_state["walker"],
            "terrain_window": state.public_state["terrain_window"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("bipedal-walker is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal bipedal-walker action")
        distance = float(state.metadata["distance"])
        velocity = float(state.metadata["velocity"])
        torso_angle = float(state.metadata["torso_angle"])
        next_foot = str(state.metadata["next_foot"])
        energy = float(state.public_state["walker"]["energy"])
        terrain = list(state.metadata["terrain"])
        slope = _terrain_at(terrain, distance)
        if action == f"{next_foot}-step":
            velocity += 0.045
            torso_angle *= 0.65
            next_foot = "right" if next_foot == "left" else "left"
            energy -= 2.0
        elif action in {"left-step", "right-step"}:
            velocity += 0.015
            torso_angle += 0.18 if action == "left-step" else -0.18
            energy -= 3.0
        elif action == "balance":
            torso_angle *= 0.35
            velocity *= 0.92
            energy = min(100.0, energy + 1.0)
        elif action == "jump":
            velocity += 0.03
            torso_angle += 0.08
            energy -= 6.0
        velocity = _clip(velocity - abs(slope) * 0.015, 0.02, 0.22)
        torso_angle += slope * 0.08
        distance += velocity
        turn = state.turn + 1
        outcome = _walker_outcome(distance, torso_angle, energy, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "distance": _round(distance), "angle": _round(torso_angle)},
        ]
        return self._state(
            distance=distance,
            velocity=velocity,
            torso_angle=torso_angle,
            next_foot=next_foot,
            energy=energy,
            terrain=terrain,
            turn=turn,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        distance: float,
        velocity: float,
        torso_angle: float,
        next_foot: str,
        energy: float,
        terrain: list[float],
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "horizon_timeout"}
        legal = [] if terminal else list(self.action_schema["enum"])
        score = (
            1.0
            if outcome and outcome.get("winner") == "player_1"
            else _clip(distance / 10.0, 0.0, 1.0)
        )
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "walker": {
                    "distance": _round(distance),
                    "velocity": _round(velocity),
                    "torso_angle": _round(torso_angle),
                    "next_foot": next_foot,
                    "energy": _round(energy),
                },
                "terrain_window": _terrain_window(terrain, distance),
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"terrain": terrain}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": score, "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"bipedal-walker:{seed}"),
            render_hints={"renderer": "bipedal-walker"},
            metadata={
                "seed": seed,
                "distance": distance,
                "velocity": velocity,
                "torso_angle": torso_angle,
                "next_foot": next_foot,
                "terrain": terrain,
            },
        )


def _lander_outcome(
    x: float,
    y: float,
    vx: float,
    vy: float,
    angle: float,
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    if y > 0.0 and turn < max_turns:
        return None
    landed = abs(x) <= 0.2 and abs(vx) <= 0.08 and abs(vy) <= 0.12 and abs(angle) <= 0.3
    if landed:
        return {"winner": "player_1", "reason": "soft_landing", "turn": turn}
    return {"winner": "player_2", "reason": "crash", "turn": turn}


def _racing_outcome(
    progress: float,
    offtrack_ticks: int,
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    if progress >= 1.0:
        return {"winner": "player_1", "reason": "lap_complete", "turn": turn}
    if offtrack_ticks >= 8:
        return {"winner": "player_2", "reason": "offtrack_failure", "turn": turn}
    if turn >= max_turns:
        return {"winner": "player_2", "reason": "lap_timeout", "turn": turn}
    return None


def _walker_outcome(
    distance: float,
    torso_angle: float,
    energy: float,
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    if distance >= 10.0:
        return {"winner": "player_1", "reason": "course_complete", "turn": turn}
    if abs(torso_angle) > 1.0:
        return {"winner": "player_2", "reason": "fall", "turn": turn}
    if energy <= 0.0:
        return {"winner": "player_2", "reason": "energy_depleted", "turn": turn}
    if turn >= max_turns:
        return {"winner": "player_2", "reason": "horizon_timeout", "turn": turn}
    return None


def _track_profile(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-0.04, 0.04) for _ in range(20)]


def _curve_at(track: list[float], progress: float) -> float:
    index = min(len(track) - 1, max(0, int(progress * len(track))))
    return track[index]


def _track_window(track: list[float], progress: float) -> list[float]:
    index = min(len(track) - 1, max(0, int(progress * len(track))))
    return [_round(item) for item in track[index : index + 4]]


def _terrain_profile(seed: int) -> list[float]:
    rng = random.Random(seed + 313)
    return [rng.uniform(-0.35, 0.35) for _ in range(40)]


def _terrain_at(terrain: list[float], distance: float) -> float:
    index = min(len(terrain) - 1, max(0, int(distance * 2.0)))
    return terrain[index]


def _terrain_window(terrain: list[float], distance: float) -> list[float]:
    index = min(len(terrain) - 1, max(0, int(distance * 2.0)))
    return [_round(item) for item in terrain[index : index + 5]]


def _round(value: float) -> float:
    return round(float(value), 6)


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
