import json
from pathlib import Path

import pytest

from eslams.artifacts import ArtifactValidator, read_member
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("path", ["../secret", "/tmp/secret", "C:/secret",
                                  "..\\secret", "a/../secret",
                                  "signatures/../../secret", "a\x00secret", "CON", "a//secret"])
@pytest.mark.parametrize("table", ["files", "unhashed_files"])
def test_manifest_members_never_read_outside_artifact(tmp_path, monkeypatch, path, table):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    secret = tmp_path / "secret"
    secret.write_bytes(b"private outside bytes")
    manifest_path = result.artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[table].append({"path": path, "sha256": "invalid", "bytes": 1})
    manifest_path.write_text(json.dumps(manifest))
    original = Path.open

    def no_external_read(self, *a, **kw):
        assert self.resolve() != secret.resolve()
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "open", no_external_read)
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid is False
    assert any("unsafe manifest member path" in error for error in report.errors)
    assert report.scoring_eligible is False
    assert report.per_case_run_valid is False
    assert report.per_case_scoring_eligible is False
    assert report.proof_row_publication_eligible is False
    assert report.aggregate_leaderboard_eligible is False


@pytest.mark.parametrize("target", ["manifest.json", "scores/score.json", "linked-directory"])
def test_expanded_symlinks_are_rejected_before_any_member_is_read(tmp_path, monkeypatch, target):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    external = tmp_path / "external"
    external.mkdir()
    secret = external / "secret"
    secret.write_bytes(b"private")
    member = result.artifact_path / target
    if member.exists():
        member.unlink()
    member.symlink_to(external if target == "linked-directory" else secret,
                      target_is_directory=target == "linked-directory")
    original = Path.open

    def no_external_read(self, *a, **kw):
        assert self.resolve() != secret.resolve()
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "open", no_external_read)
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid is False
    assert any("regular file" in error or "symlink" in error for error in report.errors)
    assert report.archive_sha256 is None
    with pytest.raises(ValueError):
        read_member(result.artifact_path, target)


@pytest.mark.parametrize("value", [[], 1, None])
def test_nonobject_manifest_is_invalid_not_a_programming_exception(tmp_path, value):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    (result.artifact_path / "manifest.json").write_text(json.dumps(value))
    report = ArtifactValidator().validate_report(result.artifact_path, profile="auto")
    assert report.valid is False
    assert "manifest must be a JSON object" in report.errors
