"""Closed recovery contracts cannot promote historical or competitive assurance."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from eslams.contracts import board_recovery as contracts
from eslams.contracts.json_schema import export_schemas, schema_filename, schema_for_version
from eslams.contracts.versions import (
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    schema_versions,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_ENGINE_SCHEMA_VERSION as ENGINE,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION as LINEAGE,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION as PREPARATION,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION as PUBLIC_RESULT,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_SCHEMA_VERSION as DESCRIPTOR,
)
from eslams.contracts.versions import (
    BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION as VALIDATION,
)
from eslams.contracts.versions import (
    LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION as EVIDENCE,
)

VALIDATORS = {
    VALIDATION: contracts.validate_board_recovery_validation,
    DESCRIPTOR: contracts.validate_board_recovery_descriptor,
    ENGINE: contracts.validate_board_recovery_engine,
    LINEAGE: contracts.validate_board_recovery_lineage,
    PREPARATION: contracts.validate_board_recovery_preparation,
    PUBLIC_RESULT: contracts.validate_board_recovery_public_result,
    EVIDENCE: contracts.validate_legacy_board_evidence,
}


def example(version: str) -> dict[str, Any]:
    return contracts.no_secret_examples()[version]


def reject(version: str, value: Any) -> None:
    with pytest.raises(ValueError, match="^invalid board recovery contract$"):
        VALIDATORS[version](value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema_for_version(version))


@pytest.mark.parametrize("version", list(VALIDATORS))
def test_recovery_contracts_registered_schema_examples_and_detached_copies(version):
    schema = schema_for_version(version)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert version in schema_versions()
    value = example(version)
    jsonschema.validate(value, schema)
    validated = VALIDATORS[version](value)
    assert validated == value
    assert validated is not value
    value.clear()
    assert validated


@pytest.mark.parametrize("version", list(VALIDATORS))
@pytest.mark.parametrize("value", [None, [], "secret-content", 1, True])
def test_recovery_rejects_nonobject_without_echoing_private_values(version, value):
    reject(version, value)


def object_paths(value: Any, path: tuple[Any, ...] = ()):
    if isinstance(value, dict):
        yield path
        for key, child in value.items():
            yield from object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from object_paths(child, (*path, index))


def at_path(value: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        value = value[key]
    return value


@pytest.mark.parametrize("version", list(VALIDATORS))
def test_every_object_is_closed_and_requires_every_declared_field(version):
    value = example(version)
    for path in object_paths(value):
        changed = copy.deepcopy(value)
        at_path(changed, path)["private_token"] = "must-not-appear-in-errors"
        reject(version, changed)
        for key in at_path(value, path):
            changed = copy.deepcopy(value)
            del at_path(changed, path)[key]
            reject(version, changed)


@pytest.mark.parametrize("path,replacement", [
    (("scoringEligible",), True),
    (("scoringEligible",), 0),
    (("officialAdmission",), True),
    (("executionMode",), "verified_continuation"),
    (("history", "coreVersion"), "0.8.1"),
    (("history", "arenaSlug"), "chess"),
    (("history", "seed"), True),
    (("history", "maxTurns"), 0),
    (("history", "timeBudgetMs"), 0),
    (("history", "timeBudgetMs"), True),
    (("prospective", "maxTurns"), -1),
    (("prospective", "timeBudgetMs"), "1000"),
    (("prospective", "turnLimitPolicy"), "unbounded"),
    (("prospective", "deadlinePolicy"), "guess-native-default"),
    (("history", "requestedTimeBudgetMs"), False),
    (("history", "requestedTimeBudgetRecorded"), 0),
    (("prefix", "acceptedPlyCount"), 65),
    (("prefix", "checkpointStateSha256"), "sha256:" + "0" * 64),
    (("source", "artifactSha256"), "A" * 64),
    (("source", "artifactSha256"), "0" * 64 + "\n"),
    (("source", "matchId"), "   "),
    (("prospective", "players", 0, "seat"), "player_2"),
    (("history", "requestedParticipants", 1, "seat"), "player_1"),
])
def test_descriptor_rejects_promotion_coercion_and_unordered_seats(path, replacement):
    value = example(DESCRIPTOR)
    at_path(value, path[:-1])[path[-1]] = replacement
    reject(DESCRIPTOR, value)


def test_signed_seeds_null_budget_and_preserve_source_policy_are_supported():
    value = example(DESCRIPTOR)
    value["history"]["seed"] = -100
    value["prospective"]["turnLimitPolicy"] = "preserve-source"
    assert contracts.validate_board_recovery_descriptor(value) == value
    jsonschema.validate(value, schema_for_version(DESCRIPTOR))


def test_historical_and_prospective_deadline_policies_are_distinct():
    value = example(DESCRIPTOR)
    assert value["history"]["timeBudgetMs"] == 30_000
    assert value["history"]["requestedTimeBudgetMs"] == 30_000
    assert value["history"]["requestedTimeBudgetRecorded"] is True
    assert value["prospective"]["deadlinePolicy"] == "native-default"
    assert value["prospective"]["timeBudgetMs"] is None
    contracts.validate_board_recovery_descriptor(value)
    value["history"].update(requestedTimeBudgetMs=None, requestedTimeBudgetRecorded=False)
    value["prospective"].update(deadlinePolicy="preserve-source-effective", timeBudgetMs=30_000)
    contracts.validate_board_recovery_descriptor(value)
    jsonschema.validate(value, schema_for_version(DESCRIPTOR))


def installed_engine():
    value = example(ENGINE)
    value.pop("runnerImageDigest")
    value.update(coreRef="a" * 40, platformRef="b" * 40,
                 wrapperSourceSha256="c" * 64, runnerBuildSha256="d" * 64)
    return value


def test_installed_and_local_engine_variants_are_closed_and_mutually_exclusive():
    value = installed_engine()
    assert contracts.validate_board_recovery_engine(value) == value
    jsonschema.validate(value, schema_for_version(ENGINE))
    for field in ("platformRef", "wrapperSourceSha256", "runnerBuildSha256"):
        changed = copy.deepcopy(value)
        del changed[field]
        reject(ENGINE, changed)
    value["runnerImageDigest"] = "local-development"
    reject(ENGINE, value)
    value = example(ENGINE)
    value["platformRef"] = "a" * 40
    reject(ENGINE, value)
    value = installed_engine()
    value["coreRef"] = "main"
    reject(ENGINE, value)


@pytest.mark.parametrize("path,replacement", [
    (("assurance", "route"), "verified"),
    (("assurance", "signed_build"), "verified"),
    (("assurance", "scoringEligible"), True),
    (("accounting", "historicalSpend"), 0),
    (("accounting", "historicalFinalPhysicalCallCount"), 0),
    (("accounting", "aggregateScope"), "all_history"),
    (("publicationRequiresAuthoritativeSourceReread",), False),
    (("historicalLedger", "path"), "../provider_receipts.jsonl"),
    (("historicalLedger", "receiptCount"), True),
    (("sourceArchive", "path"), "untrusted/source.eslams"),
    (("evidenceReport", "final_attempt", "spend"), 0),
    (("evidenceReport", "executable"), True),
])
def test_lineage_cannot_promote_historical_evidence_or_hide_source_reread(path, replacement):
    value = example(LINEAGE)
    at_path(value, path[:-1])[path[-1]] = replacement
    reject(LINEAGE, value)


def test_preparation_is_never_execution_or_publication_permission():
    for key, value in (("newProviderCalls", 1), ("newProviderCalls", False),
                       ("executionEligible", True), ("publicationEligible", True)):
        changed = example(PREPARATION)
        changed[key] = value
        reject(PREPARATION, changed)


@pytest.mark.parametrize("key,replacement", [
    ("competitiveWinner", "player_1"), ("scoringEligible", True),
    ("historicalSpend", 0), ("historicalFinalPhysicalCallCount", 1),
    ("executionLabel", "Recovered verified match"), ("accountingScope", "complete"),
    ("reconstructedTurns", True), ("incrementalTurns", -1),
    ("boardOutcome", {"winnerSeat": "player_1", "draw": False}),
])
def test_public_result_rejects_scoring_claims_and_nonterminal_outcomes(key, replacement):
    value = example(PUBLIC_RESULT)
    value[key] = replacement
    reject(PUBLIC_RESULT, value)


def test_public_result_terminal_board_outcome_is_separate_from_competitive_winner():
    value = example(PUBLIC_RESULT)
    value.update(terminal=True, incrementalTurns=4,
                 boardOutcome={"winnerSeat": "player_1", "draw": False})
    contracts.validate_board_recovery_public_result(value)
    jsonschema.validate(value, schema_for_version(PUBLIC_RESULT))
    assert value["competitiveWinner"] is None
    value["boardOutcome"]["rawScore"] = {"player_1": 1}
    reject(PUBLIC_RESULT, value)
    value["boardOutcome"] = None
    reject(PUBLIC_RESULT, value)


def test_evidence_arena_versions_match_the_historical_inspector():
    for arena, version in (("tic-tac-toe", "1.0.0"), ("connect-four", "1.0.0"),
                           ("othello", "1.0.1")):
        value = example(EVIDENCE)
        value["arena"] = {"slug": arena, "version": version}
        contracts.validate_legacy_board_evidence(value)
        jsonschema.validate(value, schema_for_version(EVIDENCE))
        value["arena"]["version"] = "1.0.1" if version == "1.0.0" else "1.0.0"
        reject(EVIDENCE, value)


def test_flat_schema_exports_preserve_wire_identity_and_deterministic_bytes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first_paths = export_schemas(first)
    export_schemas(second)
    for path in first_paths:
        relative = path.relative_to(first)
        assert path.read_bytes() == (second / relative).read_bytes()
    manifest = json.loads((first / "schema_bundle_manifest.json").read_text())
    rows = {row["schema_version"]: row for row in manifest["schemas"]}
    for version in VALIDATORS:
        assert rows[version]["name"] == schema_filename(version)
        assert (first / rows[version]["name"]).is_file()


def test_flat_export_into_current_directory_keeps_wire_version_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    export_schemas(Path("."))
    manifest = json.loads(Path("schema_bundle_manifest.json").read_text())
    rows = {row["schema_version"]: row for row in manifest["schemas"]}
    for version in VALIDATORS:
        assert rows[version]["name"] == schema_filename(version)


def test_typescript_is_generated_from_current_schema_definitions():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "generate_recovery_types", root / "scripts/generate_board_recovery_types.py",
    )
    assert spec and spec.loader
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    expected = generator.generated_typescript()
    assert generator.TARGET.read_text() == expected
    for name in contracts.board_recovery_contract_definitions():
        assert f"export interface {name} " in expected or f"export type {name} " in expected
    assert 'export * from "./board-recovery.js";' in (
        root / "packages/core-contracts/src/generated/index.ts"
    ).read_text()


@pytest.mark.parametrize("key,value", [
    ("status", "official"), ("validatorScope", "external_custody"),
    ("scoringEligible", True), ("officialAdmission", True),
    ("publicationRequiresAuthoritativeSourceReread", False),
    ("lineageSchemaVersion", "chess-continuation-lineage/v2"),
])
def test_validation_marker_cannot_claim_external_custody(key, value):
    payload = example(VALIDATION)
    payload[key] = value
    reject(VALIDATION, payload)


def test_generic_validation_schema_allows_only_closed_optional_recovery_marker():
    schema = schema_for_version(ARTIFACT_VALIDATION_SCHEMA_VERSION)
    payload = {"schema_version": ARTIFACT_VALIDATION_SCHEMA_VERSION,
               "artifact": "example.eslams", "profile": "runner_bundle", "valid": True,
               "validation_status": "valid"}
    jsonschema.validate(payload, schema)
    payload["recovered_position"] = example(VALIDATION)
    jsonschema.validate(payload, schema)
    payload["recovered_position"]["sourceIds"] = {"artifactKey": "private"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
    payload["recovered_position"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_validation_marker_contains_no_target_or_external_custody_attestation():
    marker = example(VALIDATION)
    assert marker["validatorScope"] == "child_internal_source_replay"
    for key in ("targetEngineVerified", "sourceCustodyVerified", "providerAuthenticityVerified"):
        changed = {**marker, key: True}
        reject(VALIDATION, changed)


def test_schema_filenames_remain_flat_and_collision_free(tmp_path):
    names = [schema_filename(version) for version in schema_versions()]
    assert len(names) == len(set(names))
    assert all("/" not in name and "\\" not in name for name in names)
    assert schema_filename("board-recovery/v1") == "board-recovery.v1.schema.json"
    written = export_schemas(tmp_path)
    assert all(path.parent == tmp_path and path.is_file() for path in written)
    assert all(path.is_file() for path in tmp_path.iterdir())
