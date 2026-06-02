"""Deterministic local runner."""

from __future__ import annotations

import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eslams.agents import create_builtin_agent
from eslams.arena import Arena
from eslams.arenas import registry
from eslams.artifacts import ArtifactBuildInput, write_artifact
from eslams.events import ReplayEvent, ScoreSummary, TraceEvent
from eslams.protocol import ActRequest, ActResponse, make_act_request
from eslams.state import ArenaState


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


@dataclass(frozen=True)
class RunResult:
    run_id: str
    artifact_path: Path
    score: ScoreSummary
    replay_events: list[ReplayEvent]
    trace_events: list[TraceEvent]


class Runner:
    def __init__(self, *, memory_policy: str = "current_observation_plus_public_history") -> None:
        self.memory_policy = memory_policy

    def run(self, config: RunConfig) -> RunResult:
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
            action = (
                response.action
                if response
                else arena.failure_action(state, player_id, ",".join(markers))
            )
            legal = action is not None and arena.is_legal(state, player_id, action)
            if not legal:
                markers.append("illegal_action")
                fallback = arena.failure_action(state, player_id, "illegal_action")
                if fallback is None or not arena.is_legal(state, player_id, fallback):
                    break
                action = fallback
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
        )
        artifact_path = config.output_dir / f"{run_id}.eslams"
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
        latest = config.output_dir / "latest.eslams"
        if not config.archive:
            if latest.exists() or latest.is_symlink():
                if latest.is_dir() and not latest.is_symlink():
                    import shutil

                    shutil.rmtree(latest)
                else:
                    latest.unlink()
            with suppress(OSError):
                latest.symlink_to(output.resolve(), target_is_directory=True)
        return RunResult(
            run_id=run_id,
            artifact_path=output,
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
    except TimeoutError:
        markers.append("timeout")
        response = None
    except Exception as exc:
        markers.append("agent_crash")
        response = ActResponse(action=None, metadata={"error": str(exc)})
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
            "sample_size": 1,
            "confidence_interval": [primary, primary],
            "cost_usd": 0.0,
        },
        verification_level=verification_level,
    )
