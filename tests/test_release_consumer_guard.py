"""The nested sdist suite must not rediscover excluded listener fixtures."""
import io
import runpy
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


def test_nested_sdist_suite_uses_explicit_guard_and_exclusion(tmp_path, monkeypatch):
    script = runpy.run_path(str(Path(__file__).parents[1] / "scripts/verify_distributions.py"))
    state = script["main"].__globals__
    monkeypatch.setitem(state, "smoke", lambda *args: None)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "synthetic.whl").write_bytes(b"install phase separately covered")
    with tarfile.open(dist / "synthetic.tar.gz", "w:gz") as archive:
        rows = {
            "tests/test_allowed.py": "def test_admitted(): assert True\n",
            "tests/test_elapsed_deadline_regressions.py":
                "raise AssertionError('excluded synthetic fixture was imported')\n",
        }
        for name, text in rows.items():
            data = text.encode()
            member = tarfile.TarInfo("synthetic/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    guard = tmp_path / "guards"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys\n"
        "def guard(event,args):\n"
        " if event in {'socket.bind','socket.connect','socket.getaddrinfo'}:\n"
        "  raise AssertionError('network prohibited in nested suite')\n"
        "sys.addaudithook(guard)\n"
    )
    (guard / "release_offline.py").write_text("# Synthetic suite needs no transport fixtures.\n")
    monkeypatch.setattr(sys, "argv", ["verify_distributions", "--dist", str(dist),
                                    "--expected-commit", "a" * 40,
                                    "--offline-suite-guard", str(guard)])
    script["main"]()


@pytest.mark.parametrize("platform, expected", [("win32", 480), ("linux", 300), ("darwin", 300)])
def test_only_windows_sdist_source_suite_has_a_larger_cap(platform, expected, monkeypatch):
    script = runpy.run_path(str(Path(__file__).parents[1] / "scripts/verify_distributions.py"))
    monkeypatch.setattr(sys, "platform", platform)
    assert script["_sdist_suite_timeout"]() == expected

    def fake_run(cmd, **kwargs):
        assert kwargs["timeout"] == 300
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert script["run"](["synthetic-smoke"], Path(".")) == ""


def test_timeout_progress_is_bounded_and_never_emits_raw_output(monkeypatch):
    script = runpy.run_path(str(Path(__file__).parents[1] / "scripts/verify_distributions.py"))
    marker = "synthetic-do-not-log-this-value"

    def fake_run(cmd, **kwargs):
        assert kwargs["timeout"] == 480
        raise subprocess.TimeoutExpired(
            cmd, kwargs["timeout"],
            output=b"FFFFF [1%]\n" + (b"x" * 5000) + b"\n...... [ 60%]\n"
            + marker.encode(),
            stderr=b"Synthetic traceback " + marker.encode() + b"\n.xE [ 99%]\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="exceeded 480s") as error:
        script["run"]([marker], Path("."), timeout=480)
    text = str(error.value)
    assert "...... [ 60%]" in text and ".xE [ 99%]" in text
    assert "FFFFF" not in text and marker not in text and len(text) < 320
