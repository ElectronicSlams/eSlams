"""Versioned /act protocol models.

The protocol intentionally uses plain dataclasses instead of framework-owned
objects so agents can implement it in any language.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "eslams-act-v1"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PUBLIC_EXPLANATION_BYTES = 16 * 1024


class ProtocolError(ValueError):
    """Raised when an /act payload violates the public protocol."""


@dataclass(frozen=True)
class ArenaIdentity:
    id: str
    version: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ArenaIdentity:
        arena_id = _required_str(value, "id")
        version = _required_str(value, "version")
        return cls(id=arena_id, version=version)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class AgentIdentity:
    id: str
    version: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> AgentIdentity:
        agent_id = _required_str(value, "id")
        version = _required_str(value, "version")
        return cls(id=agent_id, version=version)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class ActRequest:
    protocol_version: str
    run_id: str
    episode_id: str
    turn_id: int
    arena: ArenaIdentity
    agent: AgentIdentity
    active_player: str
    observation: dict[str, Any]
    legal_actions: list[Any]
    action_schema: dict[str, Any]
    history: list[dict[str, Any]]
    time_budget_ms: int
    memory_policy: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ActRequest:
        protocol_version = _required_str(value, "protocol_version")
        if protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"unsupported protocol_version {protocol_version!r}; expected {PROTOCOL_VERSION!r}"
            )
        turn_id = _required_int(value, "turn_id")
        time_budget_ms = _required_int(value, "time_budget_ms")
        if turn_id < 0:
            raise ProtocolError("turn_id must be non-negative")
        if time_budget_ms <= 0:
            raise ProtocolError("time_budget_ms must be positive")

        arena = value.get("arena")
        agent = value.get("agent")
        if not isinstance(arena, Mapping):
            raise ProtocolError("arena must be an object")
        if not isinstance(agent, Mapping):
            raise ProtocolError("agent must be an object")

        return cls(
            protocol_version=protocol_version,
            run_id=_required_str(value, "run_id"),
            episode_id=_required_str(value, "episode_id"),
            turn_id=turn_id,
            arena=ArenaIdentity.from_mapping(arena),
            agent=AgentIdentity.from_mapping(agent),
            active_player=_required_str(value, "active_player"),
            observation=_required_dict(value, "observation"),
            legal_actions=_required_list(value, "legal_actions"),
            action_schema=_required_dict(value, "action_schema"),
            history=_required_history(value.get("history")),
            time_budget_ms=time_budget_ms,
            memory_policy=_required_str(value, "memory_policy"),
            metadata=_optional_dict(value, "metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "turn_id": self.turn_id,
            "arena": self.arena.to_dict(),
            "agent": self.agent.to_dict(),
            "active_player": self.active_player,
            "observation": self.observation,
            "legal_actions": self.legal_actions,
            "action_schema": self.action_schema,
            "history": self.history,
            "time_budget_ms": self.time_budget_ms,
            "memory_policy": self.memory_policy,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ActResponse:
    action: Any
    confidence: float | None = None
    public_explanation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ActResponse:
        validate_json_payload(value)
        if "action" not in value:
            raise ProtocolError("response.action is required")
        confidence = value.get("confidence")
        if confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ProtocolError("response.confidence must be numeric")
            try:
                confidence = float(confidence)
            except OverflowError as exc:
                raise ProtocolError("response.confidence must be finite") from exc
            if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
                raise ProtocolError("response.confidence must be between 0 and 1")
        public_explanation = value.get("public_explanation")
        if public_explanation is not None and not isinstance(public_explanation, str):
            raise ProtocolError("response.public_explanation must be a string")
        if (
            public_explanation is not None
            and len(public_explanation.encode("utf-8")) > MAX_PUBLIC_EXPLANATION_BYTES
        ):
            raise ProtocolError("response.public_explanation exceeds 16 KiB limit")
        return cls(
            action=value["action"],
            confidence=confidence,
            public_explanation=public_explanation,
            metadata=_optional_dict(value, "metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"action": self.action, "metadata": self.metadata}
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.public_explanation is not None:
            result["public_explanation"] = self.public_explanation
        return result


def make_act_request(
    *,
    run_id: str,
    episode_id: str,
    turn_id: int,
    arena_id: str,
    arena_version: str,
    agent_id: str,
    agent_version: str,
    active_player: str,
    observation: dict[str, Any],
    legal_actions: list[Any],
    action_schema: dict[str, Any],
    history: list[dict[str, Any]],
    time_budget_ms: int,
    memory_policy: str,
    metadata: dict[str, Any] | None = None,
) -> ActRequest:
    return ActRequest(
        protocol_version=PROTOCOL_VERSION,
        run_id=run_id,
        episode_id=episode_id,
        turn_id=turn_id,
        arena=ArenaIdentity(id=arena_id, version=arena_version),
        agent=AgentIdentity(id=agent_id, version=agent_version),
        active_player=active_player,
        observation=observation,
        legal_actions=legal_actions,
        action_schema=action_schema,
        history=history,
        time_budget_ms=time_budget_ms,
        memory_policy=memory_policy,
        metadata=metadata or {},
    )


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ProtocolError(f"{key} must be a non-empty string")
    return item


def _required_int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ProtocolError(f"{key} must be an integer")
    return item


def _required_dict(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtocolError(f"{key} must be an object")
    return item


def _optional_dict(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key, {})
    if item is None:
        return {}
    if not isinstance(item, dict):
        raise ProtocolError(f"{key} must be an object")
    return item


def _required_list(value: Mapping[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise ProtocolError(f"{key} must be a list")
    return item


def _required_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProtocolError("history must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ProtocolError("history items must be objects")
    return value


def validate_json_payload(value: Any) -> None:
    """Reject invalid JSON/Unicode and oversized payloads before artifact logging."""
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise ProtocolError(
            "response must contain finite JSON values and valid UTF-8 text"
        ) from exc
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ProtocolError("agent/provider response exceeds 1 MiB limit")
