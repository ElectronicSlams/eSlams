"""Hatch build hook that embeds immutable Core source provenance."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_CONSTANT_RE = re.compile(r"^PACKAGED_CORE_COMMIT: str \| None = .+$", re.MULTILINE)


class CustomBuildHook(BuildHookInterface):
    """Force a commit-pinned provenance module into every distribution."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root).resolve()
        source_path = root / "src" / "eslams" / "_build_provenance.py"
        commit = _embedded_commit(source_path) or _repository_commit(root)
        if commit is None:
            raise RuntimeError("cannot build Core without immutable source provenance")

        source = source_path.read_text(encoding="utf-8")
        generated, replacements = _CONSTANT_RE.subn(
            f'PACKAGED_CORE_COMMIT: str | None = "{commit}"',
            source,
            count=1,
        )
        if replacements != 1:
            raise RuntimeError("Core provenance constant could not be generated")

        self._temporary_directory = Path(tempfile.mkdtemp(prefix="eslams-build-provenance-"))
        generated_path = self._temporary_directory / "_build_provenance.py"
        generated_path.write_text(generated, encoding="utf-8")
        destination = (
            "src/eslams/_build_provenance.py"
            if self.target_name == "sdist"
            else "eslams/_build_provenance.py"
        )
        build_data["force_include"][str(generated_path)] = destination

    def finalize(
        self,
        version: str,
        build_data: dict[str, Any],
        artifact_path: str,
    ) -> None:
        temporary_directory = getattr(self, "_temporary_directory", None)
        if temporary_directory is not None:
            shutil.rmtree(temporary_directory)


def _repository_commit(root: Path) -> str | None:
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if Path(top_level).resolve() != root:
            return None
        commit = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return commit if _COMMIT_RE.fullmatch(commit) else None


def _embedded_commit(source_path: Path) -> str | None:
    match = _CONSTANT_RE.search(source_path.read_text(encoding="utf-8"))
    if match is None:
        return None
    value = match.group(0).partition("=")[2].strip().strip('"')
    return value if _COMMIT_RE.fullmatch(value) else None
