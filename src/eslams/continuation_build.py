"""Image-build evidence for chess continuation, never supplied by a run request.

The container build writes this evidence after installing pinned Core and wrapper
sources. The runtime trusts its root-owned image filesystem, not a request or an
environment variable. An OCI digest belongs to external deployment custody; an
image cannot include its own final digest without a circular hash dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from eslams import _build_provenance
from eslams.contracts.versions import CORE_PACKAGE_VERSION, RUNNER_VERSION
from eslams.hashing import canonical_json

BUILD_SCHEMA = "eslams.chess-continuation-build/v1"
BUILD_PATH = Path("/opt/eslams-continuation/build.json")
WRAPPER_ROOT = Path("/app/app")
MAX_BUILD_BYTES = 1024 * 1024
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[0-9a-f]{40}$")
_FIELDS = {
    "schemaVersion", "coreVersion", "coreRef", "runnerVersion", "wrapperVersion",
    "platformRef", "coreFiles", "wrapperFiles", "coreRunnerVersion",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("chess continuation build: " + message)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _protected(path: Path, *, directory: bool = False) -> None:
    """Check the complete absolute path without resolving away symlinks."""
    _require(path.is_absolute(), "absolute installed path required")
    for candidate in (path, *path.parents):
        info = candidate.lstat()
        _require(not stat.S_ISLNK(info.st_mode), "symlink in installed path")
        _require(info.st_uid == 0 and info.st_mode & 0o022 == 0,
                 "installed path is not protected from runtime writes")
        _require(
            stat.S_ISDIR(info.st_mode) if candidate != path or directory
            else stat.S_ISREG(info.st_mode),
            "installed path has wrong file type",
        )


def python_source_manifest(root: Path, *, protected: bool = False) -> dict[str, str]:
    """Hash all Python source files, rejecting links and non-regular entries.

    Used at image build time and again at runtime. The root argument belongs to
    build tooling; the public runtime identity resolver accepts no path argument.
    """
    if protected:
        _protected(root, directory=True)
    _require(root.is_dir() and not root.is_symlink(), "source root unavailable")
    result = {}
    # Inspect every directory explicitly: pathlib glob must not hide symlinks.
    for directory, dirs, files in os.walk(root, followlinks=False):
        here = Path(directory)
        for name in dirs:
            child = here / name
            _require(not child.is_symlink(), "symlink in source tree")
            if protected:
                _protected(child, directory=True)
        for name in files:
            child = here / name
            _require(not child.is_symlink(), "symlink in source tree")
            if protected:
                _protected(child)
            if child.suffix == ".py":
                _require(child.is_file(), "source is not a regular file")
                result[child.relative_to(root).as_posix()] = hashlib.sha256(
                    child.read_bytes()
                ).hexdigest()
    _require(bool(result), "empty Python source manifest")
    return dict(sorted(result.items()))


def _validate_build(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(value) == _FIELDS, "invalid evidence fields")
    assert isinstance(value, dict)
    _require(value["schemaVersion"] == BUILD_SCHEMA, "unsupported evidence schema")
    for key in ("coreVersion", "runnerVersion", "coreRunnerVersion", "wrapperVersion"):
        _require(isinstance(value[key], str) and bool(value[key].strip()), "invalid version")
    for key in ("coreRef", "platformRef"):
        _require(isinstance(value[key], str) and _REF.fullmatch(value[key]) is not None,
                 "invalid source ref")
    for key in ("coreFiles", "wrapperFiles"):
        files = value[key]
        _require(isinstance(files, dict) and bool(files), "invalid source manifest")
        for name, digest in files.items():
            _require(isinstance(name, str) and not name.startswith("/")
                     and "\\" not in name and all(p not in {"", ".", ".."} for p in name.split("/"))
                     and name.endswith(".py"), "invalid source name")
            _require(isinstance(digest, str) and _HEX.fullmatch(digest) is not None,
                     "invalid source digest")
    return value


def build_chess_continuation_evidence(
    *, core_root: Path, wrapper_root: Path, core_ref: str,
    platform_ref: str, wrapper_version: str, runner_version: str,
) -> dict[str, Any]:
    """Produce build-time evidence after release tooling verifies its input pins.

    This helper does not install evidence, claim deployment, or authorize a run.
    The release tool must write canonical JSON to BUILD_PATH in the image as root,
    and keep both source trees root-owned and non-writable by the runner user.
    """
    _require(core_ref == _build_provenance.PACKAGED_CORE_COMMIT,
             "packaged Core ref does not match release pins")
    _require(core_root.absolute() == Path(__file__).absolute().parent,
             "build must describe the imported Core package")
    return _validate_build({
        "schemaVersion": BUILD_SCHEMA,
        "coreVersion": CORE_PACKAGE_VERSION,
        "coreRef": core_ref,
        "coreRunnerVersion": RUNNER_VERSION,
        "runnerVersion": runner_version,
        "wrapperVersion": wrapper_version,
        "platformRef": platform_ref,
        "coreFiles": python_source_manifest(core_root),
        "wrapperFiles": python_source_manifest(wrapper_root),
    })


def _unique_pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in rows:
        _require(key not in value, "duplicate evidence key")
        value[key] = child
    return value


def installed_chess_continuation_engine_identity() -> dict[str, Any]:
    """Resolve and verify trusted installed evidence; never use request/env pins."""
    from eslams.continuation import ENGINE_VERSION, LINEAGE_VERSION

    try:
        _require(os.geteuid() != 0, "runtime must not run as root")
        _protected(BUILD_PATH)
        _require(BUILD_PATH.stat().st_size <= MAX_BUILD_BYTES, "evidence too large")
        with BUILD_PATH.open("rb") as stream:
            raw = stream.read(MAX_BUILD_BYTES + 1)
        _require(len(raw) <= MAX_BUILD_BYTES, "evidence too large")
        build = _validate_build(json.loads(raw, object_pairs_hook=_unique_pairs))
        _require(build["coreVersion"] == CORE_PACKAGE_VERSION
                 and build["coreRunnerVersion"] == RUNNER_VERSION, "installed version mismatch")
        _require(build["coreRef"] == _build_provenance.PACKAGED_CORE_COMMIT,
                 "installed packaged Core ref mismatch")
        core_files = python_source_manifest(Path(__file__).absolute().parent, protected=True)
        wrapper_files = python_source_manifest(WRAPPER_ROOT, protected=True)
        _require(core_files == build["coreFiles"], "installed Core source mismatch")
        _require(wrapper_files == build["wrapperFiles"], "installed wrapper source mismatch")
        return {
            "schemaVersion": ENGINE_VERSION,
            "coreVersion": build["coreVersion"],
            "coreRef": build["coreRef"],
            "coreSourceSha256": _digest(core_files),
            "runnerVersion": build["runnerVersion"],
            "wrapperVersion": build["wrapperVersion"],
            "platformRef": build["platformRef"],
            "wrapperSourceSha256": _digest(wrapper_files),
            "runnerBuildSha256": _digest(build),
            "continuationContractVersion": LINEAGE_VERSION,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError(
            "chess continuation build: installed evidence unavailable or invalid"
        ) from error
