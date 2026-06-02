"""Deterministic control and arcade benchmark arenas."""

from __future__ import annotations

import math
import random
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")


class CartPoleArena(Arena):
    id = "cartpole"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["left", "right"],
        "description": "Apply a left or right force to the cart.",
    }
    max_turns = 200

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        return self._state(
            x=rng.uniform(-0.035, 0.035),
            x_dot=rng.uniform(-0.035, 0.035),
            theta=rng.uniform(-0.035, 0.035),
            theta_dot=rng.uniform(-0.035, 0.035),
            reward=0.0,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "cart": state.public_state["cart"],
            "pole": state.public_state["pole"],
            "reward": state.public_state["reward"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("cartpole is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal cartpole action")
        x = float(state.metadata["x"])
        x_dot = float(state.metadata["x_dot"])
        theta = float(state.metadata["theta"])
        theta_dot = float(state.metadata["theta_dot"])
        force = 10.0 if action == "right" else -10.0
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        total_mass = 1.1
        polemass_length = 0.05
        temp = (force + polemass_length * theta_dot * theta_dot * sin_theta) / total_mass
        theta_acc = (9.8 * sin_theta - cos_theta * temp) / (
            0.5 * (4.0 / 3.0 - 0.1 * cos_theta * cos_theta / total_mass)
        )
        x_acc = temp - polemass_length * theta_acc * cos_theta / total_mass
        tau = 0.02
        x += tau * x_dot
        x_dot += tau * x_acc
        theta += tau * theta_dot
        theta_dot += tau * theta_acc
        turn = state.turn + 1
        reward = float(state.public_state["reward"]) + 1.0
        outcome = _cartpole_outcome(x, theta, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "x": _round(x), "theta": _round(theta)},
        ]
        return self._state(
            x=x,
            x_dot=x_dot,
            theta=theta,
            theta_dot=theta_dot,
            reward=reward,
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
        x_dot: float,
        theta: float,
        theta_dot: float,
        reward: float,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_1", "reason": "balanced_horizon"}
        legal = [] if terminal else ["left", "right"]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "cart": {"x": _round(x), "velocity": _round(x_dot)},
                "pole": {"angle": _round(theta), "angular_velocity": _round(theta_dot)},
                "thresholds": {"x": 2.4, "angle_radians": _round(12.0 * math.pi / 180.0)},
                "reward": reward,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"role": "environment"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": min(1.0, reward / self.max_turns), "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"cartpole:{seed}"),
            render_hints={"renderer": "cartpole"},
            metadata={
                "seed": seed,
                "x": x,
                "x_dot": x_dot,
                "theta": theta,
                "theta_dot": theta_dot,
            },
        )


class MountainCarArena(Arena):
    id = "mountain-car"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["left", "coast", "right"],
        "description": "Accelerate left, coast, or accelerate right.",
    }
    max_turns = 200

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        return self._state(
            position=-0.55 + rng.uniform(-0.04, 0.04),
            velocity=0.0,
            reward=0.0,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "position": state.public_state["position"],
            "velocity": state.public_state["velocity"],
            "goal_position": state.public_state["goal_position"],
            "reward": state.public_state["reward"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("mountain-car is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal mountain-car action")
        position = float(state.metadata["position"])
        velocity = float(state.metadata["velocity"])
        throttle = {"left": -1.0, "coast": 0.0, "right": 1.0}[action]
        velocity += throttle * 0.001 + math.cos(3.0 * position) * -0.0025
        velocity = _clip(velocity, -0.07, 0.07)
        position += velocity
        if position < -1.2:
            position = -1.2
            velocity = 0.0
        position = _clip(position, -1.2, 0.6)
        turn = state.turn + 1
        reward = float(state.public_state["reward"]) - 1.0
        outcome = _mountain_car_outcome(position, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "position": _round(position), "velocity": _round(velocity)},
        ]
        return self._state(
            position=position,
            velocity=velocity,
            reward=reward,
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
        position: float,
        velocity: float,
        reward: float,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": "player_2", "reason": "step_limit"}
        legal = [] if terminal else ["left", "coast", "right"]
        progress = _clip((position + 1.2) / 1.8, 0.0, 1.0)
        score = 1.0 if outcome and outcome.get("winner") == "player_1" else progress * 0.5
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "position": _round(position),
                "velocity": _round(velocity),
                "goal_position": 0.5,
                "reward": reward,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"role": "environment"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": score, "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"mountain-car:{seed}"),
            render_hints={"renderer": "mountain-car"},
            metadata={"seed": seed, "position": position, "velocity": velocity},
        )


class PaddleBallArena(Arena):
    id = "paddle-ball"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["left", "stay", "right"],
        "description": "Move the paddle before the ball advances.",
    }
    max_turns = 160

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        return self._state(
            paddle_x=0.5,
            ball={"x": 0.5, "y": 0.75, "vx": rng.choice([-0.028, 0.028]), "vy": -0.04},
            bounces=0,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "paddle_x": state.public_state["paddle_x"],
            "ball": state.public_state["ball"],
            "bounces": state.public_state["bounces"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("paddle-ball is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal paddle-ball action")
        paddle_x = float(state.metadata["paddle_x"])
        paddle_x = _clip(paddle_x + {"left": -0.12, "stay": 0.0, "right": 0.12}[action], 0.0, 1.0)
        ball = dict(state.metadata["ball"])
        ball["x"] = float(ball["x"]) + float(ball["vx"])
        ball["y"] = float(ball["y"]) + float(ball["vy"])
        bounces = int(state.public_state["bounces"])
        if ball["x"] <= 0.0 or ball["x"] >= 1.0:
            ball["x"] = _clip(float(ball["x"]), 0.0, 1.0)
            ball["vx"] = -float(ball["vx"])
        if ball["y"] >= 1.0:
            ball["y"] = 1.0
            ball["vy"] = -abs(float(ball["vy"]))
        outcome = None
        if ball["y"] <= 0.08:
            offset = float(ball["x"]) - paddle_x
            if abs(offset) <= 0.16 and float(ball["vy"]) < 0:
                bounces += 1
                ball["y"] = 0.08
                ball["vy"] = abs(float(ball["vy"])) + 0.002
                ball["vx"] = _clip(float(ball["vx"]) + offset * 0.08, -0.08, 0.08)
            else:
                outcome = {"winner": "player_2", "reason": "missed_ball", "bounces": bounces}
        if bounces >= 10:
            outcome = {"winner": "player_1", "reason": "target_rally", "bounces": bounces}
        turn = state.turn + 1
        history = [
            *state.public_state["history"],
            {"action": action, "paddle_x": _round(paddle_x), "ball": _public_ball(ball)},
        ]
        return self._state(
            paddle_x=paddle_x,
            ball=ball,
            bounces=bounces,
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
        paddle_x: float,
        ball: dict[str, float],
        bounces: int,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "rally_timeout", "bounces": bounces}
        legal = [] if terminal else ["left", "stay", "right"]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "paddle_x": _round(paddle_x),
                "ball": _public_ball(ball),
                "bounces": bounces,
                "target_bounces": 10,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"role": "environment"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": min(1.0, bounces / 10.0), "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"paddle-ball:{seed}"),
            render_hints={"renderer": "paddle-ball"},
            metadata={"seed": seed, "paddle_x": paddle_x, "ball": ball},
        )


class AlienShooterArena(Arena):
    id = "alien-shooter"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["left", "stay", "right", "fire"],
        "description": "Move the ship or fire one projectile.",
    }
    max_turns = 96

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        aliens = [(x, 5) for x in sorted(rng.sample(range(7), 4))]
        aliens.extend((x, 4) for x in sorted(rng.sample(range(7), 3)))
        return self._state(
            player_x=3,
            aliens=aliens,
            bullets=[],
            destroyed=0,
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "player_x": state.public_state["player_x"],
            "aliens": state.public_state["aliens"],
            "bullets": state.public_state["bullets"],
            "destroyed": state.public_state["destroyed"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("alien-shooter is controlled by player_1")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal alien-shooter action")
        player_x = int(state.metadata["player_x"])
        if action == "left":
            player_x = max(0, player_x - 1)
        elif action == "right":
            player_x = min(6, player_x + 1)
        bullets = [tuple(item) for item in state.metadata["bullets"]]
        if action == "fire":
            bullets.append((player_x, 1))
        aliens = [tuple(item) for item in state.metadata["aliens"]]
        bullets = [(x, y + 1) for x, y in bullets if y + 1 <= 5]
        aliens, bullets, hits = _resolve_alien_hits(aliens, bullets)
        destroyed = int(state.public_state["destroyed"]) + hits
        turn = state.turn + 1
        if turn % 3 == 0:
            aliens = [(x, y - 1) for x, y in aliens]
        outcome = _alien_outcome(aliens, destroyed, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"action": action, "player_x": player_x, "destroyed": destroyed},
        ]
        return self._state(
            player_x=player_x,
            aliens=aliens,
            bullets=bullets,
            destroyed=destroyed,
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
        player_x: int,
        aliens: list[tuple[int, int]],
        bullets: list[tuple[int, int]],
        destroyed: int,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = {"winner": None, "reason": "time_limit", "destroyed": destroyed}
        legal = [] if terminal else ["left", "stay", "right", "fire"]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "player_x": player_x,
                "aliens": [list(item) for item in aliens],
                "bullets": [list(item) for item in bullets],
                "destroyed": destroyed,
                "history": history,
            },
            private_state_by_player={"player_1": {}, "player_2": {"role": "environment"}},
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores={"player_1": min(1.0, destroyed / 7.0), "player_2": 0.0},
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"alien-shooter:{seed}"),
            render_hints={"renderer": "alien-shooter", "width": 7, "height": 6},
            metadata={
                "seed": seed,
                "player_x": player_x,
                "aliens": aliens,
                "bullets": bullets,
            },
        )


class BoxingStyleArena(Arena):
    id = "boxing-style-arena"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["guard", "jab", "hook", "dodge-left", "dodge-right", "step-in", "step-out"],
        "description": "Boxing movement, defense, and striking actions.",
    }
    max_turns = 80

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            health={"player_1": 100.0, "player_2": 100.0},
            stamina={"player_1": 100.0, "player_2": 100.0},
            stances={"player_1": "neutral", "player_2": "neutral"},
            distance=2,
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "health": state.public_state["health"],
            "stamina": state.public_state["stamina"],
            "stances": state.public_state["stances"],
            "distance": state.public_state["distance"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal boxing-style-arena action")
        opponent = _other(player_id)
        health = dict(state.public_state["health"])
        stamina = dict(state.public_state["stamina"])
        stances = dict(state.public_state["stances"])
        distance = int(state.public_state["distance"])
        damage = 0.0
        if action in {"jab", "hook"}:
            damage = _boxing_damage(action, distance, stamina[player_id], stances[opponent])
            health[opponent] = max(0.0, health[opponent] - damage)
            stamina[player_id] = max(0.0, stamina[player_id] - (8.0 if action == "jab" else 14.0))
            stances[player_id] = "striking"
        elif action == "guard":
            stamina[player_id] = min(100.0, stamina[player_id] + 4.0)
            stances[player_id] = "guard"
        elif action.startswith("dodge"):
            stamina[player_id] = max(0.0, stamina[player_id] - 3.0)
            stances[player_id] = "evasive"
        elif action == "step-in":
            distance = max(0, distance - 1)
            stamina[player_id] = min(100.0, stamina[player_id] + 2.0)
            stances[player_id] = "neutral"
        elif action == "step-out":
            distance = min(3, distance + 1)
            stamina[player_id] = min(100.0, stamina[player_id] + 2.0)
            stances[player_id] = "neutral"
        turn = state.turn + 1
        outcome = _combat_outcome(health, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"player": player_id, "action": action, "damage": _round(damage), "distance": distance},
        ]
        return self._state(
            health=health,
            stamina=stamina,
            stances=stances,
            distance=distance,
            active=opponent,
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
        health: dict[str, float],
        stamina: dict[str, float],
        stances: dict[str, str],
        distance: int,
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _decision_outcome(health, reason="time_limit")
        legal = [] if terminal else list(self.action_schema["enum"])
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "health": {player: _round(value) for player, value in health.items()},
                "stamina": {player: _round(value) for player, value in stamina.items()},
                "stances": stances,
                "distance": distance,
                "history": history,
            },
            private_state_by_player={player: {} for player in PLAYERS},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else []) for player in PLAYERS
            },
            scores=_two_player_scores(outcome, health),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"boxing-style-arena:{seed}"),
            render_hints={"renderer": "boxing-ring"},
            metadata={"seed": seed},
        )


class IceHockeyStyleArena(Arena):
    id = "ice-hockey-style-arena"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["skate-left", "skate-right", "advance", "retreat", "hold", "shoot", "check"],
        "description": "Move, protect the puck, shoot, or challenge possession.",
    }
    max_turns = 90

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(
            positions={"player_1": {"x": 1, "lane": 1}, "player_2": {"x": 3, "lane": 1}},
            puck_owner="player_1",
            goals={"player_1": 0, "player_2": 0},
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "positions": state.public_state["positions"],
            "puck_owner": state.public_state["puck_owner"],
            "goals": state.public_state["goals"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal ice-hockey-style-arena action")
        opponent = _other(player_id)
        positions = {
            player: dict(position) for player, position in state.public_state["positions"].items()
        }
        goals = dict(state.public_state["goals"])
        puck_owner = str(state.public_state["puck_owner"])
        event = "move"
        if action in {"skate-left", "skate-right", "advance", "retreat"}:
            _move_skater(positions[player_id], player_id, action)
        elif action == "check":
            if _hockey_close(positions[player_id], positions[opponent]):
                puck_owner = player_id
                event = "takeaway"
        elif action == "shoot" and puck_owner == player_id:
            if _hockey_shot_scores(positions[player_id], player_id, positions[opponent]):
                goals[player_id] += 1
                puck_owner = opponent
                positions = _reset_hockey_positions(opponent)
                event = "goal"
            else:
                puck_owner = opponent
                event = "saved"
        elif action == "hold":
            event = "hold"
        turn = state.turn + 1
        outcome = _hockey_outcome(goals, turn, self.max_turns)
        history = [
            *state.public_state["history"],
            {"player": player_id, "action": action, "event": event, "goals": dict(goals)},
        ]
        return self._state(
            positions=positions,
            puck_owner=puck_owner,
            goals=goals,
            active=opponent,
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
        positions: dict[str, dict[str, int]],
        puck_owner: str,
        goals: dict[str, int],
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _hockey_decision(goals, reason="time_limit")
        legal = [] if terminal else list(self.action_schema["enum"])
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "positions": positions,
                "puck_owner": puck_owner,
                "goals": goals,
                "rink": {"x": 5, "lanes": 3},
                "history": history,
            },
            private_state_by_player={player: {} for player in PLAYERS},
            legal_actions_by_player={
                player: (legal if player == active and not terminal else []) for player in PLAYERS
            },
            scores=_goal_scores(outcome, goals),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"ice-hockey-style-arena:{seed}"),
            render_hints={"renderer": "ice-hockey-rink"},
            metadata={"seed": seed},
        )


def _cartpole_outcome(x: float, theta: float, turn: int, max_turns: int) -> dict[str, Any] | None:
    if abs(x) > 2.4:
        return {"winner": "player_2", "reason": "cart_out_of_bounds", "turn": turn}
    if abs(theta) > 12.0 * math.pi / 180.0:
        return {"winner": "player_2", "reason": "pole_angle_limit", "turn": turn}
    if turn >= max_turns:
        return {"winner": "player_1", "reason": "balanced_horizon", "turn": turn}
    return None


def _mountain_car_outcome(position: float, turn: int, max_turns: int) -> dict[str, Any] | None:
    if position >= 0.5:
        return {"winner": "player_1", "reason": "reached_goal", "turn": turn}
    if turn >= max_turns:
        return {"winner": "player_2", "reason": "step_limit", "turn": turn}
    return None


def _resolve_alien_hits(
    aliens: list[tuple[int, int]],
    bullets: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], int]:
    alien_set = set(aliens)
    remaining_bullets: list[tuple[int, int]] = []
    hits = 0
    for bullet in bullets:
        if bullet in alien_set:
            alien_set.remove(bullet)
            hits += 1
        else:
            remaining_bullets.append(bullet)
    return sorted(alien_set), remaining_bullets, hits


def _alien_outcome(
    aliens: list[tuple[int, int]],
    destroyed: int,
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    if not aliens:
        return {"winner": "player_1", "reason": "wave_cleared", "destroyed": destroyed}
    if any(y <= 0 for _, y in aliens):
        return {"winner": "player_2", "reason": "invasion", "destroyed": destroyed}
    if turn >= max_turns:
        return {"winner": None, "reason": "time_limit", "destroyed": destroyed}
    return None


def _boxing_damage(action: str, distance: int, stamina: float, opponent_stance: str) -> float:
    base = 8.0 if action == "jab" else 14.0
    reach = 2 if action == "jab" else 1
    if distance > reach or stamina < 4.0:
        return 0.0
    multiplier = 1.0
    if opponent_stance == "guard":
        multiplier *= 0.35
    if opponent_stance == "evasive":
        multiplier *= 0.5
    if stamina < 15.0:
        multiplier *= 0.6
    return base * multiplier


def _combat_outcome(
    health: dict[str, float],
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    for player, value in health.items():
        if value <= 0.0:
            return {"winner": _other(player), "reason": "knockout", "turn": turn}
    if turn >= max_turns:
        return _decision_outcome(health, reason="time_limit")
    return None


def _decision_outcome(health: dict[str, float], *, reason: str) -> dict[str, Any]:
    if health["player_1"] == health["player_2"]:
        winner = None
    else:
        winner = "player_1" if health["player_1"] > health["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "health": health}


def _two_player_scores(
    outcome: dict[str, Any] | None,
    health: dict[str, float],
) -> dict[str, float]:
    if outcome is not None:
        winner = outcome.get("winner")
        if winner is None:
            return {"player_1": 0.5, "player_2": 0.5}
        return {str(winner): 1.0, _other(str(winner)): 0.0}
    total = max(1.0, health["player_1"] + health["player_2"])
    return {"player_1": health["player_1"] / total, "player_2": health["player_2"] / total}


def _move_skater(position: dict[str, int], player_id: str, action: str) -> None:
    if action == "skate-left":
        position["lane"] = max(0, position["lane"] - 1)
    elif action == "skate-right":
        position["lane"] = min(2, position["lane"] + 1)
    elif action == "advance":
        delta = 1 if player_id == "player_1" else -1
        position["x"] = _int_clip(position["x"] + delta, 0, 4)
    elif action == "retreat":
        delta = -1 if player_id == "player_1" else 1
        position["x"] = _int_clip(position["x"] + delta, 0, 4)


def _hockey_close(a: dict[str, int], b: dict[str, int]) -> bool:
    return abs(a["x"] - b["x"]) + abs(a["lane"] - b["lane"]) <= 1


def _hockey_shot_scores(
    shooter: dict[str, int],
    player_id: str,
    defender: dict[str, int],
) -> bool:
    scoring_x = shooter["x"] >= 3 if player_id == "player_1" else shooter["x"] <= 1
    if not scoring_x:
        return False
    return not (defender["lane"] == shooter["lane"] and abs(defender["x"] - shooter["x"]) <= 1)


def _reset_hockey_positions(puck_owner: str) -> dict[str, dict[str, int]]:
    if puck_owner == "player_1":
        return {"player_1": {"x": 1, "lane": 1}, "player_2": {"x": 3, "lane": 1}}
    return {"player_1": {"x": 1, "lane": 1}, "player_2": {"x": 3, "lane": 1}}


def _hockey_outcome(
    goals: dict[str, int],
    turn: int,
    max_turns: int,
) -> dict[str, Any] | None:
    for player, value in goals.items():
        if value >= 2:
            return {"winner": player, "reason": "goal_limit", "goals": goals}
    if turn >= max_turns:
        return _hockey_decision(goals, reason="time_limit")
    return None


def _hockey_decision(goals: dict[str, int], *, reason: str) -> dict[str, Any]:
    if goals["player_1"] == goals["player_2"]:
        winner = None
    else:
        winner = "player_1" if goals["player_1"] > goals["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "goals": goals}


def _goal_scores(outcome: dict[str, Any] | None, goals: dict[str, int]) -> dict[str, float]:
    if outcome is not None:
        winner = outcome.get("winner")
        if winner is None:
            return {"player_1": 0.5, "player_2": 0.5}
        return {str(winner): 1.0, _other(str(winner)): 0.0}
    total = max(1, goals["player_1"] + goals["player_2"])
    return {"player_1": goals["player_1"] / total, "player_2": goals["player_2"] / total}


def _public_ball(ball: dict[str, float]) -> dict[str, float]:
    return {key: _round(float(value)) for key, value in ball.items()}


def _round(value: float) -> float:
    return round(float(value), 6)


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _int_clip(value: int, low: int, high: int) -> int:
    return min(high, max(low, value))


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
