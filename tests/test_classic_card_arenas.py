from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.classic_cards import (
    CrazyEightsArena,
    HeartsArena,
    SheddingCardGameArena,
    SpadesArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

CLASSIC_CARD_ARENAS = {
    "crazy-eights",
    "hearts",
    "shedding-card-game",
    "spades",
}


def test_classic_card_arenas_are_registered():
    assert CLASSIC_CARD_ARENAS.issubset(set(registry.list()))


def test_shedding_card_game_hides_opponent_hand_and_allows_matching_play():
    arena = SheddingCardGameArena()
    state = arena._state(
        hands={"player_1": ["5H"], "player_2": ["KC"]},
        deck=[],
        discard="9H",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    observation = arena.observation_for(state, "player_1")

    assert observation["hand"] == ["5H"]
    assert observation["hand_counts"] == {"player_1": 1, "player_2": 1}
    assert "KC" not in str(observation)
    assert state.legal_actions_by_player["player_1"] == ["play:5H"]

    terminal = arena.apply_action(state, "player_1", "play:5H")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "empty_hand"


def test_crazy_eights_allows_eight_as_wild_card():
    arena = CrazyEightsArena()
    state = arena._state(
        hands={"player_1": ["8C"], "player_2": ["KC"]},
        deck=[],
        discard="9H",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    assert state.legal_actions_by_player["player_1"] == ["play:8C"]
    terminal = arena.apply_action(state, "player_1", "play:8C")
    assert terminal.scores["player_1"] == 1.0


def test_crazy_eights_pass_does_not_block_when_opponent_has_wild_eight():
    arena = CrazyEightsArena()
    state = arena._state(
        hands={"player_1": ["KC"], "player_2": ["8C"]},
        deck=[],
        discard="9H",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    next_state = arena.apply_action(state, "player_1", "pass")

    assert next_state.terminal is False
    assert next_state.legal_actions_by_player["player_2"] == ["play:8C"]


def test_hearts_follow_suit_and_assign_penalty_to_trick_winner():
    arena = HeartsArena()
    state = arena._state(
        hands={"player_1": ["2H"], "player_2": ["3H"]},
        active="player_1",
        turn=0,
        seed=1,
        current_trick=[],
        penalties={"player_1": 0, "player_2": 0},
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "play:2H")

    assert state.legal_actions_by_player["player_2"] == ["play:3H"]

    terminal = arena.apply_action(state, "player_2", "play:3H")

    assert terminal.terminal is True
    assert terminal.public_state["penalties"]["player_2"] == 2
    assert terminal.outcome["winner"] == "player_1"


def test_hearts_treats_ace_as_high_card():
    arena = HeartsArena()
    state = arena._state(
        hands={"player_1": ["AH"], "player_2": ["KH"]},
        active="player_1",
        turn=0,
        seed=1,
        current_trick=[],
        penalties={"player_1": 0, "player_2": 0},
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "play:AH")
    terminal = arena.apply_action(state, "player_2", "play:KH")

    assert terminal.public_state["trick_history"][0]["winner"] == "player_1"
    assert terminal.public_state["penalties"]["player_1"] == 2
    assert terminal.outcome["winner"] == "player_2"


def test_spades_trump_wins_trick():
    arena = SpadesArena()
    state = arena._state(
        hands={"player_1": ["AH"], "player_2": ["2S"]},
        active="player_1",
        turn=0,
        seed=1,
        current_trick=[],
        tricks={"player_1": 0, "player_2": 0},
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "play:AH")
    terminal = arena.apply_action(state, "player_2", "play:2S")

    assert terminal.terminal is True
    assert terminal.public_state["tricks"]["player_2"] == 1
    assert terminal.scores["player_2"] == 1.0


def test_spades_treats_ace_as_high_card():
    arena = SpadesArena()
    state = arena._state(
        hands={"player_1": ["KS"], "player_2": ["AS"]},
        active="player_1",
        turn=0,
        seed=1,
        current_trick=[],
        tricks={"player_1": 0, "player_2": 0},
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "play:KS")
    terminal = arena.apply_action(state, "player_2", "play:AS")

    assert terminal.public_state["tricks"]["player_2"] == 1
    assert terminal.scores["player_2"] == 1.0


def test_runner_generates_valid_artifacts_for_classic_card_arenas(tmp_path: Path):
    for arena_id in sorted(CLASSIC_CARD_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=41, max_turns=12, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
