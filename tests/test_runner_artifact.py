import json
from pathlib import Path

from eslams.artifacts import ArtifactValidator
from eslams.cli import main
from eslams.hashing import canonical_json, sha256_file, sha256_json
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


def test_validator_verifies_deterministic_replay_contract(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path))

    report = ArtifactValidator().validate_report(result.artifact_path)
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))
    auditor_events = _read_jsonl(result.artifact_path / "traces/auditor_trace.jsonl")

    assert report.errors == []
    assert report.deterministic_replay.status == "verified"
    assert report.deterministic_replay.verified is True
    assert report.deterministic_replay.arena_id == "tic-tac-toe"
    assert manifest["deterministic_replay"]["status"] == "recorded"
    assert auditor_events[0]["state_before"]["state_hash"] == result.replay_events[0].state_hash
    assert auditor_events[0]["state_after"]["state_hash"] == result.replay_events[1].state_hash


def test_validator_detects_replay_tamper_after_manifest_refresh(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path))
    replay_path = result.artifact_path / "replay/replay_events.jsonl"
    replay_events = _read_jsonl(replay_path)
    replay_events[1]["public_state"] = {"board": ["tampered"]}
    _write_jsonl(replay_path, replay_events)
    _refresh_manifest_hashes(result.artifact_path)

    report = ArtifactValidator().validate_report(result.artifact_path)

    assert "replay event 1 public_state does not match deterministic state" in report.errors
    assert report.deterministic_replay.status == "invalid"


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


def test_cli_run_accepts_artifact_provenance_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RUNNER_SIGNING_KEY", "test-gateway-signing-key")
    monkeypatch.setenv("RUNNER_SIGNING_KEY_ID", "gateway-ci-key")

    status = main(
        [
            "run",
            "--arena",
            "tic-tac-toe",
            "--agent",
            "first-legal",
            "--opponent",
            "first-legal",
            "--output-dir",
            str(tmp_path),
            "--verification-level",
            "Gateway Verified",
            "--eval-suite-version",
            "real-provider-smoke:1.0.0",
            "--runner-version",
            "eslams-real-eval-runner:0.1.0",
        ]
    )

    assert status == 0
    artifacts = list(tmp_path.glob("run_*.eslams"))
    assert len(artifacts) == 1
    manifest = json.loads((artifacts[0] / "manifest.json").read_text(encoding="utf-8"))
    score = json.loads((artifacts[0] / "scores" / "score.json").read_text(encoding="utf-8"))
    assert manifest["verification_level"] == "Gateway Verified"
    assert manifest["eval_suite_version"] == "real-provider-smoke:1.0.0"
    assert manifest["runner_version"] == "eslams-real-eval-runner:0.1.0"
    assert score["verification_level"] == "Gateway Verified"
    assert ArtifactValidator().validate_report(artifacts[0]).signature.verified is True


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


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _refresh_manifest_hashes(artifact_path: Path) -> None:
    manifest_path = artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(manifest["files"], key=lambda item: item["path"])
    for entry in files:
        file_path = artifact_path / entry["path"]
        entry["sha256"] = sha256_file(file_path)
        entry["bytes"] = file_path.stat().st_size
    manifest["files"] = files
    manifest["artifact_id"] = sha256_json(files)
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
