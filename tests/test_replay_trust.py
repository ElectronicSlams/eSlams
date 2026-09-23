"""Replay archive confinement and Chess FEN HTML escaping."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest

from eslams.replay import render_replay_html
from eslams.zip_extract import confined_extract


def test_replay_zip_refuses_parent_member_outside_extract_root(tmp_path: Path, monkeypatch):
    extract_root = tmp_path / "extract"
    extract_root.mkdir()
    outside = tmp_path / "outside.txt"
    archive = tmp_path / "slip.eslams"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../outside.txt", "nope")

    monkeypatch.setattr(
        "eslams.replay.tempfile.TemporaryDirectory",
        lambda *args, **kwargs: _StickyTemp(extract_root),
    )

    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        render_replay_html(archive)

    assert not outside.exists()
    assert list(extract_root.rglob("*")) == []


def test_confined_extract_refuses_absolute_symlink_and_link_follow(tmp_path: Path):
    extract_root = tmp_path / "extract"
    extract_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (extract_root / "via").symlink_to(outside_dir, target_is_directory=True)

    absolute = tmp_path / "absolute.zip"
    with zipfile.ZipFile(absolute, "w") as zf:
        zf.writestr(str(outside), "abs")
    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        _extract(absolute, extract_root)
    assert not outside.exists()

    linked = tmp_path / "linked.zip"
    with zipfile.ZipFile(linked, "w") as zf:
        info = zipfile.ZipInfo("escape-link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, str(outside_dir))
        zf.writestr("escape-link/pwned.txt", "escaped")
    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        _extract(linked, extract_root)
    assert not (outside_dir / "pwned.txt").exists()
    assert not (extract_root / "escape-link").exists()

    followed = tmp_path / "followed.zip"
    with zipfile.ZipFile(followed, "w") as zf:
        zf.writestr("via/pwned.txt", "escaped")
    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        _extract(followed, extract_root)
    assert not (outside_dir / "pwned.txt").exists()


def test_replay_html_escapes_unknown_fen_piece_text(tmp_path: Path):
    artifact = tmp_path / "run.eslams.d"
    replay_dir = artifact / "replay"
    replay_dir.mkdir(parents=True)
    payload = "<img src=x onerror=alert(1)>"
    event = {
        "run_id": "fen-xss",
        "turn_id": 0,
        "active_player": "player_1",
        "state_hash": "abc",
        "public_state": {"fen": payload},
    }
    (replay_dir / "replay_events.jsonl").write_text(
        json.dumps(event) + "\n",
        encoding="utf-8",
    )

    page = render_replay_html(artifact, tmp_path / "replay.html")
    html = page.read_text(encoding="utf-8")
    events_blob, template = html.split("</script>", 1)

    assert payload in events_blob
    assert payload not in template
    assert "glyphs[piece] || escapeHtml(piece)" in template
    assert 'aria-label="${escapeHtml(side)} ${escapeHtml(piece)}"' in template


def _extract(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        confined_extract(zf, dest)


class _StickyTemp:
    def __init__(self, path: Path) -> None:
        self.name = str(path)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *args: object) -> bool:
        return False
