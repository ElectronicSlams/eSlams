"""Synthetic legacy fixtures only; no production identities or receipts."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from eslams import legacy_board_evidence as inspector
from eslams.contracts.board_recovery import board_recovery_schemas, no_secret_examples
from eslams.contracts.provider import provider_attempt_event_id

CANARY = "PRIVATE-CANARY-DO-NOT-OUTPUT"


def fixture(slug: str = "tic-tac-toe") -> dict[str, Any]:
    arena = inspector.ARENAS[slug]()
    state = arena.initial_state(0)
    action = state.legal_actions_by_player[state.active_player][0]
    after = arena.apply_action(state, state.active_player, action)
    receipt = {
        "event_id": provider_attempt_event_id(
            physical_run_id="synthetic-run",
            case_id=None,
            case_attempt_index=1,
            logical_action_id="synthetic-logical",
            attempt_index=1,
        ),
        "gateway_request_id": "synthetic-gateway",
        "physical_run_id": "synthetic-run",
        "case_id": None,
        "case_attempt_index": 1,
        "logical_action_id": "synthetic-logical",
        "run_id": "synthetic-run",
        "episode_id": "synthetic-episode",
        "turn_id": 0,
        "active_player": state.active_player,
        "seat_id": state.active_player,
        "status": "completed",
        "outcome": "ok",
        "wire_parse_status": "ok",
        "action_parse_status": "ok",
        "status_code": 200,
        "action_applied": False,
        "attempt_index": 1,
        "attempt_kind": "primary",
        "usage_complete": True,
        "cost_complete": False,
        "request_id": None,
    }
    scope = {k: receipt[k] for k in ("run_id", "episode_id", "turn_id", "active_player")}
    metadata = {
        k: receipt[k]
        for k in ("physical_run_id", "case_id", "case_attempt_index", "logical_action_id")
    }
    metadata["state_hash"] = state.state_hash
    row = {
        **scope,
        "event_id": "synthetic-trace",
        "event_type": "action",
        "protocol_version": "eslams-act-v1",
        "actor_player": state.active_player,
        "seat": state.active_player,
        "logical_action_id": "synthetic-logical",
        "markers": [],
        "action_provenance": "local_action",
        "successful_attempt_event_id": None,
        "action": action,
        "state_before": state.to_dict(),
        "state_after": after.to_dict(),
        "state_hash_before": state.state_hash,
        "state_hash_after": after.state_hash,
        "request": {
            "protocol_version": "eslams-act-v1",
            **scope,
            "arena": {"id": slug, "version": arena.version},
            "legal_actions": state.legal_actions_by_player[state.active_player],
            "metadata": metadata,
            "private_canary": CANARY,
        },
        "response": {
            "action": action,
            "private_canary": CANARY,
            "metadata": {
                "provider_receipt": dict(receipt),
                "ai_gateway_request_id": "synthetic-gateway",
                "attempt_receipts": [
                    {
                        k: v
                        for k, v in receipt.items()
                        if k not in {"usage_complete", "cost_complete"}
                    }
                ],
            },
        },
    }
    return {
        "manifest.json": {
            "run_id": "synthetic-run",
            "arena_version": arena.version,
            "artifact_version": "eslams-artifact-v1",
            "manifest_schema_version": "eslams.artifact.manifest.v1",
            "artifact_kind": "local_match",
            "artifact_profile": "runner_bundle",
            "artifact_profile_key": "runner_bundle",
            "hash_algorithm": "sha256",
            "unhashed_files": [],
            **dict.fromkeys(
                (
                    "match_valid_for_scoring",
                    "per_case_run_valid",
                    "per_case_scoring_eligible",
                    "proof_row_publication_eligible",
                    "aggregate_leaderboard_eligible",
                ),
                False,
            ),
        },
        "environment/package_versions.json": {"eslams-core": "0.6.2"},
        "receipts/provider_receipts.jsonl": [receipt],
        "traces/auditor_trace.jsonl": [row],
        "traces/public_trace.jsonl": [
            {k: row[k] for k in ("action", "event_id", "state_hash_before", "state_hash_after")}
        ],
        "logs/errors.jsonl": [
            {
                "turn_id": 1,
                "player_id": after.active_player,
                "policy": "invalid-match",
                "reason": f"{after.active_player}:agent_crash:agent_crash,no_action",
                "response_metadata": {
                    "error_kind": "agent_crash",
                    "error": CANARY
                    + " 502 Bad Gateway https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502",
                },
            }
        ],
    }


def archive(tmp_path: Path, data: dict[str, Any]) -> tuple[Path, str]:
    raw = {
        k: (
            "\n".join(json.dumps(v) for v in value) if k.endswith(".jsonl") else json.dumps(value)
        ).encode()
        for k, value in data.items()
        if k != "manifest.json"
    }
    manifest = {
        **data["manifest.json"],
        "files": [
            {"path": k, "bytes": len(v), "sha256": "sha256:" + hashlib.sha256(v).hexdigest()}
            for k, v in raw.items()
        ],
    }
    raw["manifest.json"] = json.dumps(manifest).encode()
    path = tmp_path / "synthetic.eslams"
    with zipfile.ZipFile(path, "w") as z:
        for k, v in raw.items():
            z.writestr(k, v)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("slug", list(inspector.ARENAS))
def test_supported_prefix_is_nonexecutable_and_private(tmp_path: Path, slug: str) -> None:
    path, digest = archive(tmp_path, fixture(slug))
    original = path.read_bytes()
    report = inspector.inspect_legacy_board_evidence(path, digest)
    assert path.read_bytes() == original
    assert report["prefix"]["action_count"] == 1
    assert report["final_attempt"]["spend"] == "unknown"
    assert report["final_attempt"]["physical_call_count"] == "unknown"
    assert not report["executable"] and not report["scoring_eligible"]
    assert not report["official_admission"]
    assert set(report["assurance"].values()) == {"unverified"}
    assert CANARY not in json.dumps(report)
    assert "synthetic-" not in json.dumps(report)
    assert not {"descriptor", "execution", "actions", "state", "receipt"} & report.keys()


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_receipt",
        "orphan",
        "null_gateway",
        "wrong_action",
        "bool_turn",
        "wrong_state",
        "marker",
        "failed",
        "wrong_episode",
        "missing_nested",
        "extra_attempt",
        "wrong_final",
        "version",
        "wrong_public",
    ],
)
def test_contradictions_rejected(tmp_path: Path, mutation: str) -> None:
    data = fixture()
    row = data["traces/auditor_trace.jsonl"][0]
    receipt = data["receipts/provider_receipts.jsonl"][0]
    if mutation == "duplicate_receipt":
        data["receipts/provider_receipts.jsonl"].append(receipt)
    elif mutation == "orphan":
        receipt["event_id"] = "synthetic-orphan"
    elif mutation == "null_gateway":
        receipt["gateway_request_id"] = None
    elif mutation == "wrong_action":
        row["response"]["action"] = {"bad": CANARY}
    elif mutation == "bool_turn":
        row["turn_id"] = False
    elif mutation == "wrong_state":
        row["state_after"]["state_hash"] = CANARY
    elif mutation == "marker":
        row["markers"] = ["fallback"]
    elif mutation == "failed":
        receipt["outcome"] = "error"
    elif mutation == "wrong_episode":
        row["episode_id"] = CANARY
    elif mutation == "missing_nested":
        del row["response"]["metadata"]["provider_receipt"]
    elif mutation == "extra_attempt":
        row["response"]["metadata"]["attempt_receipts"].append(receipt)
    elif mutation == "wrong_final":
        data["logs/errors.jsonl"][0]["turn_id"] = 2
    elif mutation == "version":
        data["environment/package_versions.json"]["eslams-core"] = "0.8.1"
    else:
        data["traces/public_trace.jsonl"][0]["state_hash_before"] = CANARY
    path, digest = archive(tmp_path, data)
    with pytest.raises(inspector.EvidenceError) as exc:
        inspector.inspect_legacy_board_evidence(path, digest)
    assert CANARY not in str(exc.value)
    assert "synthetic-" not in str(exc.value)


def test_digest_and_symlink_rejected(tmp_path: Path) -> None:
    path, digest = archive(tmp_path, fixture())
    with pytest.raises(inspector.EvidenceError, match="archive_digest_mismatch"):
        inspector.inspect_legacy_board_evidence(path, "0" * 64)
    link = tmp_path / "link.eslams"
    link.symlink_to(path)
    with pytest.raises(inspector.EvidenceError, match="regular_file_required"):
        inspector.inspect_legacy_board_evidence(link, digest)


def test_duplicate_keys_and_nonfinite_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.json"
    for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
        path.write_text(raw)
        with pytest.raises(inspector.EvidenceError):
            inspector.read(path)


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "alias",
        "duplicate",
        "symlink",
        "bad_member_hash",
        "missing_member",
        "line_limit",
        "row_limit",
        "archive_limit",
    ],
)
def test_archive_attacks(tmp_path: Path, kind: str, monkeypatch: Any) -> None:
    import stat

    path, _ = archive(tmp_path, fixture())
    with zipfile.ZipFile(path) as z:
        raw = {n: z.read(n) for n in z.namelist()}
    if kind == "traversal":
        raw["../escape"] = b"not allowed"
    elif kind == "alias":
        raw["MANIFEST.JSON"] = raw["manifest.json"]
    elif kind == "bad_member_hash":
        raw["logs/errors.jsonl"] += b" "
    elif kind == "missing_member":
        del raw["receipts/provider_receipts.jsonl"]
    elif kind == "line_limit":
        raw["manifest.json"] = b" " * (1024 * 1024 + 1)
    elif kind == "row_limit":
        raw["traces/auditor_trace.jsonl"] = b"{}\n" * 129
        manifest = json.loads(raw["manifest.json"])
        for entry in manifest["files"]:
            if entry["path"] == "traces/auditor_trace.jsonl":
                body = raw[entry["path"]]
                entry["bytes"] = len(body)
                entry["sha256"] = "sha256:" + hashlib.sha256(body).hexdigest()
        raw["manifest.json"] = json.dumps(manifest).encode()
    elif kind == "archive_limit":
        monkeypatch.setattr(inspector, "LIMITS", inspector.ArchiveLimits(archive_bytes=1))
    with zipfile.ZipFile(path, "w") as z:
        for name, body in raw.items():
            z.writestr(name, body)
        if kind == "symlink":
            entry = zipfile.ZipInfo("unsafe-link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(entry, "outside")
        elif kind == "duplicate":
            with pytest.warns(UserWarning):
                z.writestr("manifest.json", raw["manifest.json"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(inspector.EvidenceError):
        inspector.inspect_legacy_board_evidence(path, digest)
    assert not (tmp_path / "escape").exists()


def test_report_contract_and_502_does_not_attest_execution(tmp_path: Path) -> None:
    data = fixture()
    data["logs/errors.jsonl"][0]["response_metadata"]["error"] = (
        "Server error '502 Bad Gateway' for url 'https://synthetic.invalid/private'\n"
        "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/502"
    )
    path, digest = archive(tmp_path, data)
    report = inspector.inspect_legacy_board_evidence(path, digest)
    assert set(report) == {
        "schema_version",
        "archive_sha256",
        "arena",
        "verified",
        "prefix",
        "final_attempt",
        "assurance",
        "executable",
        "scoring_eligible",
        "official_admission",
    }
    assert report["schema_version"] == "legacy-board-evidence/v1"
    assert report["final_attempt"] == {
        "archive_error": "http_502_bad_gateway",
        "failed_receipt_present": False,
        "provider_execution": "unknown",
        "physical_call_count": "unknown",
        "spend": "unknown",
    }
    assert "https://" not in json.dumps(report)
    # No optional boolean/assurance flag is accepted by this API.
    with pytest.raises(TypeError):
        inspector.inspect_legacy_board_evidence(path, digest, trust_legacy=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest_version",
        "scoring_claim",
        "unlisted",
        "failed_final_receipt",
        "failed_final_attempt",
        "wrong_event_type",
        "wrong_protocol",
        "unknown_error",
        "missing_error",
        "null_identity",
        "bool_attempt",
        "wrong_actor",
    ],
)
def test_review_regressions(tmp_path: Path, mutation: str) -> None:
    data = fixture()
    row = data["traces/auditor_trace.jsonl"][0]
    if mutation == "manifest_version":
        data["manifest.json"]["artifact_version"] = "future-unsupported"
    elif mutation == "scoring_claim":
        data["manifest.json"]["match_valid_for_scoring"] = True
    elif mutation == "failed_final_receipt":
        data["logs/errors.jsonl"][0]["response_metadata"]["provider_receipt"] = {
            "status": "failed",
            "event_id": "synthetic-failed",
        }
    elif mutation == "failed_final_attempt":
        data["logs/errors.jsonl"][0]["response_metadata"]["attempt_receipts"] = []
    elif mutation == "wrong_event_type":
        row["event_type"] = "forfeit"
    elif mutation == "wrong_protocol":
        row["request"]["protocol_version"] = "future-unsupported"
    elif mutation == "unknown_error":
        data["logs/errors.jsonl"][0]["response_metadata"]["error"] = CANARY
    elif mutation == "missing_error":
        data["logs/errors.jsonl"] = []
    elif mutation == "null_identity":
        data["receipts/provider_receipts.jsonl"][0]["event_id"] = None
    elif mutation == "bool_attempt":
        data["receipts/provider_receipts.jsonl"][0]["attempt_index"] = True
    elif mutation == "wrong_actor":
        row["actor_player"] = "player_2"
    path, digest = archive(tmp_path, data)
    if mutation == "unlisted":
        with zipfile.ZipFile(path, "a") as z:
            z.writestr("unlisted.json", "{}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(inspector.EvidenceError):
        inspector.inspect_legacy_board_evidence(path, digest)


def test_overflow_is_not_finite_json(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    path.write_text('{"ignored":1e999}')
    with pytest.raises(inspector.EvidenceError, match="nonfinite_json"):
        inspector.read(path)


def test_schema_rejects_elevations_and_extra_fields(tmp_path: Path) -> None:
    import copy

    path, digest = archive(tmp_path, fixture())
    report = inspector.inspect_legacy_board_evidence(path, digest)
    schema = board_recovery_schemas()["legacy-board-evidence/v1"]
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    for key in ("executable", "official_admission", "scoring_eligible"):
        changed = {**report, key: True}
        assert list(validator.iter_errors(changed))
    for section in ("assurance", "verified", "prefix", "arena", "final_attempt"):
        changed = copy.deepcopy(report)
        changed[section]["extra"] = CANARY
        assert list(validator.iter_errors(changed))
    changed = copy.deepcopy(report)
    changed["assurance"]["route"] = "verified"
    assert list(validator.iter_errors(changed))
    changed = copy.deepcopy(report)
    changed["final_attempt"]["physical_call_count"] = 0
    assert list(validator.iter_errors(changed))


def test_no_secret_example_matches_closed_schema() -> None:
    schema = board_recovery_schemas()["legacy-board-evidence/v1"]
    example = no_secret_examples()["legacy-board-evidence/v1"]
    jsonschema.Draft202012Validator(schema).validate(example)
