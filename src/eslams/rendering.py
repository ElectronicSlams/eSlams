"""Public replay renderability and render-hint vocabulary."""

from __future__ import annotations

from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry as arena_registry
from eslams.contracts.safety import scan_public_payload
from eslams.contracts.versions import CATALOGUE_RENDERER_SCHEMA_VERSION
from eslams.hashing import sha256_json

RENDER_HINTS_VERSION = "render-hints-v1"
PUBLIC_STATE_SHAPE_VERSION = "public-state-v1"
TIMELINE_COMPLETENESS_VALUES = {
    "playable",
    "partial",
    "setup_only",
    "metadata_only",
    "unavailable",
}


def renderer_vocabulary_rows(*, seed: int = 1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for arena_id in arena_registry.list():
        arena = arena_registry.create(arena_id)
        state = arena.initial_state(seed)
        legal_actions = arena.legal_actions_for(state, state.active_player)
        step_status = _step_status(arena, state, legal_actions)
        public_payload = {
            "active_player": state.active_player,
            "public_state": state.public_state,
            "legal_actions": legal_actions,
            "render_hints": state.render_hints,
            "scores": state.scores,
            "terminal": state.terminal,
            "outcome": state.outcome,
        }
        safety_issues = scan_public_payload(public_payload)
        timeline_completeness = _timeline_completeness(
            has_public_state=bool(state.public_state),
            can_step=step_status["can_step"] is True,
            terminal=state.terminal,
            safe=not safety_issues,
        )
        rows.append(
            {
                "schema_version": CATALOGUE_RENDERER_SCHEMA_VERSION,
                "game_id": arena_id,
                "renderer_family": renderer_family(state.render_hints),
                "renderer_kind": renderer_kind(state.render_hints),
                "render_hints_version": RENDER_HINTS_VERSION,
                "public_state_shape_version": PUBLIC_STATE_SHAPE_VERSION,
                "timeline_completeness": timeline_completeness,
                "replay_availability": timeline_completeness,
                "has_public_state": bool(state.public_state),
                "legal_action_count": len(legal_actions),
                "visible_frame_count": 1 + int(step_status["can_step"] is True),
                "state_frame_count": 1 + int(step_status["can_step"] is True),
                "move_frame_count": int(step_status["can_step"] is True),
                "setup_only": timeline_completeness == "setup_only",
                "showcase_ready": timeline_completeness == "playable",
                "autoplay_ready": timeline_completeness == "playable",
                "minimum_autoplay_frames": 2,
                "state_hash_valid": step_status["state_hash_valid"],
                "state_hash_invalid_reason": step_status["state_hash_invalid_reason"],
                "public_safe": not safety_issues,
                "public_safety_issue_count": len(safety_issues),
                "render_hints_hash": sha256_json(state.render_hints),
            }
        )
    return rows


def renderer_family(render_hints: dict[str, Any]) -> str:
    value = render_hints.get("renderer_family")
    if isinstance(value, str) and value:
        return value
    renderer = render_hints.get("renderer")
    if isinstance(renderer, str) and renderer:
        return renderer
    board_kind = render_hints.get("board_kind")
    if isinstance(board_kind, str) and board_kind:
        return board_kind
    kind = render_hints.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    return "generic"


def renderer_kind(render_hints: dict[str, Any]) -> str:
    return renderer_family(render_hints)


def renderer_vocabulary_hash(*, seed: int = 1) -> str:
    return sha256_json(renderer_vocabulary_rows(seed=seed))


def _step_status(arena: Any, state: Any, legal_actions: list[Any]) -> dict[str, Any]:
    if not legal_actions:
        return {
            "can_step": False,
            "state_hash_valid": None,
            "state_hash_invalid_reason": "no_legal_actions",
        }
    try:
        next_state = arena.apply_action(state, state.active_player, legal_actions[0])
    except Exception as exc:
        return {
            "can_step": False,
            "state_hash_valid": False,
            "state_hash_invalid_reason": f"step_failed:{type(exc).__name__}",
        }
    return {
        "can_step": True,
        "state_hash_valid": bool(next_state.state_hash),
        "state_hash_invalid_reason": None if next_state.state_hash else "missing_state_hash",
    }


def _timeline_completeness(
    *,
    has_public_state: bool,
    can_step: bool,
    terminal: bool,
    safe: bool,
) -> str:
    if not safe:
        return "unavailable"
    if not has_public_state:
        return "metadata_only"
    if can_step:
        return "playable"
    if terminal:
        return "partial"
    return "setup_only"
