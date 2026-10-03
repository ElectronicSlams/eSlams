import json

import pytest

from eslams.agents import FunctionAgent
from eslams.arena_transport import start_session, step_session
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner

SEALED_ARENAS = ["rock-paper-scissors", "prisoners-dilemma",
                 "first-price-sealed-bid-auction", "goofspiel"]


@pytest.mark.parametrize("game", SEALED_ARENAS)
def test_sealed_commitments_stay_out_of_opponent_history_and_public_artifacts(tmp_path, game):
    requests = []

    def act(request):
        requests.append(request)
        return ActResponse(action=request.legal_actions[0],
                           public_explanation="private commitment explanation")

    agents = {player: FunctionAgent(act) for player in ("player_1", "player_2")}
    result = Runner().run(RunConfig(arena_id=game, agents=agents, output_dir=tmp_path))
    assert requests[1].history == []
    assert result.trace_events[0].public["action"] is None
    assert result.trace_events[0].public["public_explanation"] is None
    assert result.trace_events[0].auditor["action"] == requests[0].legal_actions[0]
    assert result.replay_events[1].action is None
    assert result.replay_events[1].public_reasoning_ref is None
    assert result.replay_events[2].action == requests[1].legal_actions[0]
    if game == "goofspiel":
        assert len(requests[2].history) == 2
        assert requests[3].history == requests[2].history
        assert all("reveal_turn" not in row for row in requests[2].history)
        assert result.replay_events[3].action is None
    public_rows = [json.loads(line) for line in
                   (result.artifact_path / "traces/public_trace.jsonl").read_text().splitlines()]
    assert public_rows[0]["action"] is None
    assert ArtifactValidator().validate(result.artifact_path) == []


@pytest.mark.parametrize("game", SEALED_ARENAS)
def test_session_events_and_display_frames_hide_commitments_until_reveal(game):
    players = {player: {"kind": "human"} for player in ("player_1", "player_2")}
    start = start_session(game, None, 1, players)
    committed = step_session(start["session_state"], "player_1", start["legal_actions"][0])
    assert committed["accepted"] is True
    assert committed["display_frame"]["action_label"] is None
    assert all(event["action"] is None and event["action_label"] is None
               for event in committed["events"])
    revealed = step_session(committed["session_state"], "player_2", committed["legal_actions"][0])
    assert revealed["accepted"] is True
    assert revealed["events"][0]["action"] == committed["legal_actions"][0]
