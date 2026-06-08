import json

from eslams.cli import main
from eslams.contracts.runner_job import (
    ArenaBrowserStartResponse,
    RunnerJobResult,
    validate_runner_job_result,
)
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
