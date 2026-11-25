"""No inference or private data: synthetic source archives and pinned mock calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from test_legacy_board_evidence import CANARY, archive, fixture, inspector

from eslams.agents import MockProviderAgent
from eslams.artifacts import ArtifactValidator
from eslams.board_recovery import (
    ARCHIVE_PATH,
    LABEL,
    LEDGER_PATH,
    LINEAGE_PATH,
    MODE,
    PUBLIC_PATH,
    RecoveredPosition,
    _validate_recovered_position_artifact,
    local_board_recovery_engine_identity,
    prepare_recovered_position,
    validate_recovered_position_artifact,
)
from eslams.catalogue import game_catalogue_rows
from eslams.continuation import ChessContinuation, digest_json
from eslams.contracts.board_recovery import validate_board_recovery_preparation
from eslams.contracts.versions import RUNNER_VERSION
from eslams.protocol import ActResponse
from eslams.public_replay import export_public_replay
from eslams.publication_export import export_publication_bundle
from eslams.runner import RunConfig, Runner


@pytest.fixture(autouse=True)
def synthetic_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only synthetic game tests substitute local identity inside packaged tests.
    # Installed trust/refusal has separate tests with the real resolver.
    monkeypatch.setattr("eslams.board_recovery.board_recovery_engine_identity",
                        local_board_recovery_engine_identity)


def source(tmp_path: Path, slug: str = "tic-tac-toe", *, max_turns: int | None = None,
           deadline_policy: str = "preserve-source-effective",
           requested_present: bool = True) -> tuple[Path, dict[str, Any]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    data = fixture(slug)
    arena = inspector.ARENAS[slug]()
    limit = max_turns or arena.max_turns
    metadata = {"max_turns": limit, "effective_time_budget_ms": 30000,
                "execution_profile": "interactive", "on_agent_error": "invalid-match",
                "on_illegal_action": "invalid-match", "case_id": None}
    if requested_present:
        metadata["requested_time_budget_ms"] = 30000
    data["manifest.json"].update(artifact_id="synthetic-artifact", run_metadata=metadata)
    path, digest = archive(tmp_path, data)
    custody = {"matchId": "old-match", "runId": "old-platform-run",
               "artifactId": "synthetic-artifact", "artifactKey": "private/example.eslams",
               "artifactSha256": digest, "sourcePayloadSha256": "1" * 64}
    history = {"coreVersion": "0.6.2", "arenaSlug": slug, "arenaVersion": arena.version,
               "seed": 0, "maxTurns": limit, "timeBudgetMs": 30000,
               "requestedTimeBudgetMs": 30000 if requested_present else None,
               "requestedTimeBudgetRecorded": requested_present,
               "requestedParticipants": [{"seat": seat, "modelId": "synthetic-model",
                                          "modelVersionId": "synthetic-v1"}
                                         for seat in arena.players]}
    prospective = {"wrapperVersion": "legal_action_v1:1.0.0", "runnerVersion": RUNNER_VERSION,
                   "scoringPolicyVersion": f"{slug}-score:1.0.0", "rulesSha256": digest_json(next(
                       r["public_rules"] for r in game_catalogue_rows() if r["game_id"] == slug)),
                   "maxTurns": max(limit, arena.max_turns),
                   "turnLimitPolicy": "native-arena-horizon", "deadlinePolicy": deadline_policy,
                   "timeBudgetMs": (30000 if deadline_policy == "preserve-source-effective"
                                    else None),
                   "players": [{"seat": seat, "modelId": "synthetic-model",
                                "modelVersionId": "synthetic-v1", "provider": "mock",
                                "providerModelId": "synthetic-provider-model",
                                "routeKey": "synthetic-route", "routeSha256": "2" * 64}
                               for seat in arena.players]}
    prepared = prepare_recovered_position(path, custody, history, prospective)
    validate_board_recovery_preparation(prepared)
    return path, prepared


class FutureAgent(MockProviderAgent):
    def __init__(self, *, fail_at: int | None = None, bad_route: bool = False) -> None:
        super().__init__(model="synthetic-provider-model")
        self.calls: list[Any] = []
        self.fail_at = fail_at
        self.bad_route = bad_route

    def _remember_receipt(self, receipt: dict[str, Any]) -> None:
        receipt.update(locked_model_id="synthetic-v1", model_identity_source="mock_attested",
                       model_version_id="synthetic-v1", route_key="synthetic-route",
                       route_sha256="3" * 64 if self.bad_route else "2" * 64)
        super()._remember_receipt(receipt)

    def act(self, request: Any) -> ActResponse:
        self.calls.append(copy.deepcopy(request))
        self.scenario = "provider_error" if request.turn_id == self.fail_at else "success"
        return super().act(request)


def run_child(tmp_path: Path, path: Path, prepared: dict[str, Any], *,
              agent: FutureAgent | None = None, **changes: Any) -> tuple[Any, FutureAgent]:
    agent = agent or FutureAgent()
    descriptor = prepared["descriptor"]
    recovery = RecoveredPosition(path, descriptor, prepared["targetEngine"],
                                 "child-platform-run", "child-match")
    settings = {"arena_id": descriptor["history"]["arenaSlug"], "agents": {
        "player_1": agent, "player_2": agent}, "seed": descriptor["history"]["seed"],
        "max_turns": descriptor["prospective"]["maxTurns"],
        "time_budget_ms": descriptor["prospective"]["timeBudgetMs"],
        "output_dir": tmp_path, "archive": True, "run_id": "child-core-run",
        "case_id": "child-platform-run", "run_job_id": "child-platform-run",
        "recovered_position": recovery}
    settings.update(changes)
    return Runner().run(RunConfig(**settings)), agent


@pytest.mark.parametrize("slug", list(inspector.ARENAS))
def test_finish_position_never_scores_or_rebills_history(tmp_path: Path, slug: str) -> None:
    path, prepared = source(tmp_path / "source", slug, deadline_policy="native-default")
    original = path.read_bytes()
    assert prepared["newProviderCalls"] == 0
    assert prepared["executionEligible"] is prepared["publicationEligible"] is False
    child, agent = run_child(tmp_path / "child", path, prepared)
    assert child.score.metrics["run_status"] == "completed"
    assert child.replay_events[-1].terminal
    assert child.score.match_valid_for_scoring is False
    assert child.score.model_identity_verified is False
    assert child.score.metrics["best_score"] is None
    assert child.score.metrics["sample_size"] == 0
    assert child.score.metrics["confidence_interval"] is None
    assert [r.turn_id for r in agent.calls] == list(range(1, len(child.trace_events)))
    assert all(r.time_budget_ms is None for r in agent.calls)
    first = agent.calls[0]
    assert first.run_id == "child-core-run"
    assert first.history[0]["action_provenance"] == "reconstructed_action"
    assert first.history[0]["logical_action_id"].startswith("child-core-run:")
    assert "synthetic-run" not in json.dumps(first.to_dict())
    assert CANARY not in json.dumps(first.to_dict())
    assert path.read_bytes() == original
    assert (child.expanded_path / ARCHIVE_PATH).read_bytes() == original
    manifest = json.loads((child.expanded_path / "manifest.json").read_bytes())
    # Direct reader preserves fixed errors; internal invocation helps assertion diagnosis.
    _validate_recovered_position_artifact(child.expanded_path, manifest)
    report = ArtifactValidator().validate_report(child.artifact_path)
    assert report.errors == []
    assert report.to_dict()["recovered_position"] == {
        "schemaVersion": "board-recovery-validation/v1", "status": "verified",
        "lineageSchemaVersion": "board-recovery-lineage/v1", "executionMode": MODE,
        "scoringEligible": False, "officialAdmission": False,
        "validatorScope": "child_internal_source_replay",
        "publicationRequiresAuthoritativeSourceReread": True,
    }
    public = json.loads((child.expanded_path / PUBLIC_PATH).read_bytes())
    assert public["executionLabel"] == LABEL
    assert public["competitiveWinner"] is None
    assert public["boardOutcome"] is not None
    assert set(public["historicalAssurance"].values()) == {"unverified"}
    assert public["historicalSpend"] == public["historicalFinalPhysicalCallCount"] == "unknown"
    assert public["incrementalTurns"] == len(agent.calls)
    assert "old-platform-run" not in json.dumps(public)
    assert CANARY not in json.dumps(public)
    receipts = [json.loads(line) for line in
                (child.expanded_path / "receipts/provider_receipts.jsonl")
                .read_bytes().splitlines()]
    assert len(receipts) == len(agent.calls)
    assert child.score.aggregate_usage["receiptCount"] == len(agent.calls)
    assert all(r["turn_id"] >= 1 and r["case_valid_for_scoring"] is False for r in receipts)
    assert child.trace_events[0].public["successful_attempt_event_id"] is None
    assert not {json.loads(line)["event_id"] for line in
                   (child.expanded_path / LEDGER_PATH).read_bytes().splitlines()}.intersection(
                       r["event_id"] for r in receipts)


@pytest.mark.parametrize("bad_route", [False, True])
def test_interrupted_or_wrong_route_never_advances_invalid_move(tmp_path: Path,
                                                              bad_route: bool) -> None:
    path, prepared = source(tmp_path / "source")
    child, agent = run_child(tmp_path / "child", path, prepared,
                            agent=FutureAgent(fail_at=None if bad_route else 1,
                                              bad_route=bad_route))
    assert len(child.trace_events) == 1
    assert len(agent.calls) == 1
    assert not child.replay_events[-1].terminal
    assert child.score.metrics["run_status"] == "failed"
    assert child.score.match_valid_for_scoring is False
    manifest = json.loads((child.expanded_path / "manifest.json").read_bytes())
    if bad_route:
        # Keep the audit record, but contradicting requested routing can never
        # receive the internal recovery verification marker, even without a move.
        report = ArtifactValidator().validate_report(child.artifact_path)
        assert not report.valid
        assert "recovered_position" not in report.to_dict()
    else:
        _validate_recovered_position_artifact(child.expanded_path, manifest)
        assert ArtifactValidator().validate(child.artifact_path) == []


def test_above_native_source_budget_is_preserved(tmp_path: Path) -> None:
    _, prepared = source(tmp_path, "othello", max_turns=256)
    assert prepared["descriptor"]["history"]["maxTurns"] == 256
    assert prepared["descriptor"]["prospective"]["maxTurns"] == 256


def test_missing_requested_deadline_is_not_fabricated(tmp_path: Path) -> None:
    _, prepared = source(tmp_path, requested_present=False, deadline_policy="native-default")
    assert prepared["descriptor"]["history"]["requestedTimeBudgetRecorded"] is False
    assert prepared["descriptor"]["history"]["requestedTimeBudgetMs"] is None
    assert prepared["descriptor"]["history"]["timeBudgetMs"] == 30000
    assert prepared["descriptor"]["prospective"]["timeBudgetMs"] is None


@pytest.mark.parametrize("changes", [
    {"run_id": "synthetic-run"}, {"run_id": "old-platform-run"},
    {"run_id": "child-platform-run"}, {"case_id": "other"}, {"seed": 1},
    {"time_budget_ms": 1}, {"max_turns": 100}, {"arena_id": "chess"},
    {"on_agent_error": "fallback"}, {"on_illegal_action": "forfeit"},
    {"overwrite": True}, {"execution_profile": "official_eval"},
    {"verification_level": "Server Verified"}, {"official_run_id": "official"},
])
def test_reject_changed_execution_before_calls(tmp_path: Path, changes: dict[str, Any]) -> None:
    path, prepared = source(tmp_path / "source")
    agent = FutureAgent()
    with pytest.raises(ValueError):
        run_child(tmp_path / "child", path, prepared, agent=agent, **changes)
    assert agent.calls == []


def test_changed_archive_and_engine_fail_before_calls(tmp_path: Path) -> None:
    path, prepared = source(tmp_path / "source")
    altered = copy.deepcopy(prepared)
    altered["targetEngine"]["coreSourceSha256"] = "4" * 64
    agent = FutureAgent()
    with pytest.raises(ValueError):
        run_child(tmp_path / "child", path, altered, agent=agent)
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        run_child(tmp_path / "child", path, prepared, agent=agent)
    assert agent.calls == []


@pytest.mark.parametrize("key", ["seed", "arenaVersion", "maxTurns", "timeBudgetMs"])
def test_source_constraints_are_not_authority(tmp_path: Path, key: str) -> None:
    path, prepared = source(tmp_path)
    descriptor = prepared["descriptor"]
    history = copy.deepcopy(descriptor["history"])
    history[key] = "forged" if key == "arenaVersion" else 999
    with pytest.raises(ValueError):
        prepare_recovered_position(path, descriptor["source"], history, descriptor["prospective"])


def test_substitution_rejected_and_chess_contract_is_distinct(tmp_path: Path) -> None:
    path, prepared = source(tmp_path)
    d = prepared["descriptor"]
    future = copy.deepcopy(d["prospective"])
    future["players"][0]["modelVersionId"] = "substitute"
    with pytest.raises(ValueError, match="substitution"):
        prepare_recovered_position(path, d["source"], d["history"], future)
    with pytest.raises(ValueError):
        ChessContinuation(path, d, prepared["targetEngine"], "new-platform", "new-match")


@pytest.mark.parametrize("mutation", ["score", "manifest", "label", "prefix", "archive",
                                      "ledger", "route", "replay", "assurance", "engine",
                                      "historical_cost", "official", "public_winner",
                                      "generic_label",
                                      "verified_badge"])
def test_reader_rejects_semantic_tampering(tmp_path: Path, mutation: str) -> None:
    path, prepared = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prepared)
    directory = child.expanded_path
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if mutation == "verified_badge":
        manifest["verification_level"] = "Server Verified"
    elif mutation == "manifest":
        manifest["match_valid_for_scoring"] = True
    elif mutation == "archive":
        with (directory / ARCHIVE_PATH).open("ab") as stream:
            stream.write(b"forged")
    elif mutation == "ledger":
        (directory / LEDGER_PATH).write_bytes(b"")
    else:
        target = {
            "score": "scores/score.json", "label": PUBLIC_PATH,
            "prefix": "traces/public_trace.jsonl", "route": "receipts/provider_receipts.jsonl",
            "replay": "replay/replay_events.jsonl", "assurance": LINEAGE_PATH,
            "engine": LINEAGE_PATH, "historical_cost": PUBLIC_PATH,
            "official": "scores/official_result.json",
            "public_winner": "public/public_result_summary.json",
            "generic_label": "public/public_result_summary.json",
        }[mutation]
        file = directory / target
        lines = target.endswith("jsonl")
        payload = ([json.loads(row) for row in file.read_bytes().splitlines()]
                   if lines else json.loads(file.read_bytes()))
        if mutation == "score":
            payload["metrics"]["sample_size"] = 1
        elif mutation == "label":
            payload["executionLabel"] = "Verified public proof"
        elif mutation == "prefix":
            payload[0]["logical_action_id"] = "old-id"
        elif mutation == "route":
            payload[0]["route_sha256"] = "5" * 64
        elif mutation == "replay":
            payload[1]["public_state"] = {}
        elif mutation == "assurance":
            payload["assurance"]["route"] = "verified"
        elif mutation == "engine":
            payload["targetEngine"]["coreSourceSha256"] = "6" * 64
        elif mutation == "historical_cost":
            payload["historicalSpend"] = 0
        elif mutation == "generic_label":
            payload["score"]["execution_label"] = "Verified public proof"
        elif mutation == "official":
            payload["proof_row_publication_eligible"] = True
        else:
            payload["winner"] = "player_1"
        content = "\n".join(json.dumps(row) for row in payload) if lines else json.dumps(payload)
        file.write_text(content)
    assert validate_recovered_position_artifact(directory, manifest) == [
        "invalid recovered-position evidence"]


def test_normal_publication_paths_reject_recovery(tmp_path: Path) -> None:
    path, prepared = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prepared)
    with pytest.raises(ValueError, match="separate unscored"):
        export_public_replay(child.artifact_path, tmp_path / "public")
    with pytest.raises(ValueError, match="separate unscored"):
        export_publication_bundle(kind="battlefield-sample", artifact=child.artifact_path,
                                  output_dir=tmp_path / "bundle")


def test_no_overwrite_or_second_automatic_child(tmp_path: Path) -> None:
    path, prepared = source(tmp_path / "source")
    run_child(tmp_path / "child", path, prepared)
    agent = FutureAgent()
    with pytest.raises(FileExistsError):
        run_child(tmp_path / "child", path, prepared, agent=agent)
    assert agent.calls == []


def test_missing_effective_deadline_fails_closed(tmp_path: Path) -> None:
    path, prepared = source(tmp_path / "initial")
    data = fixture()
    data["manifest.json"].update(artifact_id="synthetic-artifact", run_metadata={
        "max_turns": 9, "execution_profile": "interactive", "on_agent_error": "invalid-match",
        "on_illegal_action": "invalid-match"})
    changed, digest = archive(tmp_path, data)
    d = prepared["descriptor"]
    with pytest.raises(ValueError, match="historical_effective_deadline_missing"):
        prepare_recovered_position(changed, {**d["source"], "artifactSha256": digest},
                                   {"requestedParticipants": d["history"]["requestedParticipants"]},
                                   d["prospective"])


def test_unknown_public_replay_field_rejected(tmp_path: Path) -> None:
    path, prepared = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prepared)
    f = child.expanded_path / "replay/replay_events.jsonl"
    rows = [json.loads(line) for line in f.read_bytes().splitlines()]
    rows[0]["sourceIds"] = {"artifactKey": CANARY}
    f.write_text("\n".join(json.dumps(row) for row in rows))
    manifest = json.loads((child.expanded_path / "manifest.json").read_bytes())
    assert validate_recovered_position_artifact(child.expanded_path, manifest)
    report = ArtifactValidator().validate_report(child.expanded_path)
    assert "recovered_position" not in report.to_dict()


def test_ordinary_artifact_has_no_recovery_attestation(tmp_path: Path) -> None:
    child = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    report = ArtifactValidator().validate_report(child.artifact_path)
    assert report.valid
    assert "recovered_position" not in report.to_dict()


def test_truncated_child_is_unscored_and_not_terminal(tmp_path: Path) -> None:
    path, prep = source(tmp_path / "source", max_turns=2, deadline_policy="native-default")
    d = prep["descriptor"]
    future = {**d["prospective"], "turnLimitPolicy": "preserve-source", "maxTurns": 2}
    prep = prepare_recovered_position(path, d["source"], d["history"], future)
    child, agent = run_child(tmp_path / "child", path, prep)
    assert len(agent.calls) == 1
    assert child.score.metrics["run_status"] == "truncated"
    assert not child.score.match_valid_for_scoring
    assert not child.replay_events[-1].terminal
    assert ArtifactValidator().validate_report(child.artifact_path).valid
    result = json.loads((child.expanded_path / PUBLIC_PATH).read_bytes())
    assert result["boardOutcome"] is None and result["terminal"] is False


def test_cancelled_child_keeps_prefix_and_remains_unscored(tmp_path: Path) -> None:
    import threading

    path, prep = source(tmp_path / "source", deadline_policy="native-default")
    cancellation = threading.Event()
    cancellation.set()
    child, agent = run_child(tmp_path / "child", path, prep, cancellation=cancellation)
    assert agent.calls == []
    assert len(child.trace_events) == 1
    assert not child.score.match_valid_for_scoring
    assert "operator_cancelled" in child.score.invalid_reason_codes
    assert ArtifactValidator().validate_report(child.artifact_path).valid


def test_partial_history_derived_unknown_constraints_rejected(tmp_path: Path) -> None:
    path, prep = source(tmp_path)
    d = prep["descriptor"]
    history = {"requestedParticipants": d["history"]["requestedParticipants"]}
    assert prepare_recovered_position(path, d["source"], history,
                                      d["prospective"])["descriptor"] == d
    with pytest.raises(ValueError, match="historical_constraint_fields"):
        prepare_recovered_position(path, d["source"], {**history, "assumeVerified": True},
                                   d["prospective"])


def test_validator_wrong_public_profile_never_attests_recovery(tmp_path: Path) -> None:
    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    report = ArtifactValidator().validate_report(child.artifact_path,
                                                  profile="public_replay_package")
    assert not report.valid
    assert "recovered_position" not in report.to_dict()


@pytest.mark.parametrize("field", ["provider", "model", "requested_model", "model_version_id",
                                   "locked_model_id", "route_key", "route_sha256"])
def test_failed_receipt_route_contradictions_never_attest(tmp_path: Path, field: str) -> None:
    path, prepared = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prepared, agent=FutureAgent(fail_at=1))
    receipts = child.expanded_path / "receipts/provider_receipts.jsonl"
    rows = [json.loads(row) for row in receipts.read_bytes().splitlines()]
    assert len(rows) == 1 and rows[0]["action_applied"] is False
    rows[0][field] = "f" * 64 if field == "route_sha256" else "contradictory-future-route"
    receipts.write_text("\n".join(json.dumps(row) for row in rows))
    manifest = json.loads((child.expanded_path / "manifest.json").read_bytes())
    assert validate_recovered_position_artifact(child.expanded_path, manifest)


@pytest.mark.parametrize("relative", ["replay/replay_manifest.json", "replay/display_frames.jsonl",
                                     "public/public_manifest.json",
                                     "public/public_result_summary.json",
                                     "public_reasoning/reasoning.jsonl",
                                     "scores/official_result.json",
                                     "replay/index.html"])
def test_rehashed_public_surface_extensions_rejected(tmp_path: Path, relative: str) -> None:
    from eslams.artifacts import _file_entries
    from eslams.hashing import sha256_json

    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    target = child.expanded_path / relative
    if relative.endswith(".html"):
        target.write_text(target.read_text(encoding="utf-8") + "\n" + CANARY, encoding="utf-8")
    elif relative.endswith(".jsonl"):
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        rows[0]["sourceIds"] = {"artifactKey": CANARY}
        target.write_text("\n".join(json.dumps(row) for row in rows))
    else:
        value = json.loads(target.read_text())
        value["sourceIds"] = {"artifactKey": CANARY}
        target.write_text(json.dumps(value))
    manifest_file = child.expanded_path / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["files"] = _file_entries(child.expanded_path)
    manifest["artifact_id"] = sha256_json(manifest["files"])
    manifest_file.write_text(json.dumps(manifest))
    report = ArtifactValidator().validate_report(child.expanded_path)
    assert "invalid recovered-position evidence" in report.errors
    assert "recovered_position" not in report.to_dict()


@pytest.mark.parametrize("relative,field", [
    ("public/public_manifest.json", "verification_level"),
    ("public/public_result_summary.json", "winner"),
    ("replay/replay_manifest.json", "participants"),
])
def test_public_identity_or_badge_changes_rejected(tmp_path: Path, relative: str,
                                                 field: str) -> None:
    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    target = child.expanded_path / relative
    value = json.loads(target.read_text())
    value[field] = "Server Verified"
    target.write_text(json.dumps(value))
    manifest = json.loads((child.expanded_path / "manifest.json").read_text())
    assert validate_recovered_position_artifact(child.expanded_path, manifest)


class RetryFutureAgent(FutureAgent):
    def _remember_receipt(self, receipt: dict[str, Any]) -> None:
        for index in (1, 2):
            failed = {**copy.deepcopy(receipt), "outcome": "provider_rate_limited",
                      "status_code": 429, "attempt_index": index}
            super()._remember_receipt(failed)
        super()._remember_receipt({**receipt, "attempt_index": 3})


def test_child_receipt_count_is_not_limited_to_legacy_action_rows(tmp_path: Path) -> None:
    path, prep = source(tmp_path / "source", "othello", deadline_policy="native-default")
    child, agent = run_child(tmp_path / "child", path, prep, agent=RetryFutureAgent())
    assert child.replay_events[-1].terminal
    assert len(agent.calls) == 63
    receipts = (child.expanded_path / "receipts/provider_receipts.jsonl").read_text().splitlines()
    assert len(receipts) == 189
    report = ArtifactValidator().validate_report(child.artifact_path)
    assert report.valid, report.errors
    assert report.to_dict()["recovered_position"]["scoringEligible"] is False
    assert child.score.aggregate_usage["receiptCount"] == 189


def test_failed_attempt_recorded_history_cannot_carry_source_ids(tmp_path: Path) -> None:
    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep, agent=FutureAgent(fail_at=1))
    target = child.expanded_path / "logs/agent_io.jsonl"
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    rows[-1]["request"]["history"][0]["logical_action_id"] = CANARY
    target.write_text("\n".join(json.dumps(row) for row in rows))
    manifest = json.loads((child.expanded_path / "manifest.json").read_text())
    assert validate_recovered_position_artifact(child.expanded_path, manifest)


def test_public_export_map_cannot_expose_private_recovery_archive(tmp_path: Path) -> None:
    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    manifest = json.loads((child.expanded_path / "manifest.json").read_text())
    manifest["public_exports"]["source"] = ARCHIVE_PATH
    assert validate_recovered_position_artifact(child.expanded_path, manifest)


@pytest.mark.parametrize("field,value", [
    ("verification_level_key", "server_verified"),
    ("verification_level_label", "Server Verified"),
    ("artifact_profile_key", "official_eval"),
    ("artifact_profile_label", "Official Bundle"),
    ("artifact_profile", "official_bundle"),
    ("scoring_safety_reason", "verified"),
])
def test_manifest_display_aliases_cannot_elevate_recovery(tmp_path: Path, field: str,
                                                         value: str) -> None:
    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    manifest_path = child.expanded_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    report = ArtifactValidator().validate_report(child.expanded_path)
    assert not report.valid and "recovered_position" not in report.to_dict()


@pytest.mark.parametrize("field,value", [
    ("run_id", "synthetic-run"),
    ("arena_id", "source-private-arena"),
    ("verification_level", "Server Verified"),
    ("integrity_status", CANARY),
    ("integrity_status", "valid"),
    ("usage_complete", "false"),
    ("cost_complete", "false"),
    ("attempt_ledger_complete", "false"),
    ("usage_complete", 1),
    ("cost_complete", 1),
    ("attempt_ledger_complete", 1),
    ("usage_complete", False),
    ("cost_complete", False),
    ("attempt_ledger_complete", False),
])
def test_rehashed_score_fed_public_claims_rejected(tmp_path: Path, field: str,
                                                  value: Any) -> None:
    from eslams.artifacts import (
        _file_entries,
        _official_result_summary,
        _public_result_summary,
    )
    from eslams.events import ScoreSummary
    from eslams.hashing import sha256_json

    path, prep = source(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", path, prep)
    score_path = child.expanded_path / "scores/score.json"
    score = json.loads(score_path.read_text())
    if type(value) is bool:
        value = not score[field]
    assert score[field] != value or type(score[field]) is not type(value)
    score[field] = value
    score_path.write_text(json.dumps(score))
    summary = ScoreSummary(**score)
    for relative, projected in (
        ("public/public_result_summary.json",
         _public_result_summary(summary, "tic-tac-toe").to_dict()),
        ("scores/official_result.json", _official_result_summary(summary, "tic-tac-toe")),
    ):
        (child.expanded_path / relative).write_text(json.dumps(projected))
    manifest_path = child.expanded_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = _file_entries(child.expanded_path)
    manifest["artifact_id"] = sha256_json(manifest["files"])
    manifest_path.write_text(json.dumps(manifest))
    report = ArtifactValidator().validate_report(child.expanded_path)
    assert "invalid recovered-position evidence" in report.errors
    assert "recovered_position" not in report.to_dict()
