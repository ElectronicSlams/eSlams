import json
from pathlib import Path

import pytest

from eslams.agents import FunctionAgent, MockProviderAgent
from eslams.arena import registry
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("action", [True, 3.0])
@pytest.mark.parametrize("policy", ["invalid-match", "forfeit", "fallback"])
def test_numeric_action_aliases_follow_illegal_action_policy(tmp_path: Path, action, policy):
    arena = registry.create("tic-tac-toe")
    state = arena.initial_state(1)
    assert arena.is_legal(state, "player_1", action) is False
    with pytest.raises(ValueError):
        arena.apply_action(state, "player_1", action)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path,
                                   agents={"player_1": FunctionAgent(lambda _: action)},
                                   on_illegal_action=policy, max_turns=1))
    assert result.score.match_valid_for_scoring is False
    assert result.score.illegal_action_count_by_player["player_1"] == 1
    assert result.score.agent_error_count_by_player["player_1"] == 0
    if policy == "invalid-match":
        assert result.trace_events == []
    elif policy == "forfeit":
        assert result.trace_events[0].event_type == "forfeit"
        assert result.score.winner == "player_2"
    else:
        assert result.trace_events[0].public["action"] == 0
        assert result.trace_events[0].public["action_provenance"] == "fallback_action"
        assert result.score.fallback_action_count_by_player["player_1"] == 1
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_rejected_provider_numeric_alias_never_becomes_an_applied_receipt(tmp_path, monkeypatch):
    provider = MockProviderAgent(scenario="success")
    original = provider.act

    def alias(request):
        response = original(request)
        return ActResponse(action=True, metadata=response.metadata)

    monkeypatch.setattr(provider, "act", alias)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path,
                                   agents={"player_1": provider}, max_turns=1,
                                   on_illegal_action="fallback"))
    receipts = [
        json.loads(line) for line in
        (result.artifact_path / "receipts/provider_receipts.jsonl").read_text().splitlines()
    ]
    assert len(receipts) == 1
    assert receipts[0]["action_applied"] is False
    assert receipts[0]["case_valid_for_scoring"] is False
    assert result.trace_events[0].public["action_provenance"] == "fallback_action"
    assert ArtifactValidator().validate(result.artifact_path) == []
