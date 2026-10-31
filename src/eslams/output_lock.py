"""Crash-released output ownership; persistent guard files are never unlinked.

This guards artifact writes, not remote inference or permission to replay it.
Old empty existence-only locks are refused because their owner cannot be proven.
"""
from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_MARKER = b"eslams.output-lock.v2\n"


def _exclusive(descriptor: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            raise FileExistsError("output is in use by another writer") from exc
        raise


def _open_existing(path: Path) -> int:
    if path.is_symlink():
        raise ValueError("output guard must not be a symlink")
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("output guard must be a regular file")
        if info.st_size != len(_MARKER) or os.read(descriptor, len(_MARKER) + 1) != _MARKER:
            raise FileExistsError(
                f"legacy or unrecognized output guard: {path}; verify old writers have stopped "
                "before operator-managed recovery; it will not be removed automatically"
            )
        _exclusive(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _acquire(path: Path) -> tuple[int, Path | None]:
    try:
        return _open_existing(path), None
    except FileNotFoundError:
        pass
    # Publish a complete, already-locked inode atomically. A death before link
    # leaves an unreferenced setup file, never a half-written canonical guard.
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.setup-", dir=path.parent)
    temporary = Path(name)
    try:
        written = 0
        while written < len(_MARKER):
            count = os.write(descriptor, _MARKER[written:])
            if count <= 0:
                raise OSError("output guard marker write failed")
            written += count
        os.fsync(descriptor)
        _exclusive(descriptor)
        try:
            os.link(temporary, path)
        except FileExistsError:
            os.close(descriptor)
            descriptor = -1
            temporary.unlink(missing_ok=True)
            return _open_existing(path), None
        # Windows may retain the open setup name until its descriptor closes.
        return descriptor, temporary
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def output_lock(path: Path) -> Iterator[None]:
    """Acquire a nonblocking OS lock, keeping its canonical inode after release.

    Do not delete a persistent guard: replacement creates a second lock domain.
    Local/shared-filesystem locking support is an operator deployment property.
    This is not a distributed lock or an inference ledger.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = _acquire(path)
    try:
        yield
    finally:
        os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
