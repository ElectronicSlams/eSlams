"""Deterministic local runner."""

from __future__ import annotations

import re
import signal
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from eslams.agents import ProviderCallError, create_builtin_agent
from eslams.arena import Arena
from eslams.arenas import registry
from eslams.artifacts import ArtifactBuildInput, expanded_artifact_path, write_artifact
from eslams.contracts.integrity import ActionProvenance, FailureClass
from eslams.contracts.provider import (
    provider_attempt_event_id,
    provider_receipt_validation_errors,
)
from eslams.contracts.usage import aggregate_provider_receipts
from eslams.contracts.versions import RUNNER_VERSION
from eslams.events import ReplayEvent, ScoreSummary, TraceEvent
from eslams.hashing import sha256_json
from eslams.protocol import ActRequest, ActResponse, ProtocolError, make_act_request
from eslams.state import ArenaState

FAILURE_POLICIES = {"invalid-match", "forfeit", "fallback"}
EXECUTION_PROFILES = {"interactive", "smoke", "official_eval"}
PORTABLE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*$")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class RunConfig:
    arena_id: str
    agent_1: Any = "random"
    agent_2: Any = "first-legal"
    agents: dict[str, Any] | None = None
    verification_level: str = "Local Artifact"
    wrapper_version: str = "legal_action_v1:1.0.0"
    eval_suite_version: str = "public-smoke:1.0.0"
    scoring_policy_version: str | None = None
    runner_version: str = RUNNER_VERSION
    suite_id: str | None = None
    case_id: str | None = None
    case_attempt_index: int = 1
    suite_fingerprint: str | None = None
    plan_hash: str | None = None
    shard_index: int | None = None
    shard_count: int | None = None
    model_id_by_player: dict[str, str] | None = None
    seed: int = 1
    max_turns: int | None = None
    time_budget_ms: int = 30_000
    run_id: str | None = None
    official_run_id: str | None = None
    model_lane_id: str | None = None
    run_job_id: str | None = None
    environment: str = "local"
    output_dir: Path = Path("runs")
    archive: bool = False
    on_agent_error: str = "invalid-match"
    on_illegal_action: str = "invalid-match"
    execution_profile: Literal["interactive", "smoke", "official_eval"] = "interactive"
    overwrite: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.case_attempt_index, bool) or self.case_attempt_index < 1:
            raise ValueError("case_attempt_index must be a positive integer")
        if self.run_id is not None:
            _validate_run_id(self.run_id)
        for name, value in (
            ("official_run_id", self.official_run_id),
            ("model_lane_id", self.model_lane_id),
            ("run_job_id", self.run_job_id),
        ):
            if value is not None and not value:
                raise ValueError(f"{name} cannot be empty")
        if not self.environment:
            raise ValueError("environment cannot be empty")
        _validate_failure_policy("on_agent_error", self.on_agent_error)
        _validate_failure_policy("on_illegal_action", self.on_illegal_action)
        if self.execution_profile not in EXECUTION_PROFILES:
            options = ", ".join(sorted(EXECUTION_PROFILES))
            raise ValueError(f"execution_profile must be one of: {options}")
        if self.execution_profile == "official_eval" and (
            self.on_agent_error == "fallback" or self.on_illegal_action == "fallback"
        ):
            raise ValueError("official_eval rejects fallback failure policies")
        if self.execution_profile == "official_eval":
            _reject_official_inline_retries(
                [self.agent_1, self.agent_2, *(self.agents or {}).values()]
            )


@dataclass(frozen=True)
class RunResult:
    run_id: str
    artifact_path: Path
    expanded_path: Path
    score: ScoreSummary
    replay_events: list[ReplayEvent]
    trace_events: list[TraceEvent]


class Runner:
    def __init__(self, *, memory_policy: str = "current_observation_plus_public_history") -> None:
        self.memory_policy = memory_policy

    def run(self, config: RunConfig) -> RunResult:
        _validate_failure_policy("on_agent_error", config.on_agent_error)
        _validate_failure_policy("on_illegal_action", config.on_illegal_action)
        arena = registry.create(config.arena_id)
        agents = _agents_for_arena(arena, config)
        if config.execution_profile == "official_eval":
            _reject_official_inline_retries(list(agents.values()))
        max_turns = config.max_turns if config.max_turns is not None else arena.max_turns
        effective_time_budget_ms = max(1, config.time_budget_ms)
        suite_context = _suite_context(config)
        match_fingerprint = _match_fingerprint(arena, config, agents, max_turns)
        run_id = config.run_id or _default_run_id(arena)
        artifact_path = _artifact_output_path(
            output_dir=config.output_dir,
            run_id=run_id,
            archive=config.archive,
        )
        _refuse_existing_artifact(artifact_path, archive=config.archive, overwrite=config.overwrite)
        episode_id = "episode_001"
        state = arena.initial_state(config.seed)
        trace_events: list[TraceEvent] = []
        replay_events: list[ReplayEvent] = [
            _replay_event(
                run_id,
                episode_id,
                state,
                None,
                [],
                actor_player=None,
                state_hash_before=None,
            )
        ]
        agent_io: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        provider_receipts: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        agent_error_count = dict.fromkeys(arena.players, 0)
        illegal_action_count = dict.fromkeys(arena.players, 0)
        fallback_action_count = dict.fromkeys(arena.players, 0)
        provider_action_count = dict.fromkeys(arena.players, 0)
        logical_action_count = dict.fromkeys(arena.players, 0)
        provider_status = {
            player: (
                "provider_receipt_missing"
                if _is_provider_backed_agent(agents[player])
                else "local_agent"
            )
            for player in arena.players
        }
        match_valid_for_scoring = True
        invalid_reason: str | None = None
        invalid_reason_codes: list[str] = []
        receipt_event_ids: set[str] = set()
        start = time.perf_counter()

        while not state.terminal and state.turn < max_turns:
            player_id = state.active_player
            logical_action_id = f"{run_id}:{episode_id}:{player_id}:{state.turn:06d}"
            logical_action_count[player_id] += 1
            agent = agents[player_id]
            request = _request(
                arena=arena,
                state=state,
                run_id=run_id,
                episode_id=episode_id,
                agent=agent,
                player_id=player_id,
                time_budget_ms=effective_time_budget_ms,
                history=history,
                memory_policy=self.memory_policy,
                case_id=config.case_id,
                case_attempt_index=config.case_attempt_index,
                shard_index=config.shard_index,
                logical_action_id=logical_action_id,
            )
            response, markers, latency_ms = _call_agent(
                agent,
                request,
                time_budget_ms=effective_time_budget_ms,
            )
            receipt = _last_provider_receipt(agent)
            attempt_receipts = _provider_attempt_receipts(agent, fallback=receipt)
            if attempt_receipts:
                provider_status[player_id] = _provider_receipt_status(attempt_receipts[-1])
                enriched_receipts = _enrich_attempt_receipts(
                    attempt_receipts,
                    run_id=run_id,
                    official_run_id=config.official_run_id or run_id,
                    model_lane_id=config.model_lane_id,
                    run_job_id=config.run_job_id or run_id,
                    environment=config.environment,
                    agent_id=str(getattr(agent, "id", "agent")),
                    agent_version=str(getattr(agent, "version", "1")),
                    episode_id=episode_id,
                    case_id=config.case_id,
                    case_attempt_index=config.case_attempt_index,
                    shard_index=config.shard_index,
                    turn_id=state.turn,
                    player_id=player_id,
                    logical_action_id=logical_action_id,
                    latency_ms=latency_ms,
                    existing_event_ids=receipt_event_ids,
                )
                provider_receipts.extend(enriched_receipts)
                if response is not None:
                    response.metadata["provider_receipt"] = enriched_receipts[-1]
                    response.metadata["attempt_receipts"] = [
                        dict(item) for item in enriched_receipts
                    ]
            elif _is_provider_backed_agent(agent):
                provider_status[player_id] = "provider_receipt_missing"
            if _has_agent_error(markers):
                agent_error_count[player_id] += 1
                failure_class = _failure_class_from_response(response, markers)
                if "agent_error" not in invalid_reason_codes:
                    invalid_reason_codes.append("agent_error")
                if failure_class not in invalid_reason_codes:
                    invalid_reason_codes.append(failure_class)
                provider_status[player_id] = _provider_status(agent, response, markers)
                if config.on_agent_error != "fallback":
                    invalid_reason = _invalid_reason(player_id, failure_class, markers)
                    match_valid_for_scoring = False
                    errors.append(
                        _error_row(
                            turn_id=state.turn,
                            player_id=player_id,
                            reason=invalid_reason,
                            response=response,
                            policy=config.on_agent_error,
                        )
                    )
                    if config.on_agent_error == "forfeit":
                        next_state = _forfeit_state(
                            state,
                            forfeited_player=player_id,
                            reason=invalid_reason,
                        )
                        trace_events.append(
                            _trace_event(
                                run_id=run_id,
                                episode_id=episode_id,
                                state=state,
                                next_state=next_state,
                                request=request,
                                response=response,
                                action=response.action if response else None,
                                latency_ms=latency_ms,
                                markers=markers,
                                requested_time_budget_ms=config.time_budget_ms,
                                effective_time_budget_ms=effective_time_budget_ms,
                                suite_context=suite_context,
                                event_type="forfeit",
                            )
                        )
                        replay_events.append(
                            _replay_event(
                                run_id,
                                episode_id,
                                next_state,
                                response.action if response else None,
                                markers,
                                actor_player=player_id,
                                state_hash_before=state.state_hash,
                            )
                        )
                        state = next_state
                    break
            action = response.action if response else None
            action_provenance = (
                ActionProvenance.PROVIDER_ACTION
                if _is_provider_backed_agent(agent)
                else ActionProvenance.LOCAL_ACTION
            )
            if action is None:
                action = arena.failure_action(state, player_id, ",".join(markers))
                if action is not None:
                    markers.append("fallback_action")
                    fallback_action_count[player_id] += 1
                    action_provenance = ActionProvenance.FALLBACK_ACTION
                    match_valid_for_scoring = False
                    invalid_reason = invalid_reason or _invalid_reason(
                        player_id,
                        "fallback_action_used",
                        markers,
                    )
                    if "fallback_action_used" not in invalid_reason_codes:
                        invalid_reason_codes.append("fallback_action_used")
            legal = action is not None and arena.is_legal(state, player_id, action)
            if not legal:
                markers.extend(["illegal_action", FailureClass.ACTION_NOT_LEGAL.value])
                illegal_action_count[player_id] += 1
                if FailureClass.ACTION_NOT_LEGAL.value not in invalid_reason_codes:
                    invalid_reason_codes.append(FailureClass.ACTION_NOT_LEGAL.value)
                if config.on_illegal_action != "fallback":
                    invalid_reason = _invalid_reason(player_id, "illegal_action", markers)
                    match_valid_for_scoring = False
                    errors.append(
                        _error_row(
                            turn_id=state.turn,
                            player_id=player_id,
                            reason=invalid_reason,
                            response=response,
                            policy=config.on_illegal_action,
                        )
                    )
                    if config.on_illegal_action == "forfeit":
                        next_state = _forfeit_state(
                            state,
                            forfeited_player=player_id,
                            reason=invalid_reason,
                        )
                        trace_events.append(
                            _trace_event(
                                run_id=run_id,
                                episode_id=episode_id,
                                state=state,
                                next_state=next_state,
                                request=request,
                                response=response,
                                action=action,
                                latency_ms=latency_ms,
                                markers=markers,
                                requested_time_budget_ms=config.time_budget_ms,
                                effective_time_budget_ms=effective_time_budget_ms,
                                suite_context=suite_context,
                                event_type="forfeit",
                            )
                        )
                        replay_events.append(
                            _replay_event(
                                run_id,
                                episode_id,
                                next_state,
                                action,
                                markers,
                                actor_player=player_id,
                                state_hash_before=state.state_hash,
                            )
                        )
                        state = next_state
                    break
                fallback = arena.failure_action(state, player_id, "illegal_action")
                if fallback is None or not arena.is_legal(state, player_id, fallback):
                    invalid_reason = _invalid_reason(
                        player_id,
                        "illegal_action_no_fallback",
                        markers,
                    )
                    match_valid_for_scoring = False
                    errors.append(
                        _error_row(
                            turn_id=state.turn,
                            player_id=player_id,
                            reason=invalid_reason,
                            response=response,
                            policy=config.on_illegal_action,
                        )
                    )
                    break
                action = fallback
                markers.append("fallback_action")
                fallback_action_count[player_id] += 1
                action_provenance = ActionProvenance.FALLBACK_ACTION
                match_valid_for_scoring = False
                invalid_reason = invalid_reason or _invalid_reason(
                    player_id,
                    "fallback_action_used",
                    markers,
                )
                if "fallback_action_used" not in invalid_reason_codes:
                    invalid_reason_codes.append("fallback_action_used")
            try:
                next_state = arena.apply_action(state, player_id, action)
            except Exception as exc:
                markers.append(FailureClass.ARENA_APPLY_ERROR.value)
                match_valid_for_scoring = False
                invalid_reason = _invalid_reason(
                    player_id,
                    FailureClass.ARENA_APPLY_ERROR.value,
                    markers,
                )
                invalid_reason_codes.append(FailureClass.ARENA_APPLY_ERROR.value)
                errors.append({"turn_id": state.turn, "error": str(exc)[:500]})
                break

            if action_provenance is ActionProvenance.PROVIDER_ACTION:
                _mark_successful_attempt_applied(
                    provider_receipts,
                    logical_action_id,
                )
            successful_attempt_event_id = _successful_attempt_event_id(
                provider_receipts,
                logical_action_id,
            )
            if (
                action_provenance is ActionProvenance.PROVIDER_ACTION
                and successful_attempt_event_id is not None
            ):
                provider_action_count[player_id] += 1

            trace = _trace_event(
                run_id=run_id,
                episode_id=episode_id,
                state=state,
                next_state=next_state,
                request=request,
                response=response,
                action=action,
                latency_ms=latency_ms,
                markers=markers,
                requested_time_budget_ms=config.time_budget_ms,
                effective_time_budget_ms=effective_time_budget_ms,
                suite_context=suite_context,
                action_provenance=action_provenance.value,
                logical_action_id=logical_action_id,
                successful_attempt_event_id=successful_attempt_event_id,
            )
            trace_events.append(trace)
            replay_events.append(
                _replay_event(
                    run_id,
                    episode_id,
                    next_state,
                    action,
                    markers,
                    actor_player=player_id,
                    state_hash_before=state.state_hash,
                    action_provenance=action_provenance.value,
                    logical_action_id=logical_action_id,
                    successful_attempt_event_id=successful_attempt_event_id,
                )
            )
            agent_io.append(
                {
                    "turn_id": state.turn,
                    "agent_id": getattr(agent, "id", "agent"),
                    "request": request.to_dict(),
                    "response": response.to_dict() if response else None,
                    "latency_ms": latency_ms,
                    "markers": markers,
                    "provider_receipt": receipt if isinstance(receipt, dict) else None,
                    "action_provenance": action_provenance.value,
                    "logical_action_id": logical_action_id,
                }
            )
            history.append(
                {
                    "turn_id": state.turn,
                    "player": player_id,
                    "action": action,
                    "state_hash": next_state.state_hash,
                    "markers": markers,
                    "action_provenance": action_provenance.value,
                    "logical_action_id": logical_action_id,
                }
            )
            state = next_state

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        for provider_receipt in provider_receipts:
            receipt_usage, receipt_cost = aggregate_provider_receipts([provider_receipt])
            provider_receipt["usage_complete"] = receipt_usage["usageComplete"]
            provider_receipt["cost_complete"] = receipt_cost["costComplete"]
        aggregate_usage, aggregate_cost = aggregate_provider_receipts(provider_receipts)
        model_identity_verified = _model_identity_verified(
            provider_receipts,
            agents=agents,
            expected_by_player=config.model_id_by_player or {},
        )
        complete_case_evidence = (
            match_valid_for_scoring
            and bool(config.case_id)
            and model_identity_verified
        )
        for provider_receipt in provider_receipts:
            provider_receipt["case_valid_for_scoring"] = bool(
                complete_case_evidence and provider_receipt.get("action_applied") is True
            )
            receipt_errors = provider_receipt_validation_errors(provider_receipt)
            if receipt_errors:
                raise ValueError("invalid emitted provider receipt: " + "; ".join(receipt_errors))
        score = _score_summary(
            run_id,
            arena,
            state,
            trace_events,
            elapsed_ms,
            verification_level=config.verification_level,
            match_valid_for_scoring=match_valid_for_scoring,
            invalid_reason=invalid_reason,
            agent_error_count_by_player=agent_error_count,
            illegal_action_count_by_player=illegal_action_count,
            fallback_action_count_by_player=fallback_action_count,
            provider_status_by_player=provider_status,
            provider_action_count_by_player=provider_action_count,
            logical_action_count_by_player=logical_action_count,
            invalid_reason_codes=invalid_reason_codes,
            aggregate_usage=aggregate_usage,
            aggregate_cost=aggregate_cost,
            model_identity_verified=model_identity_verified,
            suite_context=suite_context,
            requested_time_budget_ms=config.time_budget_ms,
            effective_time_budget_ms=effective_time_budget_ms,
        )
        build = ArtifactBuildInput(
            run_id=run_id,
            arena_version=f"{arena.id}:{arena.version}",
            agent_version=_agent_versions(agents),
            score=score,
            trace_events=trace_events,
            replay_events=replay_events,
            metrics=score.metrics,
            runner_log=f"run_id={run_id} arena={arena.id}\n",
            agent_io=agent_io,
            errors=errors,
            provider_receipts=provider_receipts,
            run_metadata={
                **suite_context,
                "requested_time_budget_ms": config.time_budget_ms,
                "effective_time_budget_ms": effective_time_budget_ms,
                "max_turns": max_turns,
                "model_id_by_player": dict(config.model_id_by_player or {}),
                "match_fingerprint": match_fingerprint,
                "execution_profile": config.execution_profile,
                "on_agent_error": config.on_agent_error,
                "on_illegal_action": config.on_illegal_action,
            },
            wrapper_version=config.wrapper_version,
            eval_suite_version=config.eval_suite_version,
            scoring_policy_version=config.scoring_policy_version or f"{arena.id}-score:1.0.0",
            runner_version=config.runner_version,
            verification_level=config.verification_level,
        )
        output = write_artifact(
            build,
            artifact_path,
            archive=config.archive,
            overwrite=config.overwrite,
        )
        expanded = expanded_artifact_path(artifact_path).resolve()
        _publish_latest_links(
            output_dir=config.output_dir,
            artifact_path=output,
            expanded_path=expanded,
            archive=config.archive,
        )
        return RunResult(
            run_id=run_id,
            artifact_path=output,
            expanded_path=expanded,
            score=score,
            replay_events=replay_events,
            trace_events=trace_events,
        )


def _agent(value: Any, *, seed: int) -> Any:
    if isinstance(value, str):
        return create_builtin_agent(value, seed=seed)
    return value


def _reject_official_inline_retries(agents: list[Any]) -> None:
    for agent in agents:
        runtime_config = getattr(agent, "runtime_config", None)
        max_retries = getattr(runtime_config, "max_retries", 0)
        if isinstance(max_retries, int) and max_retries > 0:
            raise ValueError(
                "official_eval rejects provider runtime max_retries > 0; "
                "the official orchestrator owns case retries"
            )


def _agents_for_arena(arena: Arena, config: RunConfig) -> dict[str, Any]:
    provided = dict(config.agents or {})
    agents: dict[str, Any] = {}
    for index, player_id in enumerate(arena.players):
        if player_id in provided:
            value = provided[player_id]
        elif player_id == "player_1":
            value = config.agent_1
        elif player_id == "player_2":
            value = config.agent_2
        else:
            raise ValueError(
                f"Arena {arena.id} requires an explicit agent for {player_id}; "
                "pass RunConfig.agents for arenas with more than two players."
            )
        agents[player_id] = _agent(value, seed=config.seed + index)
    return agents


def _last_provider_receipt(agent: Any) -> dict[str, Any] | None:
    receipt = getattr(agent, "last_receipt", None)
    return receipt if isinstance(receipt, dict) else None


def _provider_attempt_receipts(
    agent: Any,
    *,
    fallback: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    receipts = getattr(agent, "attempt_receipts", None)
    if isinstance(receipts, list):
        return [receipt for receipt in receipts if isinstance(receipt, dict)]
    return [fallback] if fallback is not None else []


def _enrich_attempt_receipts(
    receipts: list[dict[str, Any]],
    *,
    run_id: str,
    official_run_id: str | None = None,
    model_lane_id: str | None = None,
    run_job_id: str | None = None,
    environment: str = "local",
    agent_id: str = "agent",
    agent_version: str = "1",
    episode_id: str,
    case_id: str | None,
    shard_index: int | None = None,
    turn_id: int,
    player_id: str,
    logical_action_id: str,
    latency_ms: int,
    existing_event_ids: set[str],
    case_attempt_index: int = 1,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    indexes: list[int] = []
    parent_attempt_id: str | None = None
    for fallback_index, receipt in enumerate(receipts, start=1):
        raw_index = receipt.get("attempt_index", receipt.get("attempt", fallback_index))
        if not isinstance(raw_index, int) or isinstance(raw_index, bool) or raw_index < 1:
            raise ValueError("provider attempt_index must be a positive integer")
        indexes.append(raw_index)
        event_id = provider_attempt_event_id(
            physical_run_id=run_id,
            case_id=case_id,
            case_attempt_index=case_attempt_index,
            logical_action_id=logical_action_id,
            attempt_index=raw_index,
        )
        if event_id in existing_event_ids:
            raise ValueError(f"duplicate provider attempt event id {event_id}")
        existing_event_ids.add(event_id)
        attempt_kind = receipt.get("attempt_kind") or "primary"
        if case_attempt_index > 1 and raw_index == 1 and attempt_kind == "primary":
            attempt_kind = "case_retry"
        receipt_provider = receipt.get("provider")
        receipt_model = receipt.get("locked_model_id") or receipt.get("model")
        row = {
            **receipt,
            "schema_version": "eslams.provider.receipt.v2",
            "event_id": event_id,
            "run_id": run_id,
            "physical_run_id": run_id,
            "official_run_id": official_run_id or run_id,
            "model_lane_id": model_lane_id
            or f"{receipt_provider or 'unknown'}:{receipt_model or 'unknown'}",
            "run_job_id": run_job_id or run_id,
            "environment": environment,
            "episode_id": episode_id,
            "case_id": case_id,
            "case_attempt_index": case_attempt_index,
            "shard_index": shard_index,
            "turn_id": turn_id,
            "agent_id": receipt.get("agent_id") or agent_id,
            "agent_version": receipt.get("agent_version") or agent_version,
            "active_player": player_id,
            "seat_id": player_id,
            "logical_action_id": logical_action_id,
            "attempt": raw_index,
            "attempt_index": raw_index,
            "attempt_kind": attempt_kind,
            "parent_attempt_id": receipt.get("parent_attempt_id") or parent_attempt_id,
            "status": "completed" if receipt.get("outcome") == "ok" else "failed",
            "action_applied": False,
            "case_valid_for_scoring": False,
            "latency_ms": receipt.get("latency_ms") or latency_ms,
            "reasoning_included_in_output": (
                receipt.get("usage", {}).get("reasoning_included_in_output")
                if isinstance(receipt.get("usage"), dict)
                else None
            ),
            "usage_source": (
                receipt.get("usage", {}).get("usage_source")
                if isinstance(receipt.get("usage"), dict)
                else None
            ),
            "cost_source": _receipt_cost_source(receipt),
            "wire_parse_status": _wire_parse_status(receipt),
            "action_parse_status": _action_parse_status(receipt),
        }
        enriched.append(row)
        parent_attempt_id = event_id
    if indexes != list(range(1, len(indexes) + 1)):
        raise ValueError("provider attempt indexes must be monotonic and gap-free per action")
    return enriched


def _receipt_cost_source(receipt: dict[str, Any]) -> str | None:
    estimated_cost = receipt.get("estimated_cost")
    if isinstance(estimated_cost, dict) and isinstance(estimated_cost.get("source"), str):
        return str(estimated_cost["source"])
    pricing = receipt.get("pricing")
    if (
        isinstance(estimated_cost, dict)
        and estimated_cost.get("status") == "ok"
        and isinstance(pricing, dict)
        and isinstance(pricing.get("source"), str)
    ):
        return str(pricing["source"])
    return None


def _wire_parse_status(receipt: dict[str, Any]) -> str:
    explicit = receipt.get("wire_parse_status")
    if isinstance(explicit, str) and explicit:
        return explicit
    if receipt.get("outcome") in {"ok", "action_response_unparseable", "action_not_legal"}:
        return "ok"
    if receipt.get("outcome") == "provider_response_schema_mismatch":
        return "failed"
    return "not_attempted"


def _action_parse_status(receipt: dict[str, Any]) -> str:
    explicit = receipt.get("action_parse_status")
    if isinstance(explicit, str) and explicit:
        return explicit
    if receipt.get("outcome") in {"ok", "action_not_legal"}:
        return "ok"
    if receipt.get("outcome") == "action_response_unparseable":
        return "failed"
    return "not_attempted"


def _mark_successful_attempt_applied(
    receipts: list[dict[str, Any]],
    logical_action_id: str,
) -> None:
    for receipt in reversed(receipts):
        if receipt.get("logical_action_id") == logical_action_id and receipt.get("outcome") == "ok":
            receipt["action_applied"] = True
            return


def _successful_attempt_event_id(
    receipts: list[dict[str, Any]],
    logical_action_id: str,
) -> str | None:
    for receipt in reversed(receipts):
        if (
            receipt.get("logical_action_id") == logical_action_id
            and receipt.get("outcome") == "ok"
            and receipt.get("action_applied") is True
            and isinstance(receipt.get("event_id"), str)
        ):
            return str(receipt["event_id"])
    return None


def _failure_class_from_response(response: ActResponse | None, markers: list[str]) -> str:
    if response is not None:
        value = response.metadata.get("error_kind")
        if isinstance(value, str) and value:
            return value
    for marker in markers:
        if marker in {item.value for item in FailureClass}:
            return marker
    return "agent_error"


def _model_identity_verified(
    receipts: list[dict[str, Any]],
    *,
    agents: dict[str, Any],
    expected_by_player: dict[str, str],
) -> bool:
    provider_players = {
        player for player, agent in agents.items() if _is_provider_backed_agent(agent)
    }
    if not provider_players:
        return True
    successful = [receipt for receipt in receipts if receipt.get("outcome") == "ok"]
    if not successful:
        return False
    for player in provider_players:
        player_receipts = [
            receipt for receipt in successful if receipt.get("active_player") == player
        ]
        if not player_receipts:
            return False
        expected = expected_by_player.get(player)
        for receipt in player_receipts:
            resolved = receipt.get("locked_model_id")
            if not isinstance(resolved, str) or not resolved:
                return False
            identity_source = receipt.get("model_identity_source")
            trusted_sources = {"provider_response", "pinned_endpoint"}
            if receipt.get("provider") == "mock":
                trusted_sources.add("mock_attested")
            if identity_source not in trusted_sources:
                return False
            if identity_source == "pinned_endpoint" and resolved != receipt.get("model"):
                return False
            if expected is not None and resolved != expected:
                return False
    return True


def _publish_latest_links(
    *,
    output_dir: Path,
    artifact_path: Path,
    expanded_path: Path,
    archive: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_archive = output_dir / "latest.eslams"
    latest_expanded = output_dir / "latest.eslams.d"
    targets = [latest_archive]
    if not archive or expanded_path.exists():
        targets.append(latest_expanded)
    _assert_latest_paths_replaceable(targets)
    if archive:
        _replace_latest_link(latest_archive, artifact_path, is_dir=False)
        if expanded_path.exists():
            _replace_latest_link(latest_expanded, expanded_path, is_dir=True)
        return
    _remove_latest_path(latest_archive)
    _replace_latest_link(latest_expanded, artifact_path, is_dir=True)


def _assert_latest_paths_replaceable(paths: list[Path]) -> None:
    collisions = [
        path
        for path in paths
        if (path.exists() or path.is_symlink()) and not path.is_symlink()
    ]
    if collisions:
        joined = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"refusing to replace non-symlink latest path: {joined}")


def _replace_latest_link(path: Path, target: Path, *, is_dir: bool) -> None:
    _remove_latest_path(path)
    path.symlink_to(target.resolve(), target_is_directory=is_dir)


def _remove_latest_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.is_symlink():
        raise FileExistsError(f"refusing to replace non-symlink latest path: {path}")
    path.unlink()


def _agent_versions(agents: dict[str, Any]) -> str:
    return ";".join(
        f"{player_id}:{getattr(agent, 'id', 'agent')}:{getattr(agent, 'version', '1')}"
        for player_id, agent in sorted(agents.items())
    )


def _match_fingerprint(
    arena: Arena,
    config: RunConfig,
    agents: dict[str, Any],
    max_turns: int,
) -> str:
    return sha256_json(
        {
            "arena_id": arena.id,
            "seed": config.seed,
            "max_turns": max_turns,
            "agent_version": _agent_versions(agents),
            "failure_policies": {
                "on_agent_error": config.on_agent_error,
                "on_illegal_action": config.on_illegal_action,
            },
            "execution_profile": config.execution_profile,
            "suite": _suite_context(config),
            "model_id_by_player": dict(config.model_id_by_player or {}),
        }
    )


def _default_run_id(arena: Arena) -> str:
    safe_arena_id = "".join(char if char.isalnum() else "-" for char in arena.id).strip("-")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    short_uuid = uuid.uuid4().hex[:8]
    return f"run_{safe_arena_id}_{timestamp}_{short_uuid}"


def _validate_run_id(run_id: str) -> None:
    windows_stem = run_id.partition(".")[0].upper()
    if (
        not run_id
        or len(run_id) > 200
        or ".." in run_id
        or windows_stem in WINDOWS_RESERVED_NAMES
        or PORTABLE_RUN_ID_RE.fullmatch(run_id) is None
    ):
        raise ValueError(
            "run_id must be a portable path-safe identifier using letters, digits, dots, "
            "underscores, or hyphens"
        )


def _artifact_output_path(*, output_dir: Path, run_id: str, archive: bool) -> Path:
    _validate_run_id(run_id)
    output_root = output_dir.resolve()
    output_name = f"{run_id}.eslams" if archive else f"{run_id}.eslams.d"
    candidate = output_root / output_name
    try:
        candidate.resolve().relative_to(output_root)
    except ValueError as exc:
        raise ValueError("artifact output path escapes output_dir") from exc
    return candidate


def _refuse_existing_artifact(path: Path, *, archive: bool, overwrite: bool) -> None:
    targets = [path, expanded_artifact_path(path)] if archive else [path]
    symlinks = [target for target in targets if target.is_symlink()]
    if symlinks:
        joined = ", ".join(str(target) for target in symlinks)
        raise FileExistsError(f"refusing to overwrite artifact symlink: {joined}")
    existing = [target for target in targets if target.exists() or target.is_symlink()]
    if existing and not overwrite:
        joined = ", ".join(str(target) for target in existing)
        raise FileExistsError(
            f"artifact path already exists: {joined}; pass overwrite=True or --overwrite"
        )


def _request(
    *,
    arena: Arena,
    state: ArenaState,
    run_id: str,
    episode_id: str,
    agent: Any,
    player_id: str,
    time_budget_ms: int,
    history: list[dict[str, Any]],
    memory_policy: str,
    case_id: str | None,
    case_attempt_index: int,
    shard_index: int | None,
    logical_action_id: str,
) -> ActRequest:
    return make_act_request(
        run_id=run_id,
        episode_id=episode_id,
        turn_id=state.turn,
        arena_id=arena.id,
        arena_version=arena.version,
        agent_id=getattr(agent, "id", "agent"),
        agent_version=getattr(agent, "version", "1"),
        active_player=player_id,
        observation=arena.observation_for(state, player_id),
        legal_actions=arena.legal_actions_for(state, player_id),
        action_schema=arena.action_schema,
        history=list(history),
        time_budget_ms=time_budget_ms,
        memory_policy=memory_policy,
        metadata={
            "state_hash": state.state_hash,
            "physical_run_id": run_id,
            "case_id": case_id,
            "case_attempt_index": case_attempt_index,
            "shard_index": shard_index,
            "logical_action_id": logical_action_id,
        },
    )


def _suite_context(config: RunConfig) -> dict[str, Any]:
    return {
        "suite_id": config.suite_id,
        "case_id": config.case_id,
        "case_attempt_index": config.case_attempt_index,
        "suite_fingerprint": config.suite_fingerprint,
        "plan_hash": config.plan_hash,
        "shard_index": config.shard_index,
        "shard_count": config.shard_count,
    }


def _call_agent(
    agent: Any,
    request: ActRequest,
    *,
    time_budget_ms: int,
) -> tuple[ActResponse | None, list[str], int]:
    start = time.perf_counter()
    markers: list[str] = []
    try:
        with _agent_time_limit(time_budget_ms):
            response = agent.act(request)
        if not isinstance(response, ActResponse):
            if isinstance(response, dict):
                response = ActResponse.from_mapping(response)
            else:
                response = ActResponse(action=response)
    except TimeoutError as exc:
        markers.extend(["timeout", FailureClass.PROVIDER_TIMEOUT.value])
        response = ActResponse(
            action=None,
            metadata={
                "error": str(exc)[:500],
                "error_kind": FailureClass.PROVIDER_TIMEOUT.value,
            },
        )
    except ProviderCallError as exc:
        markers.extend(["agent_error", exc.error_kind])
        response = ActResponse(
            action=None,
            metadata={
                "error": str(exc),
                "error_kind": exc.error_kind,
                "provider": exc.provider or getattr(agent, "provider", None),
                "model": exc.model or getattr(agent, "model", None),
                "status_code": exc.status_code,
            },
        )
    except ProtocolError as exc:
        markers.extend(["agent_error", FailureClass.ACTION_RESPONSE_UNPARSEABLE.value])
        response = ActResponse(
            action=None,
            metadata={
                "error": str(exc)[:500],
                "error_kind": FailureClass.ACTION_RESPONSE_UNPARSEABLE.value,
            },
        )
    except Exception as exc:
        markers.append("agent_crash")
        response = ActResponse(
            action=None,
            metadata={"error": str(exc), "error_kind": "agent_crash"},
        )
    latency_ms = int((time.perf_counter() - start) * 1000)
    if latency_ms > time_budget_ms and "timeout" not in markers:
        markers.append("timeout")
        response = ActResponse(
            action=None,
            metadata={
                "error": f"agent exceeded time budget of {time_budget_ms}ms",
                "error_kind": FailureClass.PROVIDER_TIMEOUT.value,
            },
        )
    if response is None or response.action is None:
        markers.append("no_action")
    return response, markers, latency_ms


@contextmanager
def _agent_time_limit(time_budget_ms: int) -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal,
        "setitimer",
    ):
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _raise_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"agent exceeded time budget of {time_budget_ms}ms")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, max(time_budget_ms / 1000, 0.001))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def _trace_event(
    *,
    run_id: str,
    episode_id: str,
    state: ArenaState,
    next_state: ArenaState,
    request: ActRequest,
    response: ActResponse | None,
    action: Any,
    latency_ms: int,
    markers: list[str],
    requested_time_budget_ms: int,
    effective_time_budget_ms: int,
    suite_context: dict[str, Any],
    event_type: str = "action",
    action_provenance: str | None = None,
    logical_action_id: str | None = None,
    successful_attempt_event_id: str | None = None,
) -> TraceEvent:
    event_id = f"{run_id}:{state.turn:06d}"
    public = {
        "state_hash_before": state.state_hash,
        "state_hash_after": next_state.state_hash,
        "active_player": state.active_player,
        "actor_player": state.active_player,
        "seat": state.active_player,
        "action": action,
        "scores": next_state.scores,
        "markers": markers,
        "latency_ms": latency_ms,
        "requested_time_budget_ms": requested_time_budget_ms,
        "effective_time_budget_ms": effective_time_budget_ms,
        "suite_context": suite_context,
        "public_explanation": response.public_explanation if response else None,
        "action_provenance": action_provenance,
        "logical_action_id": logical_action_id,
        "successful_attempt_event_id": successful_attempt_event_id,
    }
    return TraceEvent(
        event_id=event_id,
        run_id=run_id,
        episode_id=episode_id,
        turn_id=state.turn,
        event_type=event_type,
        public=public,
        agent_visible={
            **public,
            "observation": request.observation,
            "legal_actions": request.legal_actions,
        },
        judge={
            **public,
            "request": request.to_dict(),
            "response": response.to_dict() if response else None,
        },
        auditor={
            **public,
            "protocol_version": request.protocol_version,
            "state_before": state.to_dict(),
            "state_after": next_state.to_dict(),
        },
    )


def _replay_event(
    run_id: str,
    episode_id: str,
    state: ArenaState,
    action: Any | None,
    markers: list[str],
    *,
    actor_player: str | None,
    state_hash_before: str | None,
    action_provenance: str | None = None,
    logical_action_id: str | None = None,
    successful_attempt_event_id: str | None = None,
) -> ReplayEvent:
    public_reasoning_ref = None
    if action is not None:
        public_reasoning_ref = f"public_reasoning/reasoning.jsonl#{state.turn}"
    return ReplayEvent(
        event_id=f"{run_id}:replay:{state.turn:06d}",
        run_id=run_id,
        episode_id=episode_id,
        turn_id=state.turn,
        state_hash=str(state.state_hash),
        active_player=state.active_player,
        actor_player=actor_player,
        seat=actor_player,
        state_hash_before=state_hash_before,
        state_hash_after=str(state.state_hash),
        action=action,
        action_label=None if action is None else str(action),
        public_reasoning_ref=public_reasoning_ref,
        visibility="public",
        public_safe=True,
        state_hash_valid=True,
        state_hash_invalid_reason=None,
        action_provenance=action_provenance,
        logical_action_id=logical_action_id,
        successful_attempt_event_id=successful_attempt_event_id,
        public_state=state.public_state,
        scores=state.scores,
        terminal=state.terminal,
        outcome=state.outcome,
        render_hints=state.render_hints,
        markers=markers,
    )


def _score_summary(
    run_id: str,
    arena: Arena,
    state: ArenaState,
    trace_events: list[TraceEvent],
    elapsed_ms: int,
    *,
    verification_level: str,
    match_valid_for_scoring: bool,
    invalid_reason: str | None,
    agent_error_count_by_player: dict[str, int],
    illegal_action_count_by_player: dict[str, int],
    fallback_action_count_by_player: dict[str, int],
    provider_status_by_player: dict[str, str],
    provider_action_count_by_player: dict[str, int],
    logical_action_count_by_player: dict[str, int],
    invalid_reason_codes: list[str],
    aggregate_usage: dict[str, Any],
    aggregate_cost: dict[str, Any],
    model_identity_verified: bool,
    suite_context: dict[str, Any],
    requested_time_budget_ms: int,
    effective_time_budget_ms: int,
) -> ScoreSummary:
    scores = arena.score(state)
    winner = str(state.outcome["winner"]) if state.outcome and state.outcome.get("winner") else None
    primary = float(scores.get("player_1", 0.0)) if scores else 0.0
    best_score = max(scores.values()) if scores else 0.0
    total_turns = max(1, len(trace_events))
    illegal = sum(
        1 for event in trace_events if "illegal_action" in event.public.get("markers", [])
    )
    timeouts = sum(1 for event in trace_events if "timeout" in event.public.get("markers", []))
    usage_complete = aggregate_usage.get("usageComplete") is True
    cost_complete = aggregate_usage.get("costComplete") is True
    attempt_ledger_complete = aggregate_usage.get("attemptLedgerComplete") is True
    integrity_status = "valid" if match_valid_for_scoring else "invalid"
    if match_valid_for_scoring and (
        not usage_complete or not cost_complete or not attempt_ledger_complete
    ):
        integrity_status = "incomplete"
    return ScoreSummary(
        run_id=run_id,
        arena_id=arena.id,
        primary_score=primary,
        scores_by_player=scores,
        winner=winner,
        outcome=state.outcome,
        metrics={
            "turns": len(trace_events),
            "elapsed_ms": elapsed_ms,
            "illegal_action_rate": illegal / total_turns,
            "timeout_rate": timeouts / total_turns,
            "match_valid_for_scoring": match_valid_for_scoring,
            "invalid_reason": invalid_reason,
            "agent_error_count_by_player": agent_error_count_by_player,
            "illegal_action_count_by_player": illegal_action_count_by_player,
            "fallback_action_count_by_player": fallback_action_count_by_player,
            "provider_status_by_player": provider_status_by_player,
            "provider_action_count_by_player": provider_action_count_by_player,
            "logical_action_count_by_player": logical_action_count_by_player,
            "invalid_reason_codes": list(dict.fromkeys(invalid_reason_codes)),
            "integrity_status": integrity_status,
            "usage_complete": usage_complete,
            "cost_complete": cost_complete,
            "attempt_ledger_complete": attempt_ledger_complete,
            "model_identity_verified": model_identity_verified,
            "suite_context": suite_context,
            "requested_time_budget_ms": requested_time_budget_ms,
            "effective_time_budget_ms": effective_time_budget_ms,
            "sample_size": 1,
            "confidence_interval": [primary, primary],
            "evaluated_player": "player_1",
            "best_score": best_score,
            "estimated_cost": {"status": "cost_unavailable"},
        },
        verification_level=verification_level,
        match_valid_for_scoring=match_valid_for_scoring,
        invalid_reason=invalid_reason,
        agent_error_count_by_player=agent_error_count_by_player,
        illegal_action_count_by_player=illegal_action_count_by_player,
        fallback_action_count_by_player=fallback_action_count_by_player,
        provider_status_by_player=provider_status_by_player,
        provider_action_count_by_player=provider_action_count_by_player,
        logical_action_count_by_player=logical_action_count_by_player,
        invalid_reason_codes=list(dict.fromkeys(invalid_reason_codes)),
        integrity_status=integrity_status,
        usage_complete=usage_complete,
        cost_complete=cost_complete,
        attempt_ledger_complete=attempt_ledger_complete,
        model_identity_verified=model_identity_verified,
        scoring_safety_reason=invalid_reason,
        aggregate_usage=aggregate_usage,
        aggregate_cost=aggregate_cost,
    )


def _validate_failure_policy(name: str, value: str) -> None:
    if value not in FAILURE_POLICIES:
        options = ", ".join(sorted(FAILURE_POLICIES))
        raise ValueError(f"{name} must be one of: {options}")


def _has_agent_error(markers: list[str]) -> bool:
    return any(marker in {"timeout", "agent_crash", "no_action"} for marker in markers)


def _invalid_reason(player_id: str, reason: str, markers: list[str]) -> str:
    detail = ",".join(dict.fromkeys(markers))
    return f"{player_id}:{reason}:{detail}" if detail else f"{player_id}:{reason}"


def _error_row(
    *,
    turn_id: int,
    player_id: str,
    reason: str,
    response: ActResponse | None,
    policy: str,
) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "player_id": player_id,
        "reason": reason,
        "policy": policy,
        "response_metadata": response.metadata if response else {},
    }


def _provider_status(agent: Any, response: ActResponse | None, markers: list[str]) -> str:
    if not _is_provider_backed_agent(agent):
        return "local_agent"
    return "agent_error"


def _is_provider_backed_agent(agent: Any) -> bool:
    provider = getattr(agent, "provider", None)
    model = getattr(agent, "model", None)
    return isinstance(provider, str) and bool(provider) and isinstance(model, str) and bool(model)


def _provider_receipt_status(receipt: dict[str, Any]) -> str:
    outcome = receipt.get("outcome")
    if isinstance(outcome, str) and outcome != "ok":
        return "agent_error"
    usage = receipt.get("usage")
    reason = receipt.get("usage_unavailable_reason")
    if isinstance(reason, str) and reason:
        return "provider_usage_unavailable"
    if not isinstance(usage, dict):
        return "provider_usage_unavailable"
    if all(
        isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    ):
        return "provider_ok"
    return "provider_usage_unavailable"


def _forfeit_state(
    state: ArenaState,
    *,
    forfeited_player: str,
    reason: str,
) -> ArenaState:
    players = list(state.scores)
    remaining_players = [player for player in players if player != forfeited_player]
    outcome: dict[str, Any]
    if len(players) <= 2:
        winner = remaining_players[0] if remaining_players else None
        scores = {player: (1.0 if player == winner else 0.0) for player in players}
        outcome = {"winner": winner, "reason": "forfeit", "invalid_reason": reason}
    else:
        scores = dict(state.scores)
        if forfeited_player in scores:
            scores[forfeited_player] = 0.0
        winner = _unique_high_score_winner(scores, remaining_players)
        outcome = {
            "winner": winner,
            "reason": "forfeit",
            "invalid_reason": reason,
            "forfeited_player": forfeited_player,
            "remaining_players": remaining_players,
        }
    public_state = {
        **state.public_state,
        "terminal_reason": "forfeit",
        "winner": winner,
    }
    if isinstance(public_state.get("final_validation"), dict):
        public_state["final_validation"] = {
            **public_state["final_validation"],
            "score": scores,
        }
    return ArenaState(
        state_id=f"state_{state.turn + 1:06d}_forfeit",
        turn=state.turn + 1,
        active_player=state.active_player,
        public_state=public_state,
        private_state_by_player=state.private_state_by_player,
        legal_actions_by_player={player: [] for player in state.legal_actions_by_player},
        scores=scores,
        terminal=True,
        outcome=outcome,
        rng_commitment=state.rng_commitment,
        render_hints=state.render_hints,
        metadata={**state.metadata, "forfeited_player": forfeited_player},
    )


def _unique_high_score_winner(scores: dict[str, float], players: list[str]) -> str | None:
    if not players:
        return None
    ranked = sorted(players, key=lambda player: scores.get(player, 0.0), reverse=True)
    if len(ranked) == 1:
        return ranked[0]
    best = scores.get(ranked[0], 0.0)
    second = scores.get(ranked[1], 0.0)
    return ranked[0] if best > second else None
