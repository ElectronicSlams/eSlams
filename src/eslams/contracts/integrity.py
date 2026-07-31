"""Fail-closed execution integrity contracts.

The string values in this module are wire contracts.  Downstream consumers may
make them stricter, but must not reinterpret an upstream invalid result as valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from eslams.contracts.versions import (
    ACTION_PROVENANCE_SCHEMA_VERSION,
    RUN_INTEGRITY_SCHEMA_VERSION,
)


class FailureClass(str, Enum):
    PROVIDER_TRANSPORT_ERROR = "provider_transport_error"
    PROVIDER_REQUEST_REJECTED = "provider_request_rejected"
    PROVIDER_RESPONSE_SCHEMA_MISMATCH = "provider_response_schema_mismatch"
    ACTION_RESPONSE_UNPARSEABLE = "action_response_unparseable"
    ACTION_NOT_LEGAL = "action_not_legal"
    ARENA_APPLY_ERROR = "arena_apply_error"
    PROVIDER_AUTH_FAILED = "provider_auth_failed"
    PROVIDER_PERMISSION_FAILED = "provider_permission_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class ActionProvenance(str, Enum):
    PROVIDER_ACTION = "provider_action"
    LOCAL_ACTION = "local_action"
    FALLBACK_ACTION = "fallback_action"


FAILURE_CLASSES: tuple[str, ...] = tuple(item.value for item in FailureClass)
ACTION_PROVENANCE_VALUES: tuple[str, ...] = tuple(item.value for item in ActionProvenance)
ATTEMPT_KINDS: tuple[str, ...] = ("primary", "case_retry", "action_repair", "canary")
INTEGRITY_STATUSES: tuple[str, ...] = ("valid", "invalid", "incomplete")

INVALID_REASON_CODES: tuple[str, ...] = (
    "agent_error",
    "fallback_action_used",
    *FAILURE_CLASSES,
    "provider_usage_missing",
    "model_identity_mismatch",
    "budget_exceeded",
    "attempt_ledger_incomplete",
    "artifact_invalid",
    "signature_invalid",
    "checkpoint_incompatible",
)


@dataclass(frozen=True)
class RunIntegrity:
    integrity_status: str
    valid_for_scoring: bool
    invalid_reason_codes: list[str]
    agent_error_count_by_player: dict[str, int]
    fallback_action_count_by_player: dict[str, int]
    illegal_action_count_by_player: dict[str, int]
    provider_status_by_player: dict[str, str]
    provider_action_count_by_player: dict[str, int]
    logical_action_count_by_player: dict[str, int]
    usage_complete: bool
    cost_complete: bool
    model_identity_verified: bool
    attempt_ledger_complete: bool
    schema_version: str = RUN_INTEGRITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "integrityStatus": self.integrity_status,
            "validForScoring": self.valid_for_scoring,
            "invalidReasonCodes": list(self.invalid_reason_codes),
            "agentErrorCountByPlayer": dict(self.agent_error_count_by_player),
            "fallbackActionCountByPlayer": dict(self.fallback_action_count_by_player),
            "illegalActionCountByPlayer": dict(self.illegal_action_count_by_player),
            "providerStatusByPlayer": dict(self.provider_status_by_player),
            "providerActionCountByPlayer": dict(self.provider_action_count_by_player),
            "logicalActionCountByPlayer": dict(self.logical_action_count_by_player),
            "usageComplete": self.usage_complete,
            "costComplete": self.cost_complete,
            "modelIdentityVerified": self.model_identity_verified,
            "attemptLedgerComplete": self.attempt_ledger_complete,
        }


@dataclass(frozen=True)
class ActionProvenanceRecord:
    event_id: str
    run_id: str
    episode_id: str
    turn_id: int
    seat_id: str
    provenance: ActionProvenance
    logical_action_id: str
    successful_attempt_event_id: str | None = None
    schema_version: str = ACTION_PROVENANCE_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "runId": self.run_id,
            "episodeId": self.episode_id,
            "turnId": self.turn_id,
            "seatId": self.seat_id,
            "provenance": self.provenance.value,
            "logicalActionId": self.logical_action_id,
            "successfulAttemptEventId": self.successful_attempt_event_id,
            "metadata": dict(self.metadata),
        }


def no_secret_examples() -> dict[str, dict[str, Any]]:
    return {
        RUN_INTEGRITY_SCHEMA_VERSION: RunIntegrity(
            integrity_status="valid",
            valid_for_scoring=True,
            invalid_reason_codes=[],
            agent_error_count_by_player={"player_1": 0},
            fallback_action_count_by_player={"player_1": 0},
            illegal_action_count_by_player={"player_1": 0},
            provider_status_by_player={"player_1": "provider_ok"},
            provider_action_count_by_player={"player_1": 1},
            logical_action_count_by_player={"player_1": 1},
            usage_complete=True,
            cost_complete=True,
            model_identity_verified=True,
            attempt_ledger_complete=True,
        ).to_dict(),
        ACTION_PROVENANCE_SCHEMA_VERSION: ActionProvenanceRecord(
            event_id="run_example:action:000001",
            run_id="run_example",
            episode_id="episode_001",
            turn_id=1,
            seat_id="player_1",
            provenance=ActionProvenance.PROVIDER_ACTION,
            logical_action_id="run_example:episode_001:player_1:000001",
            successful_attempt_event_id="sha256:example",
        ).to_dict(),
    }
