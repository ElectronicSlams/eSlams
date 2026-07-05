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
    outcome: dict[str, Any] | None
    render_hints: dict[str, Any]
    markers: list[str] = field(default_factory=list)
    schema_version: str = "eslams.replay.public.v1"
    actor_player: str | None = None
    seat: str | None = None
    state_hash_before: str | None = None
    state_hash_after: str | None = None
    action_label: str | None = None
    public_reasoning_ref: str | None = None
    visibility: str = "public"
    public_safe: bool = True
    state_hash_valid: bool | None = True
    state_hash_invalid_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "turn_id": self.turn_id,
            "state_hash": self.state_hash,
            "active_player": self.active_player,
            "actor_player": self.actor_player,
            "seat": self.seat,
            "state_hash_before": self.state_hash_before,
            "state_hash_after": self.state_hash_after,
            "action": self.action,
            "action_label": self.action_label,
            "public_reasoning_ref": self.public_reasoning_ref,
            "visibility": self.visibility,
            "public_safe": self.public_safe,
            "state_hash_valid": self.state_hash_valid,
            "state_hash_invalid_reason": self.state_hash_invalid_reason,
            "public_state": self.public_state,
            "scores": self.scores,
            "terminal": self.terminal,
            "outcome": self.outcome,
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
    scoring_safety_reason: str | None = None
    aggregate_usage: dict[str, Any] = field(default_factory=dict)
    aggregate_cost: dict[str, Any] = field(default_factory=dict)

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
            "scoring_safety_reason": self.scoring_safety_reason,
            "aggregate_usage": self.aggregate_usage,
            "aggregate_cost": self.aggregate_cost,
        }
