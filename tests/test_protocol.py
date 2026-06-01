from eslams.protocol import PROTOCOL_VERSION, ActRequest, ActResponse


def test_act_request_round_trip():
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": "run_1",
        "episode_id": "episode_001",
        "turn_id": 1,
        "arena": {"id": "connect-four", "version": "1.0.0"},
        "agent": {"id": "agent", "version": "1"},
        "active_player": "player_1",
        "observation": {"board": []},
        "legal_actions": [0],
        "action_schema": {"type": "integer"},
        "history": [],
        "time_budget_ms": 1000,
        "memory_policy": "current_observation_plus_public_history",
        "metadata": {},
    }
    request = ActRequest.from_mapping(payload)
    assert request.to_dict() == payload


def test_act_response_accepts_required_action_only():
    response = ActResponse.from_mapping({"action": "e2e4"})
    assert response.to_dict() == {"action": "e2e4", "metadata": {}}
