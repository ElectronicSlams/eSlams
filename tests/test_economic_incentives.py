import pytest

from eslams.arena import registry
from eslams.artifacts import ArtifactValidator
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


def test_auction_preserves_signed_incentives_neutral_allocation_and_score_winners(tmp_path):
    arena = registry.create("first-price-sealed-bid-auction")
    for seed in range(10):
        initial = arena.initial_state(seed)
        for first_bid in range(11):
            pending = arena.apply_action(initial, "player_1", first_bid)
            assert pending.public_state["revealed_bids"] == {}
            for second_bid in range(11):
                terminal = arena.apply_action(pending, "player_2", second_bid)
                outcome = terminal.outcome
                allocation = outcome["allocation_winner"]
                expected_allocation = arena.players[seed % 2] if first_bid == second_bid else (
                    "player_1" if first_bid > second_bid else "player_2"
                )
                assert allocation == expected_allocation
                for player, bid in zip(arena.players, (first_bid, second_bid)):
                    utility = outcome["valuations"][player] - bid if player == allocation else 0
                    assert outcome["utilities"][player] == utility
                    assert terminal.scores[player] == pytest.approx((utility + 10) / 20)
                    assert 0 <= terminal.scores[player] <= 1
                first, second = (terminal.scores[p] for p in arena.players)
                expected_winner = None if first == second else (
                    "player_1" if first > second else "player_2"
                )
                assert outcome["winner"] == expected_winner
    for seed, allocation in ((0, "player_1"), (5, "player_2")):
        state = arena.apply_action(arena.initial_state(seed), "player_1", 3)
        state = arena.apply_action(state, "player_2", 3)
        assert state.outcome["valuations"] == {"player_1": 6, "player_2": 6}
        assert state.outcome["allocation_winner"] == state.outcome["winner"] == allocation

    class FixedBid:
        id = "signed-utility-auction-fixture"
        version = "1"

        def act(self, request):
            return ActResponse(action=10 if request.turn_id == 0 else 9)

    agent = FixedBid()
    result = Runner().run(RunConfig(
        arena_id=arena.id, seed=0, agent_1=agent, agent_2=agent, output_dir=tmp_path,
    ))
    assert result.score.outcome["allocation_winner"] == "player_1"
    assert result.score.outcome["utilities"] == {"player_1": -4.0, "player_2": 0.0}
    assert result.score.scores_by_player == {"player_1": 0.3, "player_2": 0.5}
    assert result.score.winner == "player_2"
    assert result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_negotiation_enforces_reserves_without_creating_impossible_seed_classes(tmp_path):
    arena = registry.create("negotiation")
    for seed in range(9):
        initial = arena.initial_state(seed)
        low = arena.apply_action(initial, "player_1", "offer:20:1")
        assert "accept" not in low.legal_actions_by_player["player_2"]
        assert "reject" in low.legal_actions_by_player["player_2"]
        with pytest.raises(ValueError, match="illegal negotiation"):
            arena.apply_action(low, "player_2", "accept")
        # Meeting the accepter's reserve alone cannot bypass the proposer's reserve.
        high = arena.apply_action(initial, "player_1", "offer:100:1")
        assert "accept" in high.legal_actions_by_player["player_2"]
        no_deal = arena.apply_action(high, "player_2", "accept")
        assert no_deal.outcome["reason"] == "reserve_not_met"
        assert no_deal.outcome["utilities"] == {"player_1": 0, "player_2": 0}
        assert no_deal.scores == {"player_1": 0.0, "player_2": 0.0}
        feasible = []
        for offer in initial.legal_actions_by_player["player_1"]:
            proposed = arena.apply_action(initial, "player_1", offer)
            if "accept" not in proposed.legal_actions_by_player["player_2"]:
                continue
            settled = arena.apply_action(proposed, "player_2", "accept")
            if settled.outcome["reason"] == "accepted":
                feasible.append(offer)
                for player in arena.players:
                    assert settled.outcome["utilities"][player] >= (
                        initial.private_state_by_player[player]["reserve_share"]
                    )
        assert feasible, seed
        # The former 20-unit grid had no mutually feasible deal for seed % 3 == 2.
        if seed % 3 == 2:
            assert "offer:70:1" in feasible
        counter = arena.apply_action(low, "player_2", "offer:70:1")
        assert "accept" in counter.legal_actions_by_player["player_1"]
        assert arena.apply_action(counter, "player_1", "accept").outcome["reason"] == "accepted"

    class FeasibleDeal:
        id = "reserve-negotiation-fixture"
        version = "1"

        def act(self, request):
            return ActResponse(action="offer:70:1" if request.turn_id == 0 else "accept")

    agent = FeasibleDeal()
    result = Runner().run(RunConfig(
        arena_id=arena.id, seed=2, agent_1=agent, agent_2=agent, output_dir=tmp_path,
    ))
    assert result.score.outcome["reason"] == "accepted"
    assert result.score.outcome["utilities"] == {"player_1": 40.0, "player_2": 60.0}
    assert result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.artifact_path) == []
