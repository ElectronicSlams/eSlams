import json
from pathlib import Path

import pytest

from eslams.artifacts import ArtifactValidator, read_member
from eslams.cli import main
from eslams.fixtures import create_artifact_fixture
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize(
    "filename", ["report.v2", "my fixture.eslams", "café.eslams", "a+b", "fix(1)"]
)
def test_fixture_filename_is_independent_of_run_id_and_preserves_siblings(tmp_path: Path, filename):
    prior = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path, archive=True))
    latest = [(tmp_path / name, (tmp_path / name).readlink())
              for name in ("latest.eslams", "latest.eslams.d")]
    unrelated = tmp_path / "report.eslams.d"
    unrelated.mkdir()
    (unrelated / "notes").write_bytes(b"precious")
    before = set(tmp_path.iterdir())
    output = tmp_path / filename
    assert create_artifact_fixture("local-tic-tac-toe", output) == output.resolve()
    assert ArtifactValidator().validate(output) == []
    manifest = json.loads(read_member(output, "manifest.json"))
    assert manifest["run_id"] == "fixture_local_tic_tac_toe"
    assert set(tmp_path.iterdir()) == before | {output}
    assert (unrelated / "notes").read_bytes() == b"precious"
    assert all(path.readlink() == target for path, target in latest)
    assert prior.artifact_path.exists()


def test_fixture_cli_overwrite_is_explicit_and_safe(tmp_path: Path):
    output = tmp_path / "fixture.eslams"
    args = ["fixtures", "artifact", "--kind", "local-tic-tac-toe", "--out", str(output)]
    assert main(args) == 0
    original = output.read_bytes()
    assert main(args) == 1
    assert output.read_bytes() == original
    assert main([*args, "--overwrite"]) == 0
    assert ArtifactValidator().validate(output) == []


def test_failed_fixture_overwrite_retains_existing_output(tmp_path: Path, monkeypatch):
    output = tmp_path / "fixture.eslams"
    output.write_bytes(b"existing")

    def fail(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr("eslams.fixtures.Runner.run", fail)
    with pytest.raises(KeyboardInterrupt):
        create_artifact_fixture("local-tic-tac-toe", output, overwrite=True)
    assert output.read_bytes() == b"existing"
    assert list(tmp_path.iterdir()) == [output]
