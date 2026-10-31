"""Owned child-process crash recovery; no provider calls or listener operations."""
import os
import selectors
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from eslams.artifacts import ArtifactValidator
from eslams.output import staged_directory
from eslams.output_lock import output_lock
from eslams.runner import RunConfig, Runner


def test_persistent_guard_keeps_one_inode_and_excludes_a_second_writer(tmp_path):
    guard = tmp_path / ".result.eslams-output.lock"
    with output_lock(guard):
        inode = guard.stat().st_ino
        with pytest.raises(FileExistsError, match="in use"), output_lock(guard):
            pytest.fail("overlapping writer acquired guard")
    with output_lock(guard):
        assert guard.stat().st_ino == inode
    assert guard.exists()  # Its existence is not an ownership claim.


def test_legacy_or_unrecognized_guard_is_never_stolen_or_removed(tmp_path):
    guard = tmp_path / ".legacy.eslams-output.lock"
    for content in (b"", b"unrelated data"):
        guard.write_bytes(content)
        with pytest.raises(FileExistsError, match="legacy or unrecognized"), output_lock(guard):
            pytest.fail("unknown guard was treated as stale")
        assert guard.read_bytes() == content


def test_guard_symlink_does_not_modify_its_target(tmp_path):
    target = tmp_path / "unrelated"
    target.write_bytes(b"must survive")
    guard = tmp_path / ".result.eslams-output.lock"
    guard.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"), output_lock(guard):
        pytest.fail("followed a guard symlink")
    assert target.read_bytes() == b"must survive"


@pytest.mark.skipif(os.name == "nt",
                    reason="POSIX owned-child signal/pipe test; Windows native gate open")
@pytest.mark.parametrize("death", [signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)])
def test_owned_exporter_death_releases_writer_without_promoting_partial_output(tmp_path, death):
    output = tmp_path / "recovered"
    script = '''
import sys,time
from pathlib import Path
from eslams.output import staged_directory
with staged_directory(Path(sys.argv[1])) as staged:
    (staged / "partial.txt").write_text("not authoritative")
    print("ready",flush=True)
    time.sleep(30)
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with subprocess.Popen([sys.executable, "-c", script, str(output)], env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        assert child.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            try:
                assert selector.select(timeout=5), "owned child did not reach writer checkpoint"
                assert child.stdout.readline().strip() == "ready"
                child.send_signal(death)
                child.wait(timeout=5)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
    assert not output.exists()
    with staged_directory(output) as staged:
        (staged / "complete.txt").write_text("complete new export")
    assert (output / "complete.txt").read_text() == "complete new export"
    assert not (output / "partial.txt").exists()
    # Orphaned staging directories remain non-authoritative; no unsafe broad GC.


def test_archive_and_directory_names_remain_mutually_fenced_and_reusable(tmp_path):
    from eslams.artifacts import _staged_artifact_outputs
    paths = [tmp_path / "same.eslams", tmp_path / "same.eslams.d"]
    with (_staged_artifact_outputs(paths, overwrite=False),
          pytest.raises(FileExistsError, match="in use"),
          _staged_artifact_outputs([paths[1]], overwrite=False)):
        pytest.fail("directory-only writer bypassed archive writer")
    result = Runner().run(RunConfig("tic-tac-toe", run_id="same", output_dir=tmp_path))
    assert ArtifactValidator().validate(result.artifact_path) == []
