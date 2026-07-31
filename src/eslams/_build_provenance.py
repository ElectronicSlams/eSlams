"""Immutable source provenance shared by source and packaged Core builds."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PACKAGED_CORE_COMMIT: str | None = None

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def core_source_commit() -> str:
    """Return the exact source commit, failing closed when it cannot be proven."""

    if PACKAGED_CORE_COMMIT is not None:
        if not _COMMIT_RE.fullmatch(PACKAGED_CORE_COMMIT):
            raise RuntimeError("packaged Core source commit is malformed")
        return PACKAGED_CORE_COMMIT

    root = Path(__file__).resolve().parents[2]
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if Path(top_level).resolve() != root.resolve():
            raise RuntimeError("Core source is not inside its own Git checkout")
        commit = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Core source commit is unavailable") from exc
    if not _COMMIT_RE.fullmatch(commit):
        raise RuntimeError("Core source commit is malformed")
    return commit
