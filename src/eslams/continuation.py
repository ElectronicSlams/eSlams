"""Verified chess continuation. Source custody is distinct from child replay validity.

Only complete, byte-pinned archives are accepted. No state/FEN input is exposed.
External execution pins are supplied by trusted Platform custody, not inferred.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from eslams.arena import validate_seed
from eslams.arenas.chess import ChessArena
from eslams.contracts.provider import (
    provider_attempt_event_id,
    provider_receipt_validation_errors,
)
from eslams.contracts.versions import CORE_PACKAGE_VERSION, RUNNER_VERSION
from eslams.events import TraceEvent
from eslams.hashing import canonical_json
from eslams.state import ArenaState
from eslams.zip_extract import DEFAULT_ARCHIVE_LIMITS

DESCRIPTOR_VERSION = "chess-continuation/v1"
LEGACY_LINEAGE_VERSION = "chess-continuation-lineage/v1"
LINEAGE_VERSION = "chess-continuation-lineage/v2"
CHILD_EXECUTION_VERSION = "chess-continuation-child-execution/v1"
ENGINE_VERSION = "chess-continuation-engine/v1"
LINEAGE_PATH = "continuation/lineage.json"
LEDGER_PATH = "continuation/source_provider_receipts.jsonl"
PREFIX_PATH = "continuation/source_prefix.json"
HEX = re.compile(r"^[0-9a-f]{64}$")
INTERRUPTIONS = {
    "operator_cancelled",
    "provider_output_truncated",
    "provider_timeout",
    "provider_pending",
    "provider_cancelled",
    "provider_interrupted",
    "provider_auth_failed",
    "provider_permission_failed",
    "provider_rate_limited",
    "provider_request_rejected",
    "provider_refused",
    "provider_response_schema_mismatch",
    "provider_transport_error",
    "provider_unavailable",
}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_json(value).encode("utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("chess continuation: " + message)


def _object(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return dict(value)


def _text(value: Any, label: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} is required")


def _hash(value: Any, label: str) -> None:
    _require(
        isinstance(value, str) and HEX.fullmatch(value) is not None,
        f"{label} must be raw lowercase SHA256 hex",
    )


def _raw_state_hash(value: Any) -> str:
    _require(isinstance(value, str) and value.startswith("sha256:"), "state hash missing")
    result = str(value)[7:]
    _hash(result, "state hash")
    return result


def _load_object(path: Path) -> dict[str, Any]:
    return _object(json.loads(path.read_bytes()), path.name)


def _rows(data: bytes) -> list[dict[str, Any]]:
    return [_object(json.loads(line), "JSONL row") for line in data.splitlines() if line.strip()]


def _execution(value: Any) -> dict[str, Any]:
    execution = _object(value, "execution")
    for key in (
        "coreVersion",
        "coreRef",
        "arenaVersion",
        "runnerVersion",
        "wrapperVersion",
        "scoringPolicyVersion",
    ):
        _text(execution.get(key), key)
    for key in ("coreSourceSha256", "rulesSha256", "sourcePayloadSha256"):
        _hash(execution.get(key), key)
    _require(execution.get("arenaSlug") == "chess", "only chess is supported")
    _require(execution.get("variantSlug") == "standard", "only standard chess is supported")
    validate_seed(execution["seed"])
    limit = execution.get("maxTurns")
    _require(type(limit) is int and limit > 0, "maxTurns must be positive")
    players = execution.get("players")
    _require(isinstance(players, list) and len(players) == 2, "two pinned players required")
    seats = []
    assert isinstance(players, list)
    for item in players:
        player = _object(item, "player")
        for key in ("seat", "modelId", "modelVersionId", "providerModelId", "routeKey"):
            _text(player.get(key), key)
        _hash(player.get("routeSha256"), "routeSha256")
        seats.append(player["seat"])
    _require(seats == ["player_1", "player_2"], "players must be ordered and unique")
    return execution


def _descriptor(value: Any) -> dict[str, Any]:
    descriptor = _object(value, "descriptor")
    _require(descriptor.get("schemaVersion") == DESCRIPTOR_VERSION, "unsupported descriptor")
    source = _object(descriptor.get("source"), "source")
    for key in ("matchId", "runId", "artifactId", "artifactKey", "coreRunId"):
        _text(source.get(key), key)
    _hash(source.get("artifactSha256"), "artifactSha256")
    execution = _execution(descriptor.get("execution"))
    _require(
        descriptor.get("executionSpecSha256") == digest_json(execution),
        "execution spec hash mismatch",
    )
    prefix = _object(descriptor.get("prefix"), "prefix")
    count = prefix.get("acceptedPlyCount")
    _require(type(count) is int and 0 <= count < execution["maxTurns"], "invalid prefix count")
    _hash(prefix.get("prefixSha256"), "prefixSha256")
    _hash(prefix.get("checkpointStateSha256"), "checkpointStateSha256")
    return descriptor


def chess_continuation_child_execution(
    descriptor: dict[str, Any], *, turn_limit_policy: str = "preserve-source"
) -> dict[str, Any]:
    """Resolve a child budget without changing any historical execution pins.

    Native-horizon continuation removes only the caller's execution cutoff. It
    never changes the arena, accepts a caller-selected horizon, or changes a
    model output/time budget. Platform must bind this result to its admission.
    """
    execution = _descriptor(descriptor)["execution"]
    _require(isinstance(turn_limit_policy, str)
             and turn_limit_policy in {"preserve-source", "native-arena-horizon"},
             "unsupported child turn-limit policy")
    max_turns = execution["maxTurns"]
    if turn_limit_policy == "native-arena-horizon":
        from eslams.catalogue import game_catalogue_rows

        arena = ChessArena()
        _require(execution["arenaVersion"] in {arena.version, f"chess:{arena.version}"},
                 "native horizon arena version mismatch")
        rules = next(row["public_rules"] for row in game_catalogue_rows()
                     if row["game_id"] == "chess")
        _require(execution["rulesSha256"] == digest_json(rules),
                 "native horizon rules mismatch")
        _require(max_turns <= arena.max_turns, "native horizon cannot reduce source budget")
        max_turns = arena.max_turns
    return {
        "schemaVersion": CHILD_EXECUTION_VERSION,
        "turnLimitPolicy": turn_limit_policy,
        "maxTurns": max_turns,
    }


def _child_execution(value: Any, descriptor: dict[str, Any]) -> dict[str, Any]:
    child = _object(value, "child execution")
    policy = child.get("turnLimitPolicy")
    _require(isinstance(policy, str), "child turn-limit policy is required")
    assert isinstance(policy, str)
    expected = chess_continuation_child_execution(descriptor, turn_limit_policy=policy)
    _require(type(child.get("maxTurns")) is int and child == expected,
             "child execution differs from resolved policy")
    return expected


def _lineage_child_execution(lineage: dict[str, Any]) -> dict[str, Any]:
    descriptor = _descriptor(lineage.get("descriptor"))
    version = lineage.get("schemaVersion")
    _require(version in {LEGACY_LINEAGE_VERSION, LINEAGE_VERSION}, "unsupported lineage")
    if version == LEGACY_LINEAGE_VERSION:
        _require("childExecution" not in lineage and "childExecutionSha256" not in lineage,
                 "legacy lineage cannot declare a child budget")
        return chess_continuation_child_execution(descriptor)
    child = _child_execution(lineage.get("childExecution"), descriptor)
    _require(lineage.get("childExecutionSha256") == digest_json(child),
             "child execution digest")
    return child


def local_chess_continuation_engine_identity(*, wrapper_version: str) -> dict[str, Any]:
    """Bind local execution to actual Python source bytes, without a release claim.

    This local-only identity deliberately cannot stand in for a deployed image's
    immutable build attestation. Platform must issue/verify that attestation when
    provisioning a production runner; local-development is not a release pin.
    """
    root = Path(__file__).resolve().parent
    files = {
        path.relative_to(root).as_posix(): digest_bytes(path.read_bytes())
        for path in sorted(root.rglob("*.py"))
    }
    return {
        "schemaVersion": ENGINE_VERSION,
        "coreVersion": CORE_PACKAGE_VERSION,
        "coreRef": "local-development",
        "coreSourceSha256": digest_json(files),
        "runnerVersion": RUNNER_VERSION,
        "wrapperVersion": wrapper_version,
        "runnerImageDigest": "local-development",
        "continuationContractVersion": LINEAGE_VERSION,
    }


def chess_continuation_engine_identity(*, wrapper_version: str) -> dict[str, Any]:
    """Choose installed evidence first; development is restricted to source checkouts."""
    from eslams import _build_provenance
    from eslams.continuation_build import BUILD_PATH, installed_chess_continuation_engine_identity

    if BUILD_PATH.exists() or BUILD_PATH.is_symlink():
        return installed_chess_continuation_engine_identity()
    root = Path(__file__).absolute().parents[2]
    _require(_build_provenance.PACKAGED_CORE_COMMIT is None and (root / ".git").exists(),
             "installed runtime requires trusted build evidence")
    return local_chess_continuation_engine_identity(wrapper_version=wrapper_version)


def _engine(value: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    engine = _object(value, "target engine")
    _require(engine.get("schemaVersion") == ENGINE_VERSION, "unsupported target engine")
    _require(
        engine.get("continuationContractVersion") in (
            {LEGACY_LINEAGE_VERSION, LINEAGE_VERSION} if allow_legacy else {LINEAGE_VERSION}
        ),
        "unsupported continuation contract",
    )
    for key in ("coreVersion", "coreRef", "runnerVersion", "wrapperVersion"):
        _text(engine.get(key), key)
    _hash(engine.get("coreSourceSha256"), "target coreSourceSha256")
    if engine.get("coreRef") == "local-development":
        _require(engine.get("runnerImageDigest") == "local-development",
                 "local engine cannot claim an image digest")
        _require(not any(key in engine for key in
                         ("runnerBuildSha256", "wrapperSourceSha256", "platformRef")),
                 "local engine cannot claim installed build evidence")
    else:
        _require("runnerImageDigest" not in engine,
                 "installed engine uses build evidence, not image claims")
        for key in ("runnerBuildSha256", "wrapperSourceSha256"):
            _hash(engine.get(key), key)
        for key in ("coreRef", "platformRef"):
            _require(isinstance(engine.get(key), str)
                     and re.fullmatch(r"[0-9a-f]{40}", engine[key]) is not None,
                     "installed engine requires immutable source refs")
    return engine


def _ancestor_ids(source: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, set[str]]:
    identities: dict[str, set[str]] = {
        key: {source[key]} for key in ("coreRunId", "runId", "matchId")
    }
    depth = 0
    while parent is not None:
        depth += 1
        _require(depth <= 256, "continuation ancestry exceeds limit")
        ancestor = _descriptor(parent.get("descriptor"))["source"]
        for key in identities:
            identities[key].add(ancestor[key])
        raw_parent = parent.get("parentLineage")
        parent = None if raw_parent is None else _object(raw_parent, "parent lineage")
    return identities


@dataclass(frozen=True)
class ChessContinuation:
    source_archive: Path
    descriptor: dict[str, Any]
    target_engine_identity: dict[str, Any]
    child_platform_run_id: str
    match_id: str
    child_execution: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _text(self.child_platform_run_id, "child Platform run ID")
        _text(self.match_id, "child match ID")
        # Isolate caller-owned objects; verification takes another snapshot at run time.
        object.__setattr__(self, "descriptor", copy.deepcopy(_descriptor(self.descriptor)))
        object.__setattr__(
            self, "target_engine_identity", copy.deepcopy(_engine(self.target_engine_identity))
        )
        object.__setattr__(self, "child_execution", (
            chess_continuation_child_execution(self.descriptor)
            if self.child_execution is None
            else _child_execution(self.child_execution, self.descriptor)
        ))


@dataclass
class VerifiedChessContinuation:
    descriptor: dict[str, Any]
    state: ArenaState
    states: list[ArenaState]
    prefix: list[dict[str, Any]]
    history: list[dict[str, Any]]
    historical_ledger: bytes
    source_manifest: dict[str, Any]
    parent_lineage: dict[str, Any] | None
    target_engine_identity: dict[str, Any] | None = None
    child_platform_run_id: str | None = None
    match_id: str | None = None
    ledger_segments: list[dict[str, Any]] | None = None
    child_execution: dict[str, Any] | None = None

    def private_files(self, child_run_id: str) -> dict[str, bytes]:
        ids = _ancestor_ids(self.descriptor["source"], self.parent_lineage)
        _require(
            child_run_id not in ids["coreRunId"] | ids["runId"],
            "child Core run ID must not reuse any source identity",
        )
        ledger_rows = _rows(self.historical_ledger)
        child_execution = _child_execution(self.child_execution, self.descriptor)
        lineage = {
            "schemaVersion": LINEAGE_VERSION,
            "descriptor": self.descriptor,
            "descriptorSha256": digest_json(self.descriptor),
            "source": self.descriptor["source"],
            "child": {
                "coreRunId": child_run_id,
                "platformRunId": self.child_platform_run_id,
                "matchId": self.match_id,
            },
            "prefix": self.descriptor["prefix"],
            "targetEngine": self.target_engine_identity,
            "targetEngineSha256": digest_json(self.target_engine_identity),
            "childExecution": child_execution,
            "childExecutionSha256": digest_json(child_execution),
            "historicalLedger": {
                "path": LEDGER_PATH,
                "sha256": digest_bytes(self.historical_ledger),
                "receiptCount": len(ledger_rows),
                "segments": self.ledger_segments,
            },
            "accounting": {
                "historical": "source_and_ancestors",
                "incremental": "receipts/provider_receipts.jsonl",
                "aggregateScope": "incremental_only",
            },
            "sourceVerification": {
                "archiveBytesVerifiedAtPreparation": True,
                "childValidatorScope": "internal_lineage_only",
                "publicationRequiresAuthoritativeSourceReread": True,
                "externalCustodyPins": [
                    "coreRef",
                    "coreSourceSha256",
                    "rulesSha256",
                    "sourcePayloadSha256",
                    "players.routeKey",
                    "players.routeSha256",
                    "players.modelVersionId",
                ],
            },
            "parentLineage": self.parent_lineage,
            "parentLineageSha256": digest_json(self.parent_lineage),
        }
        return {
            LINEAGE_PATH: canonical_json(lineage).encode("utf-8") + b"\n",
            PREFIX_PATH: canonical_json(self.prefix).encode("utf-8") + b"\n",
            LEDGER_PATH: self.historical_ledger,
        }

    def projected_traces(self, child_run_id: str) -> list[TraceEvent]:
        traces = []
        for index, row in enumerate(self.prefix):
            before, after = self.states[index : index + 2]
            common = {
                "state_hash_before": before.state_hash,
                "state_hash_after": after.state_hash,
                "active_player": row["player"],
                "actor_player": row["player"],
                "seat": row["player"],
                "action": row["action"],
                "scores": after.scores,
                "markers": list(row["markers"]),
                "action_provenance": "reconstructed_action",
                "logical_action_id": f"{child_run_id}:episode_001:{row['player']}:{index:06d}",
                "successful_attempt_event_id": None,
            }
            traces.append(
                TraceEvent(
                    event_id=f"{child_run_id}:{index:06d}",
                    run_id=child_run_id,
                    episode_id="episode_001",
                    turn_id=index,
                    event_type="action",
                    public=common,
                    agent_visible=common,
                    judge=common,
                    auditor={
                        **common,
                        "reconstruction": {
                            "sourceEventId": row["sourceEventId"],
                            "sourceLogicalActionId": row["logicalActionId"],
                            "sourceActionProvenance": row["actionProvenance"],
                        },
                        "state_before": before.to_dict(),
                        "state_after": after.to_dict(),
                    },
                )
            )
        return traces


def _normalize_prefix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "turnId": row.get("turn_id"),
            "player": row.get("active_player"),
            "action": row.get("action"),
            "stateHashBefore": row.get("state_hash_before"),
            "stateHashAfter": row.get("state_hash_after"),
            "markers": row.get("markers"),
            "actionProvenance": row.get("action_provenance"),
            "logicalActionId": row.get("logical_action_id"),
            "sourceEventId": row.get("event_id"),
        }
        for row in rows
    ]


def _reconstruct(
    prefix: list[dict[str, Any]], execution: dict[str, Any]
) -> tuple[list[ArenaState], list[dict[str, Any]]]:
    arena = ChessArena()
    _require(
        execution["arenaVersion"] in {arena.version, f"chess:{arena.version}"},
        "unsupported source arena version",
    )
    state = arena.initial_state(execution["seed"])
    states = [state]
    history = []
    events: set[str] = set()
    logical_ids: set[str] = set()
    for index, raw_row in enumerate(prefix):
        row = _object(raw_row, "prefix row")
        _require(not state.terminal, "terminal prefix cannot continue")
        _require(
            row.get("turnId") == index and row.get("player") == state.active_player,
            "noncontiguous or wrong-player prefix",
        )
        event_id, logical_id = row.get("sourceEventId"), row.get("logicalActionId")
        _text(event_id, "source event ID")
        _text(logical_id, "source logical action ID")
        _require(event_id not in events and logical_id not in logical_ids, "duplicate prefix ID")
        events.add(cast(str, event_id))
        logical_ids.add(cast(str, logical_id))
        _require(row.get("markers") == [], "prefix contains failure/fallback markers")
        _require(
            row.get("actionProvenance")
            in {"local_action", "provider_action", "reconstructed_action"},
            "invalid prefix provenance",
        )
        _require(row.get("stateHashBefore") == state.state_hash, "prefix state before mismatch")
        action = row.get("action")
        _require(arena.is_legal(state, state.active_player, action), "illegal prefix action")
        next_state = arena.apply_action(state, state.active_player, action)
        _require(row.get("stateHashAfter") == next_state.state_hash, "prefix state after mismatch")
        history.append(
            {
                "turn_id": index,
                "player": state.active_player,
                "action": action,
                "reveal_turn": arena.action_reveal_turn(next_state),
                "state_hash": next_state.state_hash,
                "markers": row["markers"],
                "action_provenance": row["actionProvenance"],
                "logical_action_id": logical_id,
            }
        )
        state = next_state
        states.append(state)
    return states, history


def _check_receipts(
    rows: list[dict[str, Any]], execution: dict[str, Any], *, check_pins: bool = True
) -> None:
    pins = {p["seat"]: p for p in execution["players"]}
    seen: set[str] = set()
    attempts: dict[tuple[str, str, int], list[int]] = {}
    for row in rows:
        _require(not provider_receipt_validation_errors(row), "invalid historical receipt")
        event_id = row.get("event_id")
        _require(isinstance(event_id, str) and event_id not in seen, "duplicate receipt event ID")
        seen.add(cast(str, event_id))
        attempt = row.get("attempt_index")
        case_attempt = row.get("case_attempt_index")
        _require(
            type(attempt) is int and attempt > 0 and type(case_attempt) is int and case_attempt > 0,
            "invalid receipt attempt index",
        )
        assert isinstance(attempt, int) and isinstance(case_attempt, int)
        _require(
            event_id
            == provider_attempt_event_id(
                physical_run_id=row["physical_run_id"],
                case_id=row.get("case_id"),
                case_attempt_index=case_attempt,
                logical_action_id=row["logical_action_id"],
                attempt_index=attempt,
            ),
            "receipt event identity mismatch",
        )
        key = (row["physical_run_id"], row["logical_action_id"], case_attempt)
        attempts.setdefault(key, []).append(attempt)
        seat = row.get("seat_id") or row.get("active_player")
        _require(seat in pins, "unknown receipt player")
        if not check_pins:
            continue
        requested = row.get("model")
        unidentified_failure = (
            row.get("outcome") != "ok"
            and row.get("action_applied") is False
            and requested == "unknown"
            and row.get("locked_model_id") in {None, pins[seat]["modelVersionId"]}
        )
        _require(
            requested == pins[seat]["providerModelId"] or unidentified_failure,
            "receipt model pin mismatch",
        )
        if "requested_model" in row:
            _require(
                row["requested_model"] == pins[seat]["providerModelId"],
                "receipt requested model pin mismatch",
            )
        for field, pin in (
            ("model_version_id", "modelVersionId"),
            ("route_key", "routeKey"),
            ("route_sha256", "routeSha256"),
        ):
            if field in row:
                _require(row[field] == pins[seat][pin], "historical optional identity mismatch")
        # Unknown resolved identity stays unknown. A contradictory attestation is rejected.
        resolved = row.get("locked_model_id")
        _require(
            resolved is None or resolved == pins[seat]["modelVersionId"],
            "receipt locked catalogue version mismatch",
        )
        if row.get("outcome") == "ok":
            _require(
                resolved == pins[seat]["modelVersionId"],
                "successful historical receipt missing locked catalogue version",
            )
    for indexes in attempts.values():
        _require(
            indexes == list(range(1, len(indexes) + 1)),
            "receipt attempt indexes must be unique and gap-free",
        )


def _inspect_archive(
    source_archive: Path, source: dict[str, Any], execution: dict[str, Any]
) -> VerifiedChessContinuation:
    from eslams.artifacts import ArtifactValidator, open_artifact

    _require(
        source_archive.is_file() and not source_archive.is_symlink(),
        "source must be a regular, non-symlink archive file",
    )
    # Validate and read one private byte-pinned snapshot, avoiding a second read
    # of a caller-controlled path and bounding memory to one transfer chunk.
    with tempfile.TemporaryDirectory(prefix="eslams-continuation-") as temporary:
        snapshot = Path(temporary) / "source.eslams"
        digest = hashlib.sha256()
        total = 0
        with source_archive.open("rb") as handle, snapshot.open("xb") as output:
            while chunk := handle.read(64 * 1024):
                total += len(chunk)
                _require(total <= DEFAULT_ARCHIVE_LIMITS.archive_bytes, "archive too large")
                digest.update(chunk)
                output.write(chunk)
        _require(digest.hexdigest() == source["artifactSha256"], "source archive hash mismatch")
        report = ArtifactValidator().validate_report(snapshot, profile="runner_bundle")
        _require(report.valid, "source artifact invalid: " + "; ".join(report.errors))
        with open_artifact(snapshot) as directory:
            manifest = _load_object(directory / "manifest.json")
            _require(manifest["artifact_id"] == source["artifactId"], "source artifact ID mismatch")
            _require(
                source.get("coreRunId", manifest["run_id"]) == manifest["run_id"],
                "source Core run ID mismatch",
            )
            source = {**source, "coreRunId": manifest["run_id"]}
            score = _load_object(directory / "scores/score.json")
            _require(score.get("arena_id") == "chess", "source is not chess")
            _require(
                manifest["arena_version"]
                in {execution["arenaVersion"], "chess:" + execution["arenaVersion"]},
                "arena pin mismatch",
            )
            for external, internal in (
                ("runnerVersion", "runner_version"),
                ("wrapperVersion", "wrapper_version"),
                ("scoringPolicyVersion", "scoring_policy_version"),
            ):
                _require(manifest.get(internal) == execution[external], external + " mismatch")
            packages = _load_object(directory / "environment/package_versions.json")
            _require(
                packages.get("eslams-core") == execution["coreVersion"], "Core version mismatch"
            )
            metadata = _object(manifest.get("run_metadata"), "run metadata")
            _require(
                metadata.get("execution_profile") != "official_eval", "official source rejected"
            )
            _require(metadata.get("case_id") == source["runId"], "source Platform case ID mismatch")
            _require(metadata.get("max_turns") == execution["maxTurns"], "maxTurns mismatch")
            _require(score.get("match_valid_for_scoring") is False, "source is not interrupted")
            codes = score.get("invalid_reason_codes", [])
            _require(
                isinstance(codes, list)
                and bool(set(codes) & INTERRUPTIONS)
                and set(codes) <= INTERRUPTIONS | {"agent_error"},
                "source must have only a supported interruption",
            )
            for name in ("fallback_action_count_by_player", "illegal_action_count_by_player"):
                _require(
                    all(value == 0 for value in score.get(name, {}).values()),
                    "source contains fallback/illegal actions",
                )
            trace_rows = _rows((directory / "traces/auditor_trace.jsonl").read_bytes())
            _require(
                all(r.get("event_type") == "action" for r in trace_rows),
                "source contains non-action transitions",
            )
            _require(
                all(
                    r.get("run_id") == source["coreRunId"] and r.get("episode_id") == "episode_001"
                    for r in trace_rows
                ),
                "source trace identity mismatch",
            )
            prefix = _normalize_prefix(trace_rows)
            states, history = _reconstruct(prefix, execution)
            state = states[-1]
            _require(
                not state.terminal and state.turn < execution["maxTurns"],
                "terminal or exhausted source",
            )
            replay = _rows((directory / "replay/replay_events.jsonl").read_bytes())
            _require(len(replay) == len(states), "source replay count mismatch")
            for index, (expected, replay_row) in enumerate(zip(states, replay)):
                _require(
                    replay_row.get("state_hash") == expected.state_hash,
                    "source replay is not the initial-state trajectory",
                )
                if index:
                    _require(
                        replay_row.get("action") == prefix[index - 1]["action"],
                        "source replay action mismatch",
                    )
            errors = _rows((directory / "logs/errors.jsonl").read_bytes())
            _require(
                bool(errors) and errors[-1].get("turn_id") == state.turn,
                "missing interruption at checkpoint",
            )
            new_ledger = (directory / "receipts/provider_receipts.jsonl").read_bytes()
            historical_ledger = new_ledger
            parent_lineage = None
            segments: list[dict[str, Any]] = []
            if (directory / LINEAGE_PATH).exists():
                parent_lineage = _load_object(directory / LINEAGE_PATH)
                parent_child = _object(parent_lineage.get("child"), "source child identity")
                _require(
                    source["coreRunId"] == parent_child.get("coreRunId")
                    and source["runId"] == parent_child.get("platformRunId")
                    and source["matchId"] == parent_child.get("matchId")
                    and source["matchId"] == metadata.get("continuation_match_id"),
                    "continued source Platform identity mismatch",
                )
                parent_engine = parent_lineage["targetEngine"]
                for key in (
                    "coreVersion",
                    "coreRef",
                    "coreSourceSha256",
                    "runnerVersion",
                    "wrapperVersion",
                ):
                    _require(
                        execution[key] == parent_engine[key], "continued source engine mismatch"
                    )
                prior_execution = parent_lineage["descriptor"]["execution"]
                parent_child_execution = _lineage_child_execution(parent_lineage)
                _require(execution["maxTurns"] == parent_child_execution["maxTurns"],
                         "continued source child budget changed")
                for key in (
                    "arenaSlug",
                    "arenaVersion",
                    "variantSlug",
                    "rulesSha256",
                    "seed",
                    "players",
                    "scoringPolicyVersion",
                ):
                    _require(
                        execution[key] == prior_execution[key], "continued source pins changed"
                    )
                segments = copy.deepcopy(parent_lineage["historicalLedger"]["segments"])
                prior = (directory / LEDGER_PATH).read_bytes()
                # Preserve each source ledger byte sequence as an exact segment.
                _require(not prior or prior.endswith(b"\n"), "historical ledger lacks newline")
                historical_ledger = prior + new_ledger
            segments.append(
                {
                    "sourceCoreRunId": source["coreRunId"],
                    "sourceArtifactId": source["artifactId"],
                    "sha256": digest_bytes(new_ledger),
                    "byteCount": len(new_ledger),
                    "receiptCount": len(_rows(new_ledger)),
                    "acceptedPlyCount": len(prefix),
                }
            )
            _check_receipts(_rows(historical_ledger), execution)
            current_receipts = _rows(new_ledger)
            _require(
                all(
                    r.get("model") != "unknown"
                    or (r.get("turn_id") == state.turn and r.get("outcome") in INTERRUPTIONS)
                    for r in current_receipts
                ),
                "unknown identity outside interruption",
            )
            for row in trace_rows:
                if row.get("action_provenance") != "reconstructed_action":
                    _require(
                        any(
                            receipt.get("logical_action_id") == row["logical_action_id"]
                            and receipt.get("turn_id") == row["turn_id"]
                            and receipt.get("active_player") == row["active_player"]
                            and receipt.get("outcome") == "ok"
                            for receipt in current_receipts
                        ),
                        "accepted source action has no successful request receipt",
                    )
            if "operator_cancelled" not in codes:
                _require(
                    any(
                        receipt.get("turn_id") == state.turn
                        and receipt.get("outcome") in INTERRUPTIONS
                        for receipt in current_receipts
                    ),
                    "interrupted source has no failed request receipt",
                )
            _require(
                all(r.get("run_id") == source["coreRunId"] for r in current_receipts),
                "source receipt run ID mismatch",
            )
            descriptor = {
                "schemaVersion": DESCRIPTOR_VERSION,
                "source": source,
                "execution": execution,
                "executionSpecSha256": digest_json(execution),
                "prefix": {
                    "acceptedPlyCount": len(prefix),
                    "prefixSha256": digest_json(prefix),
                    "checkpointStateSha256": _raw_state_hash(state.state_hash),
                },
            }
            return VerifiedChessContinuation(
                descriptor,
                state,
                states,
                prefix,
                history,
                historical_ledger,
                manifest,
                parent_lineage,
                ledger_segments=segments,
            )


def prepare_chess_continuation(
    source_archive: Path, source_identity: dict[str, Any], execution_spec: dict[str, Any]
) -> dict[str, Any]:
    """Derive a descriptor from trusted custody pins and a fully verified archive."""
    source = copy.deepcopy(_object(source_identity, "source identity"))
    for key in ("matchId", "runId", "artifactId", "artifactKey"):
        _text(source.get(key), key)
    _hash(source.get("artifactSha256"), "artifactSha256")
    execution = copy.deepcopy(_execution(execution_spec))
    return _inspect_archive(Path(source_archive), source, execution).descriptor


def verify_chess_continuation(continuation: ChessContinuation) -> VerifiedChessContinuation:
    descriptor = copy.deepcopy(_descriptor(continuation.descriptor))
    verified = _inspect_archive(
        Path(continuation.source_archive), descriptor["source"], descriptor["execution"]
    )
    _require(verified.descriptor == descriptor, "descriptor does not match source")
    target = copy.deepcopy(_engine(continuation.target_engine_identity))
    actual = chess_continuation_engine_identity(wrapper_version=target["wrapperVersion"])
    _require(target == actual, "target identity does not match verified runtime source bytes")
    ids = _ancestor_ids(descriptor["source"], verified.parent_lineage)
    _require(
        continuation.child_platform_run_id not in ids["runId"],
        "child Platform run ID must not reuse any source run",
    )
    _require(continuation.match_id not in ids["matchId"], "child must use a new match ID")
    verified.child_platform_run_id = continuation.child_platform_run_id
    verified.match_id = continuation.match_id
    verified.target_engine_identity = target
    verified.child_execution = _child_execution(continuation.child_execution, descriptor)
    return verified


def validate_continuation_artifact(directory: Path, manifest: dict[str, Any]) -> list[str]:
    """Check child-internal evidence; this does NOT reverify original archive custody."""
    present = (directory / LINEAGE_PATH).exists()
    declared = manifest.get("run_metadata", {}).get("continuation")
    try:
        trace = _rows((directory / "traces/auditor_trace.jsonl").read_bytes())
        reconstructed = [
            row for row in trace if row.get("action_provenance") == "reconstructed_action"
        ]
        if not present:
            _require(not declared and not reconstructed, "lineage missing")
            return []
        _require(bool(declared), "lineage not declared")
        lineage = _load_object(directory / LINEAGE_PATH)
        child_execution = _lineage_child_execution(lineage)
        descriptor = _descriptor(lineage.get("descriptor"))
        _require(lineage.get("descriptorSha256") == digest_json(descriptor), "descriptor digest")
        _require(lineage.get("source") == descriptor["source"], "lineage source mismatch")
        child = _object(lineage.get("child"), "child")
        _require(
            child.get("coreRunId") == manifest["run_id"]
            and isinstance(child.get("matchId"), str)
            and child.get("matchId") != descriptor["source"]["matchId"]
            and child.get("matchId") == manifest["run_metadata"].get("continuation_match_id")
            and isinstance(child.get("platformRunId"), str)
            and child["platformRunId"] != descriptor["source"]["runId"]
            and child["platformRunId"] == manifest["run_metadata"].get("case_id")
            and child["platformRunId"]
            == manifest["run_metadata"].get("continuation_platform_run_id"),
            "child ID mismatch",
        )
        _require(manifest["run_id"] != descriptor["source"]["coreRunId"], "reused source run ID")
        _require(lineage.get("prefix") == descriptor["prefix"], "lineage prefix mismatch")
        target = _engine(lineage.get("targetEngine"), allow_legacy=True)
        _require(target["continuationContractVersion"] == lineage["schemaVersion"],
                 "target and lineage contract mismatch")
        _require(manifest["run_metadata"].get("max_turns") == child_execution["maxTurns"],
                 "child manifest budget differs from lineage")
        _require(len(trace) <= child_execution["maxTurns"],
                 "child trace exceeds execution budget")
        _require(lineage.get("targetEngineSha256") == digest_json(target), "target engine digest")
        packages = _load_object(directory / "environment/package_versions.json")
        _require(
            target["coreVersion"] == packages.get("eslams-core")
            and target["runnerVersion"] == manifest.get("runner_version")
            and target["wrapperVersion"] == manifest.get("wrapper_version"),
            "target engine versions disagree with artifact",
        )
        _require(
            lineage.get("accounting")
            == {
                "historical": "source_and_ancestors",
                "incremental": "receipts/provider_receipts.jsonl",
                "aggregateScope": "incremental_only",
            },
            "accounting scope mismatch",
        )
        verification = _object(lineage.get("sourceVerification"), "source verification")
        _require(
            verification.get("childValidatorScope") == "internal_lineage_only"
            and verification.get("publicationRequiresAuthoritativeSourceReread") is True,
            "source verification scope mismatch",
        )
        prefix = json.loads((directory / PREFIX_PATH).read_bytes())
        _require(isinstance(prefix, list), "prefix must be an array")
        _require(digest_json(prefix) == descriptor["prefix"]["prefixSha256"], "prefix digest")
        _require(len(prefix) == descriptor["prefix"]["acceptedPlyCount"], "prefix count")
        states, _ = _reconstruct(prefix, descriptor["execution"])
        _require(not states[-1].terminal, "terminal checkpoint")
        _require(
            _raw_state_hash(states[-1].state_hash) == descriptor["prefix"]["checkpointStateSha256"],
            "checkpoint digest",
        )
        _require(
            len(reconstructed) == len(prefix) and len(trace) >= len(prefix),
            "reconstructed prefix count",
        )
        replay = _rows((directory / "replay/replay_events.jsonl").read_bytes())
        public = _rows((directory / "traces/public_trace.jsonl").read_bytes())
        _require(
            len(replay) >= len(prefix) + 1 and len(public) >= len(prefix),
            "prefix projections missing",
        )
        for index, source_row in enumerate(prefix):
            child_row = trace[index]
            _require(
                child_row.get("action_provenance") == "reconstructed_action",
                "prefix missing reconstructed provenance",
            )
            _require(
                child_row.get("action") == source_row["action"]
                and child_row.get("state_hash_after") == states[index + 1].state_hash
                and child_row.get("state_hash_before") == states[index].state_hash
                and child_row.get("active_player") == source_row["player"],
                "projected prefix mismatch",
            )
            _require(
                child_row.get("reconstruction")
                == {
                    "sourceEventId": source_row["sourceEventId"],
                    "sourceLogicalActionId": source_row["logicalActionId"],
                    "sourceActionProvenance": source_row["actionProvenance"],
                },
                "source provenance mismatch",
            )
            logical_id = f"{manifest['run_id']}:episode_001:{source_row['player']}:{index:06d}"
            for projection in (child_row, public[index], replay[index + 1]):
                _require(
                    projection.get("successful_attempt_event_id") is None
                    and projection.get("action_provenance") == "reconstructed_action"
                    and projection.get("logical_action_id") == logical_id
                    and projection.get("run_id") == manifest["run_id"]
                    and projection.get("action") == source_row["action"],
                    "reconstructed action projection mismatch",
                )
        ledger = (directory / LEDGER_PATH).read_bytes()
        ledger_rows = _rows(ledger)
        historical = _object(lineage.get("historicalLedger"), "historical ledger")
        _require(
            historical.get("path") == LEDGER_PATH
            and historical.get("sha256") == digest_bytes(ledger)
            and historical.get("receiptCount") == len(ledger_rows),
            "ledger digest",
        )
        segments = historical.get("segments")
        _require(isinstance(segments, list) and bool(segments), "ledger segments missing")
        offset = 0
        source_runs: set[str] = set()
        assert isinstance(segments, list)
        for raw_segment in segments:
            segment = _object(raw_segment, "ledger segment")
            count = segment.get("byteCount")
            _require(type(count) is int and count >= 0, "invalid ledger segment length")
            assert isinstance(count, int)
            data = ledger[offset : offset + count]
            _require(
                segment.get("sha256") == digest_bytes(data)
                and segment.get("receiptCount") == len(_rows(data)),
                "ledger segment digest",
            )
            source_run = segment.get("sourceCoreRunId")
            _require(
                isinstance(source_run, str)
                and source_run not in source_runs
                and all(row.get("run_id") == source_run for row in _rows(data)),
                "ledger segment source mismatch",
            )
            _require(
                all(
                    row.get("model") != "unknown"
                    or (
                        row.get("turn_id") == segment.get("acceptedPlyCount")
                        and row.get("outcome") in INTERRUPTIONS
                    )
                    for row in _rows(data)
                ),
                "unknown historical identity outside interruption",
            )
            source_runs.add(cast(str, source_run))
            offset += count
        _require(
            offset == len(ledger)
            and segments[-1].get("sourceCoreRunId") == descriptor["source"]["coreRunId"]
            and segments[-1].get("sourceArtifactId") == descriptor["source"]["artifactId"],
            "ledger source binding mismatch",
        )
        parent = lineage.get("parentLineage")
        _require(lineage.get("parentLineageSha256") == digest_json(parent), "parent lineage digest")
        if parent is not None:
            parent = _object(parent, "parent lineage")
            _require(descriptor["execution"]["maxTurns"]
                     == _lineage_child_execution(parent)["maxTurns"],
                     "continued source child budget changed")
            _require(
                parent.get("child", {}).get("coreRunId") == descriptor["source"]["coreRunId"]
                and parent.get("child", {}).get("platformRunId") == descriptor["source"]["runId"]
                and parent.get("child", {}).get("matchId") == descriptor["source"]["matchId"]
                and parent.get("historicalLedger", {}).get("segments") == segments[:-1],
                "parent lineage ledger binding mismatch",
            )
        else:
            _require(len(segments) == 1, "ancestral ledger requires parent lineage")
        _check_receipts(ledger_rows, descriptor["execution"])
        ancestors = _ancestor_ids(descriptor["source"], parent)
        _require(
            child["coreRunId"] not in ancestors["coreRunId"] | ancestors["runId"]
            and child["platformRunId"] not in ancestors["runId"]
            and child["matchId"] not in ancestors["matchId"],
            "reused ancestor identity",
        )
        incremental = _rows((directory / "receipts/provider_receipts.jsonl").read_bytes())
        _check_receipts(incremental, descriptor["execution"], check_pins=False)
        for row in incremental:
            if row.get("action_applied") is True:
                pin = next(
                    p
                    for p in descriptor["execution"]["players"]
                    if p["seat"] == row["active_player"]
                )
                _require(new_call_matches_pin([row], pin), "applied action pin mismatch")
        _require(
            len(public) == len(trace) and len(replay) == len(trace) + 1,
            "action projection count mismatch",
        )
        for index, action_row in enumerate(trace[len(prefix) :], start=len(prefix)):
            expected_logical = (
                f"{manifest['run_id']}:episode_001:{action_row.get('active_player')}:{index:06d}"
            )
            _require(
                action_row.get("logical_action_id") == expected_logical,
                "new action logical identity mismatch",
            )
            for projection, expected_turn in (
                (public[index], index),
                (replay[index + 1], index + 1),
            ):
                _require(
                    projection.get("action_provenance") == "provider_action"
                    and projection.get("run_id") == manifest["run_id"]
                    and projection.get("turn_id") == expected_turn
                    and projection.get("seat") == action_row.get("seat")
                    and projection.get("actor_player") == action_row.get("actor_player")
                    and projection.get("action") == action_row.get("action")
                    and projection.get("state_hash_before") == action_row.get("state_hash_before")
                    and projection.get("state_hash_after") == action_row.get("state_hash_after")
                    and projection.get("logical_action_id") == expected_logical
                    and projection.get("successful_attempt_event_id")
                    == action_row.get("successful_attempt_event_id"),
                    "new action projection mismatch",
                )
            _require(
                action_row.get("action_provenance") == "provider_action"
                and action_row.get("markers") == [],
                "new action has invalid provenance",
            )
            matches = [
                r
                for r in incremental
                if r.get("event_id") == action_row.get("successful_attempt_event_id")
            ]
            _require(len(matches) == 1, "new action receipt missing or duplicated")
            receipt = matches[0]
            _require(
                receipt.get("action_applied") is True
                and receipt.get("turn_id") == index
                and receipt.get("active_player") == action_row.get("active_player")
                and receipt.get("logical_action_id") == action_row.get("logical_action_id"),
                "new action receipt linkage mismatch",
            )
        referenced = [row.get("successful_attempt_event_id") for row in trace[len(prefix) :]]
        applied = [row["event_id"] for row in incremental if row.get("action_applied") is True]
        _require(
            len(set(referenced)) == len(referenced) and set(applied) == set(referenced),
            "applied receipt/action reconciliation mismatch",
        )
        final_turn = len(trace)
        terminal = replay[-1].get("terminal") is True
        for receipt in incremental:
            turn = receipt.get("turn_id")
            _require(
                type(turn) is int
                and len(prefix) <= turn <= final_turn
                and (not terminal or turn < final_turn),
                "receipt outside executed turns",
            )
            assert isinstance(turn, int)
            player = (
                trace[turn]["active_player"] if turn < final_turn else replay[-1]["active_player"]
            )
            _require(
                receipt.get("logical_action_id")
                == f"{manifest['run_id']}:episode_001:{player}:{turn:06d}"
                and receipt.get("active_player") == player,
                "receipt logical action mismatch",
            )
        public_summary = _load_object(directory / "public/public_result_summary.json")
        public_score = _object(public_summary.get("score"), "public score")
        _require(
            public_score.get("execution_label") == "continued"
            and public_score.get("reconstructed_turns") == len(prefix),
            "public continued label missing",
        )
        old_ids = {row["event_id"] for row in ledger_rows}
        _require(
            all(
                row.get("event_id") not in old_ids
                and row.get("run_id") == manifest["run_id"]
                and row.get("case_id") == child["platformRunId"]
                and row.get("run_job_id") == child["platformRunId"]
                and type(row.get("turn_id")) is int
                and row["turn_id"] >= len(prefix)
                for row in incremental
            ),
            "historical receipt in incremental ledger",
        )
        _require(
            not any(
                manifest.get(key) is True
                for key in (
                    "per_case_scoring_eligible",
                    "proof_row_publication_eligible",
                    "aggregate_leaderboard_eligible",
                )
            ),
            "continuation cannot claim official eligibility",
        )
        _require(
            manifest.get("run_metadata", {}).get("execution_profile") != "official_eval",
            "official continuation rejected",
        )
        return []
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return ["invalid continuation evidence: " + str(exc)]


def new_call_matches_pin(receipts: list[dict[str, Any]], player: dict[str, Any]) -> bool:
    """No new move without an exact trusted provider-model attestation.

    Catalogue version and route custody are externally attested; if a gateway
    adds them to its receipt, it must not contradict the frozen descriptor.
    """
    if not receipts:
        return False
    for row in receipts:
        if row.get("model") != player["providerModelId"]:
            return False
        if "requested_model" in row and row["requested_model"] != player["providerModelId"]:
            return False
        for wire, pin in (
            ("model_version_id", "modelVersionId"),
            ("route_key", "routeKey"),
            ("route_sha256", "routeSha256"),
        ):
            if wire in row and row[wire] != player[pin]:
                return False
    final = receipts[-1]
    sources = {"provider_response", "pinned_endpoint"}
    if final.get("provider") == "mock":
        sources.add("mock_attested")
    return bool(
        final.get("outcome") == "ok"
        and final.get("locked_model_id") == player["modelVersionId"]
        and final.get("model_identity_source") in sources
    )
