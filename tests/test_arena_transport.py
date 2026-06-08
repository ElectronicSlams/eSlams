import json

from eslams.arena_transport import initial_state, legal_actions, smoke_all_arenas, state_hash, step
from eslams.cli import main


def test_stateless_arena_transport_round_trip_and_step():
    state = initial_state("tic-tac-toe", seed=1)
    actions = legal_actions("tic-tac-toe", state, state["active_player"])
    next_state = step("tic-tac-toe", state, state["active_player"], actions[0])

    assert state_hash(state) == state["state_hash"]
    assert next_state["turn"] == 1
    assert next_state["state_hash"] != state["state_hash"]


def test_all_arenas_smoke_without_provider_calls():
    payload = smoke_all_arenas()

    assert payload["ok"] is True
    assert payload["game_count"] == 50
    assert all(row["legal_action_count"] >= 0 for row in payload["rows"])


def test_cli_arena_smoke_all(capsys):
    assert main(["arena", "smoke", "--all", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["game_count"] == 50
