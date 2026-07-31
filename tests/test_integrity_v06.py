from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

import eslams.arenas  # noqa: F401
from eslams.agents import (
    FunctionAgent,
    HttpAgent,
    MockProviderAgent,
    ModelProviderAgent,
    ProviderCallError,
)
from eslams.arena import Arena, registry
from eslams.artifacts import ArtifactValidator
from eslams.contracts.integrity import FailureClass
from eslams.contracts.json_schema import schema_for_version
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.runner import RunConfig, Runner, _enrich_attempt_receipts
from eslams.state import ArenaState

TEST_ED25519_PRIVATE_KEY = "base64:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def test_official_eval_rejects_fallback_policy_at_construction():
    with pytest.raises(ValueError, match="official_eval rejects fallback"):
        RunConfig(
            arena_id="tic-tac-toe",
            execution_profile="official_eval",
            on_agent_error="fallback",
        )
    with pytest.raises(ValueError, match="official_eval rejects fallback"):
        RunConfig(
            arena_id="tic-tac-toe",
            execution_profile="official_eval",
            on_illegal_action="fallback",
        )


def test_official_eval_rejects_hidden_provider_retries():
    agent = ModelProviderAgent(
        provider="openai",
        model="gpt-fixture",
        api_key_env="OPENAI_API_KEY",
        runtime_config=ProviderRuntimeConfig(max_retries=1),
    )

    with pytest.raises(ValueError, match="official orchestrator owns case retries"):
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": agent},
            execution_profile="official_eval",
        )


def test_every_failure_class_kills_scoring_without_fallback(tmp_path: Path):
    for failure_class in FailureClass:

        def fail(_request: Any, error_kind: str = failure_class.value) -> Any:
            raise ProviderCallError("fixture failure", error_kind=error_kind)

        result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                agents={
                    "player_1": FunctionAgent(
                        fail,
                        id=f"failure-{failure_class.value}",
                    )
                },
                max_turns=1,
                output_dir=tmp_path / failure_class.value,
                execution_profile="official_eval",
            )
        )
        manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))

        assert result.score.match_valid_for_scoring is False
        assert result.score.agent_error_count_by_player["player_1"] == 1
        assert result.score.fallback_action_count_by_player["player_1"] == 0
        assert failure_class.value in result.score.invalid_reason_codes
        assert manifest["match_valid_for_scoring"] is False
        assert result.trace_events == []


def test_agent_failure_mutation_is_fail_closed_across_all_fifty_arenas(tmp_path: Path):
    arena_ids = registry.list()
    assert len(arena_ids) == 50

    for arena_id in arena_ids:
        arena = registry.create(arena_id)
        agents = {
            player: FunctionAgent(
                lambda request: request.legal_actions[0],
                id=f"local-{player}",
            )
            for player in arena.players
        }
        initial = arena.initial_state(seed=1)

        def fail(_request: Any, game_id: str = arena_id) -> Any:
            raise ProviderCallError(
                f"{game_id} injected transport failure",
                error_kind="provider_transport_error",
            )

        agents[initial.active_player] = FunctionAgent(fail, id="mutated-failure-agent")
        result = Runner().run(
            RunConfig(
                arena_id=arena_id,
                agents=agents,
                max_turns=1,
                output_dir=tmp_path / arena_id,
                execution_profile="official_eval",
            )
        )

        assert result.score.match_valid_for_scoring is False, arena_id
        assert sum(result.score.agent_error_count_by_player.values()) == 1, arena_id
        assert sum(result.score.fallback_action_count_by_player.values()) == 0, arena_id
        assert result.trace_events == [], arena_id
        assert ArtifactValidator().validate(result.artifact_path) == [], arena_id


def test_june_twenty_turn_all_failure_regression_has_zero_scoreable_output(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setitem(registry._arenas, JuneFailureArena.id, JuneFailureArena)

    def fail(_request: Any) -> Any:
        raise ProviderCallError(
            "June regression fixture provider failure",
            error_kind="provider_response_schema_mismatch",
        )

    result = Runner().run(
        RunConfig(
            arena_id=JuneFailureArena.id,
            agents={"player_1": FunctionAgent(fail, id="always-failing-provider")},
            max_turns=20,
            output_dir=tmp_path,
            on_agent_error="fallback",
            execution_profile="interactive",
        )
    )
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))

    assert len(result.trace_events) == 20
    assert all(
        event.public["action_provenance"] == "fallback_action" for event in result.trace_events
    )
    assert result.score.agent_error_count_by_player == {"player_1": 20}
    assert result.score.fallback_action_count_by_player == {"player_1": 20}
    assert result.score.match_valid_for_scoring is False
    assert manifest["match_valid_for_scoring"] is False
    assert manifest["proof_row_publication_eligible"] is False


def test_signed_fallback_artifact_is_rejected_as_official_case(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", TEST_ED25519_PRIVATE_KEY)
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_KEY_ID", "integrity-fixture-key")
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(lambda _request: 99, id="illegal-agent")},
            max_turns=1,
            output_dir=tmp_path,
            on_illegal_action="fallback",
        )
    )

    report = ArtifactValidator().validate_report(
        result.artifact_path,
        profile="official_case",
    )

    assert report.signature.verified is True
    assert "fallback_action_present" in report.errors
    assert "source_score_invalid" in report.errors
    assert report.valid is False


def test_official_provider_action_without_receipt_is_unpublishable(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", TEST_ED25519_PRIVATE_KEY)

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: Any,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={"action": 0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": HttpAgent(
                    url="https://agent.fixture/act",
                    provider="openai",
                    model="gpt-fixture",
                )
            },
            max_turns=1,
            output_dir=tmp_path,
            execution_profile="official_eval",
        )
    )
    report = ArtifactValidator().validate_report(
        result.artifact_path,
        profile="official_case",
    )

    assert result.score.provider_action_count_by_player["player_1"] == 0
    assert result.score.logical_action_count_by_player["player_1"] == 1
    assert "provider_status_not_ok" in report.errors
    assert "action_provenance_incomplete" in report.errors
    assert "attempt_reconciliation_failed" in report.errors
    assert "usage_incomplete" in report.errors
    assert report.valid is False


def test_provider_action_joins_exactly_one_successful_physical_attempt(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": MockProviderAgent(scenario="success")},
            max_turns=1,
            output_dir=tmp_path,
            case_id="case_retry_001",
            case_attempt_index=2,
            shard_index=3,
        )
    )
    trace = result.trace_events[0].view("public")
    receipts = _read_jsonl(result.artifact_path / "receipts/provider_receipts.jsonl")
    manifest = json.loads((result.artifact_path / "manifest.json").read_text(encoding="utf-8"))
    public_result = json.loads(
        (result.artifact_path / "public/public_result_summary.json").read_text(encoding="utf-8")
    )

    assert len(receipts) == 1
    assert trace["action_provenance"] == "provider_action"
    assert trace["successful_attempt_event_id"] == receipts[0]["event_id"]
    assert trace["logical_action_id"] == receipts[0]["logical_action_id"]
    assert receipts[0]["seat_id"] == trace["seat"]
    assert receipts[0]["status"] == "completed"
    assert receipts[0]["action_applied"] is True
    assert receipts[0]["case_valid_for_scoring"] is True
    assert receipts[0]["attempt_kind"] == "case_retry"
    assert receipts[0]["case_attempt_index"] == 2
    assert receipts[0]["shard_index"] == 3
    assert receipts[0]["endpoint_kind"] == "mock"
    assert receipts[0]["parser_version"] == "mock-action-v1"
    assert receipts[0]["reasoning_included_in_output"] is True
    assert receipts[0]["usage_source"] == "provider"
    assert "cost_source" in receipts[0]
    assert receipts[0]["physical_run_id"] == result.run_id
    assert receipts[0]["run_id"] == result.run_id
    assert receipts[0]["official_run_id"] == result.run_id
    assert receipts[0]["run_job_id"] == result.run_id
    assert receipts[0]["environment"] == "local"
    Draft202012Validator(
        schema_for_version("eslams.provider.receipt.v2")
    ).validate(receipts[0])
    assert public_result["valid_for_scoring"] is True
    assert manifest["per_case_scoring_eligible"] is False
    assert manifest["proof_row_publication_eligible"] is False
    assert result.score.provider_action_count_by_player["player_1"] == 1


@pytest.mark.parametrize(
    ("mutation", "expected_codes"),
    [
        ("trace_reference", {"action_provenance_incomplete", "attempt_reconciliation_failed"}),
        ("replay_reference", {"action_provenance_incomplete"}),
        (
            "orphan_applied_receipt",
            {"action_provenance_incomplete", "attempt_reconciliation_failed"},
        ),
        (
            "missing_parse_status",
            {"action_provenance_incomplete", "attempt_reconciliation_failed"},
        ),
        (
            "incoherent_usage",
            {"action_provenance_incomplete", "attempt_reconciliation_failed"},
        ),
        (
            "negative_cost",
            {"action_provenance_incomplete", "attempt_reconciliation_failed"},
        ),
        (
            "negative_usage",
            {"action_provenance_incomplete", "attempt_reconciliation_failed"},
        ),
    ],
)
def test_official_case_rejects_tampered_action_attempt_joins(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
    expected_codes: set[str],
):
    monkeypatch.setenv("RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY", TEST_ED25519_PRIVATE_KEY)
    source = (
        Runner()
        .run(
            RunConfig(
                arena_id="tic-tac-toe",
                agents={"player_1": MockProviderAgent(scenario="success")},
                max_turns=1,
                output_dir=tmp_path / "source",
            )
        )
        .artifact_path
    )
    artifact = tmp_path / mutation / "tampered.eslams.d"
    shutil.copytree(source, artifact)

    if mutation == "trace_reference":
        rows = _read_jsonl(artifact / "traces/public_trace.jsonl")
        rows[0]["successful_attempt_event_id"] = "sha256:" + "f" * 64
        _write_jsonl(artifact / "traces/public_trace.jsonl", rows)
    elif mutation == "replay_reference":
        rows = _read_jsonl(artifact / "replay/replay_events.jsonl")
        provider_row = next(
            row for row in rows if row.get("action_provenance") == "provider_action"
        )
        provider_row["successful_attempt_event_id"] = "sha256:" + "e" * 64
        _write_jsonl(artifact / "replay/replay_events.jsonl", rows)
    elif mutation == "orphan_applied_receipt":
        rows = _read_jsonl(artifact / "receipts/provider_receipts.jsonl")
        orphan = dict(rows[0])
        orphan["event_id"] = "sha256:" + "d" * 64
        rows.append(orphan)
        _write_jsonl(artifact / "receipts/provider_receipts.jsonl", rows)
    else:
        rows = _read_jsonl(artifact / "receipts/provider_receipts.jsonl")
        if mutation == "missing_parse_status":
            rows[0].pop("wire_parse_status")
        elif mutation == "incoherent_usage":
            rows[0]["usage_complete"] = True
            rows[0]["usage"]["total_tokens"] = 999
        elif mutation == "negative_cost":
            rows[0]["estimated_cost"] = {"status": "ok", "cost_usd": -1}
        else:
            rows[0]["usage_complete"] = False
            rows[0]["usage"]["input_tokens"] = -1
        _write_jsonl(artifact / "receipts/provider_receipts.jsonl", rows)

    report = ArtifactValidator().validate_report(artifact, profile="official_case")

    assert expected_codes <= set(report.errors)
    assert report.valid is False


def test_duplicate_attempt_event_ids_are_rejected():
    receipt = {
        "provider": "mock",
        "model": "mock-model",
        "outcome": "provider_timeout",
        "attempt_index": 1,
    }
    with pytest.raises(ValueError, match="duplicate provider attempt event id"):
        _enrich_attempt_receipts(
            [receipt, dict(receipt)],
            run_id="run_duplicate",
            episode_id="episode_001",
            case_id="case_001",
            turn_id=0,
            player_id="player_1",
            logical_action_id="logical_001",
            latency_ms=1,
            existing_event_ids=set(),
        )


def test_existing_artifact_requires_explicit_overwrite(tmp_path: Path):
    config = RunConfig(
        arena_id="tic-tac-toe",
        run_id="run_explicit_collision",
        max_turns=1,
        output_dir=tmp_path,
    )
    first = Runner().run(config)

    with pytest.raises(FileExistsError, match="pass overwrite=True"):
        Runner().run(config)

    replacement = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            run_id="run_explicit_collision",
            max_turns=1,
            output_dir=tmp_path,
            overwrite=True,
        )
    )

    assert replacement.artifact_path == first.artifact_path
    assert ArtifactValidator().validate(replacement.artifact_path) == []


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "../../escape",
        "/tmp/escape",
        "nested/run",
        r"nested\run",
        "CON",
        "lpt1.result",
    ],
)
def test_run_id_rejects_nonportable_or_traversing_paths(run_id: str):
    with pytest.raises(ValueError, match="portable path-safe identifier"):
        RunConfig(arena_id="tic-tac-toe", run_id=run_id)


def test_overwrite_refuses_artifact_symlink_escape(tmp_path: Path):
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    artifact_link = output_dir / "safe_run.eslams.d"
    artifact_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes output_dir"):
        Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                run_id="safe_run",
                output_dir=output_dir,
                overwrite=True,
            )
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert artifact_link.is_symlink()


def test_latest_expanded_real_directory_is_never_deleted(tmp_path: Path):
    latest = tmp_path / "latest.eslams.d"
    latest.mkdir()
    sentinel = latest / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="non-symlink latest path"):
        Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                run_id="safe_latest_directory",
                output_dir=tmp_path,
            )
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert (tmp_path / "safe_latest_directory.eslams.d").is_dir()


def test_latest_archive_real_file_is_never_unlinked(tmp_path: Path):
    latest = tmp_path / "latest.eslams"
    latest.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="non-symlink latest path"):
        Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                run_id="safe_latest_archive",
                output_dir=tmp_path,
                archive=True,
            )
        )

    assert latest.read_text(encoding="utf-8") == "preserve"
    assert (tmp_path / "safe_latest_archive.eslams").is_file()
    assert (tmp_path / "safe_latest_archive.eslams.d").is_dir()
    assert not (tmp_path / "latest.eslams.d").exists()


def test_act_request_exposes_frozen_physical_attempt_join_context(tmp_path: Path):
    seen: dict[str, Any] = {}

    def capture(request: Any) -> Any:
        seen.update(request.metadata)
        return request.legal_actions[0]

    Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": FunctionAgent(capture, id="capture-agent")},
            run_id="physical_run_001",
            case_id="case_001",
            case_attempt_index=2,
            shard_index=3,
            max_turns=1,
            output_dir=tmp_path,
        )
    )

    assert seen == {
        "state_hash": seen["state_hash"],
        "physical_run_id": "physical_run_001",
        "case_id": "case_001",
        "case_attempt_index": 2,
        "shard_index": 3,
        "logical_action_id": "physical_run_001:episode_001:player_1:000000",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


class JuneFailureArena(Arena):
    id = "june-twenty-turn-failure-fixture"
    version = "1.0.0"
    players = ("player_1",)
    action_schema = {"type": "integer", "enum": [0]}
    max_turns = 20

    def initial_state(self, seed: int) -> ArenaState:
        return self._state(turn=0, terminal=False, seed=seed)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {"turn": state.turn, "you_are": player_id}

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        assert player_id == "player_1"
        assert action == 0
        next_turn = state.turn + 1
        return self._state(
            turn=next_turn,
            terminal=next_turn >= self.max_turns,
            seed=int(state.metadata["seed"]),
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(self, *, turn: int, terminal: bool, seed: int) -> ArenaState:
        return ArenaState(
            state_id=f"june-failure-{turn}",
            turn=turn,
            active_player="player_1",
            public_state={"turn": turn},
            private_state_by_player={"player_1": {}},
            legal_actions_by_player={"player_1": [] if terminal else [0]},
            scores={"player_1": float(turn)},
            terminal=terminal,
            outcome=({"winner": "player_1", "reason": "turn_limit"} if terminal else None),
            rng_commitment=f"fixture-seed:{seed}",
            render_hints={"kind": "counter"},
            metadata={"seed": seed},
        )
