import json
from pathlib import Path

import pytest

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.arena_transport import (
    StateHashMismatch,
    deserialize_state,
    initial_state,
    legal_actions,
    legal_actions_page,
    smoke_all_arenas,
    start_session,
    state_hash,
    step,
    step_session,
)
from eslams.cli import main
from eslams.contracts.safety import scan_public_payload
from eslams.public_catalogue import PUBLIC_GAME_CATALOGUE_BY_ID

REQUIRED_DESCRIPTOR_FIELDS = {
    "token",
    "label",
    "short_label",
    "verb",
    "object",
    "category",
    "group",
    "sort_key",
    "prompt_label",
    "confirm",
    "disabled_reason",
}


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


def test_deserialize_state_strict_hash_fails_and_trusted_repair_diagnoses():
    state = initial_state("tic-tac-toe", seed=1)
    stale = {**state, "state_hash": "stale-hash"}

    with pytest.raises(StateHashMismatch) as exc_info:
        deserialize_state(stale)

    repaired = deserialize_state(stale, strict_hash=False)

    assert exc_info.value.to_dict()["provided_state_hash"] == "stale-hash"
    assert repaired.state_hash == state["state_hash"]
    assert repaired.rehydration_diagnostics == {
        "status": "state_hash_repaired",
        "provided_state_hash": "stale-hash",
        "canonical_state_hash": state["state_hash"],
    }


def test_cli_arena_smoke_all(capsys):
    assert main(["arena", "smoke", "--all", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["game_count"] == 50


def test_arena_session_start_and_one_step_all_games_are_public_safe():
    for game_id in registry.list():
        arena = registry.create(game_id)
        players = _players_for(arena.players)
        variant = PUBLIC_GAME_CATALOGUE_BY_ID[game_id].variant

        start = start_session(game_id, variant, 1, players)
        assert start["schema_version"] == "eslams.arena.start_result.v1"
        assert start["state_hash_status"] == "verified"
        assert start["session_state"]["schema_version"] == "eslams.arena.session_state.v1"
        assert "private_state_by_player" not in start["session_state"]
        assert start["display_frame"]["schema_version"] == "eslams.replay.display_frame.v1"
        assert start["timing"]["total_core_ms"] <= 50
        assert _public_issues(start) == []

        descriptors = _all_descriptor_rows(start["session_state"], start["active_player"])
        assert len(descriptors) == start["total_legal_actions"]
        for descriptor in descriptors:
            assert set(descriptor) >= REQUIRED_DESCRIPTOR_FIELDS
            assert descriptor["token"]
            assert descriptor["label"]
            assert descriptor["short_label"]
            assert descriptor["prompt_label"]

        if start["legal_actions"]:
            stepped = step_session(
                start["session_state"],
                start["active_player"],
                start["legal_actions"][0],
            )
            assert stepped["accepted"] is True, game_id
            assert stepped["schema_version"] == "eslams.arena.step_result.v1"
            assert stepped["state_hash_status"] == "verified"
            assert stepped["display_frame"]["schema_version"] == "eslams.replay.display_frame.v1"
            assert stepped["timing"]["total_core_ms"] <= 50
            assert state_hash(stepped["session_state"]) == stepped["state_hash"]
            assert "private_state_by_player" not in stepped["session_state"]
            assert _public_issues(stepped) == []
            assert "state.applied" in [event["type"] for event in stepped["events"]]


def test_arena_session_failures_are_safe_and_do_not_transition():
    players = _players_for(("player_1", "player_2"))
    start = start_session("tic-tac-toe", "standard", 1, players)

    payload = str(start["session_state"]["payload"])
    tampered = {
        **start["session_state"],
        "payload": payload[:-1] + ("A" if payload[-1] != "A" else "B"),
    }
    mismatch = step_session(tampered, "player_1", "0")
    assert mismatch["accepted"] is False
    assert mismatch["state_hash_status"] == "signature_mismatch"
    assert mismatch["error"]["reason"] == "session_state_signature_invalid"
    assert mismatch["events"][0]["type"] == "turn.failed"

    wrong_actor = step_session(start["session_state"], "player_2", "0")
    assert wrong_actor["accepted"] is False
    assert wrong_actor["error"]["reason"] == "wrong_actor"
    assert wrong_actor["state_hash"] == start["state_hash"]
    assert _public_issues(wrong_actor) == []

    illegal = step_session(start["session_state"], "player_1", "99")
    assert illegal["accepted"] is False
    assert illegal["error"]["reason"] == "illegal_action"
    assert illegal["state_hash"] == start["state_hash"]
    assert _public_issues(illegal) == []


def test_arena_session_rejects_non_object_options():
    with pytest.raises(ValueError, match="options must be a JSON object"):
        start_session(
            "tic-tac-toe",
            "standard",
            1,
            _players_for(("player_1", "player_2")),
            ["not", "an", "object"],  # type: ignore[arg-type]
        )


def test_arena_legal_actions_page_large_games_and_search():
    for game_id in ("pentago", "gomoku", "hex", "go", "ultimate-tic-tac-toe"):
        arena = registry.create(game_id)
        start = start_session(
            game_id,
            PUBLIC_GAME_CATALOGUE_BY_ID[game_id].variant,
            1,
            _players_for(arena.players),
            {"legal_actions_limit": 25},
        )
        page = legal_actions_page(start["session_state"], start["active_player"], limit=25)
        assert page["schema_version"] == "eslams.arena.legal_actions_page.v1"
        assert page["total_legal_actions"] >= 25
        assert len(page["rows"]) == 25
        assert not scan_public_payload({"rows": page["rows"]})
        if page["has_more"]:
            next_page = legal_actions_page(
                start["session_state"],
                start["active_player"],
                limit=25,
                cursor=page["next_cursor"],
            )
            assert next_page["rows"][0]["token"] != page["rows"][0]["token"]

    pentago = start_session(
        "pentago",
        "standard",
        1,
        _players_for(registry.create("pentago").players),
    )
    searched = legal_actions_page(
        pentago["session_state"],
        pentago["active_player"],
        query="quadrant 1",
        limit=10,
    )
    assert searched["total_matching_actions"] > 0
    assert all("quadrant 1" in row["label"] for row in searched["rows"])


def test_arena_session_cli_start_step_and_page(tmp_path: Path, capsys):
    players_json = json.dumps(_players_for(("player_1", "player_2")))
    assert (
        main(
            [
                "arena",
                "start",
                "--game",
                "tic-tac-toe",
                "--variant",
                "standard",
                "--seed",
                "1",
                "--players-json",
                players_json,
            ]
        )
        == 0
    )
    start = json.loads(capsys.readouterr().out)
    state_file = tmp_path / "session_state.json"
    state_file.write_text(json.dumps(start["session_state"]), encoding="utf-8")

    assert (
        main(
            [
                "arena",
                "step",
                "--state",
                str(state_file),
                "--player-id",
                "player_1",
                "--action-token",
                "4",
            ]
        )
        == 0
    )
    stepped = json.loads(capsys.readouterr().out)
    assert stepped["accepted"] is True

    assert (
        main(
            [
                "arena",
                "legal-actions-page",
                "--state",
                str(state_file),
                "--player-id",
                "player_1",
                "--query",
                "center",
                "--limit",
                "5",
            ]
        )
        == 0
    )
    page = json.loads(capsys.readouterr().out)
    assert page["total_matching_actions"] == 1
    assert page["rows"][0]["label"] == "Play center"


def test_arena_session_golden_representative_descriptors():
    golden_path = Path("fixtures/arena_sessions/golden_v0_3.json")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    for row in golden["games"]:
        arena = registry.create(row["game_id"])
        start = start_session(
            row["game_id"],
            PUBLIC_GAME_CATALOGUE_BY_ID[row["game_id"]].variant,
            1,
            _players_for(arena.players),
        )
        descriptor = start["legal_action_descriptors"][0]
        assert descriptor["token"] == row["first_token"]
        assert descriptor["label"] == row["first_label"]
        assert descriptor["category"] == row["first_category"]
        assert [event["type"] for event in start["events"]] == row["start_event_types"]
        assert start["display_frame"]["renderer_family"] == row["renderer_family"]


def _players_for(player_ids: tuple[str, ...]) -> dict[str, dict[str, str]]:
    rows = {player_id: {"kind": "human", "label": player_id} for player_id in player_ids}
    rows[player_ids[-1]]["kind"] = "model"
    return rows


def _all_descriptor_rows(
    session_state: dict[str, object],
    player_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cursor = None
    while True:
        page = legal_actions_page(session_state, player_id, limit=50, cursor=cursor)
        rows.extend(page["rows"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            return rows


def _public_issues(payload: dict[str, object]) -> list[object]:
    public_subset = {
        "public_state": payload["public_state"],
        "display_frame": payload["display_frame"],
        "legal_action_descriptors": payload["legal_action_descriptors"],
        "events": payload["events"],
    }
    return scan_public_payload(public_subset)
