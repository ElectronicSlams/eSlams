"""The nested sdist suite must not rediscover excluded listener fixtures."""
import io
import runpy
import sys
import tarfile
from pathlib import Path


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
