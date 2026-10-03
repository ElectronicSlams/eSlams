import io
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from eslams.artifacts import _materialize
from eslams.public_replay import export_public_replay
from eslams.replay import render_replay_html
from eslams.zip_extract import ArchiveLimits, extract_archive


@pytest.mark.parametrize(
    "name",
    ["../outside", "nested/../outside", "/absolute", "C:/drive", "..\\outside", "CON.txt"],
)
def test_archive_rejects_unsafe_names_before_writing(tmp_path: Path, name: str):
    path = tmp_path / "unsafe.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("valid.txt", "this must not be written before validation completes")
        archive.writestr(name, "unsafe")
    output = tmp_path / "extract"
    output.mkdir()

    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        extract_archive(path, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("kind", [stat.S_IFLNK, stat.S_IFIFO])
def test_archive_rejects_link_and_special_members(tmp_path: Path, kind: int):
    path = tmp_path / "special.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        member = zipfile.ZipInfo("special")
        member.create_system = 3
        member.external_attr = (kind | 0o600) << 16
        archive.writestr(member, "target")
    output = tmp_path / "extract"
    output.mkdir()
    with pytest.raises(ValueError, match="link, special or encrypted"):
        extract_archive(path, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "names", [("file", "FILE"), ("a", "a/b"), ("caf\u00e9", "cafe\u0301")]
)
def test_archive_rejects_aliases_and_file_directory_conflicts(tmp_path: Path, names):
    path = tmp_path / "aliases.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "payload")
    output = tmp_path / "extract"
    output.mkdir()
    with pytest.raises(ValueError):
        extract_archive(path, output)
    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "limits",
    [
        ArchiveLimits(members=1),
        ArchiveLimits(member_bytes=100),
        ArchiveLimits(total_bytes=200),
        ArchiveLimits(archive_bytes=10),
    ],
)
def test_archive_size_and_member_limits_are_checked_before_extracting(tmp_path: Path, limits):
    path = tmp_path / "compressed.eslams"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("one", b"x" * 128)
        archive.writestr("two", b"x" * 128)
    output = tmp_path / "extract"
    output.mkdir()
    with pytest.raises(ValueError, match="limit"):
        extract_archive(path, output, limits=limits)
    assert list(output.iterdir()) == []


def test_crc_failure_and_interruption_clean_materialized_directories(tmp_path: Path, monkeypatch):
    path = tmp_path / "corrupt.eslams"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("one", b"benign test content")
    data = bytearray(path.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", data, 26)
    data[30 + name_length + extra_length] ^= 1
    path.write_bytes(data)
    output = tmp_path / "temporary-extract"
    output.mkdir()
    monkeypatch.setattr("eslams.artifacts.tempfile.mkdtemp", lambda **_: str(output))

    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        _materialize(path)
    assert not output.exists()
    assert path.exists()

    output.mkdir()

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("eslams.artifacts.extract_archive", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _materialize(path)
    assert not output.exists()


def test_all_archive_consumers_reject_traversal_without_public_output(tmp_path: Path):
    path = tmp_path / "traversal.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../outside", "must not escape")
    output = tmp_path / "public"
    for consume in (
        lambda: _materialize(path),
        lambda: render_replay_html(path),
        lambda: export_public_replay(path, output),
    ):
        with pytest.raises(ValueError):
            consume()
    assert list(tmp_path.iterdir()) == [path]


def test_existing_nonarchives_are_distinguished_from_missing_files(tmp_path: Path):
    path = tmp_path / "not-an-archive.eslams"
    path.write_bytes(b"ordinary file")
    for consume in (_materialize, render_replay_html):
        with pytest.raises(ValueError, match="not an artifact"):
            consume(path)
        with pytest.raises(FileNotFoundError):
            consume(tmp_path / "missing")


def test_decompressed_stream_cannot_exceed_its_declared_limits(tmp_path: Path, monkeypatch):
    path = tmp_path / "metadata-mismatch.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("one", b"x")
    output = tmp_path / "extract"
    output.mkdir()
    # Fault injection: a declared one-byte member unexpectedly produces more
    # data at the decompression boundary. No large bomb is needed.
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: io.BytesIO(b"x" * 256))
    with pytest.raises(ValueError, match="decompressed-byte limits"):
        extract_archive(path, output, limits=ArchiveLimits(member_bytes=128, total_bytes=128))
    assert (output / "one").read_bytes() == b""


def test_archive_refuses_existing_files_and_symlink_destinations(tmp_path: Path):
    path = tmp_path / "existing.eslams"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("first.txt", b"new")
        archive.writestr("directory/file.txt", b"new")
    output = tmp_path / "extract"
    output.mkdir()
    existing = output / "first.txt"
    existing.write_bytes(b"existing")
    with pytest.raises(ValueError, match="overwrite"):
        extract_archive(path, output)
    assert existing.read_bytes() == b"existing"
    existing.unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "directory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        extract_archive(path, output)
    assert not existing.exists()
    assert list(outside.iterdir()) == []
