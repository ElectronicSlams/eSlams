from eslams.arenas.chess import ChessArena


def test_chess_observation_includes_rule_derived_move_context():
    arena = ChessArena()
    state = arena.initial_state(seed=1)
    observation = arena.observation_for(state, "player_1")

    e2e4 = next(move for move in observation["legal_moves"] if move["uci"] == "e2e4")

    assert observation["fen"].startswith("rnbqkbnr/pppppppp")
    assert observation["side_to_move"] == "white"
    assert observation["side_to_move_player"] == "player_1"
    assert observation["fullmove_number"] == 1
    assert observation["halfmove_clock"] == 0
    assert observation["san_history"] == []
    assert observation["last_move_uci"] is None
    assert observation["last_move_san"] is None
    assert e2e4 == {
        "uci": "e2e4",
        "san": "e4",
        "capture": False,
        "check": False,
        "checkmate": False,
        "promotion": False,
        "castle": False,
        "en_passant": False,
    }
    assert "e4" in observation["legal_san"]
    assert observation["material_balance"]["white_minus_black"] == 0
    assert observation["king_status"] == {
        "in_check": False,
        "checking_pieces": [],
        "legal_evasions": [],
    }
    assert observation["draw_claims"]["can_claim_threefold_repetition"] is False
    assert observation["draw_claims"]["can_claim_fifty_move_rule"] is False


def test_chess_san_history_and_last_move_survive_state_transition():
    arena = ChessArena()
    state = arena.initial_state(seed=1)

    state = arena.apply_action(state, "player_1", "e2e4")
    observation = arena.observation_for(state, "player_2")

    assert observation["side_to_move"] == "black"
    assert observation["side_to_move_player"] == "player_2"
    assert observation["san_history"] == ["e4"]
    assert observation["last_move_uci"] == "e2e4"
    assert observation["last_move_san"] == "e4"
    assert "e7e5" in observation["legal_uci"]
    assert "e5" in observation["legal_san"]


def test_chess_terminal_summary_exposes_checkmate_reason_and_final_validation():
    arena = ChessArena()
    state = arena.initial_state(seed=1)
    for action in ("f2f3", "e7e5", "g2g4", "d8h4"):
        state = arena.apply_action(state, state.active_player, action)

    assert state.terminal is True
    assert state.outcome == {"winner": "player_2", "reason": "checkmate"}
    assert state.public_state["san_history"] == ["f3", "e5", "g4", "Qh4#"]
    assert state.public_state["last_move_uci"] == "d8h4"
    assert state.public_state["last_move_san"] == "Qh4#"
    assert state.public_state["terminal_reason"] == "checkmate"
    assert state.public_state["winner"] == "player_2"
    assert state.public_state["king_status"]["in_check"] is True
    assert state.public_state["final_validation"] == {
        "check": True,
        "checkmate": True,
        "legal_move_count": 0,
        "score": {"player_2": 1.0, "player_1": 0.0},
    }


def test_chess_threefold_repetition_survives_fen_rebuilds():
    arena = ChessArena()
    state = arena.initial_state(seed=1)

    for action in ("g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"):
        state = arena.apply_action(state, state.active_player, action)

    assert state.terminal is True
    assert state.outcome == {"winner": None, "reason": "threefold_repetition"}
    assert state.scores == {"player_1": 0.5, "player_2": 0.5}
