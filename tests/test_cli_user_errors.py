"""Ordinary user mistakes exit with one concise error line, not a traceback."""

from __future__ import annotations

from pathlib import Path

import pytest

from eslams.cli import main


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.err


def _assert_concise(err: str, *needles: str) -> None:
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1, err
    assert lines[0].startswith("eslams: error: ")
    assert "Traceback" not in err
    for needle in needles:
        assert needle in lines[0]


@pytest.mark.parametrize("agent", ["bogus", "notaprovider:foo"])
def test_run_unknown_agent_is_concise(agent: str, tmp_path: Path, capsys):
    code, err = _run(
        ["run", "--arena", "tic-tac-toe", "--agent", agent, "--output-dir", str(tmp_path)],
        capsys,
    )
    assert code == 2
    _assert_concise(err, "unknown agent", agent, "first-legal", "random")
    assert list(tmp_path.iterdir()) == []


def test_run_unknown_opponent_is_concise(tmp_path: Path, capsys):
    code, err = _run(
        [
            "run",
            "--arena",
            "tic-tac-toe",
            "--agent",
            "random",
            "--opponent",
            "bogus",
            "--output-dir",
            str(tmp_path),
        ],
        capsys,
    )
    assert code == 2
    _assert_concise(err, "unknown agent", "bogus")


@pytest.mark.parametrize("command", ["validate", "replay"])
def test_missing_artifact_is_concise(command: str, tmp_path: Path, capsys):
    missing = tmp_path / "nonexistent.eslams"
    code, err = _run([command, str(missing)], capsys)
    assert code == 2
    _assert_concise(err, "artifact not found", "nonexistent.eslams")


@pytest.mark.parametrize("command", ["validate", "replay"])
def test_non_archive_file_is_not_reported_as_missing(command: str, tmp_path: Path, capsys):
    not_zip = tmp_path / "notes.txt"
    not_zip.write_text("hello\n", encoding="utf-8")
    code, err = _run([command, str(not_zip)], capsys)
    assert code == 2
    _assert_concise(err, "notes.txt", "not an artifact directory or .eslams zip")
    assert "not found" not in err


def test_arena_start_invalid_players_json_is_concise(capsys):
    argv = [
        "arena",
        "start",
        "--game",
        "tic-tac-toe",
        "--variant",
        "standard",
        "--seed",
        "1",
        "--players-json",
        "not json",
    ]
    code, err = _run(argv, capsys)
    assert code == 2
    _assert_concise(err, "--players-json is not valid JSON")


def test_arena_start_non_object_json_is_concise(capsys):
    argv = [
        "arena",
        "start",
        "--game",
        "tic-tac-toe",
        "--variant",
        "standard",
        "--seed",
        "1",
        "--players-json",
        "[1]",
    ]
    code, err = _run(argv, capsys)
    assert code == 2
    _assert_concise(err, "--players-json must be a JSON object")


def test_core_step_missing_request_file_is_concise(tmp_path: Path, capsys):
    code, err = _run(["core", "step", "--request", str(tmp_path / "nofile.json")], capsys)
    assert code == 2
    _assert_concise(err, "cannot read", "nofile.json")


def test_core_step_invalid_json_file_is_concise(tmp_path: Path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    code, err = _run(["core", "step", "--request", str(bad)], capsys)
    assert code == 2
    _assert_concise(err, "bad.json", "not valid JSON")


def test_bench_unknown_game_is_concise(capsys):
    code, err = _run(["bench", "arena-step", "--games", "nope", "--iterations", "1"], capsys)
    assert code == 2
    _assert_concise(err, "unknown arena 'nope'", "eslams arenas")


def test_schemas_export_unwritable_destination_is_concise(tmp_path: Path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    code, err = _run(["schemas", "export", "--out", str(blocker / "sub")], capsys)
    assert code == 2
    _assert_concise(err, "cannot export schemas")


def test_valid_run_and_validate_still_work(tmp_path: Path, capsys):
    out = tmp_path / "runs"
    assert (
        main(
            [
                "run",
                "--arena",
                "tic-tac-toe",
                "--agent",
                "first-legal",
                "--opponent",
                "first-legal",
                "--output-dir",
                str(out),
            ]
        )
        == 0
    )
    capsys.readouterr()
    artifact = next(out.glob("*.eslams"))
    assert main(["validate", str(artifact)]) == 0
    assert main(["replay", str(artifact)]) == 0
