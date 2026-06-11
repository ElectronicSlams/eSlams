"""Benchmark harness for Core arena step performance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import quantiles
from time import perf_counter_ns
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.action_descriptors import action_token
from eslams.arena import registry
from eslams.arena_transport import deserialize_state, serialize_state
from eslams.core_contract import observation_for_view
from eslams.hashing import canonical_json


def arena_step_benchmark(
    *,
    games: list[str] | None = None,
    iterations: int = 1000,
    seed: int = 1,
) -> list[dict[str, Any]]:
    selected = registry.list() if games is None or games == ["all"] else games
    rows = []
    for game_id in selected:
        rows.append(_benchmark_game(game_id=game_id, iterations=iterations, seed=seed))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eslams_core.bench")
    sub = parser.add_subparsers(dest="command", required=True)
    arena_step = sub.add_parser("arena-step")
    arena_step.add_argument("--games", default="all")
    arena_step.add_argument("--positions", default="fixture")
    arena_step.add_argument("--iterations", type=int, default=1000)
    arena_step.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "arena-step":
        games = ["all"] if args.games == "all" else [item for item in args.games.split(",") if item]
        rows = arena_step_benchmark(games=games, iterations=max(1, args.iterations))
        payload = {
            "schemaVersion": "eslams.core.benchmark.v1",
            "positions": args.positions,
            "iterations": max(1, args.iterations),
            "results": rows,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return 0
    return 1


def _benchmark_game(*, game_id: str, iterations: int, seed: int) -> dict[str, Any]:
    init_samples: list[float] = []
    deserialize_samples: list[float] = []
    legal_samples: list[float] = []
    observation_samples: list[float] = []
    validate_samples: list[float] = []
    apply_samples: list[float] = []
    serialize_samples: list[float] = []
    total_samples: list[float] = []
    arena = registry.create(game_id)

    state = arena.initial_state(seed)
    legal = arena.legal_actions_for(state, state.active_player)
    action = legal[0] if legal else None
    serialized = serialize_state(state)
    observation = observation_for_view(
        arena=arena,
        state=state,
        actor_id=state.active_player,
        view="public_compact",
        legal_actions=legal,
    )

    for _ in range(iterations):
        total_start = perf_counter_ns()

        init_start = perf_counter_ns()
        arena = registry.create(game_id)
        init_samples.append(_elapsed_ms_float(init_start))

        deserialize_start = perf_counter_ns()
        restored = deserialize_state(serialized)
        deserialize_samples.append(_elapsed_ms_float(deserialize_start))

        legal_start = perf_counter_ns()
        legal = arena.legal_actions_for(restored, restored.active_player)
        legal_samples.append(_elapsed_ms_float(legal_start))

        observation_start = perf_counter_ns()
        observation = observation_for_view(
            arena=arena,
            state=restored,
            actor_id=restored.active_player,
            view="public_compact",
            legal_actions=legal,
        )
        observation_samples.append(_elapsed_ms_float(observation_start))

        validate_start = perf_counter_ns()
        token_to_action = {action_token(item): item for item in legal}
        raw_action = token_to_action.get(action_token(action)) if action is not None else None
        validate_samples.append(_elapsed_ms_float(validate_start))

        apply_start = perf_counter_ns()
        if raw_action is not None:
            next_state = arena.apply_action(restored, restored.active_player, raw_action)
        else:
            next_state = restored
        apply_samples.append(_elapsed_ms_float(apply_start))

        serialize_start = perf_counter_ns()
        serialized_next = serialize_state(next_state)
        serialize_samples.append(_elapsed_ms_float(serialize_start))
        total_samples.append(_elapsed_ms_float(total_start))
        serialized = serialized_next if not next_state.terminal else serialize_state(state)

    legal_bytes = len(canonical_json([action_token(item) for item in legal]))
    observation_bytes = len(canonical_json(observation))
    state_bytes = len(canonical_json(serialized))
    return {
        "gameId": game_id,
        "fixture": "initial",
        "iterations": iterations,
        "timingsMs": {
            "initP95": _p95(init_samples),
            "deserializeP95": _p95(deserialize_samples),
            "legalActionsP95": _p95(legal_samples),
            "observationP95": _p95(observation_samples),
            "validateP95": _p95(validate_samples),
            "applyP95": _p95(apply_samples),
            "serializeP95": _p95(serialize_samples),
            "totalP95": _p95(total_samples),
        },
        "sizes": {
            "stateBytes": state_bytes,
            "observationBytes": observation_bytes,
            "legalActionsBytes": legal_bytes,
            "promptTokensApprox": max(1, round((observation_bytes + legal_bytes) / 4)),
        },
    }


def _p95(samples: list[float]) -> float:
    if len(samples) < 2:
        return round(samples[0] if samples else 0.0, 4)
    return round(quantiles(samples, n=100, method="inclusive")[94], 4)


def _elapsed_ms_float(start_ns: int) -> float:
    return (perf_counter_ns() - start_ns) / 1_000_000


if __name__ == "__main__":
    raise SystemExit(main())
