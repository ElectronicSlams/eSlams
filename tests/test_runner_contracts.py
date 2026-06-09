import json
from pathlib import Path

from eslams.agents import FunctionAgent
from eslams.cli import main
from eslams.contracts.runner_job import (
    ArenaBrowserStartResponse,
    RunnerJobResult,
    validate_runner_job_result,
)
from eslams.runner import RunConfig, Runner
from eslams.runner_health import current_runner_health


def test_runner_job_result_requires_artifact_uri_when_completed():
    invalid = RunnerJobResult(
        job_id="job-1",
        runner_completed=True,
        scoring_eligible=True,
        artifact_uri=None,
    )
    valid = RunnerJobResult(
        job_id="job-1",
        runner_completed=True,
        scoring_eligible=False,
        artifact_uri="file:///runs/job-1.eslams",
        failure_category="illegal_action",
        retry_recommendation="record_non_scoring_result",
    )

    assert validate_runner_job_result(invalid) == [
        "completed runner result without artifact_uri is invalid"
    ]
    assert validate_runner_job_result(valid) == []
    assert valid.to_dict()["runner_completed"] is True
    assert valid.to_dict()["scoring_eligible"] is False


def test_runner_health_payload_includes_hashes_and_game_count():
    payload = current_runner_health()

    assert payload["schema_version"] == "eslams.runner.job.v1"
    assert payload["game_count"] == 50
    assert payload["registry_hash"]
    assert payload["renderer_vocabulary_hash"]
    assert payload["action_schema_hash"]


def test_arena_browser_start_response_contract_shape():
    payload = ArenaBrowserStartResponse(
        created=True,
        existing=False,
        session_id="session-1",
        current_turn=0,
        state_hash="state-hash",
        legal_action_count=9,
        replay_readiness="playable",
        idempotency_key={
            "user": "user-1",
            "game": "tic-tac-toe",
            "model": "builtin:first-legal",
            "client_intent": "new-session",
        },
    ).to_dict()

    assert payload["created"] is True
    assert payload["existing"] is False
    assert payload["legal_action_count"] == 9
    assert payload["idempotency_key"]["client_intent"] == "new-session"


def test_cli_runner_health(capsys):
    assert main(["runner", "health", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["game_count"] == 50


def test_cli_runner_result_completed_artifact(tmp_path: Path, capsys):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=1, output_dir=tmp_path, archive=True)
    )

    assert (
        main(
            [
                "runner",
                "result",
                "--artifact",
                str(result.artifact_path),
                "--artifact-uri",
                "s3://bucket/run.eslams",
                "--job-id",
                "job-1",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["runner_completed"] is True
    assert payload["scoring_eligible"] is True
    assert payload["artifact_uri"] == "s3://bucket/run.eslams"
    assert payload["validation_status"] == "valid"
    assert payload["artifact_key"]


def test_cli_runner_result_validation_failure(tmp_path: Path, capsys):
    artifact = tmp_path / "broken.eslams.d"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}", encoding="utf-8")

    assert (
        main(
            [
                "runner",
                "result",
                "--artifact",
                str(artifact),
                "--artifact-uri",
                "s3://bucket/broken.eslams",
                "--job-id",
                "job-broken",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["scoring_eligible"] is False
    assert payload["failure_category"] == "artifact_validation_failed"
    assert payload["retry_recommendation"] == "record_non_scoring_result"
    assert payload["validation_status"] == "invalid"


def test_cli_runner_result_non_scoring_artifact(tmp_path: Path, capsys):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(lambda _request: "not-legal")},
            on_illegal_action="invalid-match",
            seed=1,
            output_dir=tmp_path,
            archive=True,
        )
    )

    assert (
        main(
            [
                "runner",
                "result",
                "--artifact",
                str(result.artifact_path),
                "--artifact-uri",
                "s3://bucket/non-scoring.eslams",
                "--job-id",
                "job-non-scoring",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["runner_completed"] is True
    assert payload["scoring_eligible"] is False
    assert payload["retry_recommendation"] == "record_non_scoring_result"


def test_cli_run_can_emit_runner_result_json(tmp_path: Path, capsys):
    assert (
        main(
            [
                "run",
                "--arena",
                "tic-tac-toe",
                "--max-turns",
                "1",
                "--output-dir",
                str(tmp_path),
                "--runner-result-json",
                "--artifact-uri",
                "s3://bucket/from-run.eslams",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == "eslams.runner.job.v1"
    assert payload["artifact_uri"] == "s3://bucket/from-run.eslams"
