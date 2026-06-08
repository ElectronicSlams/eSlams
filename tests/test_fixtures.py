import json
from pathlib import Path

from eslams.artifacts import ArtifactValidator
from eslams.contracts.safety import scan_public_payload
from eslams.fixtures import create_artifact_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_provider_fixtures_are_redacted_and_cover_mock_scenarios():
    expected = {
        "gateway_auth_failed",
        "missing_usage",
        "parse_error",
        "provider_error",
        "success",
        "timeout",
    }
    seen = set()
    for path in sorted((ROOT / "fixtures/provider").glob("mock_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        seen.add(payload["scenario"])
        text = json.dumps(payload).lower()
        assert payload["schema_version"] == "eslams.provider.receipt.v1"
        assert payload["estimated_cost"]["status"] == "cost_unavailable"
        assert "api_key" not in text
        assert "raw_output" not in text
        assert "prompt" not in text

    assert expected <= seen


def test_public_replay_fixture_is_safe_jsonl():
    rows = [
        json.loads(line)
        for line in (ROOT / "fixtures/replay/public_tic_tac_toe.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    assert rows
    assert rows[0]["schema_version"] == "eslams.replay.public.v1"
    assert rows[1]["actor_player"] == "player_1"
    assert rows[1]["state_hash_before"] == rows[0]["state_hash"]
    assert not scan_public_payload(rows)


def test_publication_plan_fixture_is_no_secret_plan_envelope():
    payload = json.loads(
        (ROOT / "fixtures/publication/official_plan.json").read_text(encoding="utf-8")
    )

    assert payload["schema_version"] == "eslams.eval.plan.v1"
    assert payload["kind"] == "official"
    assert payload["plan_hash"]
    assert payload["required_environment_names"] == []


def test_artifact_fixture_generation_covers_signed_and_unsigned(tmp_path: Path):
    local = create_artifact_fixture("local-tic-tac-toe", tmp_path / "local_tic_tac_toe.eslams")
    signed = create_artifact_fixture("official-signed", tmp_path / "official_signed.eslams")
    unsigned = create_artifact_fixture("official-unsigned", tmp_path / "official_unsigned.eslams")

    assert ArtifactValidator().validate_report(local, profile="runner-bundle").valid is True
    signed_report = ArtifactValidator().validate_report(signed, profile="official-bundle")
    unsigned_report = ArtifactValidator().validate_report(unsigned, profile="official-bundle")

    assert signed_report.valid is True
    assert signed_report.signature.status == "unverified_missing_key"
    assert unsigned_report.valid is False
    assert "runner_signature_missing" in unsigned_report.errors


def test_materialized_artifact_fixtures_validate_when_present():
    artifacts_dir = ROOT / "fixtures/artifacts"
    expected = {
        "local_tic_tac_toe.eslams",
        "official_signed.eslams",
        "official_unsigned.eslams",
        "uploaded_replay_minimal.eslams",
    }
    available = {path.name for path in artifacts_dir.glob("*.eslams")}

    assert expected <= available
    assert (
        ArtifactValidator()
        .validate_report(artifacts_dir / "local_tic_tac_toe.eslams", profile="runner-bundle")
        .valid
        is True
    )
    assert (
        ArtifactValidator()
        .validate_report(
            artifacts_dir / "uploaded_replay_minimal.eslams",
            profile="public-replay-package",
        )
        .valid
        is True
    )
    assert (
        ArtifactValidator()
        .validate_report(artifacts_dir / "official_signed.eslams", profile="official-bundle")
        .valid
        is True
    )
    unsigned = ArtifactValidator().validate_report(
        artifacts_dir / "official_unsigned.eslams",
        profile="official-bundle",
    )
    assert unsigned.valid is False
    assert "runner_signature_missing" in unsigned.errors
