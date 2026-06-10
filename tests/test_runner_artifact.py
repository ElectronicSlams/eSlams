import hashlib
import hmac
import json
import time
import zipfile
from pathlib import Path

import pytest

from eslams.agents import FunctionAgent
from eslams.arena import Arena
from eslams.artifacts import ArtifactValidator
from eslams.cli import main
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner, _agents_for_arena, _forfeit_state, _score_summary
from eslams.state import ArenaState

TEST_ED25519_PRIVATE_KEY = "base64:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


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


def test_runner_requires_explicit_agents_for_more_than_two_players():
    with pytest.raises(ValueError, match="player_3"):
        _agents_for_arena(ThreePlayerArena(), RunConfig(arena_id="three-player"))

    agents = _agents_for_arena(
        ThreePlayerArena(),
        RunConfig(
            arena_id="three-player",
            agents={"player_3": "first-legal"},
        ),
    )

    assert set(agents) == {"player_1", "player_2", "player_3"}


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
    assert 'id="leftAgents"' in replay_text
    assert 'id="rightAgents"' in replay_text
    assert "renderPlayerPanels()" in replay_text


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
    assert not any(tmp_path.glob(".*.validate"))


def test_validator_rejects_zip_slip_archive_members(tmp_path: Path):
    archive = tmp_path / "malicious.eslams"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../outside.txt", "nope")

    with pytest.raises(ValueError, match="unsafe artifact archive path"):
        ArtifactValidator().validate(archive)

    assert not (tmp_path / "outside.txt").exists()


def test_runner_signs_artifact_when_key_is_configured(tmp_path: Path, monkeypatch):
    _set_ed25519_artifact_signing_env(monkeypatch, key_id="test-key")

    result = Runner().run(RunConfig(arena_id="connect-four", seed=11, output_dir=tmp_path))

    signature_path = result.artifact_path / "signatures" / "runner_signature.json"
    signature_text = signature_path.read_text(encoding="utf-8")
    signature = json.loads(signature_text)
    assert signature["status"] == "signed"
    assert signature["signature_version"] == "eslams-runner-signature-v2"
    assert signature["algorithm"] == "ed25519"
    assert signature["key_id"] == "test-key"
    assert TEST_ED25519_PRIVATE_KEY not in signature_text

    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.errors == []
    assert report.signature.status == "verified"
    assert report.signature.verified is True


def test_runner_stamps_platform_verified_artifact_metadata(tmp_path: Path, monkeypatch):
    _set_ed25519_artifact_signing_env(monkeypatch, key_id="platform-ci-key")

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
    _set_ed25519_artifact_signing_env(monkeypatch, key_id="gateway-ci-key")

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
            "--time-budget-ms",
            "45000",
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
    trace = _read_jsonl(expanded / "traces" / "auditor_trace.jsonl")
    assert trace[0]["request"]["time_budget_ms"] == 45_000
    assert ArtifactValidator().validate_report(artifacts[0]).signature.verified is True


def test_runner_records_suite_context_and_timeout_metadata(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            seed=3,
            output_dir=tmp_path,
            time_budget_ms=12_345,
            suite_id="official-v1",
            case_id="case-tic-tac-toe-001",
            suite_fingerprint="suite-fingerprint",
            plan_hash="plan-hash",
            shard_index=0,
            shard_count=2,
            model_id_by_player={
                "player_1": "builtin:random",
                "player_2": "builtin:first-legal",
            },
        )
    )
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))
    score = json.loads((result.artifact_path / "scores/score.json").read_text(encoding="utf-8"))
    trace = _read_jsonl(result.artifact_path / "traces/auditor_trace.jsonl")

    assert manifest["run_metadata"]["suite_id"] == "official-v1"
    assert manifest["run_metadata"]["case_id"] == "case-tic-tac-toe-001"
    assert manifest["run_metadata"]["plan_hash"] == "plan-hash"
    assert manifest["run_metadata"]["requested_time_budget_ms"] == 12_345
    assert manifest["run_metadata"]["effective_time_budget_ms"] == 12_345
    assert manifest["run_metadata"]["model_id_by_player"]["player_1"] == "builtin:random"
    assert score["metrics"]["suite_context"]["case_id"] == "case-tic-tac-toe-001"
    assert score["metrics"]["requested_time_budget_ms"] == 12_345
    assert trace[0]["suite_context"]["suite_id"] == "official-v1"
    assert trace[0]["requested_time_budget_ms"] == 12_345
    assert trace[0]["effective_time_budget_ms"] == 12_345


def test_runner_enforces_in_process_agent_timeout(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(_slow_agent, id="slow-agent")},
            output_dir=tmp_path,
            max_turns=1,
            time_budget_ms=1,
        )
    )

    trace = _read_jsonl(result.artifact_path / "traces" / "public_trace.jsonl")
    agent_io = _read_jsonl(result.artifact_path / "logs" / "agent_io.jsonl")

    assert ArtifactValidator().validate(result.artifact_path) == []
    assert "timeout" in trace[0]["markers"]
    assert agent_io[0]["response"]["metadata"]["error_kind"] == "timeout"
    assert result.score.agent_error_count_by_player["player_1"] == 1


def test_runner_honors_zero_max_turns(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            output_dir=tmp_path,
            max_turns=0,
        )
    )
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))

    assert result.trace_events == []
    assert manifest["run_metadata"]["max_turns"] == 0


def test_score_summary_primary_score_tracks_player_one():
    arena = ThreePlayerArena()
    state = _three_player_state(scores={"player_1": 0.25, "player_2": 0.9, "player_3": 0.6})

    summary = _score_summary(
        "run-primary",
        arena,
        state,
        [],
        12,
        verification_level="Local Artifact",
        match_valid_for_scoring=True,
        invalid_reason=None,
        agent_error_count_by_player={"player_1": 0, "player_2": 0, "player_3": 0},
        illegal_action_count_by_player={"player_1": 0, "player_2": 0, "player_3": 0},
        fallback_action_count_by_player={"player_1": 0, "player_2": 0, "player_3": 0},
        provider_status_by_player={
            "player_1": "local_agent",
            "player_2": "local_agent",
            "player_3": "local_agent",
        },
        suite_context={},
        requested_time_budget_ms=1000,
        effective_time_budget_ms=1000,
    )

    assert summary.primary_score == 0.25
    assert summary.metrics["best_score"] == 0.9


def test_multi_player_forfeit_preserves_remaining_scores():
    state = _three_player_state(scores={"player_1": 0.2, "player_2": 0.5, "player_3": 0.4})

    forfeited = _forfeit_state(
        state,
        forfeited_player="player_1",
        reason="player_1:illegal_action:illegal_action",
    )

    assert forfeited.terminal is True
    assert forfeited.scores == {"player_1": 0.0, "player_2": 0.5, "player_3": 0.4}
    assert forfeited.outcome == {
        "winner": "player_2",
        "reason": "forfeit",
        "invalid_reason": "player_1:illegal_action:illegal_action",
        "forfeited_player": "player_1",
        "remaining_players": ["player_2", "player_3"],
    }


def test_cli_models_list_can_emit_supported_registry_json(capsys):
    status = main(["models", "list", "--provider", "openai", "--game-agent-supported", "--json"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["model"] == "gpt-5.4-mini" for item in payload)
    assert all(item["game_agent_supported"] is True for item in payload)


def test_validator_detects_signed_manifest_tamper(tmp_path: Path, monkeypatch):
    _set_ed25519_artifact_signing_env(monkeypatch, key_id="test-key")
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=13, output_dir=tmp_path))

    manifest_path = result.artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runner_version"] = "eslams-runner:tampered"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")

    report = ArtifactValidator().validate_report(result.artifact_path)

    assert report.signature.status == "invalid"
    assert "runner signature payload does not match manifest" in report.errors


def test_validator_reads_legacy_hmac_artifact_as_untrusted(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("RUNNER_SIGNING_KEY", "legacy-runner-key")
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=14, output_dir=tmp_path))
    manifest_path = result.artifact_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["signature"] = {
        "level": "Runner Signed",
        "status": "signed",
        "algorithm": "hmac-sha256",
        "signature_path": "signatures/runner_signature.json",
        "covers": ["manifest_sha256", "artifact_id", "artifact_version", "run_id"],
    }
    manifest["runner_signature_status"] = "signed"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    signed_payload = {
        "signature_version": "eslams-runner-signature-v1",
        "algorithm": "hmac-sha256",
        "key_id": "legacy-key",
        "signed_at": "2026-06-10T00:00:00Z",
        "artifact_version": manifest["artifact_version"],
        "artifact_id": manifest["artifact_id"],
        "run_id": manifest["run_id"],
        "manifest_sha256": sha256_file(manifest_path),
    }
    signature = hmac.new(
        b"legacy-runner-key",
        canonical_json(signed_payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signature_path = result.artifact_path / "signatures" / "runner_signature.json"
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        canonical_json(
            {
                "signature_version": "eslams-runner-signature-v1",
                "status": "signed",
                "algorithm": "hmac-sha256",
                "key_id": "legacy-key",
                "signed_at": "2026-06-10T00:00:00Z",
                "signed_payload": signed_payload,
                "signature": f"hmac-sha256:{signature}",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = ArtifactValidator().validate_report(result.artifact_path)
    official_report = ArtifactValidator().validate_report(
        result.artifact_path,
        profile="official_bundle",
    )

    assert report.signature.status == "legacy_hmac"
    assert report.signature.verified is False
    assert "runner_signature_legacy_untrusted" in official_report.errors


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


def _slow_agent(_request):
    time.sleep(0.05)
    return 0


def _set_ed25519_artifact_signing_env(monkeypatch, *, key_id: str) -> None:
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", TEST_ED25519_PRIVATE_KEY)
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_KEY_ID", key_id)
    monkeypatch.delenv("RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY", raising=False)


def _three_player_state(*, scores: dict[str, float]) -> ArenaState:
    return ArenaState(
        state_id="three-player-state",
        turn=0,
        active_player="player_1",
        public_state={
            "status": "active",
            "final_validation": {"score": scores},
        },
        private_state_by_player={player: {} for player in scores},
        legal_actions_by_player={player: [0] for player in scores},
        scores=scores,
        terminal=False,
        outcome=None,
        rng_commitment={"seed": 1},
        render_hints={},
    )


class ThreePlayerArena(Arena):
    id = "three-player"
    version = "1.0.0"
    players = ("player_1", "player_2", "player_3")
    action_schema = {"type": "string"}
    max_turns = 1

    def initial_state(self, seed: int) -> ArenaState:
        raise NotImplementedError

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, object]:
        raise NotImplementedError

    def apply_action(self, state: ArenaState, player_id: str, action: object) -> ArenaState:
        raise NotImplementedError

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)


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
