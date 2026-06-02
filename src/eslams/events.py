"""Trace, replay, and score event models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TraceEvent:
    event_id: str
    run_id: str
    episode_id: str
    turn_id: int
    event_type: str
    public: dict[str, Any]
    agent_visible: dict[str, Any]
    judge: dict[str, Any]
    auditor: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)

    def view(self, privacy: str) -> dict[str, Any]:
        base = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "turn_id": self.turn_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
        }
        if privacy == "public":
            base.update(self.public)
        elif privacy == "agent_visible":
            base.update(self.agent_visible)
        elif privacy == "private_judge":
            base.update(self.public)
            base.update(self.judge)
        elif privacy == "auditor":
            base.update(self.public)
            base.update(self.judge)
            base.update(self.auditor)
        else:
            raise ValueError(f"unknown privacy view {privacy!r}")
        return base


@dataclass(frozen=True)
class ReplayEvent:
    event_id: str
    run_id: str
    episode_id: str
    turn_id: int
    state_hash: str
    active_player: str
    action: Any | None
    public_state: dict[str, Any]
    scores: dict[str, float]
    terminal: bool
    render_hints: dict[str, Any]
    markers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "turn_id": self.turn_id,
            "state_hash": self.state_hash,
            "active_player": self.active_player,
            "action": self.action,
            "public_state": self.public_state,
            "scores": self.scores,
            "terminal": self.terminal,
            "render_hints": self.render_hints,
            "markers": self.markers,
        }


@dataclass(frozen=True)
class ScoreSummary:
    run_id: str
    arena_id: str
    primary_score: float
    scores_by_player: dict[str, float]
    winner: str | None
    outcome: dict[str, Any] | None
    metrics: dict[str, Any]
    verification_level: str = "Local Artifact"
    match_valid_for_scoring: bool = True
    invalid_reason: str | None = None
    agent_error_count_by_player: dict[str, int] = field(default_factory=dict)
    illegal_action_count_by_player: dict[str, int] = field(default_factory=dict)
    fallback_action_count_by_player: dict[str, int] = field(default_factory=dict)
    provider_status_by_player: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "arena_id": self.arena_id,
            "primary_score": self.primary_score,
            "scores_by_player": self.scores_by_player,
            "winner": self.winner,
            "outcome": self.outcome,
            "metrics": self.metrics,
            "verification_level": self.verification_level,
            "match_valid_for_scoring": self.match_valid_for_scoring,
            "invalid_reason": self.invalid_reason,
            "agent_error_count_by_player": self.agent_error_count_by_player,
            "illegal_action_count_by_player": self.illegal_action_count_by_player,
            "fallback_action_count_by_player": self.fallback_action_count_by_player,
            "provider_status_by_player": self.provider_status_by_player,
        }
