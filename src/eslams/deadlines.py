"""Elapsed action deadlines and bounded waits for cooperative agent adapters.

Python cannot terminate an arbitrary callback thread safely. Timed-out callbacks
are quarantined until they exit, and global capacity bounds abandoned work.
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from typing import Any

_DEADLINE: ContextVar[float | None] = ContextVar("eslams_action_deadline", default=None)
_CALL_LOCK = threading.Lock()
_CALLS: dict[int, Any] = {}
_CALL_CAPACITY = threading.BoundedSemaphore(32)


def current_deadline() -> float | None:
    return _DEADLINE.get()


def remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("action deadline expired")
    return remaining


@contextmanager
def action_deadline(milliseconds: int) -> Iterator[None]:
    requested = time.monotonic() + milliseconds / 1000
    existing = current_deadline()
    token = _DEADLINE.set(min(requested, existing) if existing is not None else requested)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def ensure_agent_available(agent: Any) -> None:
    with _CALL_LOCK:
        if id(agent) in _CALLS:
            raise TimeoutError("agent still has an unfinished action; late work is quarantined")


def call_in_thread(agent: Any, function: Callable[[], Any], seconds: float) -> Any:
    identity = id(agent)
    with _CALL_LOCK:
        if identity in _CALLS:
            raise TimeoutError("agent still has an unfinished action; late work is quarantined")
        if not _CALL_CAPACITY.acquire(blocking=False):
            raise TimeoutError("bounded agent execution capacity is occupied")
        _CALLS[identity] = agent
    done = threading.Event()
    result: list[Any] = []
    failures: list[BaseException] = []
    context = copy_context()

    def invoke() -> None:
        try:
            result.append(context.run(function))
        except BaseException as exc:
            failures.append(exc)
        finally:
            with _CALL_LOCK:
                _CALLS.pop(identity, None)
                _CALL_CAPACITY.release()
            done.set()

    worker = threading.Thread(target=invoke, name="eslams-agent-action", daemon=True)
    try:
        worker.start()
    except BaseException:
        with _CALL_LOCK:
            _CALLS.pop(identity, None)
            _CALL_CAPACITY.release()
        raise
    if not done.wait(seconds):
        raise TimeoutError("agent action deadline expired; late result will be discarded")
    if failures:
        raise failures[0]
    return result[0]


def receipt_snapshot(agent: Any) -> list[dict[str, Any]]:
    receipts = getattr(agent, "attempt_receipts", None)
    if isinstance(receipts, list):
        return copy.deepcopy([row for row in receipts if isinstance(row, dict)])
    receipt = getattr(agent, "last_receipt", None)
    return [copy.deepcopy(receipt)] if isinstance(receipt, dict) else []
