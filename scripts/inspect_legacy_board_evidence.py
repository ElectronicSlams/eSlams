"""Experimental offline evidence inspection. Never an admission/continuation API.

Run with --archive PATH --sha256 DIGEST. Output contains no archive identities,
model content, receipts, positions or executable descriptors. All success claims
are archive-internal consistency, not external authenticity or scoring validity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Literal, TypedDict

import jsonschema  # type: ignore[import-untyped]  # Inspector dev dependency has no bundled stubs.

from eslams.arenas.connect_four import ConnectFourArena
from eslams.arenas.othello import OthelloArena
from eslams.arenas.tic_tac_toe import TicTacToeArena
from eslams.contracts.provider import provider_attempt_event_id
from eslams.zip_extract import ArchiveLimits, extract_archive

LIMITS = ArchiveLimits(
    archive_bytes=8 * 1024 * 1024,
    members=64,
    member_bytes=8 * 1024 * 1024,
    total_bytes=32 * 1024 * 1024,
)
ARENAS: dict[str, type[TicTacToeArena] | type[ConnectFourArena] | type[OthelloArena]] = {
    "tic-tac-toe": TicTacToeArena,
    "connect-four": ConnectFourArena,
    "othello": OthelloArena,
}
REQUIRED = {
    "manifest.json",
    "environment/package_versions.json",
    "receipts/provider_receipts.jsonl",
    "traces/auditor_trace.jsonl",
    "traces/public_trace.jsonl",
    "logs/errors.jsonl",
}


class ArenaReport(TypedDict):
    slug: str
    version: str


class VerifiedReport(TypedDict):
    listed_member_digests: Literal[True]
    legal_prefix: Literal[True]
    archive_internal_receipt_association: Literal[True]


class PrefixReport(TypedDict):
    action_count: int
    final_state_sha256: str
    terminal: Literal[False]


class FinalAttemptReport(TypedDict):
    archive_error: Literal["http_502_bad_gateway"]
    failed_receipt_present: Literal[False]
    provider_execution: Literal["unknown"]
    physical_call_count: Literal["unknown"]
    spend: Literal["unknown"]


class AssuranceReport(TypedDict):
    signed_build: Literal["unverified"]
    route: Literal["unverified"]
    platform_case: Literal["unverified"]
    provider_authenticity: Literal["unverified"]


class EvidenceReport(TypedDict):
    schema_version: Literal["legacy-board-evidence/v1"]
    archive_sha256: str
    arena: ArenaReport
    verified: VerifiedReport
    prefix: PrefixReport
    final_attempt: FinalAttemptReport
    assurance: AssuranceReport
    executable: Literal[False]
    scoring_eligible: Literal[False]
    official_admission: Literal[False]


class EvidenceError(ValueError):
    """Only fixed codes, never input text."""


def require(value: bool, code: str) -> None:
    if not value:
        raise EvidenceError(code)


def text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 512


def equal(a: Any, b: Any) -> bool:
    # JSON equality distinguishes bools from integers, unlike Python equality.
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(
        b, sort_keys=True, allow_nan=False
    )


def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def invalid_constant(_: str) -> Any:
    raise EvidenceError("nonfinite_json")


def finite_float(value: str) -> float:
    parsed = float(value)
    require(math.isfinite(parsed), "nonfinite_json")
    return parsed


def read(path: Path, *, lines: bool = False) -> Any:
    raw = path.read_bytes()
    chunks = raw.splitlines() if lines else [raw]
    require(len(chunks) <= 128, "row_limit")
    require(all(len(c) <= 1024 * 1024 for c in chunks), "line_limit")
    values = [
        json.loads(
            c, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float
        )
        for c in chunks
    ]
    require(all(isinstance(v, dict) for v in values), "object_required")
    return values if lines else values[0]


def inspect_legacy_board_evidence(source: Path, expected_sha256: str) -> EvidenceReport:
    """Read one byte-pinned snapshot; never mutate the input or issue requests."""
    try:
        report = _inspect(source, expected_sha256)
        schema_path = (
            Path(__file__).parents[1] / "docs/proposals/legacy-board-evidence-v1.schema.json"
        )
        jsonschema.Draft202012Validator(read(schema_path)).validate(report)
        return report
    except EvidenceError:
        raise
    except Exception:
        # Parsers, ZIP libraries and rule engines can reflect private inputs.
        raise EvidenceError("malformed_or_unsupported_archive") from None


def _inspect(source: Path, expected_sha256: str) -> EvidenceReport:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha256)), "invalid_digest")
    require(source.is_file() and not source.is_symlink(), "regular_file_required")
    with tempfile.TemporaryDirectory(prefix="legacy-evidence-") as tmp:
        root = Path(tmp)
        snapshot = root / "source.eslams"
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as src, snapshot.open("xb") as out:
            while chunk := src.read(65536):
                size += len(chunk)
                require(size <= LIMITS.archive_bytes, "archive_limit")
                digest.update(chunk)
                out.write(chunk)
        require(digest.hexdigest() == expected_sha256, "archive_digest_mismatch")
        directory = root / "members"
        directory.mkdir()
        extract_archive(snapshot, directory, limits=LIMITS)
        require(all((directory / n).is_file() for n in REQUIRED), "missing_member")
        manifest = read(directory / "manifest.json")
        require(
            all(
                manifest.get(key) == value
                for key, value in {
                    "artifact_version": "eslams-artifact-v1",
                    "manifest_schema_version": "eslams.artifact.manifest.v1",
                    "artifact_kind": "local_match",
                    "artifact_profile": "runner_bundle",
                    "artifact_profile_key": "runner_bundle",
                    "hash_algorithm": "sha256",
                }.items()
            ),
            "unsupported_manifest_profile",
        )
        require(
            all(
                manifest.get(k) is False
                for k in (
                    "match_valid_for_scoring",
                    "per_case_run_valid",
                    "per_case_scoring_eligible",
                    "proof_row_publication_eligible",
                    "aggregate_leaderboard_eligible",
                )
            ),
            "contradictory_scoring_claim",
        )
        entries = manifest["files"]
        unhashed = manifest["unhashed_files"]
        require(
            isinstance(unhashed, list)
            and all(e["path"] == "timings/timings.json" for e in unhashed),
            "unsupported_unhashed_member",
        )
        require(isinstance(entries, list), "manifest_files")
        seen: set[str] = set()
        for entry in entries + unhashed:
            name = entry["path"]
            require(isinstance(name, str) and name not in seen, "manifest_duplicate")
            # Extractor already confines paths; independently constrain references.
            require(
                name
                in {
                    p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()
                },
                "manifest_member_missing",
            )
            seen.add(name)
            data = (directory / name).read_bytes()
            require(
                type(entry["bytes"]) is int
                and entry["bytes"] == len(data)
                and entry["sha256"] == "sha256:" + hashlib.sha256(data).hexdigest(),
                "member_digest_mismatch",
            )
        require(REQUIRED - {"manifest.json"} <= {e["path"] for e in entries}, "unhashed_evidence")
        require(
            seen
            == {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
            - {"manifest.json"},
            "unlisted_member",
        )
        require(
            read(directory / "environment/package_versions.json").get("eslams-core") == "0.6.2",
            "unsupported_core_version",
        )
        rows = read(directory / "traces/auditor_trace.jsonl", lines=True)
        public = read(directory / "traces/public_trace.jsonl", lines=True)
        receipts = read(directory / "receipts/provider_receipts.jsonl", lines=True)
        errors = read(directory / "logs/errors.jsonl", lines=True)
        require(0 < len(rows) == len(public) == len(receipts) <= 64, "row_cardinality")
        info = rows[0]["request"]["arena"]
        require(info["id"] in ARENAS, "unsupported_arena")
        arena = ARENAS[info["id"]]()
        require(
            info["version"] == arena.version
            and manifest["arena_version"] in {arena.version, f"{arena.id}:{arena.version}"},
            "unsupported_arena_version",
        )
        seed = rows[0]["state_before"]["metadata"]["seed"]
        require(type(seed) is int, "invalid_seed")
        state = arena.initial_state(seed)
        ledger: dict[str, Any] = {}
        gateways: set[str] = set()
        for receipt in receipts:
            event, gateway = receipt.get("event_id"), receipt.get("gateway_request_id")
            require(
                text(event) and event not in ledger and text(gateway) and gateway not in gateways,
                "receipt_identity",
            )
            ledger[event] = receipt
            gateways.add(gateway)
        used: set[str] = set()
        events: set[str] = set()
        logicals: set[str] = set()
        episode = rows[0]["episode_id"]
        require(text(episode) and text(manifest["run_id"]), "run_identity")
        for index, (row, pub) in enumerate(zip(rows, public)):
            require(not state.terminal, "terminal_prefix")
            require(
                row.get("event_type") == "action"
                and row.get("protocol_version") == "eslams-act-v1"
                and row["request"].get("protocol_version") == "eslams-act-v1",
                "unsupported_trace_protocol",
            )
            require(
                type(row["turn_id"]) is int
                and row["turn_id"] == index
                and row["active_player"] == state.active_player
                and row["actor_player"] == state.active_player
                and row["seat"] == state.active_player,
                "trace_turn_player",
            )
            require(
                row["run_id"] == manifest["run_id"] and row["episode_id"] == episode, "trace_scope"
            )
            event, logical = row["event_id"], row["logical_action_id"]
            require(
                text(event) and event not in events and text(logical) and logical not in logicals,
                "trace_identity",
            )
            events.add(event)
            logicals.add(logical)
            require(
                row["markers"] == []
                and row["action_provenance"] == "local_action"
                and row["successful_attempt_event_id"] is None,
                "legacy_profile",
            )
            require(
                set(pub) <= set(row)
                and all(equal(v, row[k]) for k, v in pub.items())
                and {"action", "event_id", "state_hash_before", "state_hash_after"} <= set(pub),
                "public_trace_mismatch",
            )
            require(
                equal(row["state_before"], state.to_dict())
                and row["state_hash_before"] == state.state_hash,
                "state_before",
            )
            request, response = row["request"], row["response"]
            for key in ("run_id", "episode_id", "turn_id", "active_player"):
                require(equal(request[key], row[key]), "request_scope")
            require(
                equal(request["arena"], info)
                and request["metadata"]["state_hash"] == state.state_hash
                and equal(
                    request["legal_actions"], state.legal_actions_by_player[state.active_player]
                ),
                "request_state",
            )
            require(
                equal(row["action"], response["action"])
                and arena.is_legal(state, state.active_player, row["action"]),
                "action",
            )
            metadata = response["metadata"]
            receipt = metadata["provider_receipt"]
            identity = receipt["event_id"]
            require(
                identity in ledger and identity not in used and equal(receipt, ledger[identity]),
                "receipt_association",
            )
            used.add(identity)
            require(
                receipt["gateway_request_id"] == metadata["ai_gateway_request_id"]
                and receipt["seat_id"] == state.active_player
                and receipt["physical_run_id"] == manifest["run_id"],
                "gateway_association",
            )
            for key in ("run_id", "episode_id", "turn_id", "active_player", "logical_action_id"):
                require(equal(receipt[key], row[key]), "receipt_scope")
            for key in ("physical_run_id", "case_id", "case_attempt_index", "logical_action_id"):
                require(equal(receipt[key], request["metadata"][key]), "request_receipt_scope")
            require(
                receipt["status"] == "completed"
                and receipt["outcome"] == "ok"
                and receipt["wire_parse_status"] == "ok"
                and receipt["action_parse_status"] == "ok"
                and type(receipt["status_code"]) is int
                and receipt["status_code"] == 200
                and receipt["action_applied"] is False,
                "receipt_success",
            )
            require(
                type(receipt["attempt_index"]) is int
                and receipt["attempt_index"] == 1
                and type(receipt["case_attempt_index"]) is int
                and receipt["case_attempt_index"] == 1
                and receipt["attempt_kind"] == "primary"
                and text(receipt["physical_run_id"]),
                "attempt_identity",
            )
            require(
                identity
                == provider_attempt_event_id(
                    physical_run_id=receipt["physical_run_id"],
                    case_id=receipt["case_id"],
                    case_attempt_index=1,
                    logical_action_id=logical,
                    attempt_index=1,
                ),
                "attempt_event_identity",
            )
            attempts = metadata["attempt_receipts"]
            require(
                isinstance(attempts, list)
                and len(attempts) == 1
                and equal(
                    attempts[0],
                    {
                        k: v
                        for k, v in receipt.items()
                        if k not in {"usage_complete", "cost_complete"}
                    },
                ),
                "attempt_receipt_association",
            )
            state = arena.apply_action(state, state.active_player, row["action"])
            require(
                equal(row["state_after"], state.to_dict())
                and row["state_hash_after"] == state.state_hash,
                "state_after",
            )
        require(not state.terminal and used == set(ledger), "incomplete_or_terminal_prefix")
        require(len(errors) == 1, "final_error_cardinality")
        error = errors[0]
        require(
            set(error) == {"turn_id", "player_id", "policy", "reason", "response_metadata"}
            and error["reason"] == f"{state.active_player}:agent_crash:agent_crash,no_action"
            and set(error["response_metadata"]) == {"error", "error_kind"},
            "unsupported_final_error_shape",
        )
        require(
            type(error["turn_id"]) is int
            and error["turn_id"] == len(rows)
            and error["player_id"] == state.active_player
            and error["policy"] == "invalid-match"
            and error["response_metadata"]["error_kind"] == "agent_crash",
            "final_error_scope",
        )
        diagnostic = error["response_metadata"]["error"]
        require(isinstance(diagnostic, str), "final_error_diagnostic")
        require(
            "502 Bad Gateway" in diagnostic
            and diagnostic.endswith("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502"),
            "unsupported_final_error",
        )
        return {
            "schema_version": "legacy-board-evidence/v1",
            "archive_sha256": expected_sha256,
            "arena": {"slug": arena.id, "version": arena.version},
            "verified": {
                "listed_member_digests": True,
                "legal_prefix": True,
                "archive_internal_receipt_association": True,
            },
            "prefix": {
                "action_count": len(rows),
                "final_state_sha256": str(state.state_hash),
                "terminal": False,
            },
            "final_attempt": {
                "archive_error": "http_502_bad_gateway",
                "failed_receipt_present": False,
                "provider_execution": "unknown",
                "physical_call_count": "unknown",
                "spend": "unknown",
            },
            "assurance": {
                "signed_build": "unverified",
                "route": "unverified",
                "platform_case": "unverified",
                "provider_authenticity": "unverified",
            },
            "executable": False,
            "scoring_eligible": False,
            "official_admission": False,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_legacy_board_evidence(args.archive, args.sha256), sort_keys=True))
    except EvidenceError as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1) from None
