"""Recovery may reuse build evidence, never reinterpret chess runtime authority."""
from __future__ import annotations

from pathlib import Path

import pytest
from test_continuation_build import installed  # noqa: F401

from eslams import continuation_build as build
from eslams.board_recovery import (
    board_recovery_engine_identity,
    local_board_recovery_engine_identity,
)
from eslams.contracts.board_recovery import validate_board_recovery_engine


def test_recovery_installed_identity_reuses_actual_source_evidence(installed):  # noqa: F811
    _, _, _, evidence = installed
    identity = board_recovery_engine_identity(wrapper_version="caller-value-ignored")
    assert identity["schemaVersion"] == "board-recovery-engine/v1"
    assert identity["recoveryContractVersion"] == "board-recovery-lineage/v1"
    assert "continuationContractVersion" not in identity
    assert identity["runnerBuildSha256"] == build._digest(evidence)
    assert identity["coreRef"] == "a" * 40
    assert identity["wrapperVersion"] == "wrapper:test"
    assert validate_board_recovery_engine(identity) == identity


@pytest.mark.parametrize("tree", ["core", "wrapper"])
def test_recovery_rejects_installed_source_drift(installed, tree):  # noqa: F811
    _, core, wrapper, _ = installed
    root = core if tree == "core" else wrapper
    (root / "changed.py").write_text("# altered source\n")
    with pytest.raises(ValueError, match="source mismatch"):
        board_recovery_engine_identity(wrapper_version="wrapper:test")


def test_packaged_recovery_has_no_development_fallback(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "BUILD_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(build._build_provenance, "PACKAGED_CORE_COMMIT", "a" * 40)
    monkeypatch.setenv("ESLAMS_RECOVERY_BUILD_PATH", str(tmp_path / "fake.json"))
    with pytest.raises(ValueError, match="requires trusted build evidence"):
        board_recovery_engine_identity(wrapper_version="caller-value")
    assert local_board_recovery_engine_identity(wrapper_version="test")["coreRef"] == (
        "local-development")
