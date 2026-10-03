"""Stage exports without deleting inputs or pre-existing output directories."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def staged_directory(output: Path, *, sources: Sequence[Path] = ()) -> Iterator[Path]:
    """Commit a completed export to a new directory on the same filesystem.

    Existing outputs are deliberately refused. The sibling lock prevents two
    Core exporters from racing to install the same destination. Cleanup owns
    only the lock and temporary directory created by this invocation.
    """
    if output.is_symlink():
        raise ValueError("output directory must not be a symlink")
    destination = output.resolve()
    cwd = Path.cwd().resolve()
    if cwd == destination or cwd.is_relative_to(destination):
        raise ValueError("output directory must not be the working directory or its ancestor")
    if (destination / ".git").exists():
        raise ValueError("output directory must not be a Git checkout")
    for source in sources:
        resolved = source.resolve()
        if destination.is_relative_to(resolved) or resolved.is_relative_to(destination):
            raise ValueError("output directory must be separate from every input path")
    _require_new_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(f".{destination.name}.eslams-output.lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}.eslams-output-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary)
            yield staged
            _require_new_destination(destination)
            staged.rename(destination)
    finally:
        os.close(descriptor)
        lock.unlink()


def _require_new_destination(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"output already exists: {path}; choose a new output directory")
