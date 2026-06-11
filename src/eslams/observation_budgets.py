"""Observation and prompt-size budget helpers for Core v0.4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.core_contract import estimate_prompt_tokens, observation_for_view, prompt_package
from eslams.hashing import canonical_json


@dataclass(frozen=True)
class ObservationBudget:
    max_public_compact_bytes: int
    max_prompt_tokens: int
    documented_override: str | None = None


DEFAULT_OBSERVATION_BUDGET = ObservationBudget(
    max_public_compact_bytes=16_000,
    max_prompt_tokens=4_000,
)

OBSERVATION_BUDGETS: dict[str, ObservationBudget] = {
    "tic-tac-toe": ObservationBudget(2_000, 800),
    "connect-four": ObservationBudget(2_000, 800),
    "gomoku": ObservationBudget(8_000, 2_000),
    "othello": ObservationBudget(8_000, 2_000),
    "chess": ObservationBudget(12_000, 3_000),
    "go": ObservationBudget(20_000, 5_000, "19x19 board needs a larger compact state budget."),
}


def budget_for_game(game_id: str) -> ObservationBudget:
    return OBSERVATION_BUDGETS.get(game_id, DEFAULT_OBSERVATION_BUDGET)


def observation_budget_report(*, game_id: str, seed: int = 1) -> dict[str, Any]:
    arena = registry.create(game_id)
    state = arena.initial_state(seed)
    legal_actions = arena.legal_actions_for(state, state.active_player)
    observation = observation_for_view(
        arena=arena,
        state=state,
        actor_id=state.active_player,
        view="public_compact",
        legal_actions=legal_actions,
    )
    prompt = prompt_package(arena=arena, state=state, actor_id=state.active_player)
    budget = budget_for_game(game_id)
    observation_bytes = len(canonical_json(observation))
    prompt_tokens = estimate_prompt_tokens(prompt)
    return {
        "gameId": game_id,
        "observationBytes": observation_bytes,
        "promptTokensApprox": prompt_tokens,
        "budget": {
            "maxPublicCompactBytes": budget.max_public_compact_bytes,
            "maxPromptTokens": budget.max_prompt_tokens,
            "documentedOverride": budget.documented_override,
        },
        "ok": (
            observation_bytes <= budget.max_public_compact_bytes
            and prompt_tokens <= budget.max_prompt_tokens
        ),
    }


def all_observation_budget_reports(*, seed: int = 1) -> list[dict[str, Any]]:
    return [observation_budget_report(game_id=game_id, seed=seed) for game_id in registry.list()]
