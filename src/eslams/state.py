"""Canonical eSlams arena state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.hashing import sha256_json


@dataclass(frozen=True)
class ArenaState:
    state_id: str
    turn: int
    active_player: str
    public_state: dict[str, Any]
    private_state_by_player: dict[str, dict[str, Any]]
    legal_actions_by_player: dict[str, list[Any]]
    scores: dict[str, float]
    terminal: bool
    outcome: dict[str, Any] | None
    rng_commitment: str
    render_hints: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    state_hash: str | None = None
    rehydration_diagnostics: dict[str, Any] | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.turn < 0:
            raise ValueError("turn must be non-negative")
        if not self.state_id:
            raise ValueError("state_id is required")
        if not self.active_player:
            raise ValueError("active_player is required")
        calculated = self.calculate_hash()
        object.__setattr__(self, "state_hash", self.state_hash or calculated)
        if self.state_hash != calculated:
            raise ValueError("state_hash does not match canonical state")

    def calculate_hash(self) -> str:
        return sha256_json(
            {
                "state_id": self.state_id,
                "turn": self.turn,
                "active_player": self.active_player,
                "public_state": self.public_state,
                "private_state_by_player": self.private_state_by_player,
                "legal_actions_by_player": self.legal_actions_by_player,
                "scores": self.scores,
                "terminal": self.terminal,
                "outcome": self.outcome,
                "rng_commitment": self.rng_commitment,
                "render_hints": self.render_hints,
                "metadata": self.metadata,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "state_hash": self.state_hash,
            "turn": self.turn,
            "active_player": self.active_player,
            "public_state": self.public_state,
            "private_state_by_player": self.private_state_by_player,
            "legal_actions_by_player": self.legal_actions_by_player,
            "scores": self.scores,
            "terminal": self.terminal,
            "outcome": self.outcome,
            "rng_commitment": self.rng_commitment,
            "render_hints": self.render_hints,
            "metadata": self.metadata,
        }

    def public_view(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "state_hash": self.state_hash,
            "turn": self.turn,
            "active_player": self.active_player,
            "public_state": self.public_state,
            "legal_actions_by_player": self.legal_actions_by_player,
            "scores": self.scores,
            "terminal": self.terminal,
            "outcome": self.outcome,
            "rng_commitment": self.rng_commitment,
            "render_hints": self.render_hints,
        }
