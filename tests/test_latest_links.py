import errno
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


def test_latest_links_follow_a_copied_or_moved_workspace(tmp_path):
    source = tmp_path / "original"
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=source, archive=True))
    assert not Path(os.readlink(source / "latest.eslams")).is_absolute()
    backup = tmp_path / "backup"
    shutil.copytree(source, backup, symlinks=True)
    source.rename(tmp_path / "moved")
    for root in (backup, tmp_path / "moved"):
        assert (root / "latest.eslams").resolve() == root / result.artifact_path.name
        assert (root / "latest.eslams.d").resolve() == root / result.expanded_path.name
        assert ArtifactValidator().validate(root / "latest.eslams") == []


def test_symlink_unavailable_keeps_completed_artifacts_and_reports_paths(
    tmp_path, monkeypatch, capsys
):
    def unavailable(*args, **kwargs):
        raise OSError(errno.EPERM, "symlink privilege unavailable")

    monkeypatch.setattr(Path, "symlink_to", unavailable)
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path, archive=True))
    assert result.artifact_path.is_file()
    assert result.expanded_path.is_dir()
    assert ArtifactValidator().validate(result.artifact_path) == []
    assert "latest links were not updated" in capsys.readouterr().err
    assert not list(tmp_path.glob(".*.link"))


def test_concurrent_latest_updates_do_not_lose_individual_results(tmp_path):
    def run(index):
        return Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                seed=index,
                output_dir=tmp_path,
                archive=True,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(run, range(24)))
    assert len({result.run_id for result in results}) == 24
    for result in results:
        manifest = json.loads((result.expanded_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"] == result.run_id
        assert ArtifactValidator().validate(result.artifact_path) == []
    assert (tmp_path / "latest.eslams").resolve().is_file()
    assert (tmp_path / "latest.eslams.d").resolve().is_dir()
    assert not list(tmp_path.glob(".*.link"))
