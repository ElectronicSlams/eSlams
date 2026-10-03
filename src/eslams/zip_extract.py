"""Bounded, portable extraction of untrusted artifact archives."""

from __future__ import annotations

import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveLimits:
    """Limits apply to archive bytes, metadata and actual decompressed bytes."""

    archive_bytes: int = 64 * 1024 * 1024
    members: int = 4096
    member_bytes: int = 64 * 1024 * 1024
    total_bytes: int = 256 * 1024 * 1024


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def extract_archive(
    path: Path, destination: Path, *, limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS
) -> None:
    """Read bounded ZIP metadata, then extract only allowed members."""
    if path.stat().st_size > limits.archive_bytes:
        raise ValueError("artifact archive exceeds the compressed-byte limit")
    with zipfile.ZipFile(path) as archive:
        confined_extract(archive, destination, limits=limits)


def confined_extract(
    archive: zipfile.ZipFile,
    destination: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> None:
    """Validate all names/declared sizes before writing; enforce sizes while reading.

    Extraction refuses links, special/encrypted members, traversal and names
    that alias on Windows or common case-insensitive filesystems. It never
    overwrites a destination file. Callers own and clean their temporary root
    if reading fails, including CRC, decompression, I/O or interruption errors.
    """
    members = archive.infolist()
    if len(members) > limits.members:
        raise ValueError("artifact archive exceeds the member-count limit")
    declared_total = 0
    seen: set[str] = set()
    files: set[str] = set()
    rows: list[tuple[zipfile.ZipInfo, str]] = []
    if destination.is_symlink():
        raise ValueError("artifact extraction directory must not be a symlink")
    root = destination.resolve()
    for member in members:
        relative = _member_path(member)
        identity = unicodedata.normalize("NFC", relative).casefold()
        if identity in seen:
            raise ValueError("artifact archive contains aliased or duplicate members")
        seen.add(identity)
        if member.file_size < 0 or member.file_size > limits.member_bytes:
            raise ValueError("artifact archive exceeds the per-member byte limit")
        declared_total += member.file_size
        if declared_total > limits.total_bytes:
            raise ValueError("artifact archive exceeds the total decompressed-byte limit")
        if not member.is_dir():
            files.add(identity)
        elif member.file_size:
            raise ValueError("artifact archive directory member contains data")
        rows.append((member, relative))
    for _, relative in rows:
        parents = Path(relative).parents
        if any(unicodedata.normalize("NFC", p.as_posix()).casefold() in files for p in parents):
            raise ValueError("artifact archive uses a file as a directory")
        target = root / relative
        current = root
        for component in Path(relative).parts:
            current /= component
            if current.is_symlink():
                raise ValueError("artifact archive member follows a symlink")
            if current.exists() and current != target and not current.is_dir():
                raise ValueError("artifact archive destination has a file as a directory")
        if target.exists() or target.is_symlink():
            raise ValueError("artifact archive member would overwrite an existing path")

    actual_total = 0
    for member, relative in rows:
        target = root / relative
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        actual_member = 0
        with archive.open(member) as source, target.open("xb") as output:
            while chunk := source.read(64 * 1024):
                actual_member += len(chunk)
                actual_total += len(chunk)
                if actual_member > limits.member_bytes or actual_total > limits.total_bytes:
                    raise ValueError("artifact archive exceeds decompressed-byte limits")
                output.write(chunk)
        if actual_member != member.file_size:
            raise ValueError("artifact archive member size does not match its declaration")


def _member_path(member: zipfile.ZipInfo) -> str:
    name = member.filename
    mode = stat.S_IFMT(member.external_attr >> 16)
    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
        raise ValueError("artifact archive contains a link, special or encrypted member")
    if name != member.orig_filename or "\\" in name or name.startswith("/"):
        raise ValueError("unsafe artifact archive path")
    relative = name[:-1] if member.is_dir() else name
    parts = relative.split("/")
    if len(relative.encode("utf-8")) > 1024 or any(
        part in ("", ".", "..")
        or part != part.rstrip(" .")
        or any(char in '<>:"|?*' or ord(char) < 32 for char in part)
        or part.split(".", 1)[0].upper() in _RESERVED_NAMES
        or len(part.encode("utf-8")) > 240
        for part in parts
    ):
        raise ValueError("unsafe artifact archive path")
    return relative
