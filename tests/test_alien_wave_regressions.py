from itertools import combinations

from eslams.arenas.control_arcade import AlienShooterArena
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


def tracking_action(observation):
    ship = observation["player_x"]
    target = min((a[0] for a in observation["aliens"]), key=lambda x: (abs(x - ship), x))
    return "fire" if target == ship else "left" if target < ship else "right"


def test_hits_resolve_during_both_projectile_advance_and_alien_descent():
    arena = AlienShooterArena()
    state = arena._state(
        player_x=3, aliens=[(2, 3), (3, 4), (5, 5)],
        bullets=[(2, 2), (3, 2), (3, 2)], destroyed=4,
        turn=arena.descent_interval - 1, seed=0, history=[], outcome=None,
    )
    next_state = arena.apply_action(state, "player_1", "stay")
    assert next_state.public_state["destroyed"] == 6
    assert next_state.public_state["aliens"] == [[5, 4]]
    assert next_state.public_state["bullets"] == [[3, 3]]
    assert next_state.scores == {"player_1": 6 / 7}
    assert not next_state.terminal
    assert state.public_state["destroyed"] == 4
    assert state.metadata["aliens"] == [(2, 3), (3, 4), (5, 5)]


def test_every_initial_formation_has_a_public_policy_completion_path(tmp_path):
    arena = AlienShooterArena()
    count = 0
    maximum_turns = 0
    for top in combinations(range(7), 4):
        for bottom in combinations(range(7), 3):
            # These 35 x 35 formations exhaust the seeded initialization support.
            state = arena._state(
                player_x=3, aliens=[*((x, 5) for x in top), *((x, 4) for x in bottom)],
                bullets=[], destroyed=0, turn=0, seed=0, history=[], outcome=None,
            )
            while not state.terminal:
                observation = arena.observation_for(state, "player_1")
                assert observation["descent_interval"] == 12
                state = arena.apply_action(state, "player_1", tracking_action(observation))
                assert not (set(map(tuple, state.public_state["aliens"]))
                            & set(map(tuple, state.public_state["bullets"])))
                assert state.public_state["destroyed"] + len(state.public_state["aliens"]) == 7
            count += 1
            maximum_turns = max(maximum_turns, state.turn)
            assert state.outcome["reason"] == "wave_cleared", (top, bottom)
            assert state.outcome["success"] is True
            assert state.scores == {"player_1": 1.0}
    assert count == 1225
    assert maximum_turns < 3 * arena.descent_interval < arena.max_turns

    class TrackingAgent:
        id = "public-alien-tracker"
        version = "1"

        def act(self, request):
            return ActResponse(action=tracking_action(request.observation))

    result = Runner().run(RunConfig(
        arena_id=arena.id, seed=0, agent_1=TrackingAgent(), output_dir=tmp_path,
    ))
    assert result.score.outcome["reason"] == "wave_cleared"
    assert result.score.outcome["success"] is True
    assert result.score.winner is None
    assert result.score.scores_by_player == {"player_1": 1.0}
    assert result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.artifact_path) == []
