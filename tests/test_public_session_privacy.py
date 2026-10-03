import pytest

from eslams.arena import registry
from eslams.arena_transport import (
    deserialize_session_state,
    legal_actions_page,
    start_session,
    step_session,
)


@pytest.mark.parametrize("game", ["mahjong", "hearts", "bridge", "spades", "dou-dizhu"])
def test_model_hands_are_absent_from_public_and_paginated_session_actions(game):
    arena = registry.create(game)
    players = {player: {"kind": "model" if player == "player_1" else "human"}
               for player in arena.players}
    started = start_session(game, None, 3, players)
    assert started["legal_actions"] == []
    assert started["legal_action_descriptors"] == []
    assert started["total_legal_actions"] == 0
    assert legal_actions_page(started["session_state"], "player_1")["rows"] == []
    state = deserialize_session_state(started["session_state"])
    assert state.legal_actions_by_player["player_1"]  # trusted runner still has actions
    assert "legal_actions_by_player" not in state.public_view()


@pytest.mark.parametrize("game", ["hearts", "bridge", "spades"])
def test_step_to_model_seat_does_not_publish_its_private_actions(game):
    arena = registry.create(game)
    players = {player: {"kind": "human" if player == "player_1" else "model"}
               for player in arena.players}
    started = start_session(game, None, 3, players)
    stepped = step_session(started["session_state"], "player_1", started["legal_actions"][0])
    assert stepped["accepted"] is True
    assert stepped["next_actor_kind"] == "model"
    assert stepped["legal_actions"] == []
    assert stepped["legal_action_descriptors"] == []
    assert stepped["total_legal_actions"] == 0
    assert legal_actions_page(stepped["session_state"], stepped["active_player"])["rows"] == []
