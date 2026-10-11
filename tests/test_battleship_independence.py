from eslams.arenas.battleship import GRID_SIZE, SHIP_COUNT, BattleshipArena, _ship_layout


def test_fleets_are_sampled_from_independent_full_grids(monkeypatch):
    populations = []

    class SameCellsRandom:
        def __init__(self, seed):
            pass

        def sample(self, population, count):
            populations.append(list(population))
            assert count == SHIP_COUNT
            return population[:count]

    monkeypatch.setattr("eslams.arenas.battleship.random.Random", SameCellsRandom)
    layout = _ship_layout(1)
    assert len(populations) == 2
    assert populations[0] == populations[1]
    assert len(populations[1]) == GRID_SIZE ** 2
    assert layout["player_1"] == layout["player_2"]  # overlap is permitted


def test_independent_layouts_remain_seed_deterministic_and_private():
    arena = BattleshipArena()
    state = arena.initial_state(1)
    assert state.to_dict() == arena.initial_state(1).to_dict()
    assert arena.version == "1.1.0"
    observed = arena.observation_for(state, "player_1")
    assert observed["own_ships"] == state.private_state_by_player["player_1"]["own_ships"]
    assert "own_ships" not in state.public_state
