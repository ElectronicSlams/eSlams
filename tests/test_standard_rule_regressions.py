import random

import chess
import pytest

from eslams.arena import registry
from eslams.arenas.advanced_cards import (
    CribbageArena,
    GinRummyArena,
    _cribbage_hand_score,
    _cribbage_outcome,
    _deadwood,
    _gin_legal,
)
from eslams.arenas.chess import ChessArena
from eslams.arenas.othello import OthelloArena, _legal_actions
from eslams.arenas.pentago import PentagoArena
from eslams.arenas.poker import (
    LeducHoldemArena,
    LimitTexasHoldemArena,
    NoLimitTexasHoldemArena,
    _winner_scores,
)
from eslams.artifacts import ArtifactValidator
from eslams.catalogue import game_catalogue_rows
from eslams.game_metadata import SOLO_SCORE_GAMES
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


def test_solo_results_and_competitive_arcade_topology_use_only_actual_seats(tmp_path):
    rows = {r["game_id"]: r for r in game_catalogue_rows()}
    for game in sorted(SOLO_SCORE_GAMES):
        arena = registry.create(game)
        assert arena.players == ("player_1",)
        result = Runner().run(
            RunConfig(arena_id=game, agent_1="first-legal", output_dir=tmp_path / game)
        )
        assert result.score.winner is None
        assert result.score.outcome["winner"] is None
        assert isinstance(result.score.outcome["success"], bool)
        assert set(result.score.scores_by_player) == {"player_1"}
        assert all(set(e.scores) == {"player_1"} for e in result.replay_events)
        assert ArtifactValidator().validate(result.artifact_path) == []
    for game in ("boxing-style-arena", "ice-hockey-style-arena"):
        topology = rows[game]["topology"]
        assert topology["mode"] == "head_to_head"
        assert topology["controlledPlayers"] == ["player_1", "player_2"]
        arena = registry.create(game)
        state = arena.initial_state(1)
        state = arena.apply_action(state, "player_1", state.legal_actions_by_player["player_1"][0])
        assert state.active_player == "player_2"
        assert state.legal_actions_by_player["player_2"]
    for game in ("goofspiel", "mahjong"):
        assert rows[game]["topology"]["drawAllowed"] is True
        assert rows[game]["resultContract"]["drawAllowed"] is True
    for game in ("backgammon", "battleship", "crazy-eights"):
        assert rows[game]["fidelity"] == "compact"


def test_cribbage_paired_seeds_balance_the_same_deal_and_report_each_seat(tmp_path):
    arena = CribbageArena()
    for even in (-2, 0, 2, 100):
        left = arena.initial_state(even)
        right = arena.initial_state(even + 1)
        assert left.public_state["dealer"] == "player_1"
        assert right.public_state["dealer"] == "player_2"
        assert left.active_player == "player_2" and right.active_player == "player_1"
        assert left.private_state_by_player == right.private_state_by_player
        assert left.public_state["starter"] == right.public_state["starter"]
        assert left.state_hash == arena.initial_state(even).state_hash
    for seed in (0, 1):
        result = Runner().run(RunConfig(arena_id="cribbage", seed=seed, output_dir=tmp_path))
        assert result.score.metrics["evaluated_player"] == "player_1"
        assert result.score.primary_score == result.score.scores_by_player["player_1"]
        assert set(result.score.scores_by_player) == {"player_1", "player_2"}
        assert ArtifactValidator().validate(result.artifact_path) == []


def test_gin_deadwood_uses_ace_low_and_optimal_disjoint_melds():
    for hand, expected in (
        (["AH", "2H", "3H", "9C", "9D", "KS", "QD"], 38),
        (["QH", "KH", "AH", "9C", "8D", "7S", "6D"], 51),
        (["5H", "5D", "5S", "3H", "4H", "KC", "QD"], 27),
        (["3H", "4H", "5H", "5D", "5S", "6H", "7H"], 10),
        (["3H", "4H", "5H", "5D", "5S", "6H", "7H", "5C"], 0),
        ([], 0),
    ):
        assert _deadwood(hand) == expected
        assert _deadwood(list(reversed(hand))) == expected
    # The old union-of-melds count was 10, allowing an illegal knock here.
    hand = ["5H", "5D", "5S", "3H", "4H", "2C", "8C", "KH"]
    assert "knock:KH" not in _gin_legal(hand, ["AS"], ["AC"], "discard")


def test_gin_stock_exhaustion_waits_for_discard_and_cancels_without_points(tmp_path):
    class StockAgent:
        id = "stock-exhaustion-fixture"
        version = "1"

        def act(self, request):
            action = (
                "draw:deck"
                if "draw:deck" in request.legal_actions
                else next(a for a in request.legal_actions if a.startswith("discard:"))
            )
            return ActResponse(action=action)

    result = Runner().run(
        RunConfig(
            arena_id="gin-rummy",
            agent_1=StockAgent(),
            agent_2=StockAgent(),
            output_dir=tmp_path,
        )
    )
    assert result.score.outcome == {"winner": None, "reason": "stock_exhausted"}
    assert result.score.scores_by_player == {"player_1": 0.0, "player_2": 0.0}
    assert result.replay_events[-1].action.startswith("discard:")
    assert result.replay_events[-1].public_state["deck_count"] == 2
    assert result.replay_events[-1].public_state["hand_counts"] == {
        "player_1": 7,
        "player_2": 7,
    }
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid and report.deterministic_replay.verified


def test_gin_can_knock_after_drawing_the_third_last_stock_card():
    arena = GinRummyArena()
    state = arena._state(
        hands={
            "player_1": ["AH", "2H", "3H", "4H", "5H", "6H", "KC"],
            "player_2": ["AD", "3C", "5S", "7D", "9C", "JS", "KD"],
        },
        deck=["7H", "AC", "AS"],
        discard=["QD"],
        phase="draw",
        active="player_1",
        turn=0,
        seed=1,
        history=[],
        outcome=None,
    )
    state = arena.apply_action(state, "player_1", "draw:deck")
    assert not state.terminal
    assert "knock:KC" in state.legal_actions_by_player["player_1"]
    terminal = arena.apply_action(state, "player_1", "knock:KC")
    assert terminal.outcome["winner"] == "player_1"
    assert terminal.outcome["deadwood"]["player_1"] == 0


def test_cribbage_show_counts_ace_low_multiplicity_flush_and_nobs():
    cases = [
        (["AC", "2D", "3H", "9S", "KC"], 7),
        (["QC", "KD", "AH", "7S", "2C"], 0),
        (["3C", "4D", "5H", "5S", "KC"], 12),
        (["JH", "2D", "6S", "8C", "4H"], 1),
        (["5C", "5D", "5H", "JS", "5S"], 29),
        (["AC", "2D", "3H", "4S", "KC"], 8),
    ]
    for cards, score in cases:
        assert _cribbage_hand_score(cards) == score, cards
    cards = ["2C", "5C", "9C", "KC", "3D"]
    assert _cribbage_hand_score(cards) == 8
    assert _cribbage_hand_score(cards, crib=True) == 4
    assert _cribbage_hand_score(["2C", "5C", "9C", "KC", "3C"], crib=True) == 9
    with pytest.raises(ValueError, match="four cards"):
        _cribbage_hand_score(["AC"])
    outcome = _cribbage_outcome(
        {"player_1": ["AC", "2D", "3H", "9S"], "player_2": ["QD", "KH", "AS", "7S"]},
        {"player_1": ["2C", "5C"], "player_2": ["9C", "KC"]},
        "3D",
        "player_2",
    )
    assert outcome["hand_scores"]["player_2"] == (
        _cribbage_hand_score(["QD", "KH", "AS", "7S", "3D"])
        + _cribbage_hand_score(cards, crib=True)
    )

    # Retained assertions from test_cribbage_scores_fifteens_and_pairs_after_discards.
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


def test_pentago_placement_win_precedes_destructive_rotation():
    arena = PentagoArena()
    state = arena.initial_state(1)
    for action in (
        "0:3:cw",
        "35:3:cw",
        "1:3:cw",
        "34:3:cw",
        "2:3:cw",
        "33:3:cw",
        "3:3:cw",
        "29:3:cw",
    ):
        state = arena.apply_action(state, state.active_player, action)
    for action in ("4:0:cw", "4:3:cw"):
        terminal = arena.apply_action(state, "player_1", action)
        assert terminal.outcome == {"winner": "player_1", "reason": "five_in_a_row"}
        assert terminal.public_state["board"][0][:5] == ["B"] * 5

    # Retained assertions from test_pentago_rotates_quadrant.
    arena = PentagoArena()
    state = arena.initial_state(1)

    next_state = arena.apply_action(state, "player_1", "0:0:cw")

    assert next_state.public_state["board"][0][2] == "B"
    assert next_state.active_player == "player_2"


def test_othello_passes_never_finish_an_incomplete_board():
    arena = OthelloArena()
    for seed in (134, 0, 12, 57):
        rng = random.Random(seed)
        state = arena.initial_state(seed)
        while not state.terminal:
            actions = arena.legal_actions_for(state, state.active_player)
            assert actions
            state = arena.apply_action(state, state.active_player, rng.choice(actions))
        board = state.public_state["board"]
        assert not _legal_actions(board, "B") and not _legal_actions(board, "W")
        assert state.outcome["reason"] == "finished"
        assert state.turn <= arena.max_turns
        if seed == 134:
            assert state.turn > 64

    # Retained assertions from test_othello_initial_move_flips_disc.
    arena = OthelloArena()
    state = arena.initial_state(7)

    assert sorted(state.legal_actions_by_player["player_1"]) == [[2, 3], [3, 2], [4, 5], [5, 4]]

    next_state = arena.apply_action(state, "player_1", [2, 3])

    assert next_state.public_state["board"][2][3] == "B"
    assert next_state.public_state["board"][3][3] == "B"
    assert next_state.active_player == "player_2"


def test_chess_claimable_draw_does_not_preempt_checkmate():
    arena = ChessArena()
    state = arena._state(
        board=chess.Board("7k/8/1n4K1/8/8/8/8/R7 b - - 98 99"),
        turn=0,
        seed=0,
        outcome=None,
    )
    state = arena.apply_action(state, "player_2", "b6c4")
    assert not state.terminal
    assert "claim-draw:a1a2" in arena.legal_actions_for(state, "player_1")
    assert "claim-draw:a1a8" not in arena.legal_actions_for(state, "player_1")
    assert "claim-draw:a1a2" not in state.public_state["legal_uci"]
    mate = arena.apply_action(state, "player_1", "a1a8")
    assert mate.outcome == {"winner": "player_1", "reason": "checkmate"}
    claim = arena.apply_action(state, "player_1", "claim-draw:a1a2")
    assert claim.outcome == {"winner": None, "reason": "fifty_moves"}
    assert claim.public_state["fen"] == state.public_state["fen"]
    with pytest.raises(ValueError, match="illegal"):
        arena.apply_action(arena.initial_state(1), "player_1", "claim-draw")


def test_chess_repetition_requires_a_claim_until_fivefold():
    arena = ChessArena()
    state = arena.initial_state(0)
    for _ in range(4):
        for action in ("g1f3", "g8f6", "f3g1", "f6g8"):
            state = arena.apply_action(state, state.active_player, action)
        if state.turn == 8:
            assert not state.terminal
            claim = arena.apply_action(state, state.active_player, "claim-draw")
            assert claim.outcome == {"winner": None, "reason": "threefold_repetition"}
            assert not claim.public_state["legal_uci"]
    assert state.outcome == {"winner": None, "reason": "fivefold_repetition"}


def test_chess_automatic_seventyfive_move_draw_keeps_mate_precedence():
    arena = ChessArena()
    for fen, move, reason in (
        ("7k/8/6K1/8/2n5/8/8/R7 w - - 149 100", "a1a8", "checkmate"),
        ("7k/8/6K1/8/2n5/8/8/R7 w - - 149 100", "a1a2", "seventyfive_moves"),
    ):
        state = arena._state(board=chess.Board(fen), turn=0, seed=0, outcome=None)
        terminal = arena.apply_action(state, state.active_player, move)
        assert terminal.outcome["reason"] == reason


def test_chess_draw_claim_replays_as_a_valid_artifact(tmp_path):
    class RepetitionAgent:
        id = "repetition-fixture"
        version = "1"

        def act(self, request):
            claims = [a for a in request.legal_actions if a.startswith("claim-draw")]
            if claims:
                return ActResponse(action=claims[0])
            cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
            return ActResponse(action=cycle[request.turn_id % 4])

    result = Runner().run(
        RunConfig(
            arena_id="chess",
            agent_1=RepetitionAgent(),
            agent_2=RepetitionAgent(),
            output_dir=tmp_path,
        )
    )
    assert result.score.outcome == {"winner": None, "reason": "threefold_repetition"}
    assert result.score.match_valid_for_scoring
    assert result.replay_events[-1].action.startswith("claim-draw")
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid and report.deterministic_replay.verified


def test_poker_only_tied_best_hands_share_showdown_score():
    outcome = {
        "winner": None,
        "reason": "showdown",
        "folded": [],
        "hand_values": {
            "player_1": (1, [5]),
            "player_2": (1, [5]),
            "player_3": (0, [2]),
            "player_4": (0, [1]),
        },
    }
    assert _winner_scores(outcome) == {
        "player_1": 0.5,
        "player_2": 0.5,
        "player_3": 0.0,
        "player_4": 0.0,
    }
    for arena, seed in (
        (LimitTexasHoldemArena(), 4),
        (NoLimitTexasHoldemArena(), 4),
        (LeducHoldemArena(), 12),
    ):
        rng = random.Random(seed)
        state = arena.initial_state(seed)
        while not state.terminal:
            legal = arena.legal_actions_for(state, state.active_player)
            action = rng.choice([a for a in legal if a in ("check", "call")] or legal)
            state = arena.apply_action(state, state.active_player, action)
        values = state.outcome["hand_values"]
        best = max(values.values())
        winners = [p for p, value in values.items() if value == best]
        assert len(winners) == 2
        assert all(
            state.scores[p] == (1 / len(winners) if p in winners else 0) for p in arena.players
        )


def test_poker_fold_closes_matched_round_without_an_extra_bet():
    for arena in (LeducHoldemArena(), LimitTexasHoldemArena(), NoLimitTexasHoldemArena()):
        state = arena.initial_state(4)
        for action in (
            "bet:2" if isinstance(arena, NoLimitTexasHoldemArena) else "bet",
            "fold",
            "call",
        ):
            state = arena.apply_action(state, state.active_player, action)
            assert state.public_state["street"] == "preflop"
        state = arena.apply_action(state, state.active_player, "fold")
        assert state.public_state["street"] == (
            "board" if isinstance(arena, LeducHoldemArena) else "flop"
        )
        assert len(state.public_state["board"]) == (1 if isinstance(arena, LeducHoldemArena) else 3)
        assert not state.terminal
