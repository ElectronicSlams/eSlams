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
from typing import Any, overload

_DEADLINE: ContextVar[float | None] = ContextVar("eslams_action_deadline", default=None)
_RECEIPT_INVOCATION: ContextVar[object | None] = ContextVar(
    "eslams_receipt_invocation", default=None,
)
_CANCELLATION: ContextVar[threading.Event | None] = ContextVar("eslams_cancellation", default=None)
_CALL_LOCK = threading.Lock()
_CALLS: dict[int, Any] = {}
_CALL_CAPACITY = threading.BoundedSemaphore(32)


def current_receipt_invocation() -> object | None:
    return _RECEIPT_INVOCATION.get()


@contextmanager
def receipt_invocation(invocation: object) -> Iterator[None]:
    token = _RECEIPT_INVOCATION.set(invocation)
    try:
        yield
    finally:
        _RECEIPT_INVOCATION.reset(token)


def current_deadline() -> float | None:
    return _DEADLINE.get()


class ExecutionCancelled(RuntimeError):
    """Caller interruption; never a competitive game result."""


def check_cancelled() -> None:
    cancellation = _CANCELLATION.get()
    if cancellation is not None and cancellation.is_set():
        raise ExecutionCancelled("execution cancelled by caller; remote work may remain unknown")


@contextmanager
def cancellation_scope(cancellation: threading.Event | None) -> Iterator[None]:
    token = _CANCELLATION.set(cancellation if cancellation is not None else _CANCELLATION.get())
    try:
        check_cancelled()
        yield
    finally:
        _CANCELLATION.reset(token)


def sleep_with_cancellation(seconds: float) -> None:
    check_cancelled()
    if _CANCELLATION.get() is None:
        time.sleep(seconds)
        return
    remaining = seconds
    while remaining > 0:
        check_cancelled()
        remaining_seconds(current_deadline())
        interval = min(remaining, 0.05)
        time.sleep(interval)
        remaining -= interval


@overload
def remaining_seconds(deadline: float) -> float: ...


@overload
def remaining_seconds(deadline: None) -> None: ...


@overload
def remaining_seconds(deadline: float | None) -> float | None: ...


def remaining_seconds(deadline: float | None) -> float | None:
    check_cancelled()
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("action deadline expired")
    return remaining


@contextmanager
def action_deadline(milliseconds: int | None) -> Iterator[None]:
    requested = time.monotonic() + milliseconds / 1000 if milliseconds is not None else None
    existing = current_deadline()
    effective = min(requested, existing) if requested is not None and existing is not None else (
        existing if existing is not None else requested
    )
    token = _DEADLINE.set(effective)
    try:
        check_cancelled()
        yield
    finally:
        _DEADLINE.reset(token)


def ensure_agent_available(agent: Any) -> None:
    with _CALL_LOCK:
        if id(agent) in _CALLS:
            raise TimeoutError("agent still has an unfinished action; late work is quarantined")


def call_in_thread(agent: Any, function: Callable[[], Any], seconds: float | None) -> Any:
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
    deadline = time.monotonic() + seconds if seconds is not None else None
    while not done.is_set():
        check_cancelled()
        remaining = remaining_seconds(deadline)
        done.wait(0.05 if remaining is None else min(0.05, remaining))
    check_cancelled()
    if failures:
        raise failures[0]
    return result[0]


def receipt_snapshot(
    agent: Any, *, invocation: object | None = None,
) -> list[dict[str, Any]]:
    snapshot = getattr(agent, "_receipt_snapshot", None)
    if invocation is not None and callable(snapshot):
        rows: object = snapshot(invocation)
        if not isinstance(rows, list):
            return []
        return copy.deepcopy([row for row in rows if isinstance(row, dict)])
    receipts = getattr(agent, "attempt_receipts", None)
    if isinstance(receipts, list):
        return copy.deepcopy([row for row in receipts if isinstance(row, dict)])
    receipt = getattr(agent, "last_receipt", None)
    return [copy.deepcopy(receipt)] if isinstance(receipt, dict) else []
