import random

import chess
import pytest

from eslams.arenas.advanced_cards import _cribbage_hand_score, _cribbage_outcome
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
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


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
