import random

import pytest
from jsonschema import Draft202012Validator

from eslams.arenas.advanced_cards import HANABI_COLORS, HANABI_RANKS, HanabiArena
from eslams.catalogue import game_catalogue_rows
from eslams.contracts.json_schema import schema_for_version
from eslams.contracts.result import validate_result
from eslams.contracts.topology import validate_topology
from eslams.contracts.versions import COOPERATIVE_RESULT_SCHEMA_VERSION


def test_hanabi_cannot_discard_with_full_clues_and_can_discard_after_a_hint():
    arena = HanabiArena()
    state = arena.initial_state(1)
    assert not any(
        action.startswith("discard:") for action in arena.legal_actions_for(state, "player_1")
    )
    with pytest.raises(ValueError):
        arena.apply_action(state, "player_1", "discard:0")
    state = arena.apply_action(state, "player_1", "hint:player_2:R")
    assert "discard:0" in arena.legal_actions_for(state, "player_2")
    state = arena.apply_action(state, "player_2", "discard:0")
    assert state.public_state["clues"] == 8
    assert not any(
        action.startswith("discard:") for action in arena.legal_actions_for(state, "player_1")
    )


def test_seeded_hanabi_playouts_finish_without_stranding_an_agent():
    arena = HanabiArena()
    for seed in range(200):
        state = arena.initial_state(seed)
        rng = random.Random(seed)
        while not state.terminal:
            actions = arena.legal_actions_for(state, state.active_player)
            assert actions, (seed, state.turn)
            state = arena.apply_action(state, state.active_player, rng.choice(actions))
        assert state.outcome is not None
        assert state.outcome["winner"] is None
        assert state.scores["player_1"] == state.scores["player_2"]


def test_cooperative_catalogue_result_schema_and_perfect_game_agree():
    row = next(row for row in game_catalogue_rows() if row["game_id"] == "hanabi")
    topology = row["topology"]
    assert topology["mode"] == "cooperative"
    assert topology["winnerRequired"] is False
    assert row["resultContract"]["winnerRequired"] is False
    assert row["resultContract"]["scoreType"] == "cooperative_score"
    assert row["surface"]["battlefield"] == "disabled"
    assert row["core_0_5_validation_errors"] == []
    assert validate_topology(topology) == []
    assert topology["schemaVersion"] == "eslams.game.topology.v2"
    Draft202012Validator(schema_for_version(topology["schemaVersion"])).validate(topology)
    Draft202012Validator(schema_for_version(row["resultContract"]["schemaVersion"])).validate(
        row["resultContract"]
    )
    from eslams.arenas.advanced_cards import _hanabi_result, _hanabi_scores

    fireworks = dict.fromkeys(HANABI_COLORS, max(HANABI_RANKS))
    outcome = _hanabi_result(fireworks, reason="perfect_fireworks")
    assert outcome["winner"] is None
    assert outcome["team_success"] is True
    result = {
        "schemaVersion": COOPERATIVE_RESULT_SCHEMA_VERSION,
        "mode": "cooperative",
        "terminal": True,
        "winner": None,
        "draw": False,
        "resultType": "score",
        "scores": _hanabi_scores(outcome, fireworks),
    }
    assert validate_result(result, topology) == []
    Draft202012Validator(schema_for_version(COOPERATIVE_RESULT_SCHEMA_VERSION)).validate(result)
    assert validate_result({**result, "winner": "player_1"}, topology)
    legacy = {**topology, "schemaVersion": "eslams.game.topology.v1"}
    assert validate_topology(legacy)
    legacy_validator = Draft202012Validator(schema_for_version("eslams.game.topology.v1"))
    assert list(legacy_validator.iter_errors(topology))
