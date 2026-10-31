"""Complete bounded pages with actor/state/query/order-bound opaque cursors."""
import base64
import json

import pytest

from eslams.arena import registry
from eslams.arena_transport import legal_actions_page, start_session, step_session

pytestmark = pytest.mark.usefixtures("arena_session_env")


def start(game="gomoku", *, model=False):
    players = {p: {"kind": "model" if model and p == "player_1" else "human"}
               for p in registry.create(game).players}
    return start_session(game, None, 1, players)


@pytest.mark.parametrize("game,count", [("gomoku", 225), ("pentago", 288)])
@pytest.mark.parametrize("limit", [50, 200])
def test_every_opening_action_is_reachable_once_in_canonical_order(game, count, limit):
    opened = start(game)
    cursor = None
    tokens = []
    while True:
        page = legal_actions_page(opened["session_state"], "player_1", limit=limit, cursor=cursor)
        assert len(page["rows"]) <= min(limit, 200)
        assert page["total_legal_actions"] == count
        tokens.extend(row["token"] for row in page["rows"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
        assert cursor.startswith("ep2.")
    assert len(tokens) == len(set(tokens)) == count
    assert tokens[:len(opened["legal_actions"])] == opened["legal_actions"]


@pytest.mark.parametrize("mutation", ["actor", "state", "query", "ordering"])
def test_cursor_cannot_be_reused_for_different_page_scope(monkeypatch, mutation):
    import eslams.arena_transport as module
    opened = start()
    page = legal_actions_page(opened["session_state"], "player_1", limit=50)
    state, player, query = opened["session_state"], "player_1", None
    if mutation == "actor":
        player = "player_2"
    elif mutation == "state":
        stepped = step_session(state, player, opened["legal_actions"][0])
        assert stepped["accepted"]
        state, player = stepped["session_state"], stepped["active_player"]
    elif mutation == "query":
        query = "row 1"
    else:
        original = module.action_descriptors
        monkeypatch.setattr(module, "action_descriptors",
                            lambda **kw: list(reversed(original(**kw))))
    with pytest.raises(ValueError, match="invalid or stale"):
        legal_actions_page(state, player, query=query, cursor=page["next_cursor"])


def test_tampered_offset_cannot_be_accepted_under_the_original_mac():
    opened = start()
    cursor = legal_actions_page(opened["session_state"], "player_1")["next_cursor"]
    prefix, encoded, signature = cursor.split(".")
    body = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    body["offset"] = 224
    modified = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    with pytest.raises(ValueError, match="invalid or stale"):
        legal_actions_page(opened["session_state"], "player_1",
                           cursor=f"{prefix}.{modified}.{signature}")


@pytest.mark.parametrize("cursor", ["50", "-1", "bad", "1.2", "ep3.data.signature"])
def test_legacy_or_malformed_cursors_do_not_silently_reset_to_first_page(cursor):
    opened = start()
    with pytest.raises(ValueError, match="invalid or stale"):
        legal_actions_page(opened["session_state"], "player_1", cursor=cursor)


def test_legacy_offset_requires_explicit_migration_choice_and_is_never_emitted():
    opened = start()
    page = legal_actions_page(opened["session_state"], "player_1", cursor="200",
                              allow_legacy_cursor=True, limit=200)
    assert len(page["rows"]) == 25 and not page["has_more"]
    assert legal_actions_page(opened["session_state"], "player_1")["next_cursor"].startswith("ep2.")


def test_model_seat_private_actions_stay_absent_from_pages():
    opened = start("hearts", model=True)
    page = legal_actions_page(opened["session_state"], "player_1")
    assert page["rows"] == [] and page["total_legal_actions"] == 0
    assert page["next_cursor"] is None and not page["has_more"]
