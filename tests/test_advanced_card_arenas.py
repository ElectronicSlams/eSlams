from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.advanced_cards import (
    CribbageArena,
    EuchreArena,
    GinRummyArena,
    HanabiArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

ADVANCED_CARD_ARENAS = {
    "cribbage",
    "euchre",
    "gin-rummy",
    "hanabi",
}


def test_advanced_card_arenas_are_registered():
    assert ADVANCED_CARD_ARENAS.issubset(set(registry.list()))


def test_gin_rummy_hides_opponent_hand_and_detects_undercut():
    arena = GinRummyArena()
    state = arena._state(
        hands={
            "player_1": ["2C", "3C", "4C", "9D"],
            "player_2": ["5H", "6H", "7H", "8H"],
        },
        deck=["KC"],
        discard=["9S"],
        phase="discard",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    observation = arena.observation_for(state, "player_1")

    assert "5H" not in str(observation)
    assert "knock:9D" in state.legal_actions_by_player["player_1"]

    terminal = arena.apply_action(state, "player_1", "knock:9D")

    assert terminal.terminal is True
    assert terminal.outcome["reason"] == "undercut"
    assert terminal.outcome["winner"] == "player_2"


def test_euchre_left_bower_counts_as_trump():
    arena = EuchreArena()
    state = arena._state(
        hands={"player_1": ["JS"], "player_2": ["AC"]},
        trump="C",
        upcard="9C",
        phase="play",
        active="player_1",
        dealer="player_2",
        current_trick=[],
        tricks={"player_1": 0, "player_2": 0},
        passes=[],
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "play:JS")
    terminal = arena.apply_action(state, "player_2", "play:AC")

    assert terminal.terminal is True
    assert terminal.public_state["tricks"]["player_1"] == 1
    assert terminal.outcome["winner"] == "player_1"


def test_cribbage_scores_fifteens_and_pairs_after_discards():
    arena = CribbageArena()
    state = arena._state(
        hands={
            "player_1": ["5C", "5D", "10H", "KS", "2C", "3D"],
            "player_2": ["AC", "2D", "3H", "4S", "9C", "QD"],
        },
        discards={"player_1": [], "player_2": []},
        starter="5H",
        dealer="player_2",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )

    state = arena.apply_action(state, "player_1", "discard:2C,3D")
    terminal = arena.apply_action(state, "player_2", "discard:9C,QD")

    assert terminal.terminal is True
    assert terminal.outcome["hand_scores"]["player_1"] > terminal.outcome["hand_scores"]["player_2"]
    assert terminal.scores["player_1"] == 1.0


def test_hanabi_observation_shows_partner_hand_but_hides_own_cards():
    arena = HanabiArena()
    state = arena._state(
        hands={"player_1": ["R1", "B2"], "player_2": ["B1", "R2"]},
        deck=[],
        fireworks={"R": 0, "B": 0},
        discard=[],
        clues=8,
        lives=3,
        active="player_1",
        turn=0,
        seed=1,
        hints={"player_1": [[], []], "player_2": [[], []]},
        history=[],
        outcome=None,
    )

    observation = arena.observation_for(state, "player_1")

    assert observation["visible_partner_hand"] == ["B1", "R2"]
    assert "R1" not in str(observation)
    assert "play:0" in state.legal_actions_by_player["player_1"]

    next_state = arena.apply_action(state, "player_1", "play:0")

    assert next_state.public_state["fireworks"]["R"] == 1
    assert next_state.scores["player_1"] > 0


def test_runner_generates_valid_artifacts_for_advanced_card_arenas(tmp_path: Path):
    for arena_id in sorted(ADVANCED_CARD_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=73, max_turns=16, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
