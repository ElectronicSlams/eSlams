from pathlib import Path

from eslams.arenas import registry
from eslams.arenas.strategic_games import (
    BargainingArena,
    BlackjackArena,
    FirstPriceSealedBidAuctionArena,
    GoofspielArena,
    LiarsDiceArena,
    NegotiationArena,
)
from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner

STRATEGIC_ARENAS = {
    "bargaining",
    "blackjack",
    "first-price-sealed-bid-auction",
    "goofspiel",
    "liars-dice",
    "negotiation",
}


def test_strategic_arenas_are_registered():
    assert STRATEGIC_ARENAS.issubset(set(registry.list()))


def test_blackjack_reveals_dealer_hand_only_on_terminal():
    arena = BlackjackArena()
    state = arena.initial_state(3)

    assert len(state.public_state["dealer_hand"]) == 1
    assert set(state.scores) == {"player_1"}
    assert set(state.private_state_by_player) == {"player_1"}

    terminal = arena.apply_action(state, "player_1", "stand")

    assert terminal.terminal is True
    assert len(terminal.public_state["dealer_hand"]) >= 2
    assert set(terminal.scores) == {"player_1"}


def test_sealed_bid_hides_first_bid_until_terminal():
    arena = FirstPriceSealedBidAuctionArena()
    state = arena.initial_state(4)
    state = arena.apply_action(state, "player_1", 7)

    assert state.public_state["revealed_bids"] == {}
    assert state.private_state_by_player["player_1"]["pending_bid"] == 7

    terminal = arena.apply_action(state, "player_2", 6)

    assert terminal.terminal is True
    assert terminal.outcome["bids"] == {"player_1": 7, "player_2": 6}


def test_goofspiel_awards_prize_after_both_bids():
    arena = GoofspielArena()
    state = arena.initial_state(1)
    prize = state.public_state["current_prize"]
    state = arena.apply_action(state, "player_1", 5)
    state = arena.apply_action(state, "player_2", 1)

    assert state.public_state["round_history"][0]["winner"] == "player_1"
    assert state.public_state["points"]["player_1"] == prize


def test_liars_dice_challenge_reveals_dice():
    arena = LiarsDiceArena()
    state = arena.initial_state(1)
    state = arena.apply_action(state, "player_1", state.legal_actions_by_player["player_1"][0])
    terminal = arena.apply_action(state, "player_2", "challenge")

    assert terminal.terminal is True
    assert terminal.public_state["revealed_dice"]
    assert terminal.outcome["reason"] == "challenge_resolved"


def test_bargaining_and_negotiation_accept_offers():
    bargaining = BargainingArena()
    bargain_state = bargaining.initial_state(1)
    bargain_state = bargaining.apply_action(bargain_state, "player_1", "offer:60")
    bargain_state = bargaining.apply_action(bargain_state, "player_2", "accept")

    assert bargain_state.terminal is True
    assert bargain_state.scores["player_1"] == 0.6

    negotiation = NegotiationArena()
    negotiation_state = negotiation.initial_state(1)
    negotiation_state = negotiation.apply_action(negotiation_state, "player_1", "offer:60:2")
    negotiation_state = negotiation.apply_action(negotiation_state, "player_2", "accept")

    assert negotiation_state.terminal is True
    assert negotiation_state.outcome["price"] == 60


def test_bargaining_reserves_control_accept_legality():
    arena = BargainingArena()
    state = arena.initial_state(1)
    state = arena.apply_action(state, "player_1", "offer:90")

    assert "accept" not in state.legal_actions_by_player["player_2"]
    assert "reject" in state.legal_actions_by_player["player_2"]


def test_runner_generates_valid_artifacts_for_strategic_arenas(tmp_path: Path):
    for arena_id in sorted(STRATEGIC_ARENAS):
        output_dir = tmp_path / arena_id
        result = Runner().run(
            RunConfig(arena_id=arena_id, seed=29, max_turns=10, output_dir=output_dir)
        )
        assert result.artifact_path.exists()
        assert ArtifactValidator().validate(result.artifact_path) == []
