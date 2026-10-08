from eslams.arenas.checkers import CheckersArena
from eslams.arenas.mancala import MancalaArena
from eslams.arenas.matrix_games import PrisonersDilemmaArena, RockPaperScissorsArena
from eslams.arenas.ultimate_tic_tac_toe import UltimateTicTacToeArena


def test_checkers_multi_jump_capture_must_continue_with_same_piece():
    arena = CheckersArena()
    board = [[None for _ in range(8)] for _ in range(8)]
    board[5][0] = "r"
    board[4][1] = "b"
    board[2][3] = "b"
    board[5][4] = "r"
    board[4][5] = "b"
    state = arena._state(
        board=board,
        turn=0,
        active="player_1",
        seed=1,
        outcome=None,
        forced_piece=None,
    )

    jumped = arena.apply_action(state, "player_1", "5,0-3,2")

    assert jumped.active_player == "player_1"
    assert jumped.public_state["forced_piece"] == [3, 2]
    assert jumped.legal_actions_by_player["player_1"] == ["3,2-1,4"]
    assert "5,4-3,6" not in jumped.legal_actions_by_player["player_1"]

    # Retained assertions from test_checkers_initial_moves_and_capture.
    arena = CheckersArena()
    state = arena.initial_state(1)

    assert "5,0-4,1" in state.legal_actions_by_player["player_1"]

    board = [[None for _ in range(8)] for _ in range(8)]
    board[5][0] = "r"
    board[4][1] = "b"
    custom = arena._state(
        board=board,
        turn=0,
        active="player_1",
        seed=1,
        outcome=None,
        forced_piece=None,
    )

    assert custom.legal_actions_by_player["player_1"] == ["5,0-3,2"]
    captured = arena.apply_action(custom, "player_1", "5,0-3,2")
    assert captured.public_state["board"][4][1] is None
    assert captured.public_state["board"][3][2] == "r"
    assert captured.terminal is True


def test_mancala_extra_turn_and_store_update():
    arena = MancalaArena()
    state = arena.initial_state(1)

    next_state = arena.apply_action(state, "player_1", 2)

    assert next_state.public_state["stores"]["player_1"] == 1
    assert next_state.active_player == "player_1"


def test_ultimate_tic_tac_toe_routes_next_board():
    arena = UltimateTicTacToeArena()
    state = arena.initial_state(1)

    next_state = arena.apply_action(state, "player_1", 10)

    assert next_state.public_state["boards"][1][1] == "X"
    assert next_state.public_state["next_board"] == 1
    assert all(9 <= action <= 17 for action in next_state.legal_actions_by_player["player_2"])


def test_matrix_games_score_terminal_rounds():
    rps = RockPaperScissorsArena()
    state = rps.initial_state(1)
    state = rps.apply_action(state, "player_1", "rock")
    state = rps.apply_action(state, "player_2", "scissors")

    assert state.terminal is True
    assert state.outcome["winner"] == "player_1"
    assert state.scores["player_1"] == 1.0

    dilemma = PrisonersDilemmaArena()
    dilemma_state = dilemma.initial_state(1)
    dilemma_state = dilemma.apply_action(dilemma_state, "player_1", "defect")
    dilemma_state = dilemma.apply_action(dilemma_state, "player_2", "cooperate")

    assert dilemma_state.terminal is True
    assert dilemma_state.outcome["winner"] == "player_1"
    assert dilemma_state.scores["player_1"] == 1.0

    mutual_cooperate = PrisonersDilemmaArena()
    cooperate_state = mutual_cooperate.initial_state(1)
    cooperate_state = mutual_cooperate.apply_action(cooperate_state, "player_1", "cooperate")
    cooperate_state = mutual_cooperate.apply_action(cooperate_state, "player_2", "cooperate")
    mutual_defect = PrisonersDilemmaArena()
    defect_state = mutual_defect.initial_state(1)
    defect_state = mutual_defect.apply_action(defect_state, "player_1", "defect")
    defect_state = mutual_defect.apply_action(defect_state, "player_2", "defect")

    assert cooperate_state.scores == {"player_1": 0.6, "player_2": 0.6}
    assert defect_state.scores == {"player_1": 0.2, "player_2": 0.2}
