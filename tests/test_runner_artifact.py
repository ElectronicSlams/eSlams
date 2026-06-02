import json
from pathlib import Path

from eslams.artifacts import ArtifactValidator
from eslams.hashing import canonical_json
from eslams.runner import RunConfig, Runner


def test_runner_generates_valid_connect_four_artifact(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="connect-four", seed=7, output_dir=tmp_path))
    assert result.artifact_path.exists()
    assert result.score.run_id == result.run_id
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_runner_generates_replay_events(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path))
    assert result.replay_events[0].action is None
    assert result.replay_events[-1].terminal is True


def test_runner_generates_replay_html(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="hex", seed=5, output_dir=tmp_path, max_turns=2))
    replay_path = result.artifact_path / "replay" / "index.html"
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))

    assert replay_path.exists()
    assert "eSlams Replay" in replay_path.read_text(encoding="utf-8")
    assert any(item["path"] == "replay/index.html" for item in manifest["files"])


def test_runner_signs_artifact_when_key_is_configured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNNER_SIGNING_KEY", "test-runner-signing-key")
    monkeypatch.setenv("RUNNER_SIGNING_KEY_ID", "test-key")

    result = Runner().run(RunConfig(arena_id="connect-four", seed=11, output_dir=tmp_path))

    signature_path = result.artifact_path / "signatures" / "runner_signature.json"
    signature_text = signature_path.read_text(encoding="utf-8")
    signature = json.loads(signature_text)
    assert signature["status"] == "signed"
    assert signature["algorithm"] == "hmac-sha256"
    assert signature["key_id"] == "test-key"
    assert "test-runner-signing-key" not in signature_text

    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.errors == []
    assert report.signature.status == "verified"
    assert report.signature.verified is True


def test_runner_stamps_platform_verified_artifact_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNNER_SIGNING_KEY", "test-platform-signing-key")
    monkeypatch.setenv("RUNNER_SIGNING_KEY_ID", "platform-ci-key")

    result = Runner().run(
        RunConfig(
            arena_id="connect-four",
            seed=19,
            output_dir=tmp_path,
            verification_level="Platform Verified",
            eval_suite_version="platform-public-run:1.0.0",
            runner_version="eslams-platform-runner:0.1.0",
        )
    )
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))
    score = json.loads((result.artifact_path / "scores" / "score.json").read_text(encoding="utf-8"))

    assert manifest["verification_level"] == "Platform Verified"
    assert manifest["eval_suite_version"] == "platform-public-run:1.0.0"
    assert manifest["runner_version"] == "eslams-platform-runner:0.1.0"
    assert score["verification_level"] == "Platform Verified"

    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.errors == []
    assert report.signature.verified is True


def test_validator_detects_signed_manifest_tamper(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNNER_SIGNING_KEY", "test-runner-signing-key")
    monkeypatch.setenv("RUNNER_SIGNING_KEY_ID", "test-key")
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=13, output_dir=tmp_path))

    manifest_path = result.artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runner_version"] = "eslams-runner:tampered"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")

    report = ArtifactValidator().validate_report(result.artifact_path)

    assert report.signature.status == "invalid"
    assert "runner signature payload does not match manifest" in report.errors
