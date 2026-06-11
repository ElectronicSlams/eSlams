"""Golden Core fixture generation and validation helpers."""

from __future__ import annotations

from typing import Any

import eslams.arenas  # noqa: F401
from eslams.action_descriptors import action_token
from eslams.arena import registry
from eslams.arena_transport import serialize_state
from eslams.contracts.versions import CORE_CONTRACT_VERSION, CORE_PACKAGE_VERSION
from eslams.core_contract import (
    core_step,
    observation_for_view,
)
from eslams.hashing import legal_action_hash, observation_hash


def golden_fixture_for_game(*, game_id: str, seed: int = 1) -> dict[str, Any]:
    arena = registry.create(game_id)
    state = arena.initial_state(seed)
    legal = arena.legal_actions_for(state, state.active_player)
    action = legal[0] if legal else None
    observation = observation_for_view(
        arena=arena,
        state=state,
        actor_id=state.active_player,
        view="public_compact",
        legal_actions=legal,
    )
    expected_next_state_hash = None
    expected_scores: dict[str, float] = dict(state.scores)
    expected_terminal = state.terminal
    if action is not None:
        response = core_step(
            {
                "coreContractVersion": CORE_CONTRACT_VERSION,
                "gameId": game_id,
                "rulesetVersion": "standard",
                "state": serialize_state(state),
                "action": {"actionId": action_token(action)},
                "actorId": state.active_player,
                "requestId": f"golden:{game_id}:initial",
                "includeObservation": True,
                "includeLegalActions": "compact",
                "includeReplayEvent": True,
            }
        )
        expected_next_state_hash = response["nextStateHash"] if response["ok"] else None
        terminal = response.get("terminal")
        if isinstance(terminal, dict):
            scores = terminal.get("scores")
            if isinstance(scores, dict):
                expected_scores = {str(key): float(value) for key, value in scores.items()}
            expected_terminal = bool(terminal.get("terminal"))
    return {
        "gameId": game_id,
        "coreVersion": CORE_PACKAGE_VERSION,
        "coreContractVersion": CORE_CONTRACT_VERSION,
        "fixture": "initial",
        "stateHash": state.state_hash,
        "legalActionHash": legal_action_hash([action_token(item) for item in legal]),
        "observationHash": observation_hash(observation),
        "validActions": [action_token(item) for item in legal],
        "expectedNextStateHash": expected_next_state_hash,
        "expectedScores": expected_scores,
        "expectedTerminal": expected_terminal,
    }


def golden_fixture_bundle(*, game_ids: list[str] | None = None, seed: int = 1) -> dict[str, Any]:
    selected = registry.list() if game_ids is None else game_ids
    return {
        "schemaVersion": "eslams.core.golden_fixtures.v1",
        "coreVersion": CORE_PACKAGE_VERSION,
        "fixtures": [
            golden_fixture_for_game(game_id=game_id, seed=seed)
            for game_id in selected
        ],
    }
