"""Version 2 Core step, observation, action, prompt, and timing contracts."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter_ns
from typing import Any, Literal

import eslams.arenas  # noqa: F401
from eslams.action_descriptors import action_descriptors, action_token
from eslams.arena import Arena, registry
from eslams.arena_transport import deserialize_state, serialize_state
from eslams.contracts.versions import (
    CORE_ACTION_SCHEMA_VERSION,
    CORE_CONTRACT_VERSION,
    CORE_PACKAGE_VERSION,
    CORE_PROMPT_VERSION,
    CORE_REPLAY_EVENT_SCHEMA_VERSION,
)
from eslams.hashing import (
    action_hash,
    canonical_json,
    legal_action_hash,
    observation_hash,
    prompt_hash,
)
from eslams.model_actions import (
    InvalidModelAction,
    action_output_schema,
    coerce_action,
)
from eslams.state import ArenaState

IncludeLegalActions = Literal["none", "ids", "compact", "full"]
ObservationView = Literal["public_compact", "public_full", "private_actor", "ui_delta", "debug"]

DEFAULT_RULESET_VERSION = "standard"
DEFAULT_MAX_LEGAL_ACTIONS_SERIALIZED = 200
DEFAULT_PAYLOAD_SIZE_LIMIT_BYTES = 1_000_000
log = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class CoreStepError(RuntimeError):
    def __init__(self, code: str, message: str, *, stage: str, recoverable: bool = True) -> None:
        self.code = code
        self.message = message
        self.stage = stage
        self.recoverable = recoverable
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "recoverable": self.recoverable,
        }


@dataclass
class CoreStepTimer:
    received_at: str = field(default_factory=_utc_now)
    started_ns: int = field(default_factory=perf_counter_ns)
    timings_ms: dict[str, int] = field(default_factory=dict)

    def elapsed_ms(self) -> int:
        return _elapsed_ms(self.started_ns)

    def mark(self, key: str, started_ns: int) -> None:
        self.timings_ms[key] = _elapsed_ms(started_ns)

    def check_deadline(self, deadline_ms: int | None, stage: str) -> None:
        if deadline_ms is None:
            return
        elapsed = self.elapsed_ms()
        if elapsed > deadline_ms:
            raise CoreStepError(
                "core_timeout",
                f"Core deadline exceeded during {stage}",
                stage=stage,
                recoverable=True,
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"receivedAt": self.received_at}
        payload.update(self.timings_ms)
        payload["totalMs"] = self.elapsed_ms()
        return payload


def core_step(request: dict[str, Any]) -> dict[str, Any]:
    """Apply one deterministic Core action and return a v2 step response."""

    timer = CoreStepTimer()
    request_id = _optional_str(request.get("requestId")) or "core-step"
    game_id = _optional_str(request.get("gameId")) or ""
    ruleset_version = _optional_str(request.get("rulesetVersion")) or DEFAULT_RULESET_VERSION
    deadline_ms = _optional_positive_int(request.get("deadlineMs"))
    previous_state_hash: str | None = None
    legal_hash_before: str | None = None
    action_digest = action_hash(request.get("action"))

    try:
        _validate_core_contract_version(request)
        _check_payload_size(request)
        include_observation = bool(request.get("includeObservation", True))
        include_replay_event = bool(request.get("includeReplayEvent", True))
        include_legal_actions = _include_legal_actions(request.get("includeLegalActions"))
        observation_view = _observation_view(request.get("observationView"))

        init_start = perf_counter_ns()
        arena = registry.create(game_id)
        timer.mark("initMs", init_start)
        timer.check_deadline(deadline_ms, "init")

        deserialize_start = perf_counter_ns()
        state_payload = _required_dict(request, "state")
        state = deserialize_state(state_payload, strict_hash=True)
        previous_state_hash = str(state.state_hash)
        timer.mark("deserializeMs", deserialize_start)
        timer.check_deadline(deadline_ms, "deserialize")

        actor_id = _optional_str(request.get("actorId")) or state.active_player
        if state.terminal:
            raise CoreStepError(
                "terminal_state",
                "state is already terminal",
                stage="validate",
                recoverable=False,
            )
        if actor_id != state.active_player:
            raise CoreStepError(
                "action_valid_but_wrong_actor",
                f"{actor_id} is not the active player",
                stage="validate",
                recoverable=True,
            )

        legal_start = perf_counter_ns()
        legal_actions = arena.legal_actions_for(state, actor_id)
        legal_hash_before = legal_action_hash([action_token(action) for action in legal_actions])
        timer.mark("legalActionsMs", legal_start)
        timer.check_deadline(deadline_ms, "legal_actions")

        validate_start = perf_counter_ns()
        raw_action = _resolve_core_action(request.get("action"), legal_actions)
        action_digest = action_hash(_core_action_payload(arena.id, state, raw_action))
        timer.mark("validateMs", validate_start)
        timer.check_deadline(deadline_ms, "validate")

        apply_start = perf_counter_ns()
        next_state = arena.apply_action(state, actor_id, raw_action)
        timer.mark("applyMs", apply_start)
        timer.check_deadline(deadline_ms, "apply")

        scoring_start = perf_counter_ns()
        scores = arena.score(next_state) if next_state.terminal else dict(next_state.scores)
        timer.mark("scoringMs", scoring_start)

        legal_after_start = perf_counter_ns()
        next_legal = (
            []
            if next_state.terminal
            else arena.legal_actions_for(next_state, next_state.active_player)
        )
        legal_hash_after = legal_action_hash([action_token(action) for action in next_legal])
        timer.timings_ms["legalActionsAfterMs"] = _elapsed_ms(legal_after_start)
        timer.check_deadline(deadline_ms, "legal_actions_after")

        observation: dict[str, Any] | None = None
        if include_observation:
            observation_start = perf_counter_ns()
            observation = observation_for_view(
                arena=arena,
                state=next_state,
                actor_id=next_state.active_player,
                view=observation_view,
                legal_actions=next_legal,
            )
            timer.mark("observationMs", observation_start)
            timer.check_deadline(deadline_ms, "observation")

        replay_event: dict[str, Any] | None = None
        if include_replay_event:
            replay_start = perf_counter_ns()
            replay_event = core_replay_event(
                game_id=arena.id,
                turn=state.turn,
                actor_id=actor_id,
                action=raw_action,
                previous_state_hash=previous_state_hash,
                next_state_hash=str(next_state.state_hash),
                timings_ms=timer.to_dict(),
            )
            timer.mark("replayEventMs", replay_start)

        serialize_start = perf_counter_ns()
        state_snapshot = serialize_state(next_state)
        timer.mark("serializeMs", serialize_start)

        response = {
            "coreVersion": CORE_PACKAGE_VERSION,
            "coreContractVersion": CORE_CONTRACT_VERSION,
            "rulesetVersion": ruleset_version,
            "promptVersion": CORE_PROMPT_VERSION,
            "actionSchemaVersion": CORE_ACTION_SCHEMA_VERSION,
            "replaySchemaVersion": CORE_REPLAY_EVENT_SCHEMA_VERSION,
            "ok": True,
            "gameId": arena.id,
            "requestId": request_id,
            "previousStateHash": previous_state_hash,
            "actionHash": action_digest,
            "nextStateHash": next_state.state_hash,
            "legalActionHashBefore": legal_hash_before,
            "legalActionHashAfter": legal_hash_after,
            "state": state_snapshot,
            "observation": observation,
            "legalActions": legal_action_view(
                game_id=arena.id,
                state=next_state,
                actions=next_legal,
                include=include_legal_actions,
            ),
            "replayEvent": replay_event,
            "terminal": {
                "terminal": next_state.terminal,
                "outcome": next_state.outcome,
                "scores": scores,
            },
            "error": None,
            "timingsMs": timer.to_dict(),
        }
        _emit_step_telemetry(response)
        return response
    except InvalidModelAction as exc:
        return _error_response(
            timer=timer,
            game_id=game_id,
            ruleset_version=ruleset_version,
            request_id=request_id,
            previous_state_hash=previous_state_hash,
            action_digest=action_digest,
            legal_hash_before=legal_hash_before,
            error={
                "code": exc.code,
                "message": exc.detail,
                "stage": "validate",
                "recoverable": True,
            },
        )
    except CoreStepError as exc:
        return _error_response(
            timer=timer,
            game_id=game_id,
            ruleset_version=ruleset_version,
            request_id=request_id,
            previous_state_hash=previous_state_hash,
            action_digest=action_digest,
            legal_hash_before=legal_hash_before,
            error=exc.to_dict(),
        )
    except Exception as exc:
        log.warning("core_step failed for %s: %s", game_id, exc, exc_info=True)
        return _error_response(
            timer=timer,
            game_id=game_id,
            ruleset_version=ruleset_version,
            request_id=request_id,
            previous_state_hash=previous_state_hash,
            action_digest=action_digest,
            legal_hash_before=legal_hash_before,
            error={
                "code": "transition_error",
                "message": str(exc),
                "stage": "unknown",
                "recoverable": False,
            },
        )


def observation_for_view(
    *,
    arena: Arena,
    state: ArenaState,
    actor_id: str,
    view: ObservationView = "public_compact",
    legal_actions: list[Any] | None = None,
) -> dict[str, Any]:
    actions = (
        legal_actions
        if legal_actions is not None
        else arena.legal_actions_for(state, actor_id)
    )
    action_ids = [action_token(action) for action in actions]
    if view == "ui_delta":
        return {
            "view": view,
            "stateHash": state.state_hash,
            "turn": state.turn,
            "activePlayer": state.active_player,
            "terminal": state.terminal,
            "outcome": state.outcome,
        }
    if view == "debug":
        return {"view": view, "state": state.to_dict(), "legalActionIds": action_ids}

    public_state = (
        _compact_public_state(state.public_state)
        if view == "public_compact"
        else state.public_state
    )
    payload: dict[str, Any] = {
        "view": view,
        "stateHash": state.state_hash,
        "observationHash": observation_hash(public_state),
        "turn": state.turn,
        "activePlayer": state.active_player,
        "actorId": actor_id,
        "publicState": public_state,
        "scores": state.scores,
        "terminal": state.terminal,
        "outcome": state.outcome,
        "legalActionIds": action_ids,
    }
    if view in {"public_full", "private_actor"}:
        payload["observation"] = arena.observation_for(state, actor_id)
    return payload


def legal_action_view(
    *,
    game_id: str,
    state: ArenaState,
    actions: list[Any],
    include: IncludeLegalActions,
) -> dict[str, Any]:
    action_ids = [action_token(action) for action in actions]
    base: dict[str, Any] = {
        "include": include,
        "count": len(actions),
        "hash": legal_action_hash(action_ids),
    }
    if include == "none":
        return base
    if include == "ids":
        return {**base, "ids": action_ids[:DEFAULT_MAX_LEGAL_ACTIONS_SERIALIZED]}
    descriptors = action_descriptors(game_id=game_id, state=state, actions=actions)
    compact_rows = [
        {
            "actionId": str(row["token"]),
            "label": str(row["label"]),
            "compact": str(row["token"]),
        }
        for row in descriptors[:DEFAULT_MAX_LEGAL_ACTIONS_SERIALIZED]
    ]
    if include == "compact":
        return {**base, "actions": compact_rows}
    full_rows = [
        {
            **compact_rows[index],
            "kind": str(row["category"]),
            "payload": actions[index],
            "descriptor": row,
            "hash": action_hash(_core_action_payload(game_id, state, actions[index])),
        }
        for index, row in enumerate(descriptors[:DEFAULT_MAX_LEGAL_ACTIONS_SERIALIZED])
    ]
    return {**base, "actions": full_rows}


def prompt_package(
    *,
    arena: Arena,
    state: ArenaState,
    actor_id: str,
    history: list[dict[str, Any]] | None = None,
    provider_family: str = "generic",
) -> dict[str, Any]:
    actions = arena.legal_actions_for(state, actor_id)
    observation = observation_for_view(
        arena=arena,
        state=state,
        actor_id=actor_id,
        view="public_compact",
        legal_actions=actions,
    )
    legal_rows = legal_action_view(
        game_id=arena.id,
        state=state,
        actions=actions,
        include="compact",
    )
    package = {
        "gameId": arena.id,
        "rulesetVersion": DEFAULT_RULESET_VERSION,
        "promptVersion": CORE_PROMPT_VERSION,
        "stablePrefix": [
            {
                "role": "developer",
                "content": (
                    "Choose exactly one legal eSlams Core action. Return JSON with "
                    "the action field first and no hidden information."
                ),
                "cacheRecommended": True,
            },
            {
                "role": "developer",
                "content": canonical_json(
                    {
                        "arena": {"id": arena.id, "version": arena.version},
                        "actionSchemaVersion": CORE_ACTION_SCHEMA_VERSION,
                        "outputSchema": action_output_schema(actions),
                    }
                ),
                "cacheRecommended": True,
            },
        ],
        "dynamicTurn": {
            "moveHistory": canonical_json(list(history or [])[-24:]),
            "currentObservation": canonical_json(observation),
            "legalActions": canonical_json(legal_rows),
        },
        "outputSchema": action_output_schema(actions),
        "parserVersion": "eslams.model_actions.v1",
    }
    return {
        **package,
        "promptHash": prompt_hash(package),
        "tokenEstimate": estimate_prompt_tokens(package, provider_family=provider_family),
    }


def estimate_prompt_tokens(prompt: dict[str, Any], *, provider_family: str = "generic") -> int:
    divisor = 4
    if provider_family.lower() in {"anthropic", "claude"}:
        divisor = 3
    return max(1, round(len(canonical_json(prompt)) / divisor))


def action_equivalent(action_a: Any, action_b: Any) -> bool:
    return (
        action_token(action_a) == action_token(action_b)
        or canonical_json(action_a) == canonical_json(action_b)
    )


def core_replay_event(
    *,
    game_id: str,
    turn: int,
    actor_id: str,
    action: Any,
    previous_state_hash: str,
    next_state_hash: str,
    timings_ms: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": CORE_REPLAY_EVENT_SCHEMA_VERSION,
        "seq": turn,
        "turn": turn,
        "type": "action_applied",
        "gameId": game_id,
        "actorId": actor_id,
        "actionHash": action_hash(action),
        "previousStateHash": previous_state_hash,
        "nextStateHash": next_state_hash,
        "timestamp": _utc_now(),
        "timingsMs": timings_ms,
        "payload": {"action": action},
    }


def speculative_precompute_eligibility(game_id: str) -> dict[str, Any]:
    hidden_info = game_id in {
        "poker",
        "leduc-poker",
        "texas-holdem",
        "hanabi",
        "liars-dice",
        "bridge",
        "mahjong",
        "dou-dizhu",
    }
    safe_games = {
        "tic-tac-toe": 9,
        "connect-four": 7,
        "gomoku": 225,
        "othello": 64,
        "checkers": 32,
        "mancala": 6,
    }
    return {
        "safe": game_id in safe_games and not hidden_info,
        "maxBranchingFactorRecommended": safe_games.get(game_id),
        "requiresDeterministicModelSettings": True,
        "hiddenInfo": hidden_info,
    }


def engine_capabilities(game_id: str) -> dict[str, Any]:
    core_lite_games = {"tic-tac-toe", "connect-four"}
    return {
        "gameId": game_id,
        "engines": {
            "python_core": {"official": True, "arenaInteractive": True},
            "core_lite_ts": {
                "official": False,
                "arenaInteractive": game_id in core_lite_games,
                "verifiedAgainst": CORE_PACKAGE_VERSION if game_id in core_lite_games else None,
            },
            "wasm": {"official": False, "arenaInteractive": False},
        },
        "speculativePrecompute": speculative_precompute_eligibility(game_id),
    }


def _resolve_core_action(action: Any, legal_actions: list[Any]) -> Any:
    if isinstance(action, dict):
        action_id = action.get("actionId") or action.get("action_id") or action.get("token")
        if isinstance(action_id, str):
            return coerce_action(action_id, legal_actions)
        if "payload" in action:
            return coerce_action(action["payload"], legal_actions)
        if "compact" in action:
            return coerce_action(action["compact"], legal_actions)
    return coerce_action(action, legal_actions)


def _core_action_payload(game_id: str, state: ArenaState, action: Any) -> dict[str, Any]:
    descriptor = action_descriptors(game_id=game_id, state=state, actions=[action])[0]
    return {
        "actionId": descriptor["token"],
        "kind": descriptor["category"],
        "compact": descriptor["token"],
        "payload": action,
        "label": descriptor["label"],
    }


def _error_response(
    *,
    timer: CoreStepTimer,
    game_id: str,
    ruleset_version: str,
    request_id: str,
    previous_state_hash: str | None,
    action_digest: str,
    legal_hash_before: str | None,
    error: dict[str, Any],
) -> dict[str, Any]:
    response = {
        "coreVersion": CORE_PACKAGE_VERSION,
        "coreContractVersion": CORE_CONTRACT_VERSION,
        "rulesetVersion": ruleset_version,
        "promptVersion": CORE_PROMPT_VERSION,
        "actionSchemaVersion": CORE_ACTION_SCHEMA_VERSION,
        "replaySchemaVersion": CORE_REPLAY_EVENT_SCHEMA_VERSION,
        "ok": False,
        "gameId": game_id,
        "requestId": request_id,
        "previousStateHash": previous_state_hash,
        "actionHash": action_digest,
        "nextStateHash": None,
        "legalActionHashBefore": legal_hash_before,
        "legalActionHashAfter": None,
        "state": None,
        "observation": None,
        "legalActions": None,
        "replayEvent": None,
        "terminal": None,
        "error": error,
        "timingsMs": timer.to_dict(),
    }
    _emit_step_telemetry(response)
    return response


def _emit_step_telemetry(response: dict[str, Any]) -> None:
    observation = response.get("observation")
    legal_actions = response.get("legalActions")
    event = {
        "event": "core.step.completed" if response.get("ok") else "core.step.failed",
        "requestId": response.get("requestId"),
        "gameId": response.get("gameId"),
        "coreVersion": CORE_PACKAGE_VERSION,
        "engineImpl": "python_core",
        "stateBytes": len(canonical_json(response.get("state"))) if response.get("state") else 0,
        "observationBytes": len(canonical_json(observation)) if observation else 0,
        "legalActionCount": legal_actions.get("count") if isinstance(legal_actions, dict) else None,
        "timingsMs": response.get("timingsMs"),
    }
    log.info("core telemetry %s", canonical_json(event))


def _compact_public_state(public_state: dict[str, Any]) -> dict[str, Any]:
    compact = dict(public_state)
    legal_moves = compact.get("legal_moves")
    if isinstance(legal_moves, list) and len(canonical_json(legal_moves)) > 1000:
        compact["legal_moves_count"] = len(legal_moves)
        compact.pop("legal_moves", None)
    return compact


def _validate_core_contract_version(request: dict[str, Any]) -> None:
    version = request.get("coreContractVersion")
    if version != CORE_CONTRACT_VERSION:
        raise CoreStepError(
            "schema_mismatch",
            f"coreContractVersion must be {CORE_CONTRACT_VERSION!r}",
            stage="validate_request",
            recoverable=False,
        )


def _check_payload_size(request: dict[str, Any]) -> None:
    payload_size = len(canonical_json(request))
    if payload_size > DEFAULT_PAYLOAD_SIZE_LIMIT_BYTES:
        raise CoreStepError(
            "payload_too_large",
            "Core step request exceeds payload size limit",
            stage="validate_request",
            recoverable=False,
        )


def _include_legal_actions(value: Any) -> IncludeLegalActions:
    if value == "none":
        return "none"
    if value == "ids":
        return "ids"
    if value == "full":
        return "full"
    return "compact"


def _observation_view(value: Any) -> ObservationView:
    if value == "public_full":
        return "public_full"
    if value == "private_actor":
        return "private_actor"
    if value == "ui_delta":
        return "ui_delta"
    if value == "debug" and os.getenv("ESLAMS_ENABLE_DEBUG_OBSERVATION") == "1":
        return "debug"
    return "public_compact"


def _required_dict(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise CoreStepError(
            "schema_mismatch",
            f"{key} must be an object",
            stage="validate_request",
            recoverable=False,
        )
    return item


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _elapsed_ms(start_ns: int) -> int:
    return max(0, round((perf_counter_ns() - start_ns) / 1_000_000))
