"""Closed, non-scoring wire contracts for archive-internal board recovery.

These contracts describe custody claims; structural validation does not verify
source authority, digests, replay legality, provider identity or build evidence.
The execution layer must independently verify those before running a child.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from eslams.contracts.versions import (
    BOARD_RECOVERY_ENGINE_SCHEMA_VERSION,
    BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION,
    BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION,
    BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION,
    BOARD_RECOVERY_SCHEMA_VERSION,
    BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION,
    CORE_PACKAGE_VERSION,
    LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION,
    RUNNER_VERSION,
)
from eslams.hashing import canonical_json

if TYPE_CHECKING:
    from eslams.legacy_board_evidence import EvidenceReport

BoardRecoveryArena = Literal["tic-tac-toe", "connect-four", "othello"]
BoardRecoverySeat = Literal["player_1", "player_2"]
BoardRecoveryTurnLimitPolicy = Literal["preserve-source", "native-arena-horizon"]
BoardRecoveryDeadlinePolicy = Literal["preserve-source-effective", "native-default"]


class BoardRecoveryValidation(TypedDict):
    schemaVersion: Literal["board-recovery-validation/v1"]
    status: Literal["verified"]
    lineageSchemaVersion: Literal["board-recovery-lineage/v1"]
    executionMode: Literal["unscored_recovered_position"]
    scoringEligible: Literal[False]
    officialAdmission: Literal[False]
    validatorScope: Literal["child_internal_source_replay"]
    publicationRequiresAuthoritativeSourceReread: Literal[True]


class BoardRecoverySource(TypedDict):
    matchId: str
    runId: str
    artifactId: str
    artifactKey: str
    coreRunId: str
    artifactSha256: str
    sourcePayloadSha256: str


class BoardRecoveryRequestedParticipant(TypedDict):
    seat: BoardRecoverySeat
    modelId: str
    modelVersionId: str


class BoardRecoveryHistory(TypedDict):
    coreVersion: Literal["0.6.2"]
    arenaSlug: BoardRecoveryArena
    arenaVersion: str
    seed: int
    maxTurns: int
    timeBudgetMs: int | None
    requestedTimeBudgetMs: int | None
    requestedTimeBudgetRecorded: bool
    requestedParticipants: list[BoardRecoveryRequestedParticipant]


class BoardRecoveryPrefix(TypedDict):
    acceptedPlyCount: int
    prefixSha256: str
    checkpointStateSha256: str


class BoardRecoveryPlayer(BoardRecoveryRequestedParticipant):
    provider: str
    providerModelId: str
    routeKey: str
    routeSha256: str


class BoardRecoveryProspective(TypedDict):
    wrapperVersion: str
    runnerVersion: str
    scoringPolicyVersion: str
    rulesSha256: str
    maxTurns: int
    turnLimitPolicy: BoardRecoveryTurnLimitPolicy
    deadlinePolicy: BoardRecoveryDeadlinePolicy
    timeBudgetMs: int | None
    players: list[BoardRecoveryPlayer]


class BoardRecoveryDescriptor(TypedDict):
    schemaVersion: Literal["board-recovery/v1"]
    executionMode: Literal["unscored_recovered_position"]
    scoringEligible: Literal[False]
    officialAdmission: Literal[False]
    source: BoardRecoverySource
    history: BoardRecoveryHistory
    prefix: BoardRecoveryPrefix
    prospective: BoardRecoveryProspective
    evidenceReportSha256: str
    prospectiveSha256: str


class _BoardRecoveryEngineBase(TypedDict):
    schemaVersion: Literal["board-recovery-engine/v1"]
    coreVersion: str
    coreSourceSha256: str
    runnerVersion: str
    wrapperVersion: str
    recoveryContractVersion: Literal["board-recovery-lineage/v1"]


class BoardRecoveryLocalEngine(_BoardRecoveryEngineBase):
    coreRef: Literal["local-development"]
    runnerImageDigest: Literal["local-development"]


class BoardRecoveryInstalledEngine(_BoardRecoveryEngineBase):
    coreRef: str
    platformRef: str
    wrapperSourceSha256: str
    runnerBuildSha256: str


BoardRecoveryEngine = BoardRecoveryLocalEngine | BoardRecoveryInstalledEngine


class BoardRecoveryPreparation(TypedDict):
    schemaVersion: Literal["board-recovery-preparation/v1"]
    descriptor: BoardRecoveryDescriptor
    targetEngine: BoardRecoveryEngine
    descriptorSha256: str
    targetEngineSha256: str
    newProviderCalls: Literal[0]
    executionEligible: Literal[False]
    publicationEligible: Literal[False]


class BoardRecoveryPublicParticipant(BoardRecoveryRequestedParticipant):
    provider: str
    providerModelId: str


class BoardRecoveryHistoricalAssurance(TypedDict):
    signed_build: Literal["unverified"]
    route: Literal["unverified"]
    platform_case: Literal["unverified"]
    provider_authenticity: Literal["unverified"]


class BoardRecoveryBoardOutcome(TypedDict):
    winnerSeat: BoardRecoverySeat | None
    draw: bool


class BoardRecoveryPublicResult(TypedDict):
    schemaVersion: Literal["board-recovery-public-result/v1"]
    executionMode: Literal["unscored_recovered_position"]
    executionLabel: Literal["Recovered position; historical model routing unverified"]
    scoringEligible: Literal[False]
    officialAdmission: Literal[False]
    competitiveWinner: None
    historicalAssurance: BoardRecoveryHistoricalAssurance
    historicalSpend: Literal["unknown"]
    historicalFinalPhysicalCallCount: Literal["unknown"]
    accountingScope: Literal["incremental_only"]
    reconstructedTurns: int
    incrementalTurns: int
    terminal: bool
    boardOutcome: BoardRecoveryBoardOutcome | None
    requestedHistoricalParticipants: list[BoardRecoveryRequestedParticipant]
    prospectiveParticipants: list[BoardRecoveryPublicParticipant]


class BoardRecoveryChild(TypedDict):
    coreRunId: str
    platformRunId: str
    matchId: str


class BoardRecoveryHistoricalLedger(TypedDict):
    path: Literal["recovery/source_provider_receipts.jsonl"]
    sha256: str
    receiptCount: int


class BoardRecoverySourceArchive(TypedDict):
    path: Literal["recovery/source.eslams"]
    sha256: str


class BoardRecoveryAccounting(TypedDict):
    historicalSpend: Literal["unknown"]
    historicalFinalPhysicalCallCount: Literal["unknown"]
    aggregateScope: Literal["incremental_only"]


class BoardRecoveryAssurance(TypedDict):
    signed_build: Literal["unverified"]
    route: Literal["unverified"]
    platform_case: Literal["unverified"]
    provider_authenticity: Literal["unverified"]
    scoringEligible: Literal[False]
    officialAdmission: Literal[False]


class BoardRecoveryLineage(TypedDict):
    schemaVersion: Literal["board-recovery-lineage/v1"]
    descriptor: BoardRecoveryDescriptor
    descriptorSha256: str
    child: BoardRecoveryChild
    targetEngine: BoardRecoveryEngine
    targetEngineSha256: str
    evidenceReport: EvidenceReport
    evidenceReportSha256: str
    historicalLedger: BoardRecoveryHistoricalLedger
    sourceArchive: BoardRecoverySourceArchive
    accounting: BoardRecoveryAccounting
    assurance: BoardRecoveryAssurance
    publicationRequiresAuthoritativeSourceReread: Literal[True]


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": properties, "required": list(properties),
    }


def _seats(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "array", "minItems": 2, "maxItems": 2,
        "prefixItems": [
            _object({**item["properties"], "seat": {"const": seat}})
            for seat in ("player_1", "player_2")
        ],
        "items": False,
    }


def board_recovery_contract_definitions() -> dict[str, dict[str, Any]]:
    """Return fresh closed definitions, also used by the TypeScript generator."""
    text = {"type": "string", "minLength": 1, "maxLength": 512, "pattern": r"\S"}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$",
              "minLength": 64, "maxLength": 64}
    positive = {"type": "integer", "minimum": 1}
    budget = {"type": ["integer", "null"], "minimum": 1}
    arena = {"enum": ["tic-tac-toe", "connect-four", "othello"]}
    seat = {"enum": ["player_1", "player_2"]}
    assurance = _object({key: {"const": "unverified"} for key in (
        "signed_build", "route", "platform_case", "provider_authenticity",
    )})
    evidence_arena = _object({"slug": arena, "version": {"enum": ["1.0.0", "1.0.1"]}})
    evidence_arena["oneOf"] = [{"properties": {
        "slug": {"const": slug}, "version": {"const": version},
    }} for slug, version in (
        ("tic-tac-toe", "1.0.0"), ("connect-four", "1.0.0"), ("othello", "1.0.1"),
    )]
    evidence = _object({
        "schema_version": {"const": LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION},
        "archive_sha256": digest,
        "arena": evidence_arena,
        "verified": _object({key: {"const": True} for key in (
            "listed_member_digests", "legal_prefix", "archive_internal_receipt_association",
        )}),
        "prefix": _object({
            "action_count": {"type": "integer", "minimum": 1, "maximum": 64},
            "final_state_sha256": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$",
                                   "minLength": 71, "maxLength": 71},
            "terminal": {"const": False},
        }),
        "final_attempt": _object({
            "archive_error": {"const": "http_502_bad_gateway"},
            "failed_receipt_present": {"const": False},
            **{key: {"const": "unknown"} for key in (
                "provider_execution", "physical_call_count", "spend",
            )},
        }),
        "assurance": assurance,
        "executable": {"const": False},
        "scoring_eligible": {"const": False},
        "official_admission": {"const": False},
    })
    source = _object({
        **dict.fromkeys(("matchId", "runId", "artifactId", "artifactKey", "coreRunId"), text),
        "artifactSha256": digest, "sourcePayloadSha256": digest,
    })
    participant = _object({"seat": seat, "modelId": text, "modelVersionId": text})
    player = _object({
        **participant["properties"], "provider": text, "providerModelId": text,
        "routeKey": text, "routeSha256": digest,
    })
    history = _object({
        "coreVersion": {"const": "0.6.2"}, "arenaSlug": arena, "arenaVersion": text,
        "seed": {"type": "integer"}, "maxTurns": positive,
        "timeBudgetMs": budget, "requestedTimeBudgetMs": budget,
        "requestedTimeBudgetRecorded": {"type": "boolean"},
        "requestedParticipants": _seats(participant),
    })
    prefix = _object({
        "acceptedPlyCount": {"type": "integer", "minimum": 1, "maximum": 64},
        "prefixSha256": digest, "checkpointStateSha256": digest,
    })
    prospective = _object({
        "wrapperVersion": text, "runnerVersion": text, "scoringPolicyVersion": text,
        "rulesSha256": digest, "maxTurns": positive,
        "turnLimitPolicy": {"enum": ["preserve-source", "native-arena-horizon"]},
        "deadlinePolicy": {"enum": ["preserve-source-effective", "native-default"]},
        "timeBudgetMs": budget, "players": _seats(player),
    })
    descriptor = _object({
        "schemaVersion": {"const": BOARD_RECOVERY_SCHEMA_VERSION},
        "executionMode": {"const": "unscored_recovered_position"},
        "scoringEligible": {"const": False}, "officialAdmission": {"const": False},
        "source": source, "history": history, "prefix": prefix, "prospective": prospective,
        "evidenceReportSha256": digest, "prospectiveSha256": digest,
    })
    engine_base = {
        "schemaVersion": {"const": BOARD_RECOVERY_ENGINE_SCHEMA_VERSION},
        "coreVersion": text, "coreSourceSha256": digest,
        "runnerVersion": text, "wrapperVersion": text,
        "recoveryContractVersion": {"const": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION},
    }
    local_engine = _object({
        **engine_base, "coreRef": {"const": "local-development"},
        "runnerImageDigest": {"const": "local-development"},
    })
    installed_engine = _object({
        **engine_base, "coreRef": {"type": "string", "pattern": "^[0-9a-f]{40}$",
                                   "minLength": 40, "maxLength": 40},
        "platformRef": {"type": "string", "pattern": "^[0-9a-f]{40}$",
                        "minLength": 40, "maxLength": 40},
        "wrapperSourceSha256": digest, "runnerBuildSha256": digest,
    })
    engine = {"oneOf": [local_engine, installed_engine]}
    child = _object(dict.fromkeys(("coreRunId", "platformRunId", "matchId"), text))
    ledger = _object({
        "path": {"const": "recovery/source_provider_receipts.jsonl"}, "sha256": digest,
        "receiptCount": {"type": "integer", "minimum": 0},
    })
    archive = _object({"path": {"const": "recovery/source.eslams"}, "sha256": digest})
    accounting = _object({
        "historicalSpend": {"const": "unknown"},
        "historicalFinalPhysicalCallCount": {"const": "unknown"},
        "aggregateScope": {"const": "incremental_only"},
    })
    lineage_assurance = _object({
        **assurance["properties"],
        "scoringEligible": {"const": False}, "officialAdmission": {"const": False},
    })
    lineage = _object({
        "schemaVersion": {"const": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION},
        "descriptor": descriptor, "descriptorSha256": digest, "child": child,
        "targetEngine": engine, "targetEngineSha256": digest,
        "evidenceReport": evidence, "evidenceReportSha256": digest,
        "historicalLedger": ledger, "sourceArchive": archive, "accounting": accounting,
        "assurance": lineage_assurance,
        "publicationRequiresAuthoritativeSourceReread": {"const": True},
    })
    preparation = _object({
        "schemaVersion": {"const": BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION},
        "descriptor": descriptor, "targetEngine": engine,
        "descriptorSha256": digest, "targetEngineSha256": digest,
        "newProviderCalls": {"const": 0}, "executionEligible": {"const": False},
        "publicationEligible": {"const": False},
    })
    public_participant = _object({
        **participant["properties"], "provider": text, "providerModelId": text,
    })
    board_outcome = _object({
        "winnerSeat": {"enum": ["player_1", "player_2", None]}, "draw": {"type": "boolean"},
    })
    public_result = _object({
        "schemaVersion": {"const": BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION},
        "executionMode": {"const": "unscored_recovered_position"},
        "executionLabel": {"const": "Recovered position; historical model routing unverified"},
        "scoringEligible": {"const": False}, "officialAdmission": {"const": False},
        "competitiveWinner": {"const": None}, "historicalAssurance": assurance,
        "historicalSpend": {"const": "unknown"},
        "historicalFinalPhysicalCallCount": {"const": "unknown"},
        "accountingScope": {"const": "incremental_only"},
        "reconstructedTurns": {"type": "integer", "minimum": 0},
        "incrementalTurns": {"type": "integer", "minimum": 0},
        "terminal": {"type": "boolean"},
        "boardOutcome": {"oneOf": [board_outcome, {"type": "null"}]},
        "requestedHistoricalParticipants": _seats(participant),
        "prospectiveParticipants": _seats(public_participant),
    })
    public_result["oneOf"] = [
        {"properties": {"terminal": {"const": False}, "boardOutcome": {"type": "null"}}},
        {"properties": {"terminal": {"const": True}, "boardOutcome": board_outcome}},
    ]
    validation = _object({
        "schemaVersion": {"const": BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION},
        "status": {"const": "verified"},
        "lineageSchemaVersion": {"const": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION},
        "executionMode": {"const": "unscored_recovered_position"},
        "scoringEligible": {"const": False}, "officialAdmission": {"const": False},
        "validatorScope": {"const": "child_internal_source_replay"},
        "publicationRequiresAuthoritativeSourceReread": {"const": True},
    })
    return {
        "BoardRecoveryValidation": validation,
        "LegacyBoardEvidenceReport": evidence,
        "BoardRecoverySource": source,
        "BoardRecoveryRequestedParticipant": participant,
        "BoardRecoveryHistory": history,
        "BoardRecoveryPrefix": prefix,
        "BoardRecoveryPlayer": player,
        "BoardRecoveryProspective": prospective,
        "BoardRecoveryDescriptor": descriptor,
        "BoardRecoveryLocalEngine": local_engine,
        "BoardRecoveryInstalledEngine": installed_engine,
        "BoardRecoveryEngine": engine,
        "BoardRecoveryChild": child,
        "BoardRecoveryHistoricalLedger": ledger,
        "BoardRecoverySourceArchive": archive,
        "BoardRecoveryAccounting": accounting,
        "BoardRecoveryAssurance": lineage_assurance,
        "BoardRecoveryLineage": lineage,
        "BoardRecoveryPreparation": preparation,
        "BoardRecoveryPublicParticipant": public_participant,
        "BoardRecoveryHistoricalAssurance": assurance,
        "BoardRecoveryBoardOutcome": board_outcome,
        "BoardRecoveryPublicResult": public_result,
    }


_CONTRACT_NAMES = {
    BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION: "BoardRecoveryValidation",
    BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION: "BoardRecoveryPreparation",
    BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION: "BoardRecoveryPublicResult",
    LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION: "LegacyBoardEvidenceReport",
    BOARD_RECOVERY_SCHEMA_VERSION: "BoardRecoveryDescriptor",
    BOARD_RECOVERY_ENGINE_SCHEMA_VERSION: "BoardRecoveryEngine",
    BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION: "BoardRecoveryLineage",
}


def board_recovery_schemas() -> dict[str, dict[str, Any]]:
    """Return standalone JSON Schema documents without external references."""
    definitions = board_recovery_contract_definitions()
    return {version: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://eslams.com/schemas/{version}.schema.json",
        "title": name,
        **definitions[name],
    } for version, name in _CONTRACT_NAMES.items()}


def _matches(value: object, schema: dict[str, Any], depth: int = 0) -> bool:
    """Evaluate exactly the small JSON Schema subset emitted above, without IO."""
    if depth > 32:
        return False
    if "const" in schema and (type(value) is not type(schema["const"])
                              or value != schema["const"]):
        return False
    if "enum" in schema and not any(type(value) is type(item) and value == item
                                     for item in schema["enum"]):
        return False
    if "oneOf" in schema and sum(_matches(value, item, depth + 1)
                                  for item in schema["oneOf"]) != 1:
        return False
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        kinds = {"object": dict, "array": list, "string": str, "integer": int,
                 "boolean": bool, "null": type(None)}
        if not any(kinds[kind] is type(value) for kind in types):
            return False
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if not set(schema.get("required", [])).issubset(value):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        if any(not _matches(value[key], child, depth + 1)
               for key, child in properties.items() if key in value):
            return False
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", len(value)):
            return False
        prefix = schema.get("prefixItems", [])
        if schema.get("items") is False and len(value) > len(prefix):
            return False
        if any(not _matches(item, child, depth + 1) for item, child in zip(value, prefix)):
            return False
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", len(value)):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    return not (type(value) is int and (
        value < schema.get("minimum", value) or value > schema.get("maximum", value)
    ))


def _validate(value: object, version: str) -> Any:
    if not _matches(value, board_recovery_schemas()[version]):
        raise ValueError("invalid board recovery contract")
    return copy.deepcopy(value)


def validate_board_recovery_validation(value: object) -> BoardRecoveryValidation:
    """Validate a child-internal marker, never an external custody attestation."""
    return cast(BoardRecoveryValidation, _validate(value, BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION))


def validate_board_recovery_descriptor(value: object) -> BoardRecoveryDescriptor:
    """Validate the closed structure; execution verification is separate."""
    return cast(BoardRecoveryDescriptor, _validate(value, BOARD_RECOVERY_SCHEMA_VERSION))


def validate_board_recovery_engine(value: object) -> BoardRecoveryEngine:
    """Validate mutually exclusive local and installed attestation structures."""
    return cast(BoardRecoveryEngine, _validate(value, BOARD_RECOVERY_ENGINE_SCHEMA_VERSION))


def validate_board_recovery_lineage(value: object) -> BoardRecoveryLineage:
    """Validate lineage structure without asserting archive or build authenticity."""
    return cast(BoardRecoveryLineage, _validate(value, BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION))


def validate_board_recovery_preparation(value: object) -> BoardRecoveryPreparation:
    """Validate a non-executing preparation wrapper; it is not publication authority."""
    return cast(
        BoardRecoveryPreparation, _validate(value, BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION),
    )


def validate_board_recovery_public_result(value: object) -> BoardRecoveryPublicResult:
    """Reject private identity, provider route and scoring claims in public output."""
    return cast(
        BoardRecoveryPublicResult, _validate(value, BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION),
    )


def validate_legacy_board_evidence(value: object) -> EvidenceReport:
    """Validate the historical inspector's unchanged, non-executable report."""
    return cast("EvidenceReport", _validate(value, LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION))


def no_secret_examples() -> dict[str, dict[str, Any]]:
    """Synthetic examples with separate source history and prospective pins."""
    import hashlib

    def digest(value: object) -> str:
        return hashlib.sha256(canonical_json(value).encode()).hexdigest()

    h = "0" * 64
    evidence: dict[str, Any] = {
        "schema_version": LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION,
        "archive_sha256": h, "arena": {"slug": "tic-tac-toe", "version": "1.0.0"},
        "verified": dict.fromkeys((
            "listed_member_digests", "legal_prefix", "archive_internal_receipt_association",
        ), True),
        "prefix": {"action_count": 1, "final_state_sha256": "sha256:" + h, "terminal": False},
        "final_attempt": {
            "archive_error": "http_502_bad_gateway", "failed_receipt_present": False,
            "provider_execution": "unknown", "physical_call_count": "unknown", "spend": "unknown",
        },
        "assurance": dict.fromkeys((
            "signed_build", "route", "platform_case", "provider_authenticity",
        ), "unverified"),
        "executable": False, "scoring_eligible": False, "official_admission": False,
    }
    participants = [{"seat": seat, "modelId": "example-model", "modelVersionId": "example-v1"}
                    for seat in ("player_1", "player_2")]
    prospective: dict[str, Any] = {
        "wrapperVersion": "example-wrapper:v1", "runnerVersion": RUNNER_VERSION,
        "scoringPolicyVersion": "unscored:v1", "rulesSha256": h, "maxTurns": 9,
        "turnLimitPolicy": "native-arena-horizon", "deadlinePolicy": "native-default",
        "timeBudgetMs": None,
        "players": [{**item, "provider": "example-provider", "providerModelId": "example-v1",
                     "routeKey": "example-route", "routeSha256": h} for item in participants],
    }
    descriptor = {
        "schemaVersion": BOARD_RECOVERY_SCHEMA_VERSION,
        "executionMode": "unscored_recovered_position",
        "scoringEligible": False, "officialAdmission": False,
        "source": {"matchId": "example-source-match", "runId": "example-source-run",
                   "artifactId": "example-artifact", "artifactKey": "example/source.eslams",
                   "coreRunId": "example-source-core", "artifactSha256": h,
                   "sourcePayloadSha256": h},
        "history": {"coreVersion": "0.6.2", "arenaSlug": "tic-tac-toe", "arenaVersion": "1.0.0",
                    "seed": 0, "maxTurns": 3, "timeBudgetMs": 30_000,
                    "requestedTimeBudgetMs": 30_000, "requestedTimeBudgetRecorded": True,
                    "requestedParticipants": participants},
        "prefix": {"acceptedPlyCount": 1, "prefixSha256": h, "checkpointStateSha256": h},
        "prospective": prospective, "prospectiveSha256": digest(prospective),
        "evidenceReportSha256": digest(evidence),
    }
    engine = {
        "schemaVersion": BOARD_RECOVERY_ENGINE_SCHEMA_VERSION,
        "coreVersion": CORE_PACKAGE_VERSION, "coreRef": "local-development",
        "coreSourceSha256": h, "runnerVersion": RUNNER_VERSION,
        "wrapperVersion": "example-wrapper:v1", "runnerImageDigest": "local-development",
        "recoveryContractVersion": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION,
    }
    lineage = {
        "schemaVersion": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION,
        "descriptor": descriptor, "descriptorSha256": digest(descriptor),
        "child": {"coreRunId": "example-child-core", "platformRunId": "example-child-run",
                  "matchId": "example-child-match"},
        "targetEngine": engine, "targetEngineSha256": digest(engine),
        "evidenceReport": evidence, "evidenceReportSha256": digest(evidence),
        "historicalLedger": {"path": "recovery/source_provider_receipts.jsonl",
                             "sha256": h, "receiptCount": 1},
        "sourceArchive": {"path": "recovery/source.eslams", "sha256": h},
        "accounting": {"historicalSpend": "unknown", "historicalFinalPhysicalCallCount": "unknown",
                       "aggregateScope": "incremental_only"},
        "assurance": {**evidence["assurance"],
                      "scoringEligible": False, "officialAdmission": False},
        "publicationRequiresAuthoritativeSourceReread": True,
    }
    preparation = {
        "schemaVersion": BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION,
        "descriptor": descriptor, "targetEngine": engine,
        "descriptorSha256": digest(descriptor), "targetEngineSha256": digest(engine),
        "newProviderCalls": 0, "executionEligible": False, "publicationEligible": False,
    }
    public_result = {
        "schemaVersion": BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION,
        "executionMode": "unscored_recovered_position",
        "executionLabel": "Recovered position; historical model routing unverified",
        "scoringEligible": False, "officialAdmission": False, "competitiveWinner": None,
        "historicalAssurance": copy.deepcopy(evidence["assurance"]),
        "historicalSpend": "unknown", "historicalFinalPhysicalCallCount": "unknown",
        "accountingScope": "incremental_only", "reconstructedTurns": 1, "incrementalTurns": 0,
        "terminal": False, "boardOutcome": None,
        "requestedHistoricalParticipants": copy.deepcopy(participants),
        "prospectiveParticipants": [{key: value for key, value in item.items()
                                     if key not in {"routeKey", "routeSha256"}}
                                    for item in prospective["players"]],
    }
    validation = {
        "schemaVersion": BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION,
        "status": "verified", "lineageSchemaVersion": BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION,
        "executionMode": "unscored_recovered_position",
        "scoringEligible": False, "officialAdmission": False,
        "validatorScope": "child_internal_source_replay",
        "publicationRequiresAuthoritativeSourceReread": True,
    }
    return {BOARD_RECOVERY_VALIDATION_SCHEMA_VERSION: validation,
            BOARD_RECOVERY_PREPARATION_SCHEMA_VERSION: preparation,
            BOARD_RECOVERY_PUBLIC_RESULT_SCHEMA_VERSION: public_result,
            LEGACY_BOARD_EVIDENCE_SCHEMA_VERSION: evidence,
            BOARD_RECOVERY_SCHEMA_VERSION: descriptor,
            BOARD_RECOVERY_ENGINE_SCHEMA_VERSION: engine,
            BOARD_RECOVERY_LINEAGE_SCHEMA_VERSION: lineage}
