"""Full supplied-history default and byte-exact legacy prompt compatibility."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator

from eslams.arena_transport import serialize_state
from eslams.arenas import registry
from eslams.cli import main
from eslams.contracts.json_schema import schema_for_version
from eslams.core_contract import engine_capabilities, prompt_package

VECTORS = json.loads((Path(__file__).parents[1] /
    "fixtures/prompt_history/prompt_versions.v1.json").read_text())


def make_prompt(case, **options):
    arena = registry.create(VECTORS["arena_id"])
    state = arena.initial_state(VECTORS["seed"])
    return prompt_package(arena=arena, state=state, actor_id=state.active_player,
                          history=case["history"], **options)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["id"])
def test_default_v3_keeps_every_supplied_history_entry_without_mutating_input(case):
    original = copy.deepcopy(case)
    package = make_prompt(case)
    assert package["promptVersion"] == "eslams.core.prompt.v3"
    assert json.loads(package["dynamicTurn"]["moveHistory"]) == case["history"]
    assert package == case["v3_package"]
    assert case == original
    Draft202012Validator(schema_for_version(VECTORS["envelope_schema_version"])).validate(package)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["id"])
def test_explicit_legacy_v2_package_preserves_all_bytes_hash_and_estimate(case):
    assert make_prompt(case, prompt_version="eslams.core.prompt.v2") == case["legacy_v2_package"]


@pytest.mark.parametrize("bad", ["v3", "eslams.core.prompt.v4", None, True, [], {}])
def test_unknown_prompt_version_is_rejected_before_observation_or_action_work(bad):
    arena = Mock()
    arena.legal_actions_for.side_effect = AssertionError("invalid policy reached game callbacks")
    with pytest.raises(ValueError, match="prompt version"):
        prompt_package(arena=arena, state=Mock(), actor_id="player_1", prompt_version=bad)


@pytest.mark.parametrize("bad", ["history", {}, (), [None], ["history"]])
def test_v3_history_requires_public_json_record_list_before_game_callbacks(bad):
    arena = Mock()
    arena.legal_actions_for.side_effect = AssertionError("invalid history reached game callbacks")
    with pytest.raises(ValueError, match="history"):
        prompt_package(arena=arena, state=Mock(), actor_id="player_1", history=bad)


def test_invalid_early_record_cannot_disappear_behind_the_old_window():
    history = [{"turn": 0, "value": float("nan")}, *[{"turn": i} for i in range(1, 40)]]
    arena = Mock()
    arena.legal_actions_for.side_effect = AssertionError(
        "non-finite history reached game callbacks"
    )
    with pytest.raises(ValueError):
        prompt_package(arena=arena, state=Mock(), actor_id="player_1", history=history)


@pytest.mark.parametrize("game", ["connect-four", "hanabi"])
def test_prompt_history_version_does_not_change_game_or_view_projection(game):
    arena = registry.create(game)
    state = arena.initial_state(7)
    before = state.to_dict()
    options = {"arena": arena, "state": state, "actor_id": state.active_player,
               "history": [{"turn": 0}]}
    old = prompt_package(**options, prompt_version="eslams.core.prompt.v2")
    new = prompt_package(**options)
    assert old["stablePrefix"] == new["stablePrefix"]
    assert old["outputSchema"] == new["outputSchema"]
    assert old["dynamicTurn"]["currentObservation"] == new["dynamicTurn"]["currentObservation"]
    assert old["dynamicTurn"]["legalActions"] == new["dynamicTurn"]["legalActions"]
    assert old["promptHash"] != new["promptHash"]
    assert state.to_dict() == before


def test_default_capability_advertises_new_prompt_semantics():
    capabilities = engine_capabilities("connect-four")
    assert capabilities["promptVersion"] == "eslams.core.prompt.v3"
    assert capabilities["supportedPromptVersions"] == [
        "eslams.core.prompt.v3", "eslams.core.prompt.v2"
    ]


def test_cli_history_and_explicit_legacy_choice_match_api(tmp_path, capsys):
    case = VECTORS["cases"][-1]
    arena = registry.create("connect-four")
    state = tmp_path / "state.json"
    state.write_text(json.dumps(serialize_state(arena.initial_state(1))))
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"history": case["history"]}))
    args = ["core", "prompt", "--game", "connect-four", "--state", str(state),
            "--history", str(history)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == make_prompt(case)
    assert main([*args, "--prompt-version", "eslams.core.prompt.v2"]) == 0
    assert json.loads(capsys.readouterr().out) == case["legacy_v2_package"]


def test_cli_history_envelope_rejects_unknown_fields(tmp_path, capsys):
    arena = registry.create("connect-four")
    state = tmp_path / "state.json"
    state.write_text(json.dumps(serialize_state(arena.initial_state(1))))
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"history": [], "private": "synthetic-rejected"}))
    assert main(["core", "prompt", "--game", "connect-four", "--state", str(state),
                 "--history", str(history)]) == 1
    assert "history" in capsys.readouterr().err
