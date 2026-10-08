import os
from pathlib import Path

import pytest

from eslams.output import staged_directory, write_text_file
from eslams.public_replay import create_uploaded_smoke_fixture, export_public_replay
from eslams.publication_export import export_publication_bundle
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("operation", ["public-replay", "publication", "fixture"])
def test_exports_preserve_existing_files_on_invalid_input(tmp_path: Path, operation: str):
    output = tmp_path / "existing"
    output.mkdir()
    unrelated = output / "unrelated.txt"
    unrelated.write_bytes(b"must survive")

    with pytest.raises(FileExistsError, match="choose a new output directory"):
        if operation == "public-replay":
            export_public_replay(tmp_path / "missing.eslams", output)
        elif operation == "publication":
            export_publication_bundle(
                kind="uploaded-replay", artifact=tmp_path / "missing.eslams", output_dir=output
            )
        else:
            create_uploaded_smoke_fixture(output)

    assert unrelated.read_bytes() == b"must survive"
    assert list(output.iterdir()) == [unrelated]


@pytest.mark.parametrize(
    "target", ["cwd", "ancestor", "input", "input-child", "input-parent", "symlink", "git"]
)
def test_directory_export_rejects_dangerous_destinations(tmp_path: Path, monkeypatch, target: str):
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.chdir(working)
    source = tmp_path / "inputs" / "run.eslams.d"
    source.mkdir(parents=True)
    marker = source / "source.txt"
    marker.write_bytes(b"input must survive")
    link = tmp_path / "alias"
    link.symlink_to(source, target_is_directory=True)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    output = {
        "cwd": working,
        "ancestor": tmp_path,
        "input": source,
        "input-child": source / "public",
        "input-parent": source.parent,
        "symlink": link,
        "git": checkout,
    }[target]

    with pytest.raises(ValueError), staged_directory(output, sources=[source]):
        pytest.fail("unsafe export destination reached the writer")

    assert marker.read_bytes() == b"input must survive"
    assert link.is_symlink()
    assert not (source / "public").exists()


def test_failed_export_does_not_install_partial_output(tmp_path: Path):
    output = tmp_path / "new"
    with pytest.raises(FileNotFoundError):
        export_public_replay(tmp_path / "missing.eslams", output)

    assert list(tmp_path.iterdir()) == []


def test_competing_exporters_cannot_replace_each_other(tmp_path: Path):
    output = tmp_path / "result"
    with staged_directory(output) as first:
        (first / "complete.txt").write_bytes(b"complete")
        with pytest.raises(FileExistsError), staged_directory(output):
            pytest.fail("a second exporter acquired the same destination")
        assert not output.exists()

    assert (output / "complete.txt").read_bytes() == b"complete"
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize("archive", [False, True])
def test_replay_preserves_source_and_requires_explicit_output_overwrite(
    tmp_path: Path, archive: bool
):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=1, output_dir=tmp_path, archive=archive)
    )
    input_file = (
        result.artifact_path if archive else result.artifact_path / "replay" / "replay_events.jsonl"
    )
    original = input_file.read_bytes()
    with pytest.raises(ValueError, match="separate from every input"):
        render_replay_html(result.artifact_path, input_file, overwrite=True)
    alias = tmp_path / "input-alias"
    os.link(input_file, alias)
    with pytest.raises(ValueError, match="alias an input"):
        # For directories, every original member remains an input too.
        write_text_file(alias, "do not write", overwrite=True, sources=[input_file])

    output = render_replay_html(result.artifact_path)
    rendered = output.read_bytes()
    with pytest.raises(FileExistsError):
        render_replay_html(result.artifact_path)
    assert render_replay_html(result.artifact_path, overwrite=True) == output
    assert output.read_bytes() == rendered
    assert input_file.read_bytes() == original


def test_golden_export_preserves_existing_artifact_and_rejects_extra_argument(tmp_path: Path):
    from eslams.cli import main

    artifact = tmp_path / "source.eslams"
    artifact.write_bytes(b"existing artifact")
    assert main(["core", "golden", "--out", str(artifact)]) == 1
    assert artifact.read_bytes() == b"existing artifact"
    with pytest.raises(SystemExit) as error:
        main(["replay", str(artifact), "mistyped-output.html"])
    assert error.value.code == 2
    assert not (tmp_path / "mistyped-output.html").exists()
