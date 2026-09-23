"""Keyless Local Artifact smoke: one in-process tic-tac-toe match.

Related: #29 (local test smoke) and #18 (lab-smoke suite). This pytest is the
thin default-tree check, not a second lab-smoke suite.
"""

import json
import socket
from pathlib import Path

from eslams.cli import main

_KEYLESS_ENV = (
    "RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY",
    "RUNNER_ARTIFACT_SIGNING_KEY_ID",
    "RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)


def test_keyless_tic_tac_toe_is_a_local_artifact(tmp_path: Path, capsys, monkeypatch) -> None:
    for name in _KEYLESS_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket, "create_connection", _refuse_network)

    output_dir = tmp_path / "runs"
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
                "--seed",
                "1",
                "--execution-profile",
                "smoke",
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    run_payload = json.loads(capsys.readouterr().out)
    artifact = Path(run_payload["artifact"])
    expanded = Path(run_payload["expanded_artifact"])

    assert artifact.is_file()
    assert artifact.name.endswith(".eslams")
    assert run_payload["summary"]["match_valid_for_scoring"] is True

    manifest = json.loads((expanded / "manifest.json").read_text(encoding="utf-8"))
    _assert_local_not_official(manifest)
    assert manifest["artifact_kind"] == "local_match"
    assert manifest["artifact_profile_key"] == "runner_bundle"
    assert manifest["deterministic_replay"]["status"] == "recorded"
    assert manifest["provider_status_by_player"] == {
        "player_1": "local_agent",
        "player_2": "local_agent",
    }

    official_result = json.loads(
        (expanded / "scores" / "official_result.json").read_text(encoding="utf-8")
    )
    assert official_result["case_counts"]["non_scoring"] == 1
    assert official_result["integrity"]["validForScoring"] is True

    assert (
        main(
            [
                "validate",
                str(artifact),
                "--profile",
                "runner-bundle",
                "--summary-json",
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["schema_version"] == "eslams.artifact.validation.v1"
    assert summary["valid"] is True
    assert summary["profile"] == "runner_bundle"
    assert summary["deterministic_replay"]["verified"] is True
    assert summary["deterministic_replay"]["arena_id"] == "tic-tac-toe"
    assert summary["runner_signature_status"] == "unsigned"
    assert summary["signature"]["verified"] is False
    _assert_local_not_official(summary)

    assert (
        main(
            [
                "validate",
                str(artifact),
                "--profile",
                "official-bundle",
                "--summary-json",
            ]
        )
        == 1
    )
    official = json.loads(capsys.readouterr().out)
    assert official["valid"] is False
    assert "runner_signature_missing" in official["errors"]
    _assert_local_not_official(official)


def _assert_local_not_official(payload: dict) -> None:
    level = str(payload["verification_level"])
    key = str(payload["verification_level_key"])
    label = str(payload["verification_level_label"])
    folded = f"{level}\n{key}\n{label}".lower()

    assert level == "Local Artifact"
    assert key == "local_artifact"
    assert label == "Local Artifact"
    assert "official" not in folded
    assert "grand slam" not in folded
    assert "grand_slam" not in folded
    assert payload["per_case_scoring_eligible"] is False
    assert payload["proof_row_publication_eligible"] is False
    assert payload["aggregate_leaderboard_eligible"] is False


def _refuse_network(*_args, **_kwargs):
    raise AssertionError("keyless local smoke must not open a network connection")
