"""Atomic replay admission backends; never store request bodies or credentials."""
from __future__ import annotations

import math
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Protocol


class NonceStoreError(ValueError):
    """Replay protection is unavailable; callers must fail closed."""


class NonceStore(Protocol):
    def claim(self, nonce: str, *, expires_at: float, now: float) -> bool:
        """Atomically retain a fresh nonce, or return false for a replay."""
        ...


def _validate_claim(nonce: str, expires_at: float, now: float) -> None:
    if not isinstance(nonce, str) or not 1 <= len(nonce) <= 256:
        raise NonceStoreError("invalid replay identifier")
    for value in (expires_at, now):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise NonceStoreError("invalid replay lifetime")
    if expires_at < now:
        raise NonceStoreError("replay lifetime has already expired")


class MemoryNonceStore:
    """Bounded atomic single-process backend; not shared across worker processes."""

    def __init__(self, max_entries: int = 10000) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._entries: dict[str, float] = {}
        self._lock = threading.Lock()

    def claim(self, nonce: str, *, expires_at: float, now: float) -> bool:
        _validate_claim(nonce, expires_at, now)
        with self._lock:
            self._entries = {key: expiry for key, expiry in self._entries.items() if expiry >= now}
            if nonce in self._entries:
                return False
            if len(self._entries) >= self.max_entries:
                raise NonceStoreError("replay protection capacity is occupied")
            self._entries[nonce] = expires_at
            return True


class SQLiteNonceStore:
    """Shared-file atomic replay protection for workers on one host.

    A multi-host deployment needs its own atomic NonceStore implementation;
    do not infer distributed safety from a local file or network filesystem.
    The operator owns the database path, retention capacity and filesystem.
    """

    def __init__(self, path: str | Path, max_entries: int = 10000) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError("max_entries must be positive")
        if str(path) == ":memory:":
            raise ValueError("use MemoryNonceStore for process-local replay protection")
        self.path = str(path)
        self.max_entries = max_entries

    def claim(self, nonce: str, *, expires_at: float, now: float) -> bool:
        _validate_claim(nonce, expires_at, now)
        try:
            with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as db:
                db.execute("CREATE TABLE IF NOT EXISTS runner_nonces "
                           "(nonce TEXT PRIMARY KEY, expires_at REAL NOT NULL)")
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute("DELETE FROM runner_nonces WHERE expires_at < ?", (now,))
                    exists = db.execute(
                        "SELECT 1 FROM runner_nonces WHERE nonce = ?", (nonce,),
                    ).fetchone()
                    if exists:
                        db.commit()
                        return False
                    count = db.execute("SELECT COUNT(*) FROM runner_nonces").fetchone()[0]
                    if count >= self.max_entries:
                        raise NonceStoreError("replay protection capacity is occupied")
                    db.execute("INSERT INTO runner_nonces VALUES (?, ?)", (nonce, expires_at))
                    db.commit()
                    return True
                except BaseException:
                    db.rollback()
                    raise
        except sqlite3.Error as exc:
            raise NonceStoreError("replay protection database is unavailable") from exc
