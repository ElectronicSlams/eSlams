import errno
import os
import zipfile
from pathlib import Path

import pytest

from eslams.artifacts import ArtifactValidator, _artifact_file_paths, _write_archive
from eslams.runner import RunConfig, Runner


def _run(root: Path, *, overwrite=False):
    return Runner().run(RunConfig(
        arena_id="tic-tac-toe", seed=1, run_id="proof", output_dir=root,
        archive=True, overwrite=overwrite,
    ))


@pytest.mark.parametrize("failure", [OSError(errno.EMFILE, "too many files"), KeyboardInterrupt()])
@pytest.mark.parametrize("phase", ["_write_json", "_write_archive"])
@pytest.mark.parametrize("overwrite", [False, True])
def test_failed_write_preserves_prior_outputs_and_installs_no_partial_artifact(
    tmp_path: Path, monkeypatch, failure, overwrite, phase
):
    old_archive = old_manifest = None
    if overwrite:
        prior = _run(tmp_path)
        old_archive = prior.artifact_path.read_bytes()
        old_manifest = (prior.expanded_path / "manifest.json").read_bytes()

    def fail(*args):
        raise failure

    monkeypatch.setattr(f"eslams.artifacts.{phase}", fail)
    with pytest.raises(type(failure)):
        _run(tmp_path, overwrite=overwrite)
    if overwrite:
        assert (tmp_path / "proof.eslams").read_bytes() == old_archive
        assert (tmp_path / "proof.eslams.d/manifest.json").read_bytes() == old_manifest
        assert ArtifactValidator().validate(tmp_path / "proof.eslams") == []
    else:
        assert list(tmp_path.iterdir()) == []
    assert not list(tmp_path.glob(".*eslams*"))


def test_install_failure_rolls_back_both_artifact_outputs(tmp_path: Path, monkeypatch):
    prior = _run(tmp_path)
    archive = prior.artifact_path.read_bytes()
    manifest = (prior.expanded_path / "manifest.json").read_bytes()
    original = os.replace

    def fail_archive_install(source, destination):
        if Path(source).name == "payload.eslams":
            raise OSError("simulated archive install failure")
        return original(source, destination)

    monkeypatch.setattr(os, "replace", fail_archive_install)
    with pytest.raises(OSError, match="install failure"):
        _run(tmp_path, overwrite=True)
    assert prior.artifact_path.read_bytes() == archive
    assert (prior.expanded_path / "manifest.json").read_bytes() == manifest
    assert ArtifactValidator().validate(prior.artifact_path) == []
    assert not list(tmp_path.glob(".*eslams*"))


def test_artifact_walk_propagates_nested_emfile(tmp_path: Path, monkeypatch):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "proof.json").write_text("{}")
    original = os.scandir

    def fail_nested(path):
        if Path(path) == nested:
            raise OSError(errno.EMFILE, "too many files")
        return original(path)

    monkeypatch.setattr(os, "scandir", fail_nested)
    with pytest.raises(OSError) as error:
        _artifact_file_paths(tmp_path)
    assert error.value.errno == errno.EMFILE


@pytest.mark.parametrize("directory", [False, True])
def test_artifact_walk_rejects_symlink_members(tmp_path: Path, directory):
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret").write_text("private")
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "linked").symlink_to(external if directory else external / "secret",
                                target_is_directory=directory)
    with pytest.raises(ValueError, match="symlink|regular file"):
        _artifact_file_paths(root)


@pytest.mark.parametrize("timestamp", [0, 4354819200])
def test_zip_members_use_fixed_portable_timestamps(tmp_path: Path, timestamp):
    root = tmp_path / "payload"
    root.mkdir()
    member = root / "proof.json"
    member.write_bytes(b'{"proof":true}\n')
    os.utime(member, (timestamp, timestamp))
    archive = tmp_path / "proof.eslams"
    _write_archive(root, archive)
    with zipfile.ZipFile(archive) as package:
        assert package.getinfo("proof.json").date_time == (1980, 1, 1, 0, 0, 0)
        assert package.read("proof.json") == member.read_bytes()


def test_explicit_overwrite_preserves_nonartifact_directory(tmp_path: Path):
    root = tmp_path / "proof.eslams.d"
    root.mkdir()
    (root / "user-data").write_bytes(b"keep")
    with pytest.raises(ValueError, match="without an artifact manifest"):
        _run(tmp_path, overwrite=True)
    assert (root / "user-data").read_bytes() == b"keep"
