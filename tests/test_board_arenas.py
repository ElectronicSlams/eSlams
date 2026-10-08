from eslams.arenas.gomoku import GomokuArena
from eslams.arenas.hex import HexArena


def test_gomoku_detects_five_in_a_row():
    arena = GomokuArena()
    state = arena.initial_state(1)
    for action in [0, 15, 1, 16, 2, 17, 3, 18, 4]:
        state = arena.apply_action(state, state.active_player, action)

    assert state.terminal is True
    assert state.outcome == {"winner": "player_1", "reason": "five_in_a_row"}
    assert state.scores["player_1"] == 1.0


def test_hex_detects_top_bottom_connection():
    arena = HexArena()
    state = arena.initial_state(1)
    player_2_fillers = [10, 21, 32, 43, 54, 65, 76, 87, 98, 109]
    player_1_path = [row * 11 for row in range(11)]
    actions: list[int] = []
    for index, action in enumerate(player_1_path):
        actions.append(action)
        if index < len(player_2_fillers):
            actions.append(player_2_fillers[index])

    for action in actions:
        state = arena.apply_action(state, state.active_player, action)
        if state.terminal:
            break

    assert state.terminal is True
    assert state.outcome == {"winner": "player_1", "reason": "connected_sides"}
    assert state.scores["player_1"] == 1.0
