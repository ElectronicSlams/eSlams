"""Keyless host policy/concurrency checks; no listener or provider invocation."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from eslams.arena_transport import deserialize_session_state
from eslams.runner_session import (
    RunnerSessionCapacityError,
    RunnerSessionExists,
    RunnerSessionStore,
)


@pytest.mark.usefixtures("arena_session_env")
def test_no_default_session_expiration_even_after_seven_day_virtual_wait():
    now = [0.0]
    store = RunnerSessionStore(clock=lambda: now[0])
    store.create(game_id="tic-tac-toe", session_id="long-thinking")
    now[0] += 7 * 86400
    assert store.session_ping("long-thinking")["turn"] == 0


def test_optional_idle_expiry_and_capacity_do_not_evict_live_sessions():
    now = [0.0]
    store = RunnerSessionStore(max_sessions=1, idle_ttl_seconds=10, clock=lambda: now[0])
    store.create(game_id="tic-tac-toe", session_id="first")
    with pytest.raises(RunnerSessionCapacityError):
        store.create(game_id="tic-tac-toe", session_id="second")
    assert store.session_ping("first")["turn"] == 0
    now[0] = 10
    with pytest.raises(KeyError):
        store.snapshot("first")
    assert store.create(game_id="tic-tac-toe", session_id="second")["sessionId"] == "second"


@pytest.mark.parametrize("options", [
    {"max_sessions": 0}, {"max_sessions": True}, {"max_sessions": 1.5},
    {"idle_ttl_seconds": 0}, {"idle_ttl_seconds": True},
    {"idle_ttl_seconds": float("inf")}, {"idle_ttl_seconds": float("nan")},
])
def test_invalid_host_policy_is_rejected(options):
    with pytest.raises(ValueError):
        RunnerSessionStore(**options)


def test_concurrent_create_same_id_is_atomic_without_overwrite():
    store = RunnerSessionStore()
    barrier = threading.Barrier(4)
    def create():
        barrier.wait(timeout=3)
        try:
            store.create(game_id="tic-tac-toe", session_id="same")
            return "created"
        except RunnerSessionExists:
            return "exists"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: create(), range(4)))
    assert sorted(results) == ["created", "exists", "exists", "exists"]
    assert store.ping()["activeSessions"] == 1


@pytest.mark.usefixtures("arena_session_env")
def test_same_session_serialization_other_sessions_progress_and_active_lease_survives_expiry(
    monkeypatch,
):
    import eslams.runner_session as module
    now = [0.0]
    store = RunnerSessionStore(idle_ttl_seconds=10, clock=lambda: now[0])
    store.create(game_id="tic-tac-toe", session_id="one")
    store.create(game_id="tic-tac-toe", session_id="other")
    original = module.core_step
    entered, release = threading.Event(), threading.Event()
    turns = []
    def step(payload):
        turns.append(payload["state"]["turn"])
        if len(turns) == 1:
            entered.set()
            assert release.wait(3)
        return original(payload)
    monkeypatch.setattr(module, "core_step", step)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.step, session_id="one", action=0, include_signed_state=True)
        assert entered.wait(3)
        second = pool.submit(store.step, session_id="one", action=1, include_signed_state=True)
        try:
            assert store.session_ping("other")["turn"] == 0  # No global compute lock.
            now[0] = 100
            assert store.ping()["activeSessions"] == 1  # Idle other expired; active one retained.
        finally:
            release.set()
        replies = [first.result(timeout=3), second.result(timeout=3)]
    assert turns == [0, 1] and store.snapshot("one")["turn"] == 2
    for reply in replies:
        state = deserialize_session_state(reply["sessionState"])
        assert state.state_hash == reply["session"]["stateHash"]
        assert state.turn == reply["session"]["turn"]


@pytest.mark.usefixtures("arena_session_env")
def test_signed_snapshot_and_create_are_coherent_and_closed_id_is_not_reused_by_reference():
    store = RunnerSessionStore()
    reply = store.create(game_id="tic-tac-toe", session_id="first", include_signed_state=True)
    assert deserialize_session_state(reply["sessionState"]).state_hash == reply["stateHash"]
    snapshot = store.snapshot("first", include_signed_state=True)
    assert deserialize_session_state(snapshot["sessionState"]).state_hash == snapshot["stateHash"]
    store.close("first")
    with pytest.raises(KeyError):
        store.snapshot("first")
    assert store.create(game_id="tic-tac-toe", session_id="first")["turn"] == 0
