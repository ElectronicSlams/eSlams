"""Public replay contracts and deterministic replay metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eslams.contracts.versions import REPLAY_MANIFEST_SCHEMA_VERSION, REPLAY_PUBLIC_SCHEMA_VERSION

TIMELINE_COMPLETENESS_VALUES: tuple[str, ...] = (
    "playable",
    "partial",
    "setup_only",
    "metadata_only",
    "unavailable",
)


@dataclass(frozen=True)
class ReplayParticipant:
    player_id: str
    seat: str
    label: str
    model_identity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "seat": self.seat,
            "label": self.label,
            "model_identity": dict(self.model_identity),
        }


@dataclass(frozen=True)
class PublicReplayManifest:
    replay_id: str
    run_id: str
    arena_id: str
    variant_id: str
    event_count: int
    visible_frame_count: int
    state_frame_count: int
    move_frame_count: int
    setup_only: bool
    timeline_completeness: str
    renderer_kind: str
    render_hints_version: str
    public_state_shape_version: str
    has_public_state: bool
    state_hash_valid: bool | None
    participants: list[ReplayParticipant]
    showcase_ready: bool
    minimum_autoplay_frames: int
    autoplay_ready: bool
    reasoning_frame_coverage: float
    schema_version: str = REPLAY_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "replay_id": self.replay_id,
            "run_id": self.run_id,
            "arena_id": self.arena_id,
            "variant_id": self.variant_id,
            "event_count": self.event_count,
            "visible_frame_count": self.visible_frame_count,
            "state_frame_count": self.state_frame_count,
            "move_frame_count": self.move_frame_count,
            "setup_only": self.setup_only,
            "timeline_completeness": self.timeline_completeness,
            "renderer_kind": self.renderer_kind,
            "render_hints_version": self.render_hints_version,
            "public_state_shape_version": self.public_state_shape_version,
            "has_public_state": self.has_public_state,
            "state_hash_valid": self.state_hash_valid,
            "participants": [participant.to_dict() for participant in self.participants],
            "showcase_ready": self.showcase_ready,
            "minimum_autoplay_frames": self.minimum_autoplay_frames,
            "autoplay_ready": self.autoplay_ready,
            "reasoning_frame_coverage": self.reasoning_frame_coverage,
        }


@dataclass(frozen=True)
class PublicReasoningRow:
    turn: int
    seat: str | None
    actor_player: str | None
    action: Any
    state_hash_before: str | None
    state_hash_after: str | None
    public_explanation: str | None
    source_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "seat": self.seat,
            "actor_player": self.actor_player,
            "action": self.action,
            "state_hash_before": self.state_hash_before,
            "state_hash_after": self.state_hash_after,
            "public_explanation": self.public_explanation,
            "source_event_id": self.source_event_id,
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    participant = ReplayParticipant("player_1", "seat_1", "Player 1")
    return {
        REPLAY_PUBLIC_SCHEMA_VERSION: {
            "schema_version": REPLAY_PUBLIC_SCHEMA_VERSION,
            "event_id": "run_example:replay:000001",
            "run_id": "run_example",
            "turn_id": 1,
            "actor_player": "player_1",
            "seat": "seat_1",
            "visibility": "public",
            "public_safe": True,
            "state_hash_valid": True,
        },
        REPLAY_MANIFEST_SCHEMA_VERSION: PublicReplayManifest(
            replay_id="run_example:public-replay",
            run_id="run_example",
            arena_id="tic-tac-toe",
            variant_id="default",
            event_count=2,
            visible_frame_count=2,
            state_frame_count=2,
            move_frame_count=1,
            setup_only=False,
            timeline_completeness="playable",
            renderer_kind="eslams-html-v1",
            render_hints_version="render-hints-v1",
            public_state_shape_version="public-state-v1",
            has_public_state=True,
            state_hash_valid=True,
            participants=[participant],
            showcase_ready=True,
            minimum_autoplay_frames=2,
            autoplay_ready=True,
            reasoning_frame_coverage=0.0,
        ).to_dict(),
    }
