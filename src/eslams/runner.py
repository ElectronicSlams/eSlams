"""Deterministic local runner."""

from __future__ import annotations

import shutil
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eslams.agents import create_builtin_agent
from eslams.arena import Arena
from eslams.arenas import registry
from eslams.artifacts import ArtifactBuildInput, expanded_artifact_path, write_artifact
from eslams.events import ReplayEvent, ScoreSummary, TraceEvent
from eslams.protocol import ActRequest, ActResponse, make_act_request
from eslams.state import ArenaState

FAILURE_POLICIES = {"invalid-match", "forfeit", "fallback"}


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
    runner_version: str = "eslams-runner:0.1.0"
    seed: int = 1
    max_turns: int | None = None
    time_budget_ms: int = 30_000
    run_id: str | None = None
    output_dir: Path = Path("runs")
    archive: bool = False
    on_agent_error: str = "fallback"
    on_illegal_action: str = "fallback"


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
        run_id = config.run_id or f"run_{uuid.uuid4().hex[:16]}"
        episode_id = "episode_001"
        state = arena.initial_state(config.seed)
        trace_events: list[TraceEvent] = []
        replay_events: list[ReplayEvent] = [_replay_event(run_id, episode_id, state, None, [])]
        agent_io: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        provider_receipts: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        agent_error_count = dict.fromkeys(arena.players, 0)
        illegal_action_count = dict.fromkeys(arena.players, 0)
        fallback_action_count = dict.fromkeys(arena.players, 0)
        provider_status = {
            player: ("not_called" if hasattr(agents[player], "provider") else "not_provider")
            for player in arena.players
        }
        match_valid_for_scoring = True
        invalid_reason: str | None = None
        max_turns = config.max_turns or arena.max_turns
        start = time.perf_counter()

        while not state.terminal and state.turn < max_turns:
            player_id = state.active_player
            agent = agents[player_id]
            request = _request(
                arena=arena,
                state=state,
                run_id=run_id,
                episode_id=episode_id,
                agent=agent,
                player_id=player_id,
                time_budget_ms=config.time_budget_ms,
                history=history,
                memory_policy=self.memory_policy,
            )
            response, markers, latency_ms = _call_agent(agent, request)
            receipt = getattr(agent, "last_receipt", None)
            if isinstance(receipt, dict):
                provider_status[player_id] = "ok"
                provider_receipts.append(
                    {
                        **receipt,
                        "run_id": run_id,
                        "episode_id": episode_id,
                        "turn_id": state.turn,
                        "active_player": player_id,
                        "latency_ms": latency_ms,
                    }
                )
            if _has_agent_error(markers):
                agent_error_count[player_id] += 1
                provider_status[player_id] = _provider_status(agent, response, markers)
                if config.on_agent_error != "fallback":
                    invalid_reason = _invalid_reason(player_id, "agent_error", markers)
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
                        state = _forfeit_state(
                            state,
                            forfeited_player=player_id,
                            reason=invalid_reason,
                        )
                    break
            action = (
                response.action
                if response
                else arena.failure_action(state, player_id, ",".join(markers))
            )
            if action is None:
                action = arena.failure_action(state, player_id, ",".join(markers))
                if action is not None:
                    markers.append("fallback_action")
                    fallback_action_count[player_id] += 1
            legal = action is not None and arena.is_legal(state, player_id, action)
            if not legal:
                markers.append("illegal_action")
                illegal_action_count[player_id] += 1
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
                        state = _forfeit_state(
                            state,
                            forfeited_player=player_id,
                            reason=invalid_reason,
                        )
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
            try:
                next_state = arena.apply_action(state, player_id, action)
            except Exception as exc:
                markers.append("arena_apply_error")
                errors.append({"turn_id": state.turn, "error": str(exc)})
                break

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
            )
            trace_events.append(trace)
            replay_events.append(_replay_event(run_id, episode_id, next_state, action, markers))
            agent_io.append(
                {
                    "turn_id": state.turn,
                    "agent_id": getattr(agent, "id", "agent"),
                    "request": request.to_dict(),
                    "response": response.to_dict() if response else None,
                    "latency_ms": latency_ms,
                    "markers": markers,
                    "provider_receipt": receipt if isinstance(receipt, dict) else None,
                }
            )
            history.append(
                {
                    "turn_id": state.turn,
                    "player": player_id,
                    "action": action,
                    "state_hash": next_state.state_hash,
                    "markers": markers,
                }
            )
            state = next_state

        elapsed_ms = int((time.perf_counter() - start) * 1000)
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
        )
        output_name = f"{run_id}.eslams" if config.archive else f"{run_id}.eslams.d"
        artifact_path = config.output_dir / output_name
        build = ArtifactBuildInput(
            run_id=run_id,
            arena_version=f"{arena.id}:{arena.version}",
            agent_version=_agent_versions(agents),
            score=score,
            trace_events=trace_events,
            replay_events=replay_events,
            metrics=score.metrics,
            runner_log=f"run_id={run_id} arena={arena.id} elapsed_ms={elapsed_ms}\n",
            agent_io=agent_io,
            errors=errors,
            provider_receipts=provider_receipts,
            wrapper_version=config.wrapper_version,
            eval_suite_version=config.eval_suite_version,
            scoring_policy_version=config.scoring_policy_version or f"{arena.id}-score:1.0.0",
            runner_version=config.runner_version,
            verification_level=config.verification_level,
        )
        output = write_artifact(build, artifact_path, archive=config.archive)
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
            value = config.agent_1
        agents[player_id] = _agent(value, seed=config.seed + index)
    return agents


def _publish_latest_links(
    *,
    output_dir: Path,
    artifact_path: Path,
    expanded_path: Path,
    archive: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if archive:
        _replace_latest_link(output_dir / "latest.eslams", artifact_path, is_dir=False)
        if expanded_path.exists():
            _replace_latest_link(output_dir / "latest.eslams.d", expanded_path, is_dir=True)
        return
    _remove_latest_path(output_dir / "latest.eslams")
    _replace_latest_link(output_dir / "latest.eslams.d", artifact_path, is_dir=True)


def _replace_latest_link(path: Path, target: Path, *, is_dir: bool) -> None:
    _remove_latest_path(path)
    with suppress(OSError):
        path.symlink_to(target.resolve(), target_is_directory=is_dir)


def _remove_latest_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _agent_versions(agents: dict[str, Any]) -> str:
    return ";".join(
        f"{player_id}:{getattr(agent, 'id', 'agent')}:{getattr(agent, 'version', '1')}"
        for player_id, agent in sorted(agents.items())
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
        metadata={"state_hash": state.state_hash},
    )


def _call_agent(agent: Any, request: ActRequest) -> tuple[ActResponse | None, list[str], int]:
    start = time.perf_counter()
    markers: list[str] = []
    try:
        response = agent.act(request)
        if not isinstance(response, ActResponse):
            if isinstance(response, dict):
                response = ActResponse.from_mapping(response)
            else:
                response = ActResponse(action=response)
    except TimeoutError as exc:
        markers.append("timeout")
        response = ActResponse(action=None, metadata={"error": str(exc), "error_kind": "timeout"})
    except Exception as exc:
        markers.append("agent_crash")
        response = ActResponse(
            action=None,
            metadata={"error": str(exc), "error_kind": "agent_crash"},
        )
    latency_ms = int((time.perf_counter() - start) * 1000)
    if response is None or response.action is None:
        markers.append("no_action")
    return response, markers, latency_ms


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
) -> TraceEvent:
    event_id = f"{run_id}:{state.turn:06d}"
    public = {
        "state_hash_before": state.state_hash,
        "state_hash_after": next_state.state_hash,
        "active_player": state.active_player,
        "action": action,
        "scores": next_state.scores,
        "markers": markers,
        "latency_ms": latency_ms,
        "public_explanation": response.public_explanation if response else None,
    }
    return TraceEvent(
        event_id=event_id,
        run_id=run_id,
        episode_id=episode_id,
        turn_id=state.turn,
        event_type="action",
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
) -> ReplayEvent:
    return ReplayEvent(
        event_id=f"{run_id}:replay:{state.turn:06d}",
        run_id=run_id,
        episode_id=episode_id,
        turn_id=state.turn,
        state_hash=str(state.state_hash),
        active_player=state.active_player,
        action=action,
        public_state=state.public_state,
        scores=state.scores,
        terminal=state.terminal,
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
) -> ScoreSummary:
    scores = arena.score(state)
    winner = str(state.outcome["winner"]) if state.outcome and state.outcome.get("winner") else None
    primary = max(scores.values()) if scores else 0.0
    total_turns = max(1, len(trace_events))
    illegal = sum(
        1 for event in trace_events if "illegal_action" in event.public.get("markers", [])
    )
    timeouts = sum(1 for event in trace_events if "timeout" in event.public.get("markers", []))
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
            "sample_size": 1,
            "confidence_interval": [primary, primary],
            "cost_usd": 0.0,
        },
        verification_level=verification_level,
        match_valid_for_scoring=match_valid_for_scoring,
        invalid_reason=invalid_reason,
        agent_error_count_by_player=agent_error_count_by_player,
        illegal_action_count_by_player=illegal_action_count_by_player,
        fallback_action_count_by_player=fallback_action_count_by_player,
        provider_status_by_player=provider_status_by_player,
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
    if not hasattr(agent, "provider"):
        return "not_provider"
    error = str((response.metadata if response else {}).get("error", "")).lower()
    if "missing api key" in error:
        return "missing_api_key"
    if "provider" in error:
        return "provider_error"
    if "timeout" in markers:
        return "timeout"
    return "agent_error"


def _forfeit_state(
    state: ArenaState,
    *,
    forfeited_player: str,
    reason: str,
) -> ArenaState:
    winner = next((player for player in state.scores if player != forfeited_player), None)
    outcome = {"winner": winner, "reason": "forfeit", "invalid_reason": reason}
    scores = {
        player: (1.0 if player == winner else 0.0)
        for player in state.scores
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
        state_id=f"{state.state_id}_forfeit",
        turn=state.turn,
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
