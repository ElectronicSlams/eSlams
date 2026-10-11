import os
import subprocess
import sys
from pathlib import Path

import pytest

from eslams.cli import main


@pytest.mark.parametrize(
    "entry",
    [
        ["-m", "eslams.cli"],
        ["-c", "from eslams.cli import main; raise SystemExit(main())"],
    ],
)
@pytest.mark.parametrize("debug", [False, True])
def test_console_target_and_module_report_user_errors_consistently(tmp_path: Path, entry, debug):
    environment = dict(os.environ)
    environment["ESLAMS_DEBUG"] = "1" if debug else "0"
    result = subprocess.run(
        [sys.executable, *entry, "validate", str(tmp_path / "missing.eslams")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert ("Traceback (most recent call last)" in result.stderr) is debug
    assert "missing.eslams" in result.stderr
    if not debug:
        assert result.stderr.startswith("error: ")


def test_cli_does_not_hide_unexpected_programming_errors(monkeypatch):
    def broken(argv):
        raise TypeError("programming defect")

    monkeypatch.setattr("eslams.cli._main", broken)
    with pytest.raises(TypeError, match="programming defect"):
        main(["arenas"])


def test_large_cli_output_accepts_an_early_closing_pipe(tmp_path: Path):
    with subprocess.Popen(
        [sys.executable, "-m", "eslams.cli", "catalogue", "games", "--json"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        assert process.stdout is not None
        assert process.stderr is not None
        assert process.stdout.readline()
        process.stdout.close()
        assert process.wait(timeout=15) == 0
        assert process.stderr.read() == ""
