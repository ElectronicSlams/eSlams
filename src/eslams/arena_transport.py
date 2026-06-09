"""Stateless arena transport helpers for runner/container integrations."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter_ns
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.action_descriptors import action_descriptors, action_token
from eslams.arena import registry
from eslams.contracts.safety import assert_public_payload_safe
from eslams.contracts.versions import (
    ARENA_EVENT_SCHEMA_VERSION,
    ARENA_LEGAL_ACTIONS_PAGE_SCHEMA_VERSION,
    ARENA_START_RESULT_SCHEMA_VERSION,
    ARENA_STEP_RESULT_SCHEMA_VERSION,
)
from eslams.public_catalogue import PUBLIC_GAME_CATALOGUE_BY_ID
from eslams.replay_projection import display_frame_for_state
from eslams.state import ArenaState

SESSION_METADATA_KEY = "arena_session"
DEFAULT_SESSION_ACTION_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50
MAX_ACTION_LIMIT = 200


class StateHashMismatch(ValueError):
    """Raised when serialized state carries a stale canonical hash."""

    def __init__(self, *, provided: str, canonical: str) -> None:
        self.provided = provided
        self.canonical = canonical
        super().__init__("state_hash does not match canonical state")

    def to_dict(self) -> dict[str, str]:
        return {
            "status": "state_hash_mismatch",
            "provided_state_hash": self.provided,
            "canonical_state_hash": self.canonical,
        }


def serialize_state(state: ArenaState) -> dict[str, Any]:
    return state.to_dict()


def deserialize_state(payload: dict[str, Any], strict_hash: bool = True) -> ArenaState:
    provided_hash = str(payload["state_hash"]) if payload.get("state_hash") else None
    state = ArenaState(
        state_id=str(payload["state_id"]),
        turn=int(payload["turn"]),
        active_player=str(payload["active_player"]),
        public_state=_dict(payload["public_state"]),
        private_state_by_player={
            str(key): _dict(value)
            for key, value in _dict(payload["private_state_by_player"]).items()
        },
        legal_actions_by_player={
            str(key): _list(value)
            for key, value in _dict(payload["legal_actions_by_player"]).items()
        },
        scores={str(key): float(value) for key, value in _dict(payload["scores"]).items()},
        terminal=bool(payload["terminal"]),
        outcome=_optional_dict(payload.get("outcome")),
        rng_commitment=str(payload["rng_commitment"]),
        render_hints=_dict(payload["render_hints"]),
        metadata=_dict(payload.get("metadata", {})),
        state_hash=None,
    )
    canonical_hash = str(state.state_hash)
    if provided_hash is None or provided_hash == canonical_hash:
        return state
    diagnostics = {
        "status": "state_hash_repaired",
        "provided_state_hash": provided_hash,
        "canonical_state_hash": canonical_hash,
    }
    if strict_hash:
        raise StateHashMismatch(provided=provided_hash, canonical=canonical_hash)
    object.__setattr__(state, "rehydration_diagnostics", diagnostics)
    return state


def start_session(
    game_slug: str,
    variant: str | None,
    seed: int,
    players: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a lightweight trusted Arena session for Platform orchestration."""

    total_start = perf_counter_ns()
    arena = registry.create(game_slug)
    normalized_variant = _normalize_variant(game_slug, variant)
    player_map = _normalize_players(arena.players, players)
    options_map = _normalize_options(options)

    create_start = perf_counter_ns()
    state = arena.initial_state(seed)
    state = _attach_session_metadata(
        state,
        game_slug=game_slug,
        variant=normalized_variant,
        players=player_map,
        options=options_map,
    )
    create_ms = _elapsed_ms(create_start)

    display_start = perf_counter_ns()
    frame = _display_frame(
        state,
        event_id=_event_id(state, "session.started", 0),
        actor_player=None,
        action=None,
        action_label=None,
    )
    display_ms = _elapsed_ms(display_start)

    legal_start = perf_counter_ns()
    page = _legal_action_page(
        game_slug=game_slug,
        state=state,
        player_id=state.active_player,
        query=None,
        limit=_response_action_limit(options_map),
        cursor=None,
    )
    legal_actions_ms = _elapsed_ms(legal_start)

    events = _start_events(state, players=player_map, display_frame=frame)
    timing = {
        "create_ms": create_ms,
        "display_ms": display_ms,
        "legal_actions_ms": legal_actions_ms,
        "total_core_ms": _elapsed_ms(total_start),
    }
    return _result_payload(
        schema_version=ARENA_START_RESULT_SCHEMA_VERSION,
        state=state,
        state_hash_status="verified",
        display_frame=frame,
        page=page,
        events=events,
        timing=timing,
    )


def step_session(
    session_state: dict[str, Any],
    player_id: str,
    action_token: str,
) -> dict[str, Any]:
    """Apply one trusted Arena action token and return the full UI payload."""

    total_start = perf_counter_ns()
    timing: dict[str, int] = {}

    deserialize_start = perf_counter_ns()
    try:
        state = deserialize_state(session_state, strict_hash=True)
    except StateHashMismatch as exc:
        timing["deserialize_ms"] = _elapsed_ms(deserialize_start)
        timing.update(
            {
                "legality_ms": 0,
                "apply_ms": 0,
                "display_ms": 0,
                "legal_actions_ms": 0,
                "total_core_ms": _elapsed_ms(total_start),
            }
        )
        return _mismatch_payload(session_state, exc, timing)
    timing["deserialize_ms"] = _elapsed_ms(deserialize_start)

    session = _session_metadata(state)
    game_slug = str(session["game_slug"])
    players = _dict(session["players"])
    options = _dict(session.get("options", {}))
    arena = registry.create(game_slug)

    display_start = perf_counter_ns()
    current_frame = _display_frame(
        state,
        event_id=_event_id(state, "turn.failed", 0),
        actor_player=player_id,
        action=action_token,
        action_label=None,
    )
    timing["display_ms"] = _elapsed_ms(display_start)

    if state.terminal:
        timing.update({"legality_ms": 0, "apply_ms": 0})
        return _failure_result(
            state=state,
            players=players,
            options=options,
            display_frame=current_frame,
            reason="terminal_state",
            message="session is already terminal",
            timing=timing,
            total_start=total_start,
        )
    if player_id != state.active_player:
        timing.update({"legality_ms": 0, "apply_ms": 0})
        return _failure_result(
            state=state,
            players=players,
            options=options,
            display_frame=current_frame,
            reason="wrong_actor",
            message=f"{player_id} is not the active player",
            timing=timing,
            total_start=total_start,
        )

    legality_start = perf_counter_ns()
    legal = arena.legal_actions_for(state, player_id)
    token_to_action = dict(_token_pairs(legal))
    raw_action = token_to_action.get(action_token)
    if raw_action is None:
        timing["legality_ms"] = _elapsed_ms(legality_start)
        timing["apply_ms"] = 0
        return _failure_result(
            state=state,
            players=players,
            options=options,
            display_frame=current_frame,
            reason="illegal_action",
            message="action token is not legal for the active player",
            timing=timing,
            total_start=total_start,
        )
    accepted_descriptor = action_descriptors(
        game_id=game_slug,
        state=state,
        actions=[raw_action],
    )[0]
    timing["legality_ms"] = _elapsed_ms(legality_start)

    apply_start = perf_counter_ns()
    try:
        next_state = arena.apply_action(state, player_id, raw_action)
    except Exception:
        timing["apply_ms"] = _elapsed_ms(apply_start)
        return _failure_result(
            state=state,
            players=players,
            options=options,
            display_frame=current_frame,
            reason="transition_error",
            message="arena rejected the action",
            timing=timing,
            total_start=total_start,
        )
    next_state = _reattach_session_metadata(next_state, session)
    timing["apply_ms"] = _elapsed_ms(apply_start)

    display_start = perf_counter_ns()
    frame = _display_frame(
        next_state,
        event_id=_event_id(next_state, "state.applied", 1),
        actor_player=player_id,
        action=action_token,
        action_label=str(accepted_descriptor["label"]),
    )
    timing["display_ms"] = _elapsed_ms(display_start)

    legal_start = perf_counter_ns()
    page = _legal_action_page(
        game_slug=game_slug,
        state=next_state,
        player_id=next_state.active_player,
        query=None,
        limit=_response_action_limit(options),
        cursor=None,
    )
    timing["legal_actions_ms"] = _elapsed_ms(legal_start)
    events = _step_events(
        previous_state=state,
        state=next_state,
        players=players,
        actor=player_id,
        action=action_token,
        action_label=str(accepted_descriptor["label"]),
        display_frame=frame,
    )
    timing["total_core_ms"] = _elapsed_ms(total_start)
    return _result_payload(
        schema_version=ARENA_STEP_RESULT_SCHEMA_VERSION,
        state=next_state,
        state_hash_status="verified",
        display_frame=frame,
        page=page,
        events=events,
        timing=timing,
        accepted=True,
    )


def legal_actions_page(
    session_state: dict[str, Any],
    player_id: str,
    query: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    state = deserialize_state(session_state, strict_hash=True)
    session = _session_metadata(state)
    game_slug = str(session["game_slug"])
    return _legal_action_page(
        game_slug=game_slug,
        state=state,
        player_id=player_id,
        query=query,
        limit=limit,
        cursor=cursor,
    )


def initial_state(arena_id: str, *, seed: int = 1) -> dict[str, Any]:
    arena = registry.create(arena_id)
    return serialize_state(arena.initial_state(seed))


def legal_actions(arena_id: str, state_payload: dict[str, Any], player_id: str) -> list[Any]:
    arena = registry.create(arena_id)
    state = deserialize_state(state_payload)
    return arena.legal_actions_for(state, player_id)


def public_state(state_payload: dict[str, Any]) -> dict[str, Any]:
    return deserialize_state(state_payload).public_view()


def state_hash(state_payload: dict[str, Any]) -> str:
    return str(deserialize_state(state_payload).state_hash)


def step(
    arena_id: str,
    state_payload: dict[str, Any],
    player_id: str,
    action: Any,
) -> dict[str, Any]:
    arena = registry.create(arena_id)
    state = deserialize_state(state_payload)
    next_state = arena.apply_action(state, player_id, action)
    return serialize_state(next_state)


def smoke_all_arenas(*, seed: int = 1) -> dict[str, Any]:
    rows = []
    for arena_id in registry.list():
        arena = registry.create(arena_id)
        state = arena.initial_state(seed)
        serialized = serialize_state(state)
        restored = deserialize_state(serialized)
        actions = arena.legal_actions_for(restored, restored.active_player)
        stepped = None
        if actions:
            stepped = arena.apply_action(restored, restored.active_player, actions[0])
        rows.append(
            {
                "arena_id": arena_id,
                "ok": restored.state_hash == state.state_hash,
                "state_hash": restored.state_hash,
                "legal_action_count": len(actions),
                "can_step": stepped is not None,
                "replay_readiness": "playable" if state.public_state else "setup_only",
            }
        )
    return {
        "ok": all(row["ok"] for row in rows),
        "game_count": len(rows),
        "rows": rows,
    }


def _normalize_variant(game_slug: str, variant: str | None) -> str:
    public = PUBLIC_GAME_CATALOGUE_BY_ID.get(game_slug)
    if public is None:
        raise KeyError(f"unknown public game {game_slug!r}")
    if variant is not None and variant not in {"", public.variant}:
        raise ValueError(
            f"unsupported variant {variant!r} for {game_slug!r}; expected {public.variant!r}"
        )
    return public.variant


def _normalize_players(arena_players: tuple[str, ...], players: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(players, dict):
        raise ValueError("players must be a map keyed by arena player id")
    normalized: dict[str, Any] = {}
    for player_id in arena_players:
        if player_id not in players:
            raise ValueError(f"missing player entry for {player_id}")
        value = _dict(players[player_id])
        kind = str(value.get("kind", "")).lower()
        if kind not in {"human", "model"}:
            raise ValueError(f"{player_id}.kind must be 'human' or 'model'")
        normalized[player_id] = {
            "kind": kind,
            "label": str(value.get("label") or player_id),
        }
    extra = sorted(set(players) - set(arena_players))
    if extra:
        raise ValueError(f"unknown player ids: {', '.join(extra)}")
    return normalized


def _normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    value = {} if options is None else _dict(options)
    if options is not None and not isinstance(options, dict):
        raise ValueError("options must be a JSON object")
    assert_public_payload_safe(value, root="arena.options")
    return value


def _attach_session_metadata(
    state: ArenaState,
    *,
    game_slug: str,
    variant: str,
    players: dict[str, Any],
    options: dict[str, Any],
) -> ArenaState:
    metadata = {
        **state.metadata,
        SESSION_METADATA_KEY: {
            "game_slug": game_slug,
            "variant": variant,
            "players": players,
            "options": options,
        },
    }
    return replace(state, metadata=metadata, state_hash=None)


def _reattach_session_metadata(state: ArenaState, session: dict[str, Any]) -> ArenaState:
    metadata = {**state.metadata, SESSION_METADATA_KEY: session}
    return replace(state, metadata=metadata, state_hash=None)


def _session_metadata(state: ArenaState) -> dict[str, Any]:
    session = _dict(state.metadata.get(SESSION_METADATA_KEY))
    if not session:
        raise ValueError("session_state is missing Arena session metadata")
    return session


def _response_action_limit(options: dict[str, Any]) -> int:
    limit = options.get("legal_actions_limit", DEFAULT_SESSION_ACTION_LIMIT)
    return _bounded_limit(limit, default=DEFAULT_SESSION_ACTION_LIMIT)


def _bounded_limit(value: Any, *, default: int = DEFAULT_PAGE_LIMIT) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, MAX_ACTION_LIMIT))


def _legal_action_page(
    *,
    game_slug: str,
    state: ArenaState,
    player_id: str,
    query: str | None,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    bounded_limit = _bounded_limit(limit)
    offset = _cursor_offset(cursor)
    legal = registry.create(game_slug).legal_actions_for(state, player_id)
    descriptors = action_descriptors(game_id=game_slug, state=state, actions=legal)
    matching = _filter_descriptors(descriptors, query)
    page_rows = matching[offset : offset + bounded_limit]
    next_offset = offset + len(page_rows)
    has_more = next_offset < len(matching)
    return {
        "schema_version": ARENA_LEGAL_ACTIONS_PAGE_SCHEMA_VERSION,
        "player_id": player_id,
        "query": query,
        "limit": bounded_limit,
        "cursor": cursor,
        "next_cursor": str(next_offset) if has_more else None,
        "total_legal_actions": len(descriptors),
        "total_matching_actions": len(matching),
        "has_more": has_more,
        "rows": page_rows,
    }


def _filter_descriptors(rows: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    if not query:
        return rows
    needle = query.casefold()
    fields = ("token", "label", "short_label", "prompt_label", "group", "category")
    return [
        row
        for row in rows
        if any(needle in str(row.get(field, "")).casefold() for field in fields)
    ]


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        return max(0, int(cursor))
    except ValueError:
        return 0


def _token_pairs(actions: list[Any]) -> list[tuple[str, Any]]:
    return [(action_token(action), action) for action in actions]


def _display_frame(
    state: ArenaState,
    *,
    event_id: str,
    actor_player: str | None,
    action: Any | None,
    action_label: str | None,
) -> dict[str, Any]:
    return display_frame_for_state(
        state,
        run_id=_session_run_id(state),
        event_id=event_id,
        actor_player=actor_player,
        action=action,
        action_label=action_label,
    )


def _session_run_id(state: ArenaState) -> str:
    game_slug = _dict(state.metadata.get(SESSION_METADATA_KEY)).get("game_slug", "arena")
    digest = str(state.state_hash).removeprefix("sha256:")[:12]
    return f"{game_slug}:arena:{digest}"


def _result_payload(
    *,
    schema_version: str,
    state: ArenaState,
    state_hash_status: str,
    display_frame: dict[str, Any],
    page: dict[str, Any],
    events: list[dict[str, Any]],
    timing: dict[str, int],
    accepted: bool | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "session_state": serialize_state(state),
        "state_hash": state.state_hash,
        "state_hash_status": state_hash_status,
        "public_state": state.public_state,
        "display_frame": display_frame,
        "active_player": state.active_player,
        "next_actor_kind": _next_actor_kind(state, _dict(_session_metadata(state).get("players"))),
        "terminal": state.terminal,
        "outcome": state.outcome,
        "scores": state.scores if state.terminal else None,
        "legal_actions": [str(row["token"]) for row in page["rows"]],
        "legal_action_descriptors": page["rows"],
        "total_legal_actions": page["total_legal_actions"],
        "total_matching_legal_actions": page["total_matching_actions"],
        "has_more_legal_actions": page["has_more"],
        "legal_actions_cursor": page["next_cursor"],
        "events": events,
        "timing": timing,
    }
    if accepted is not None:
        payload["accepted"] = accepted
        payload["turn_id"] = state.turn
        payload["error"] = error
    return payload


def _mismatch_payload(
    session_state: dict[str, Any],
    exc: StateHashMismatch,
    timing: dict[str, int],
) -> dict[str, Any]:
    turn_id = _safe_int(session_state.get("turn"), 0)
    provided = session_state.get("state_hash")
    event = _arena_event(
        event_type="turn.failed",
        event_id=f"arena:mismatch:{turn_id}:000",
        turn_id=turn_id,
        actor=_optional_str(session_state.get("active_player")),
        action=None,
        action_label=None,
        display_frame={},
        state_hash=str(provided) if provided is not None else None,
    )
    return {
        "schema_version": ARENA_STEP_RESULT_SCHEMA_VERSION,
        "accepted": False,
        "turn_id": turn_id,
        "session_state": session_state,
        "state_hash": str(provided) if provided is not None else None,
        "state_hash_status": "mismatch",
        "public_state": {},
        "display_frame": {},
        "active_player": _optional_str(session_state.get("active_player")),
        "next_actor_kind": None,
        "terminal": False,
        "outcome": None,
        "scores": None,
        "legal_actions": [],
        "legal_action_descriptors": [],
        "total_legal_actions": 0,
        "total_matching_legal_actions": 0,
        "has_more_legal_actions": False,
        "legal_actions_cursor": None,
        "events": [event],
        "timing": timing,
        "error": {"reason": "state_hash_mismatch", "diagnostics": exc.to_dict()},
    }


def _failure_result(
    *,
    state: ArenaState,
    players: dict[str, Any],
    options: dict[str, Any],
    display_frame: dict[str, Any],
    reason: str,
    message: str,
    timing: dict[str, int],
    total_start: int,
) -> dict[str, Any]:
    legal_start = perf_counter_ns()
    page = _legal_action_page(
        game_slug=str(_session_metadata(state)["game_slug"]),
        state=state,
        player_id=state.active_player,
        query=None,
        limit=_response_action_limit(options),
        cursor=None,
    )
    timing["legal_actions_ms"] = _elapsed_ms(legal_start)
    timing["total_core_ms"] = _elapsed_ms(total_start)
    event = _arena_event(
        event_type="turn.failed",
        event_id=_event_id(state, "turn.failed", 0),
        turn_id=state.turn,
        actor=state.active_player,
        action=None,
        action_label=message,
        display_frame=display_frame,
        state_hash=str(state.state_hash),
    )
    payload = _result_payload(
        schema_version=ARENA_STEP_RESULT_SCHEMA_VERSION,
        state=state,
        state_hash_status="verified",
        display_frame=display_frame,
        page=page,
        events=[event],
        timing=timing,
        accepted=False,
        error={"reason": reason, "message": message},
    )
    payload["next_actor_kind"] = _next_actor_kind(state, players)
    return payload


def _start_events(
    state: ArenaState,
    *,
    players: dict[str, Any],
    display_frame: dict[str, Any],
) -> list[dict[str, Any]]:
    events = [
        _arena_event(
            event_type="session.started",
            event_id=_event_id(state, "session.started", 0),
            turn_id=state.turn,
            actor=None,
            action=None,
            action_label=None,
            display_frame=display_frame,
            state_hash=str(state.state_hash),
        )
    ]
    events.append(_readiness_event(state, players=players, index=1, display_frame=display_frame))
    return events


def _step_events(
    *,
    previous_state: ArenaState,
    state: ArenaState,
    players: dict[str, Any],
    actor: str,
    action: str,
    action_label: str,
    display_frame: dict[str, Any],
) -> list[dict[str, Any]]:
    actor_kind = _player_kind(actor, players)
    accepted_type = "model.action.accepted" if actor_kind == "model" else "human.action.accepted"
    return [
        _arena_event(
            event_type=accepted_type,
            event_id=_event_id(previous_state, accepted_type, 0),
            turn_id=previous_state.turn,
            actor=actor,
            action=action,
            action_label=action_label,
            display_frame=display_frame,
            state_hash=str(state.state_hash),
        ),
        _arena_event(
            event_type="state.applied",
            event_id=_event_id(state, "state.applied", 1),
            turn_id=state.turn,
            actor=actor,
            action=action,
            action_label=action_label,
            display_frame=display_frame,
            state_hash=str(state.state_hash),
        ),
        _readiness_event(state, players=players, index=2, display_frame=display_frame),
    ]


def _readiness_event(
    state: ArenaState,
    *,
    players: dict[str, Any],
    index: int,
    display_frame: dict[str, Any],
) -> dict[str, Any]:
    if state.terminal:
        event_type = "match.completed"
    else:
        event_type = (
            "model.action.requested"
            if _next_actor_kind(state, players) == "model"
            else "turn.ready_for_human"
        )
    return _arena_event(
        event_type=event_type,
        event_id=_event_id(state, event_type, index),
        turn_id=state.turn,
        actor=state.active_player if not state.terminal else None,
        action=None,
        action_label=None,
        display_frame=display_frame,
        state_hash=str(state.state_hash),
    )


def _arena_event(
    *,
    event_type: str,
    event_id: str,
    turn_id: int,
    actor: str | None,
    action: str | None,
    action_label: str | None,
    display_frame: dict[str, Any],
    state_hash: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": ARENA_EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "type": event_type,
        "turn_id": turn_id,
        "actor": actor,
        "action": action,
        "action_label": action_label,
        "display_frame": display_frame,
        "state_hash": state_hash,
        "created_at": _utc_now(),
    }


def _event_id(state: ArenaState, event_type: str, index: int) -> str:
    digest = str(state.state_hash).removeprefix("sha256:")[:12]
    normalized_type = event_type.replace(".", "_")
    return f"arena:{digest}:turn:{state.turn:06d}:{index:03d}:{normalized_type}"


def _next_actor_kind(state: ArenaState, players: dict[str, Any]) -> str | None:
    if state.terminal:
        return None
    return _player_kind(state.active_player, players)


def _player_kind(player_id: str, players: dict[str, Any]) -> str:
    value = _dict(players.get(player_id))
    kind = str(value.get("kind", "human")).lower()
    return kind if kind in {"human", "model"} else "human"


def _elapsed_ms(start_ns: int) -> int:
    return max(0, round((perf_counter_ns() - start_ns) / 1_000_000))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
