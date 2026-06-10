from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.east_asian_board import GoArena, ShogiArena, XiangqiArena
from eslams.arenas.tile_card_games import BridgeArena, DouDizhuArena, MahjongArena
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

FINAL_CATALOG_ARENAS = {
    "bridge",
    "dou-dizhu",
    "go",
    "mahjong",
    "shogi",
    "xiangqi",
}


def test_final_catalog_arenas_are_registered() -> None:
    registered = set(registry.list())

    assert FINAL_CATALOG_ARENAS.issubset(registered)
    assert len(registered) >= 50


def test_go_two_passes_reaches_scored_terminal_state() -> None:
    arena = GoArena()
    state = arena.initial_state(seed=5)

    state = arena.apply_action(state, "player_1", "pass")
    state = arena.apply_action(state, "player_2", "pass")

    assert state.terminal is True
    assert state.outcome is not None
    assert state.outcome["reason"] == "two_passes"
    assert set(state.scores) == {"player_1", "player_2"}


def test_shogi_and_xiangqi_have_legal_opening_moves() -> None:
    for arena in (ShogiArena(), XiangqiArena()):
        state = arena.initial_state(seed=7)
        action = state.legal_actions_by_player[state.active_player][0]

        next_state = arena.apply_action(state, state.active_player, action)

        assert next_state.turn == 1
        assert next_state.active_player == "player_2"
        assert next_state.terminal is False


def test_mahjong_hides_other_hands_and_advances_draw_discard_cycle() -> None:
    arena = MahjongArena()
    state = arena.initial_state(seed=7)
    observation = arena.observation_for(state, "player_1")

    assert len(observation["hand"]) == 11
    assert state.public_state["hand_counts"] == {
        "player_1": 11,
        "player_2": 10,
        "player_3": 10,
        "player_4": 10,
    }
    assert "hand" not in state.public_state
    assert "wall" not in state.public_state

    action = state.legal_actions_by_player["player_1"][0]
    next_state = arena.apply_action(state, "player_1", action)

    assert next_state.active_player == "player_2"
    assert next_state.public_state["hand_counts"]["player_1"] == 10
    assert next_state.public_state["hand_counts"]["player_2"] == 11


def test_dou_dizhu_tracks_landlord_and_hidden_hand_counts() -> None:
    arena = DouDizhuArena()
    state = arena.initial_state(seed=7)
    landlord = state.public_state["landlord"]

    assert landlord == "player_2"
    assert state.public_state["hand_counts"][landlord] == 20
    assert "hand" not in state.public_state

    action = state.legal_actions_by_player[landlord][0]
    next_state = arena.apply_action(state, landlord, action)

    assert next_state.turn == 1
    assert next_state.public_state["hand_counts"][landlord] < 20
    assert next_state.public_state["history"][-1]["player"] == landlord


def test_bridge_follow_suit_state_uses_public_trick_and_private_hands() -> None:
    arena = BridgeArena()
    state = arena.initial_state(seed=7)

    assert state.active_player == "player_1"
    assert state.public_state["hand_counts"] == {
        "player_1": 13,
        "player_2": 13,
        "player_3": 13,
        "player_4": 13,
    }
    assert "hand" not in state.public_state

    action = state.legal_actions_by_player["player_1"][0]
    next_state = arena.apply_action(state, "player_1", action)

    assert next_state.public_state["current_trick"] == [
        {"player": "player_1", "card": action.removeprefix("play:")}
    ]
    assert next_state.public_state["hand_counts"]["player_1"] == 12
    assert next_state.active_player == "player_2"


def test_runner_generates_valid_artifacts_for_final_catalog_arenas(tmp_path: Path) -> None:
    for arena_id in sorted(FINAL_CATALOG_ARENAS):
        output_dir = tmp_path / arena_id
        arena = registry.create(arena_id)
        agents = {
            player_id: "random" if player_id == "player_1" else "first-legal"
            for player_id in arena.players
        }
        result = Runner().run(
            RunConfig(
                arena_id=arena_id,
                agents=agents,
                seed=17,
                max_turns=18,
                output_dir=output_dir,
            )
        )

        assert result.artifact_path.exists()
        assert result.trace_events
        assert ArtifactValidator().validate(result.artifact_path) == []
