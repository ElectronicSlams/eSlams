from pathlib import Path

import pytest

from eslams.output import staged_directory
from eslams.public_replay import create_uploaded_smoke_fixture, export_public_replay
from eslams.publication_export import export_publication_bundle


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
