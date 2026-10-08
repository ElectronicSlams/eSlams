import json
from pathlib import Path

import pytest

from eslams.arena import registry
from eslams.artifacts import ArtifactValidator
from eslams.cli import main


@pytest.mark.parametrize(
    "game",
    [
        "bridge",
        "dou-dizhu",
        "mahjong",
        "leduc-holdem",
        "limit-texas-holdem",
        "no-limit-texas-holdem",
    ],
)
def test_cli_table_seats_are_explicit_and_artifacts_validate(tmp_path, capsys, game):
    options = ["run", "--arena", game, "--max-turns", "2", "--output-dir", str(tmp_path)]
    assert main(options) == 1
    assert "player_3" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
    for player in registry.create(game).players:
        options.extend(["--seat-agent", f"{player}=first-legal"])
    assert main(options) == 0
    payload = json.loads(capsys.readouterr().out)
    report = ArtifactValidator().validate_report(Path(payload["artifact"]))
    assert report.valid and report.deterministic_replay.verified
    assert payload["score"]["invalid_reason_codes"] == ["run_truncated"]


def test_cli_rejects_malformed_duplicate_and_unknown_seat_assignments(tmp_path, capsys):
    for assignments in (
        ["player_1"],
        ["player_1="],
        ["player_9=random"],
        ["player_1=random", "player_1=first-legal"],
    ):
        options = ["run", "--arena", "tic-tac-toe", "--output-dir", str(tmp_path)]
        for value in assignments:
            options.extend(["--seat-agent", value])
        assert main(options) == 1
        assert "--seat-agent" in capsys.readouterr().err
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("job_output", [False, True])
def test_cli_scoring_status_preserves_diagnostics_and_supports_strict_mode(
    tmp_path, capsys, job_output
):
    options = ["run", "--arena", "tic-tac-toe", "--output-dir", str(tmp_path), "--max-turns", "1"]
    if job_output:
        options.append("--runner-result-json")
    assert main(options) == 0
    assert json.loads(capsys.readouterr().out)
    assert main([*options, "--require-scoring-valid"]) == 1
    assert json.loads(capsys.readouterr().out)
    assert len(list(tmp_path.glob("run_*.eslams"))) == 2
    for artifact in tmp_path.glob("run_*.eslams"):
        report = ArtifactValidator().validate_report(artifact)
        assert report.valid and not report.scoring_eligible
    complete = [
        "run",
        "--arena",
        "tic-tac-toe",
        "--output-dir",
        str(tmp_path),
        "--require-scoring-valid",
    ]
    assert main(complete) == 0
    assert json.loads(capsys.readouterr().out)["score"]["match_valid_for_scoring"]


def test_cli_fixed_run_id_refuses_existing_output_and_explicitly_overwrites(tmp_path, capsys):
    options = [
        "run",
        "--arena",
        "tic-tac-toe",
        "--output-dir",
        str(tmp_path),
        "--run-id",
        "chosen-run",
    ]
    assert main(options) == 0
    first = json.loads(capsys.readouterr().out)
    artifact = Path(first["artifact"])
    original = artifact.read_bytes()
    assert main(options) == 1
    assert "overwrite" in capsys.readouterr().err
    assert artifact.read_bytes() == original
    assert main([*options, "--seed", "2", "--overwrite"]) == 0
    replacement = json.loads(capsys.readouterr().out)
    assert replacement["run_id"] == "chosen-run"
    assert replacement["artifact"] == first["artifact"]
    assert artifact.read_bytes() != original
    assert ArtifactValidator().validate(artifact) == []
    assert main([*options, "--run-id", "../escape"]) == 1
    assert not (tmp_path.parent / "escape.eslams").exists()


def test_catalogue_text_summarizes_availability_and_uses_actual_renderer_fields(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        "eslams.cli.availability_rows",
        lambda: [
            {"provider": "a", "model": "m1", "game_id": "chess", "status": "ready", "reason": None},
            {"provider": "b", "model": "m2", "game_id": "chess", "status": "ready", "reason": None},
            {
                "provider": "c",
                "model": "m3",
                "game_id": "chess",
                "status": "not_evaluated",
                "reason": "not_game_agent_supported",
            },
        ],
    )
    assert main(["catalogue", "availability"]) == 0
    text = capsys.readouterr().out
    assert len(text.splitlines()) == 3
    assert "chess status=ready reason=none models=2" in text
    assert "not_game_agent_supported models=1" in text
    assert main(["catalogue", "renderers"]) == 0
    text = capsys.readouterr().out
    assert "status=ready" not in text
    assert "replay_availability=" in text and "timeline_completeness=" in text
    for flag in ("--include-help", "--include-render", "--include-animation"):
        with pytest.raises(SystemExit) as error:
            main(["catalogue", "games", flag])
        assert error.value.code == 2
