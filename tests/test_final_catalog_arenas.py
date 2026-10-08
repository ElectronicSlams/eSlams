import json
from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.east_asian_board import GoArena, ShogiArena, XiangqiArena
from eslams.arenas.tile_card_games import BridgeArena, DouDizhuArena, MahjongArena
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


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
    # One shared artifact contract check replaces repeated family smoke tests,
    # preserving each family's seed, horizon and seat policy. Rule/privacy
    # assertions stay in their dedicated tests.
    cases = [
        ("alien-shooter", 67, 16),
        ("backgammon", 79, 18),
        ("bargaining", 29, 10),
        ("battleship", 31, 12),
        ("bipedal-walker", 79, 18),
        ("blackjack", 29, 10),
        ("boxing-style-arena", 67, 16),
        ("bridge", 17, 18),
        ("car-racing", 79, 18),
        ("cartpole", 67, 16),
        ("checkers", 17, 8),
        ("chess", 5, 1),
        ("cliff-walking", 31, 12),
        ("connect-four", 7, None),
        ("crazy-eights", 41, 12),
        ("cribbage", 73, 16),
        ("dou-dizhu", 17, 18),
        ("euchre", 73, 16),
        ("first-price-sealed-bid-auction", 29, 10),
        ("frozen-lake", 31, 12),
        ("gin-rummy", 73, 16),
        ("go", 17, 18),
        ("gomoku", 5, 4),
        ("goofspiel", 29, 10),
        ("hanabi", 73, 16),
        ("hearts", 41, 12),
        ("hex", 5, 4),
        ("ice-hockey-style-arena", 67, 16),
        ("leduc-holdem", 53, 16),
        ("liars-dice", 29, 10),
        ("limit-texas-holdem", 53, 16),
        ("lunar-lander", 79, 18),
        ("mahjong", 17, 18),
        ("mancala", 17, 8),
        ("mountain-car", 67, 16),
        ("negotiation", 29, 10),
        ("nine-mens-morris", 53, 16),
        ("no-limit-texas-holdem", 53, 16),
        ("othello", 5, 4),
        ("paddle-ball", 67, 16),
        ("pentago", 17, 8),
        ("prisoners-dilemma", 17, 8),
        ("rock-paper-scissors", 17, 8),
        ("shedding-card-game", 41, 12),
        ("shogi", 17, 18),
        ("spades", 41, 12),
        ("taxi", 31, 12),
        ("tic-tac-toe", 3, None),
        ("ultimate-tic-tac-toe", 17, 8),
        ("xiangqi", 17, 18),
    ]
    assert {case[0] for case in cases} == set(registry.list())
    for arena_id, seed, max_turns in cases:
        arena = registry.create(arena_id)
        agents = {
            player: (
                "first-legal"
                if "holdem" in arena_id
                else "random"
                if player == "player_1"
                else "first-legal"
            )
            for player in arena.players
        }
        result = Runner().run(
            RunConfig(
                arena_id=arena_id,
                agents=agents,
                seed=seed,
                max_turns=max_turns,
                output_dir=tmp_path / arena_id,
            )
        )
        assert result.artifact_path.exists(), arena_id
        assert result.artifact_path.name.endswith(".eslams.d"), arena_id
        assert result.score.run_id == result.run_id, arena_id
        assert result.trace_events, arena_id
        assert result.replay_events[0].action is None, arena_id
        if arena_id in ("tic-tac-toe", "connect-four"):
            assert result.replay_events[-1].terminal is True, arena_id
        assert ArtifactValidator().validate(result.artifact_path) == [], arena_id
        replay = result.expanded_path / "replay/index.html"
        assert "eSlams Replay" in replay.read_text(encoding="utf-8"), arena_id
        manifest = json.loads((result.expanded_path / "manifest.json").read_text(encoding="utf-8"))
        assert any(row["path"] == "replay/index.html" for row in manifest["files"]), arena_id
