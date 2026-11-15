"""Explicitly unscored public-board recovery, separate from competitive continuation.

Archive consistency is not historical route authenticity or Platform custody.
Preparation is inference-free and cannot authorize admission or publication.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from eslams.continuation import (
    _check_receipts,
    _normalize_prefix,
    chess_continuation_engine_identity,
    digest_bytes,
    digest_json,
    local_chess_continuation_engine_identity,
    new_call_matches_pin,
)
from eslams.contracts.board_recovery import (
    validate_board_recovery_descriptor,
    validate_board_recovery_engine,
    validate_board_recovery_lineage,
    validate_board_recovery_preparation,
    validate_board_recovery_public_result,
)
from eslams.events import TraceEvent
from eslams.hashing import canonical_json
from eslams.legacy_board_evidence import (
    ARENAS,
    EvidenceError,
    LegacyBoardSnapshot,
    equal,
    read,
    read_legacy_board_snapshot,
    require,
)
from eslams.state import ArenaState

MODE = "unscored_recovered_position"
LABEL = "Recovered position; historical model routing unverified"
REASON = "recovered_position_history_unverified"
LINEAGE_PATH = "recovery/lineage.json"
PREFIX_PATH = "recovery/source_prefix.json"
LEDGER_PATH = "recovery/source_provider_receipts.jsonl"
ARCHIVE_PATH = "recovery/source.eslams"
PUBLIC_PATH = "recovery/public_result.json"
ASSURANCE = dict.fromkeys(("signed_build", "route", "platform_case", "provider_authenticity"),
                          "unverified")


def _engine_from_chess(identity: dict[str, Any]) -> dict[str, Any]:
    return {**{k: v for k, v in identity.items()
               if k not in {"schemaVersion", "continuationContractVersion"}},
            "schemaVersion": "board-recovery-engine/v1",
            "recoveryContractVersion": "board-recovery-lineage/v1"}


def local_board_recovery_engine_identity(*, wrapper_version: str) -> dict[str, Any]:
    """Local test/development identity, never installed release evidence."""
    return _engine_from_chess(local_chess_continuation_engine_identity(
        wrapper_version=wrapper_version))


def board_recovery_engine_identity(*, wrapper_version: str) -> dict[str, Any]:
    """Use the same protected installed source inventory without a chess admission claim."""
    return _engine_from_chess(chess_continuation_engine_identity(wrapper_version=wrapper_version))


def _pins(snapshot: LegacyBoardSnapshot, source: dict[str, Any], history: dict[str, Any],
          prospective: dict[str, Any]) -> dict[str, Any]:
    manifest = snapshot.manifest
    metadata = manifest.get("run_metadata")
    require(isinstance(metadata, dict), "source_metadata_missing")
    assert isinstance(metadata, dict)
    require("effective_time_budget_ms" in metadata, "historical_effective_deadline_missing")
    first = snapshot.rows[0]
    derived = {
        "coreVersion": "0.6.2", "arenaSlug": snapshot.report["arena"]["slug"],
        "arenaVersion": snapshot.report["arena"]["version"],
        "seed": first["state_before"]["metadata"]["seed"],
        "maxTurns": metadata.get("max_turns"),
        "timeBudgetMs": metadata.get("effective_time_budget_ms"),
        "requestedTimeBudgetMs": metadata.get("requested_time_budget_ms"),
        "requestedTimeBudgetRecorded": "requested_time_budget_ms" in metadata,
    }
    require(set(history) <= set(derived) | {"requestedParticipants"}
            and "requestedParticipants" in history, "historical_constraint_fields")
    require(all(equal(history[k], v) for k, v in derived.items() if k in history),
            "historical_constraints_mismatch")
    history = {**copy.deepcopy(history), **derived}
    require(metadata.get("execution_profile") in {"interactive", "smoke"}
            and metadata.get("on_agent_error") == "invalid-match"
            and metadata.get("on_illegal_action") == "invalid-match", "source_profile_unsupported")
    require(source["artifactId"] == manifest.get("artifact_id")
            and source["coreRunId"] == manifest.get("run_id"), "source_identity_mismatch")
    # Old HTTP runners can lack a Platform case attestation. A contradictory
    # present value is not absence; Platform must independently verify custody.
    require(metadata.get("case_id") in {None, source["runId"]}, "source_case_mismatch")
    arena = ARENAS[derived["arenaSlug"]]()
    from eslams.catalogue import game_catalogue_rows

    rules = next(row["public_rules"] for row in game_catalogue_rows()
                 if row["game_id"] == arena.id)
    require(prospective["rulesSha256"] == digest_json(rules), "prospective_rules_mismatch")
    expected_max = (derived["maxTurns"] if prospective["turnLimitPolicy"] == "preserve-source"
                    else max(derived["maxTurns"], arena.max_turns))
    deadline = (derived["timeBudgetMs"]
                if prospective["deadlinePolicy"] == "preserve-source-effective" else None)
    require(prospective["maxTurns"] == expected_max
            and prospective["timeBudgetMs"] == deadline,
            "prospective_budget_mismatch")
    require(prospective["scoringPolicyVersion"] == f"{arena.id}-score:1.0.0",
            "prospective_scoring_policy_mismatch")
    require(len(snapshot.rows) < prospective["maxTurns"], "prefix_exhausts_horizon")
    for row in snapshot.rows:
        receipt = row["response"]["metadata"]["provider_receipt"]
        old = next(p for p in history["requestedParticipants"] if p["seat"] == row["seat"])
        if receipt.get("locked_model_id") is not None:
            require(receipt["locked_model_id"] == old["modelVersionId"],
                    "historical_requested_version_contradiction")
    for old, new in zip(history["requestedParticipants"], prospective["players"]):
        require(all(old[k] == new[k] for k in ("seat", "modelId", "modelVersionId")),
                "requested_model_substitution")
    prefix = _normalize_prefix(snapshot.rows)
    return {"schemaVersion": "board-recovery/v1", "executionMode": MODE,
            "scoringEligible": False, "officialAdmission": False,
            "source": copy.deepcopy(source), "history": {**copy.deepcopy(history), **derived},
            "prospective": copy.deepcopy(prospective),
            "prospectiveSha256": digest_json(prospective),
            "evidenceReportSha256": digest_json(snapshot.report),
            "prefix": {"acceptedPlyCount": len(prefix), "prefixSha256": digest_json(prefix),
                       "checkpointStateSha256": str(snapshot.states[-1].state_hash)[7:]}}


def prepare_recovered_position(
    source_archive: Path, source: dict[str, Any], history: dict[str, Any],
    prospective: dict[str, Any], *, target_engine_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify source bytes and caller constraints; return review material, never permission."""
    try:
        snapshot = read_legacy_board_snapshot(Path(source_archive), source["artifactSha256"])
        source = {**copy.deepcopy(source), "coreRunId": source.get(
            "coreRunId", snapshot.manifest["run_id"])}
        descriptor = _pins(snapshot, source, history, prospective)
        descriptor = dict(validate_board_recovery_descriptor(descriptor))
        target = board_recovery_engine_identity(wrapper_version=prospective["wrapperVersion"])
        validate_board_recovery_engine(target)
        require(target["wrapperVersion"] == prospective["wrapperVersion"]
                and target["runnerVersion"] == prospective["runnerVersion"],
                "prospective_engine_versions_mismatch")
        if target_engine_identity is not None:
            require(equal(target_engine_identity, target), "target_runtime_mismatch")
        result = {"schemaVersion": "board-recovery-preparation/v1", "descriptor": descriptor,
                "descriptorSha256": digest_json(descriptor), "targetEngine": target,
                "targetEngineSha256": digest_json(target), "newProviderCalls": 0,
                "executionEligible": False, "publicationEligible": False}
        return dict(validate_board_recovery_preparation(result))
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError("invalid_recovery_preparation") from None


@dataclass(frozen=True)
class RecoveredPosition:
    source_archive: Path
    descriptor: dict[str, Any]
    target_engine_identity: dict[str, Any]
    child_platform_run_id: str
    match_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptor", dict(validate_board_recovery_descriptor(
            self.descriptor)))
        object.__setattr__(self, "target_engine_identity", dict(validate_board_recovery_engine(
            self.target_engine_identity)))
        require(all(isinstance(value, str) and 0 < len(value) <= 512
                    for value in (self.child_platform_run_id, self.match_id)), "child_id_invalid")
        self.check_ids()

    def check_ids(self, core_run_id: str | None = None) -> None:
        source = self.descriptor["source"]
        old = {source[k] for k in ("matchId", "runId", "coreRunId")}
        children = [self.child_platform_run_id, self.match_id]
        if core_run_id is not None:
            children.append(core_run_id)
        require(not old.intersection(children) and len(set(children)) == len(children),
                "reused_source_or_child_identity")


@dataclass
class VerifiedRecoveredPosition:
    request: RecoveredPosition
    snapshot: LegacyBoardSnapshot

    @property
    def descriptor(self) -> dict[str, Any]:
        return self.request.descriptor

    @property
    def prefix(self) -> list[dict[str, Any]]:
        return _normalize_prefix(self.snapshot.rows)

    @property
    def state(self) -> ArenaState:
        return self.snapshot.states[-1]

    @property
    def states(self) -> list[ArenaState]:
        return self.snapshot.states

    def history(self, child_run_id: str) -> list[dict[str, Any]]:
        arena = ARENAS[self.descriptor["history"]["arenaSlug"]]()
        return [{"turn_id": i, "player": row["player"], "action": row["action"],
                 "reveal_turn": arena.action_reveal_turn(self.states[i + 1]),
                 "state_hash": self.states[i + 1].state_hash, "markers": [],
                 "action_provenance": "reconstructed_action",
                 "logical_action_id": f"{child_run_id}:episode_001:{row['player']}:{i:06d}"}
                for i, row in enumerate(self.prefix)]

    def projected_traces(self, child_run_id: str) -> list[TraceEvent]:
        result = []
        for index, row in enumerate(self.prefix):
            before, after = self.states[index:index + 2]
            common = {"state_hash_before": before.state_hash, "state_hash_after": after.state_hash,
                      "active_player": row["player"], "actor_player": row["player"],
                      "seat": row["player"], "action": row["action"], "scores": after.scores,
                      "markers": [], "action_provenance": "reconstructed_action",
                      "logical_action_id": (
                          f"{child_run_id}:episode_001:{row['player']}:{index:06d}"),
                      "successful_attempt_event_id": None}
            result.append(TraceEvent(
                event_id=f"{child_run_id}:{index:06d}", run_id=child_run_id,
                episode_id="episode_001", turn_id=index, event_type="action", public=common,
                agent_visible=common, judge=common,
                auditor={**common, "state_before": before.to_dict(),
                         "state_after": after.to_dict(), "reconstruction": {
                             "sourceEventId": row["sourceEventId"],
                             "sourceLogicalActionId": row["logicalActionId"],
                             "sourceActionProvenance": row["actionProvenance"]}}))
        return result

    def private_files(self, child_run_id: str) -> dict[str, bytes]:
        self.request.check_ids(child_run_id)
        target = self.request.target_engine_identity
        ledger = self.snapshot.ledger
        lineage = {
            "schemaVersion": "board-recovery-lineage/v1", "descriptor": self.descriptor,
            "descriptorSha256": digest_json(self.descriptor),
            "child": {"coreRunId": child_run_id,
                      "platformRunId": self.request.child_platform_run_id,
                      "matchId": self.request.match_id},
            "targetEngine": target, "targetEngineSha256": digest_json(target),
            "evidenceReport": self.snapshot.report,
            "evidenceReportSha256": digest_json(self.snapshot.report),
            "historicalLedger": {"path": LEDGER_PATH, "sha256": digest_bytes(ledger),
                                 "receiptCount": len(self.snapshot.rows)},
            "sourceArchive": {"path": ARCHIVE_PATH, "sha256": digest_bytes(self.snapshot.archive)},
            "accounting": {"historicalSpend": "unknown", "historicalFinalPhysicalCallCount":
                           "unknown", "aggregateScope": "incremental_only"},
            "assurance": {**ASSURANCE, "scoringEligible": False, "officialAdmission": False},
            "publicationRequiresAuthoritativeSourceReread": True,
        }
        validate_board_recovery_lineage(lineage)
        return {LINEAGE_PATH: canonical_json(lineage).encode() + b"\n",
                PREFIX_PATH: canonical_json(self.prefix).encode() + b"\n",
                LEDGER_PATH: ledger, ARCHIVE_PATH: self.snapshot.archive}

    def public_result(self, state: ArenaState, total_turns: int) -> dict[str, Any]:
        return public_recovery_result(self.descriptor, state, total_turns)


def public_recovery_result(descriptor: dict[str, Any], state: ArenaState,
                           total_turns: int) -> dict[str, Any]:
    prefix_count = descriptor["prefix"]["acceptedPlyCount"]
    winner = state.outcome.get("winner") if state.outcome else None
    result = {"schemaVersion": "board-recovery-public-result/v1", "executionMode": MODE,
            "executionLabel": LABEL, "scoringEligible": False, "officialAdmission": False,
            "competitiveWinner": None, "historicalAssurance": dict(ASSURANCE),
            "historicalSpend": "unknown", "historicalFinalPhysicalCallCount": "unknown",
            "accountingScope": "incremental_only", "reconstructedTurns": prefix_count,
            "incrementalTurns": total_turns - prefix_count,
            "boardOutcome": {"winnerSeat": winner, "draw": winner is None}
            if state.terminal else None, "terminal": state.terminal,
            "requestedHistoricalParticipants": descriptor["history"]["requestedParticipants"],
            "prospectiveParticipants": [{k: p[k] for k in (
                "seat", "modelId", "modelVersionId", "provider", "providerModelId")}
                for p in descriptor["prospective"]["players"]]}
    return dict(validate_board_recovery_public_result(result))


def verify_recovered_position(request: RecoveredPosition) -> VerifiedRecoveredPosition:
    request = RecoveredPosition(request.source_archive, request.descriptor,
                                request.target_engine_identity,
                                request.child_platform_run_id, request.match_id)
    prepared = prepare_recovered_position(
        request.source_archive, request.descriptor["source"], request.descriptor["history"],
        request.descriptor["prospective"], target_engine_identity=request.target_engine_identity)
    require(equal(prepared["descriptor"], request.descriptor), "source_descriptor_changed")
    snapshot = read_legacy_board_snapshot(request.source_archive,
                                          request.descriptor["source"]["artifactSha256"])
    return VerifiedRecoveredPosition(request, snapshot)


def recovery_call_matches_pin(receipts: list[dict[str, Any]], player: dict[str, Any]) -> bool:
    return new_call_matches_pin(receipts, player) and all(
        row.get("provider") == player["provider"] and all(row.get(wire) == player[pin]
            for wire, pin in (("model_version_id", "modelVersionId"),
                              ("route_key", "routeKey"), ("route_sha256", "routeSha256")))
        for row in receipts)


def validate_recovered_position_artifact(directory: Path, manifest: dict[str, Any]) -> list[str]:
    """Strict child-internal reader; authoritative Platform source reread remains mandatory."""
    try:
        _validate_recovered_position_artifact(directory, manifest)
        return []
    except Exception:
        # Neither private source errors nor reflected fields are public diagnostics.
        return ["invalid recovered-position evidence"]


def _validate_recovered_position_artifact(directory: Path, manifest: dict[str, Any]) -> None:
    lineage: dict[str, Any] = dict(validate_board_recovery_lineage(read(directory / LINEAGE_PATH)))
    descriptor = cast(dict[str, Any], lineage["descriptor"])
    target = cast(dict[str, Any], lineage["targetEngine"])
    require(lineage["descriptorSha256"] == digest_json(descriptor)
            and lineage["targetEngineSha256"] == digest_json(target), "lineage_digest")
    snapshot = read_legacy_board_snapshot(directory / ARCHIVE_PATH,
                                          descriptor["source"]["artifactSha256"])
    derived = _pins(snapshot, descriptor["source"], descriptor["history"],
                    descriptor["prospective"])
    require(equal(derived, descriptor), "source_descriptor_mismatch")
    require(equal(snapshot.report, lineage["evidenceReport"])
            and lineage["evidenceReportSha256"] == digest_json(snapshot.report), "report_mismatch")
    prefix = _normalize_prefix(snapshot.rows)
    require(equal(json.loads((directory / PREFIX_PATH).read_bytes()), prefix), "prefix_mismatch")
    ledger = (directory / LEDGER_PATH).read_bytes()
    require(ledger == snapshot.ledger and lineage["historicalLedger"] == {
        "path": LEDGER_PATH, "sha256": digest_bytes(ledger), "receiptCount": len(prefix)},
        "ledger_mismatch")
    require(lineage["sourceArchive"] == {
        "path": ARCHIVE_PATH, "sha256": digest_bytes(snapshot.archive)}, "archive_mismatch")
    child: dict[str, Any] = lineage["child"]
    request = RecoveredPosition(directory / ARCHIVE_PATH, descriptor, target,
                                child["platformRunId"], child["matchId"])
    request.check_ids(child["coreRunId"])
    verified = VerifiedRecoveredPosition(request, snapshot)
    metadata = manifest["run_metadata"]
    pins = descriptor["prospective"]
    require(manifest.get("artifact_kind") == "recovered_position"
            and metadata.get("execution_mode") == MODE
            and metadata.get("execution_label") == LABEL
            and metadata.get("accounting_scope") == "incremental_only"
            and manifest.get("verification_level") == "Local Artifact"
            and metadata.get("recovery_contract_version") == lineage["schemaVersion"]
            and not metadata.get("continuation")
            and metadata.get("execution_profile") != "official_eval", "recovery_mode_missing")
    require(manifest["run_id"] == child["coreRunId"]
            and metadata.get("case_id") == child["platformRunId"]
            and metadata.get("recovery_platform_run_id") == child["platformRunId"]
            and metadata.get("recovery_match_id") == child["matchId"], "child_identity_mismatch")
    require(metadata.get("max_turns") == pins["maxTurns"]
            and metadata.get("requested_time_budget_ms") == pins["timeBudgetMs"]
            and metadata.get("effective_time_budget_ms") == pins["timeBudgetMs"],
            "child_budget_mismatch")
    packages = read(directory / "environment/package_versions.json")
    require(target["coreVersion"] == packages.get("eslams-core")
            and target["runnerVersion"] == manifest.get("runner_version") == pins["runnerVersion"]
            and target["wrapperVersion"] == manifest.get("wrapper_version")
            == pins["wrapperVersion"],
            "target_versions_mismatch")
    trace = read(directory / "traces/auditor_trace.jsonl", lines=True)
    public = read(directory / "traces/public_trace.jsonl", lines=True)
    replay = read(directory / "replay/replay_events.jsonl", lines=True)
    require(len(prefix) <= len(trace) <= pins["maxTurns"] and len(trace) == len(public)
            and len(replay) == len(trace) + 1, "projection_count")
    arena = ARENAS[descriptor["history"]["arenaSlug"]]()
    state = arena.initial_state(descriptor["history"]["seed"])
    from eslams.artifacts import _canonical_hashed_payload
    from eslams.runner import _replay_event

    initial = _replay_event(child["coreRunId"], "episode_001", state, None, [],
                            arena=arena, actor_player=None, state_hash_before=None).to_dict()
    require(equal(replay[0], initial), "initial_replay_projection")
    require(replay[0].get("state_hash") == state.state_hash
            and replay[0].get("run_id") == child["coreRunId"]
            and replay[0].get("action") is None, "initial_replay")
    projected = verified.projected_traces(child["coreRunId"])
    for index, row in enumerate(trace):
        logical = f"{child['coreRunId']}:episode_001:{state.active_player}:{index:06d}"
        is_old = index < len(prefix)
        provenance = "reconstructed_action" if is_old else "provider_action"
        require(not state.terminal and type(row.get("turn_id")) is int
                and row.get("turn_id") == index
                and row.get("active_player") == state.active_player
                and row.get("markers") == [] and row.get("logical_action_id") == logical
                and row.get("state_hash_before") == state.state_hash
                and equal(row.get("state_before"), state.to_dict())
                and arena.is_legal(state, state.active_player, row.get("action")), "illegal_trace")
        if is_old:
            require(equal(row.get("action"), prefix[index]["action"])
                    and equal(row.get("reconstruction"),
                              projected[index].auditor["reconstruction"]),
                    "copied_prefix_mismatch")
        next_state = arena.apply_action(state, state.active_player, row["action"])
        require(row.get("state_hash_after") == next_state.state_hash
                and equal(row.get("state_after"), next_state.to_dict()), "trace_state_after")
        for projection, turn in ((row, index), (public[index], index),
                                 (replay[index + 1], index + 1)):
            require(projection.get("run_id") == child["coreRunId"]
                    and projection.get("episode_id") == "episode_001"
                    and type(projection.get("turn_id")) is int
                    and projection.get("turn_id") == turn
                    and projection.get("action_provenance") == provenance
                    and projection.get("logical_action_id") == logical
                    and projection.get("seat") == state.active_player
                    and projection.get("actor_player") == state.active_player
                    and equal(projection.get("action"), row["action"])
                    and projection.get("state_hash_before") == state.state_hash
                    and projection.get("state_hash_after") == next_state.state_hash
                    and projection.get("markers") == [], "projection_mismatch")
            require(projection.get("successful_attempt_event_id") == (
                None if is_old else row.get("successful_attempt_event_id")), "receipt_projection")
        expected_replay = _replay_event(
            child["coreRunId"], "episode_001", next_state, row["action"], [], arena=arena,
            actor_player=state.active_player, state_hash_before=state.state_hash,
            action_provenance=provenance, logical_action_id=logical,
            successful_attempt_event_id=None if is_old else row.get("successful_attempt_event_id"),
        ).to_dict()
        require(equal(replay[index + 1], expected_replay), "replay_projection_extensions")
        if is_old:
            expected_trace = _canonical_hashed_payload(projected[index].view("public"))
            require(equal(public[index], expected_trace), "public_prefix_extensions")
        else:
            expected_keys = {
                "event_id", "run_id", "episode_id", "turn_id", "event_type",
                "state_hash_before", "state_hash_after", "active_player", "actor_player", "seat",
                "action", "scores", "markers", "requested_time_budget_ms",
                "effective_time_budget_ms", "suite_context", "public_explanation",
                "action_provenance", "logical_action_id", "successful_attempt_event_id",
            }
            require(set(public[index]) == expected_keys
                    and all(equal(value, row.get(key)) for key, value in public[index].items()),
                    "public_new_trace_extensions")
        require(equal(replay[index + 1].get("public_state"), next_state.public_state)
                and replay[index + 1].get("terminal") is next_state.terminal
                and equal(replay[index + 1].get("outcome"), next_state.outcome), "replay_state")
        state = next_state
    incremental = read(directory / "receipts/provider_receipts.jsonl", lines=True)
    _check_receipts(incremental, {"players": pins["players"]}, check_pins=False)
    applied = set()
    for receipt in incremental:
        turn = receipt.get("turn_id")
        require(type(turn) is int and len(prefix) <= turn <= len(trace)
                and (not state.terminal or turn < len(trace)), "receipt_turn")
        player = trace[turn]["active_player"] if turn < len(trace) else state.active_player
        require(receipt.get("run_id") == child["coreRunId"]
                and receipt.get("physical_run_id") == child["coreRunId"]
                and receipt.get("case_id") == child["platformRunId"]
                and receipt.get("run_job_id") == child["platformRunId"]
                and receipt.get("active_player") == player
                and receipt.get("seat_id") == player
                and receipt.get("logical_action_id")
                == f"{child['coreRunId']}:episode_001:{player}:{turn:06d}"
                and receipt.get("case_valid_for_scoring") is False, "receipt_scope")
        if receipt.get("action_applied") is True:
            pin = next(p for p in pins["players"] if p["seat"] == player)
            require(recovery_call_matches_pin([receipt], pin), "receipt_route")
            require(turn < len(trace) and receipt["event_id"]
                    == trace[turn].get("successful_attempt_event_id"), "receipt_action")
            applied.add(receipt["event_id"])
    referenced = [row.get("successful_attempt_event_id") for row in trace[len(prefix):]]
    require(len(set(referenced)) == len(referenced) and set(referenced) == applied,
            "applied_receipt_reconciliation")
    from eslams.contracts.usage import aggregate_provider_receipts

    usage, cost = aggregate_provider_receipts(incremental)
    score = read(directory / "scores/score.json")
    require(equal(score.get("aggregate_usage"), usage)
            and equal(score.get("aggregate_cost"), cost), "incremental_accounting_mismatch")
    require(score.get("match_valid_for_scoring") is False
            and score.get("model_identity_verified") is False
            and score.get("scoring_safety_reason") == REASON
            and score["metrics"].get("execution_mode") == MODE
            and score["metrics"].get("execution_label") == LABEL
            and score["metrics"].get("accounting_scope") == "incremental_only"
            and score["metrics"].get("historical_spend") == "unknown"
            and score["metrics"].get("historical_final_physical_call_count") == "unknown"
            and score["metrics"].get("reconstructed_turns") == len(prefix)
            and score["metrics"].get("incremental_turns") == len(trace) - len(prefix)
            and score["metrics"].get("sample_size") == 0
            and score["metrics"].get("best_score") is None
            and score["metrics"].get("confidence_interval") is None
            and equal(score.get("outcome"), state.outcome), "scoring_elevation")
    for key in ("match_valid_for_scoring", "per_case_run_valid", "per_case_scoring_eligible",
                "proof_row_publication_eligible", "aggregate_leaderboard_eligible",
                "model_identity_verified"):
        require(manifest.get(key) is False, "manifest_scoring_elevation")
    for path in ("public/public_result_summary.json", "scores/official_result.json"):
        summary = read(directory / path)
        public_score = summary.get("score", {})
        require(public_score.get("execution_label") == LABEL
                and public_score.get("execution_mode") == MODE
                and public_score.get("historical_spend") == "unknown"
                and public_score.get("accounting_scope") == "incremental_only"
                and public_score.get("reconstructed_turns") == len(prefix)
                and public_score.get("incremental_turns") == len(trace) - len(prefix)
                and public_score.get("primary_score") is None
                and public_score.get("scores_by_player") is None, "public_ambiguous_label")
        require(summary.get("winner") is None and summary.get("valid_for_scoring") is False
                and all(summary.get(k) is False for k in (
                    "per_case_run_valid", "per_case_scoring_eligible",
                    "proof_row_publication_eligible", "aggregate_leaderboard_eligible")),
                "public_scoring_elevation")
    expected_public = public_recovery_result(descriptor, state, len(trace))
    require(equal(read(directory / PUBLIC_PATH), expected_public), "public_recovery_mismatch")
