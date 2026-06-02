import json
from pathlib import Path

import pytest

from eslams.agents import FunctionAgent
from eslams.artifacts import ArtifactValidator
from eslams.cli import main
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner


def test_runner_generates_valid_connect_four_artifact(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="connect-four", seed=7, output_dir=tmp_path))
    assert result.artifact_path.exists()
    assert result.artifact_path.name.endswith(".eslams.d")
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


def test_chess_replay_html_has_coordinates_side_colored_pieces_and_split_moves(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="chess",
            seed=5,
            max_turns=1,
            output_dir=tmp_path,
        )
    )
    replay_text = (result.artifact_path / "replay" / "index.html").read_text(encoding="utf-8")

    assert "chess-frame" in replay_text
    assert "file-labels" in replay_text
    assert "rank-labels" in replay_text
    assert "piece-white" in replay_text
    assert "piece-black" in replay_text
    assert 'id="play"' in replay_text
    assert 'id="moves-player_1"' in replay_text
    assert 'id="moves-player_2"' in replay_text


def test_replay_renderer_can_materialize_archive_artifacts(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            seed=7,
            output_dir=tmp_path,
            archive=True,
        )
    )

    replay_path = render_replay_html(result.artifact_path)

    assert replay_path == result.artifact_path.with_suffix(".replay.html")
    assert replay_path.exists()
    assert "Frame" in replay_path.read_text(encoding="utf-8")


def test_runner_archive_writes_archive_expanded_copy_and_latest_links(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            seed=7,
            output_dir=tmp_path,
            archive=True,
        )
    )

    assert result.artifact_path.name.endswith(".eslams")
    assert result.artifact_path.is_file()
    assert result.expanded_path.name.endswith(".eslams.d")
    assert result.expanded_path.is_dir()
    assert (tmp_path / "latest.eslams").resolve() == result.artifact_path.resolve()
    assert (tmp_path / "latest.eslams.d").resolve() == result.expanded_path.resolve()
    assert ArtifactValidator().validate(result.artifact_path) == []
    assert ArtifactValidator().validate(result.expanded_path) == []


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


def test_cli_run_accepts_artifact_provenance_metadata(tmp_path: Path, monkeypatch, capsys):
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
    payload = json.loads(capsys.readouterr().out)
    artifacts = list(tmp_path.glob("run_*.eslams"))
    assert len(artifacts) == 1
    expanded = artifacts[0].with_suffix(".eslams.d")
    manifest = json.loads((expanded / "manifest.json").read_text(encoding="utf-8"))
    score = json.loads((expanded / "scores" / "score.json").read_text(encoding="utf-8"))
    assert manifest["verification_level"] == "Gateway Verified"
    assert manifest["eval_suite_version"] == "real-provider-smoke:1.0.0"
    assert manifest["runner_version"] == "eslams-real-eval-runner:0.1.0"
    assert score["verification_level"] == "Gateway Verified"
    assert payload["artifact"].endswith(".eslams")
    assert payload["expanded_artifact"].endswith(".eslams.d")
    assert payload["summary"]["match_valid_for_scoring"] is True
    assert ArtifactValidator().validate_report(artifacts[0]).signature.verified is True


def test_cli_models_list_can_emit_supported_registry_json(capsys):
    status = main(["models", "list", "--provider", "openai", "--game-agent-supported", "--json"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["model"] == "gpt-5.4-mini" for item in payload)
    assert all(item["game_agent_supported"] is True for item in payload)


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


def test_runner_marks_agent_error_invalid_match_artifacts(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(_raise_agent_error, id="crashing-agent")},
            output_dir=tmp_path,
            on_agent_error="invalid-match",
        )
    )

    score = json.loads((result.artifact_path / "scores" / "score.json").read_text("utf-8"))
    manifest = json.loads((result.artifact_path / "manifest.json").read_text("utf-8"))
    errors = _read_jsonl(result.artifact_path / "logs" / "errors.jsonl")

    assert ArtifactValidator().validate(result.artifact_path) == []
    assert result.score.match_valid_for_scoring is False
    assert result.score.invalid_reason == "player_1:agent_error:agent_crash,no_action"
    assert result.score.agent_error_count_by_player == {"player_1": 1, "player_2": 0}
    assert result.score.fallback_action_count_by_player == {"player_1": 0, "player_2": 0}
    assert result.trace_events == []
    assert score["match_valid_for_scoring"] is False
    assert score["invalid_reason"] == result.score.invalid_reason
    assert manifest["match_valid_for_scoring"] is False
    assert manifest["agent_error_count_by_player"]["player_1"] == 1
    assert errors[0]["policy"] == "invalid-match"
    assert errors[0]["response_metadata"]["error_kind"] == "agent_crash"


def test_runner_falls_back_after_illegal_action_by_default(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(lambda _request: 99, id="illegal-agent")},
            output_dir=tmp_path,
            max_turns=1,
        )
    )

    score = json.loads((result.artifact_path / "scores" / "score.json").read_text("utf-8"))
    trace = _read_jsonl(result.artifact_path / "traces" / "public_trace.jsonl")

    assert ArtifactValidator().validate(result.artifact_path) == []
    assert result.score.match_valid_for_scoring is True
    assert result.score.invalid_reason is None
    assert result.score.illegal_action_count_by_player == {"player_1": 1, "player_2": 0}
    assert result.score.fallback_action_count_by_player == {"player_1": 1, "player_2": 0}
    assert trace[0]["action"] == 0
    assert trace[0]["markers"] == ["illegal_action", "fallback_action"]
    assert score["metrics"]["illegal_action_count_by_player"]["player_1"] == 1


def test_runner_can_forfeit_after_illegal_action(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(lambda _request: 99, id="illegal-agent")},
            output_dir=tmp_path,
            on_illegal_action="forfeit",
        )
    )

    errors = _read_jsonl(result.artifact_path / "logs" / "errors.jsonl")

    assert ArtifactValidator().validate(result.artifact_path) == []
    assert result.score.match_valid_for_scoring is False
    assert result.score.invalid_reason == "player_1:illegal_action:illegal_action"
    assert result.score.winner == "player_2"
    assert result.score.outcome == {
        "winner": "player_2",
        "reason": "forfeit",
        "invalid_reason": result.score.invalid_reason,
    }
    assert result.score.illegal_action_count_by_player == {"player_1": 1, "player_2": 0}
    assert result.score.fallback_action_count_by_player == {"player_1": 0, "player_2": 0}
    assert result.trace_events == []
    assert errors[0]["policy"] == "forfeit"


def test_runner_rejects_unknown_failure_policy(tmp_path: Path):
    with pytest.raises(ValueError, match="on_illegal_action"):
        Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                output_dir=tmp_path,
                on_illegal_action="shrug",
            )
        )


def _raise_agent_error(_request):
    raise RuntimeError("intentional crash")


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
