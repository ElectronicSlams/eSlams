"""Zip extraction confined to a destination directory."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path


def confined_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    """Extract ``archive`` under ``dest``.

    Refuses absolute member paths, ``..`` components, and symlink members.
    The same check is used for artifact materialization and replay rendering
    so a crafted archive cannot write outside the extract root.
    """
    root = dest.resolve()
    for member in archive.infolist():
        if _is_symlink_member(member):
            raise ValueError(f"unsafe artifact archive path: {member.filename}")
        member_path = (root / member.filename).resolve()
        try:
            member_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"unsafe artifact archive path: {member.filename}") from exc
    archive.extractall(root)


def _is_symlink_member(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)
