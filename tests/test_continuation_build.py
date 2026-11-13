"""Installed continuation identities must attest actual immutable runtime bytes."""
from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from eslams import continuation_build as build
from eslams.continuation import (
    _engine,
    chess_continuation_engine_identity,
    local_chess_continuation_engine_identity,
)
from eslams.hashing import canonical_json


@pytest.fixture
def installed(tmp_path, monkeypatch):
    core = tmp_path / "core"
    wrapper = tmp_path / "wrapper"
    core.mkdir()
    wrapper.mkdir()
    (core / "continuation_build.py").write_text("# synthetic Core source\n")
    (wrapper / "main.py").write_text("# synthetic wrapper source\n")
    path = tmp_path / "build.json"
    monkeypatch.setattr(build, "__file__", str(core / "continuation_build.py"))
    monkeypatch.setattr(build, "BUILD_PATH", path)
    monkeypatch.setattr(build, "WRAPPER_ROOT", wrapper)
    monkeypatch.setattr(build._build_provenance, "PACKAGED_CORE_COMMIT", "a" * 40)
    monkeypatch.setattr(build.os, "geteuid", lambda: 10001)
    # Model a protected image filesystem without changing local OS ownership.
    monkeypatch.setattr(build, "_protected", lambda *args, **kwargs: None)
    evidence = build.build_chess_continuation_evidence(
        core_root=core, wrapper_root=wrapper, core_ref="a" * 40,
        platform_ref="b" * 40, wrapper_version="wrapper:test", runner_version="platform:test",
    )
    path.write_text(canonical_json(evidence))
    return path, core, wrapper, evidence


def test_installed_identity_binds_both_source_trees_and_build(installed):
    path, _, _, evidence = installed
    identity = build.installed_chess_continuation_engine_identity()
    assert identity["coreRef"] == "a" * 40
    assert identity["platformRef"] == "b" * 40
    assert identity["runnerBuildSha256"] == build._digest(evidence)
    assert identity["coreSourceSha256"] == build._digest(evidence["coreFiles"])
    assert identity["wrapperSourceSha256"] == build._digest(evidence["wrapperFiles"])
    assert "runnerImageDigest" not in identity
    assert _engine(identity) == identity
    # Cosmetic JSON formatting is not a different immutable build.
    path.write_text(json.dumps(evidence, indent=2))
    assert build.installed_chess_continuation_engine_identity() == identity
    assert chess_continuation_engine_identity(wrapper_version="caller-ignored") == identity


@pytest.mark.parametrize("tree", ["core", "wrapper"])
@pytest.mark.parametrize("mutation", ["change", "extra", "missing"])
def test_runtime_source_drift_is_rejected(installed, tree, mutation):
    _, core, wrapper, _ = installed
    root = core if tree == "core" else wrapper
    file = next(root.glob("*.py"))
    if mutation == "change":
        file.write_text("# changed\n")
    elif mutation == "extra":
        (root / "extra.py").write_text("# unlisted\n")
    else:
        file.unlink()
    with pytest.raises(ValueError, match="source mismatch|empty Python"):
        build.installed_chess_continuation_engine_identity()


@pytest.mark.parametrize("key,value", [
    ("coreRef", "c" * 40), ("coreVersion", "wrong"), ("coreRunnerVersion", "wrong"),
    ("platformRef", "main"), ("extra", True), ("schemaVersion", "unknown"),
])
def test_bad_build_evidence_fails_closed(installed, key, value):
    path, _, _, evidence = installed
    evidence[key] = value
    path.write_text(canonical_json(evidence))
    with pytest.raises(ValueError):
        build.installed_chess_continuation_engine_identity()


def test_evidence_duplicate_keys_oversize_and_root_are_rejected(installed, monkeypatch):
    path, _, _, evidence = installed
    path.write_text('{"schemaVersion":"x","schemaVersion":"y"}')
    with pytest.raises(ValueError, match="duplicate"):
        build.installed_chess_continuation_engine_identity()
    path.write_bytes(b" " * (build.MAX_BUILD_BYTES + 1))
    with pytest.raises(ValueError, match="too large"):
        build.installed_chess_continuation_engine_identity()
    path.write_text(canonical_json(evidence))
    monkeypatch.setattr(build.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="must not run as root"):
        build.installed_chess_continuation_engine_identity()


def test_installed_target_cannot_claim_oci_or_local_identity(installed):
    identity = build.installed_chess_continuation_engine_identity()
    with pytest.raises(ValueError, match="image claims"):
        _engine({**identity, "runnerImageDigest": "sha256:" + "1" * 64})
    with pytest.raises(ValueError, match="local engine"):
        _engine({**identity, "coreRef": "local-development"})


def test_packaged_runtime_has_no_local_development_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "BUILD_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(build._build_provenance, "PACKAGED_CORE_COMMIT", "a" * 40)
    with pytest.raises(ValueError, match="requires trusted build evidence"):
        chess_continuation_engine_identity(wrapper_version="caller-value")
    # The helper itself still describes local bytes, but does not authorize them.
    identity = local_chess_continuation_engine_identity(wrapper_version="test")
    assert identity["coreRef"] == "local-development"


def test_source_manifest_rejects_links(tmp_path):
    (tmp_path / "source.py").write_text("# synthetic\n")
    (tmp_path / "alias.py").symlink_to(tmp_path / "source.py")
    with pytest.raises(ValueError, match="symlink"):
        build.python_source_manifest(tmp_path)


@pytest.mark.parametrize("uid,mode", [
    (10001, stat.S_IFREG | 0o644), (0, stat.S_IFREG | 0o666),
    (0, stat.S_IFLNK | 0o777), (0, stat.S_IFIFO | 0o644),
])
def test_protection_rejects_runtime_writable_or_nonregular_file(monkeypatch, uid, mode):
    monkeypatch.setattr(Path, "lstat", lambda self: SimpleNamespace(st_uid=uid, st_mode=mode))
    with pytest.raises(ValueError):
        build._protected(Path("/protected/evidence.json"))


def test_protection_checks_every_ancestor(monkeypatch):
    def info(path):
        mode = stat.S_IFREG | 0o644 if path.name == "build.json" else stat.S_IFDIR | 0o755
        if path == Path("/opt"):
            mode |= 0o002
        return SimpleNamespace(st_uid=0, st_mode=mode)
    monkeypatch.setattr(Path, "lstat", info)
    with pytest.raises(ValueError, match="runtime writes"):
        build._protected(Path("/opt/eslams-continuation/build.json"))


def test_build_writer_requires_packaged_ref_and_actual_imported_root(installed):
    _, core, wrapper, _ = installed
    with pytest.raises(ValueError, match="packaged Core ref"):
        build.build_chess_continuation_evidence(
            core_root=core, wrapper_root=wrapper, core_ref="c" * 40,
            platform_ref="b" * 40, wrapper_version="wrapper:test", runner_version="platform:test",
        )
    with pytest.raises(ValueError, match="imported Core package"):
        build.build_chess_continuation_evidence(
            core_root=wrapper, wrapper_root=wrapper, core_ref="a" * 40,
            platform_ref="b" * 40, wrapper_version="wrapper:test", runner_version="platform:test",
        )
