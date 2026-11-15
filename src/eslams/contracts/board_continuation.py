"""Private-custody board continuation wire shapes, distinct from legacy chess.

Structural schemas are not custody verification. Only the archive verifier may
admit a continuation; hashes, replay, provenance and receipts must still verify.
"""
from __future__ import annotations

import hashlib
from typing import Any

from eslams.contracts.versions import (
    BOARD_CONTINUATION_CHILD_EXECUTION_SCHEMA_VERSION as CHILD,
)
from eslams.contracts.versions import (
    BOARD_CONTINUATION_ENGINE_SCHEMA_VERSION as ENGINE,
)
from eslams.contracts.versions import (
    BOARD_CONTINUATION_LINEAGE_SCHEMA_VERSION as LINEAGE,
)
from eslams.contracts.versions import (
    BOARD_CONTINUATION_SCHEMA_VERSION as DESCRIPTOR,
)
from eslams.contracts.versions import CORE_PACKAGE_VERSION, RUNNER_VERSION
from eslams.hashing import canonical_json


def _object(properties: dict[str, Any], *, extensions: bool = True) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": extensions}


def board_continuation_schemas() -> dict[str, dict[str, Any]]:
    text = {"type": "string", "minLength": 1}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    count = {"type": "integer", "minimum": 0}
    source = _object({**dict.fromkeys(
        ("matchId", "runId", "artifactId", "artifactKey", "coreRunId"), text),
                      "artifactSha256": digest})
    player = _object({**dict.fromkeys(
        ("seat", "modelId", "modelVersionId", "providerModelId", "routeKey"), text),
                      "routeSha256": digest})
    execution = _object({
        **dict.fromkeys(("coreVersion", "coreRef", "arenaVersion", "runnerVersion",
                         "wrapperVersion", "scoringPolicyVersion"), text),
        **dict.fromkeys(("coreSourceSha256", "rulesSha256", "sourcePayloadSha256"), digest),
        "arenaSlug": {"enum": ["tic-tac-toe", "connect-four", "othello"]},
        "variantSlug": {"const": "standard"}, "seed": {"type": "integer"},
        "maxTurns": {"type": "integer", "minimum": 1},
        "players": {"type": "array", "minItems": 2, "maxItems": 2,
                    "prefixItems": [
                        {**player, "properties": {**player["properties"], "seat": {"const": seat}}}
                        for seat in ("player_1", "player_2")
                    ]},
    })
    prefix = _object({"acceptedPlyCount": count, "prefixSha256": digest,
                      "checkpointStateSha256": digest})
    descriptor = _object({"schemaVersion": {"const": DESCRIPTOR}, "source": source,
                          "execution": execution, "executionSpecSha256": digest, "prefix": prefix})
    child = _object({"schemaVersion": {"const": CHILD},
                     "turnLimitPolicy": {"enum": ["preserve-source", "native-arena-horizon"]},
                     "maxTurns": {"type": "integer", "minimum": 1}}, extensions=False)
    engine = _object({"schemaVersion": {"const": ENGINE}, "coreVersion": text,
                      "coreRef": {"const": "local-development"}, "coreSourceSha256": digest,
                      "runnerVersion": text, "wrapperVersion": text,
                      "runnerImageDigest": {"const": "local-development"},
                      "continuationContractVersion": {"const": LINEAGE}}, extensions=False)
    segment = _object({"sourceCoreRunId": text, "sourceArtifactId": text, "sha256": digest,
                       "byteCount": count, "receiptCount": count, "acceptedPlyCount": count})
    lineage = _object({
        "schemaVersion": {"const": LINEAGE}, "descriptor": descriptor,
        "descriptorSha256": digest, "source": source, "prefix": prefix,
        "child": _object(dict.fromkeys(("coreRunId", "platformRunId", "matchId"), text)),
        "targetEngine": engine, "targetEngineSha256": digest,
        "childExecution": child, "childExecutionSha256": digest,
        "historicalLedger": _object({
            "path": {"const": "continuation/source_provider_receipts.jsonl"},
                                     "sha256": digest, "receiptCount": count,
                                     "segments": {"type": "array", "minItems": 1,
                                                  "items": segment}}),
        "accounting": _object({"historical": {"const": "source_and_ancestors"},
                                "incremental": {"const": "receipts/provider_receipts.jsonl"},
                                "aggregateScope": {"const": "incremental_only"}}, extensions=False),
        "sourceVerification": _object({
            "archiveBytesVerifiedAtPreparation": {"const": True},
            "childValidatorScope": {"const": "internal_lineage_only"},
            "publicationRequiresAuthoritativeSourceReread": {"const": True},
            "externalCustodyPins": {"type": "array", "items": text},
        }),
        "parentLineage": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/lineage"}]},
        "parentLineageSha256": digest,
    })
    return {
        version: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": version, **schema,
                  **({"$defs": {"lineage": lineage}} if version == LINEAGE else {})}
        for version, schema in ((DESCRIPTOR, descriptor), (CHILD, child),
                                (ENGINE, engine), (LINEAGE, lineage))
    }


def board_continuation_examples() -> dict[str, dict[str, Any]]:
    """No-secret examples are structural illustrations, not runnable source evidence."""
    def digest(value: Any) -> str:
        return hashlib.sha256(canonical_json(value).encode()).hexdigest()

    source = {**{key: "example-" + key for key in
                  ("matchId", "runId", "artifactId", "artifactKey", "coreRunId")},
              "artifactSha256": "0" * 64}
    execution = {
        "coreVersion": CORE_PACKAGE_VERSION, "coreRef": "1" * 40,
        "coreSourceSha256": "2" * 64, "arenaSlug": "tic-tac-toe", "arenaVersion": "1.0.0",
        "variantSlug": "standard", "runnerVersion": RUNNER_VERSION,
        "wrapperVersion": "legal_action_v1:1.0.0",
        "scoringPolicyVersion": "tic-tac-toe-score:1.0.0",
        "rulesSha256": "3" * 64, "sourcePayloadSha256": "4" * 64, "seed": 7, "maxTurns": 9,
        "players": [{"seat": seat, "modelId": "example-model", "modelVersionId": "example-v1",
                     "providerModelId": "example-provider-model", "routeKey": "example-route",
                     "routeSha256": "5" * 64} for seat in ("player_1", "player_2")],
    }
    prefix = {"acceptedPlyCount": 0, "prefixSha256": digest([]), "checkpointStateSha256": "6" * 64}
    descriptor = {"schemaVersion": DESCRIPTOR, "source": source, "execution": execution,
                  "executionSpecSha256": digest(execution), "prefix": prefix}
    child = {"schemaVersion": CHILD, "turnLimitPolicy": "preserve-source", "maxTurns": 9}
    engine = {"schemaVersion": ENGINE, "coreVersion": CORE_PACKAGE_VERSION,
              "coreRef": "local-development", "coreSourceSha256": "7" * 64,
              "runnerVersion": RUNNER_VERSION, "wrapperVersion": "legal_action_v1:1.0.0",
              "runnerImageDigest": "local-development", "continuationContractVersion": LINEAGE}
    lineage = {
        "schemaVersion": LINEAGE, "descriptor": descriptor, "descriptorSha256": digest(descriptor),
        "source": source, "prefix": prefix,
        "child": {key: "new-" + key for key in ("coreRunId", "platformRunId", "matchId")},
        "targetEngine": engine, "targetEngineSha256": digest(engine),
        "childExecution": child, "childExecutionSha256": digest(child),
        "historicalLedger": {"path": "continuation/source_provider_receipts.jsonl",
                             "sha256": hashlib.sha256(b"").hexdigest(), "receiptCount": 0,
                             "segments": [{"sourceCoreRunId": source["coreRunId"],
                                           "sourceArtifactId": source["artifactId"],
                                           "sha256": hashlib.sha256(b"").hexdigest(),
                                           "byteCount": 0, "receiptCount": 0,
                                           "acceptedPlyCount": 0}]},
        "accounting": {"historical": "source_and_ancestors",
                       "incremental": "receipts/provider_receipts.jsonl",
                       "aggregateScope": "incremental_only"},
        "sourceVerification": {"archiveBytesVerifiedAtPreparation": True,
                               "childValidatorScope": "internal_lineage_only",
                               "publicationRequiresAuthoritativeSourceReread": True,
                               "externalCustodyPins": ["coreRef", "coreSourceSha256", "rulesSha256",
                                                       "sourcePayloadSha256", "players.routeKey",
                                                       "players.routeSha256",
                                                       "players.modelVersionId"]},
        "parentLineage": None, "parentLineageSha256": digest(None),
    }
    return {DESCRIPTOR: descriptor, CHILD: child, ENGINE: engine, LINEAGE: lineage}
