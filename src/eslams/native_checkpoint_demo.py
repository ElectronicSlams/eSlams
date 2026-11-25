"""Private opt-in settled boundary custody. No public serialization or production store."""

from __future__ import annotations

import hmac
import json
from dataclasses import asdict, dataclass, field

from eslams.hashing import canonical_json, sha256_json
from eslams.native_rounds_demo import NativeRoundArena, NativeState

_VERSION = "eslams.native-boundary-checkpoint.v1"


@dataclass(frozen=True)
class TrustedBoundary:
    """Authority-only and repr-redacted: contains earlier raw native actions."""

    version: str
    run_id: str
    settled_rounds: int
    actions: tuple[str, ...] = field(repr=False)
    signature: bytes = field(repr=False)
    execution_binding: str = field(default="", repr=False)


def _boundary(state: NativeState) -> bool:
    return (
        not state.finalized
        and not state.invalid
        and not state.unit.terminal
        and state.unit.turn == 0
        and state.completed > 0
        and state.round_index == state.completed + 1
        and state.events[-1].kind == "round_opened"
        and state.events[-1].round_index == state.round_index
        and state.global_actions == len(state._audit_actions)
    )


def _sign(arena: NativeRoundArena, state: NativeState, key: bytes, binding: str) -> bytes:
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("trusted checkpoint key must contain at least 32 bytes")
    authoritative = canonical_json({
        "schema": _VERSION,
        "run_id": arena.run_id,
        "profile": asdict(arena.profile),
        "seats": arena.seats,
        "rules_version": arena.rules.version,
        "active_position_binding": state.seat_for_position,
        "settled_rounds": state.completed,
        "global_action_index": state.global_actions,
        "event_head": state.events[-1].event_seq,
        "stream_sha256": sha256_json([e.public_document() for e in state.events]),
        "private_round_seed_state": state.unit.state_hash,
        "private_auction_authority": None if arena._auction_authority is None else
        arena._auction_authority.hex(),
        "private_match_authority": (None if arena._private_authority is None else
                                    arena._private_authority.hex()),
        "execution_binding": binding,
        "role_lane_own_context": [[asdict(x) for x in row] for row in state.own_prior],
        "utility_totals": state.totals,
        "audit_actions": state._audit_actions,
        "seat_history": [[asdict(e) for e in own] for own in state._seat_history],
    }).encode("utf-8")
    return hmac.digest(key, authoritative, "sha256")


def capture_settled_boundary(
    arena: NativeRoundArena, state: NativeState, key: bytes, *, execution_binding: str = ""
) -> TrustedBoundary:
    """Call only before issuing an action request in the next hand."""
    if not _boundary(state):
        raise ValueError("only complete settled boundaries can be checkpointed")
    return TrustedBoundary(_VERSION, arena.run_id, state.completed, state._audit_actions,
                           _sign(arena, state, key, execution_binding), execution_binding)


def restore_settled_boundary(
    arena: NativeRoundArena, checkpoint: TrustedBoundary, key: bytes, *,
    execution_binding: str = "",
) -> NativeState:
    """Reapply only pre-verified local mechanics history, never agent callbacks."""
    if type(checkpoint) is not TrustedBoundary or (
        checkpoint.version != _VERSION
        or checkpoint.run_id != arena.run_id
        or checkpoint.execution_binding != execution_binding
        or type(checkpoint.settled_rounds) is not int
        or not 1 <= checkpoint.settled_rounds < arena.profile.round_count
        or type(checkpoint.actions) is not tuple
        or len(checkpoint.actions) > checkpoint.settled_rounds * arena.rules.max_turns
        or type(checkpoint.signature) is not bytes
    ):
        raise ValueError("unsupported private checkpoint metadata")
    state = arena.start()
    for blob in checkpoint.actions:
        if type(blob) is not str or len(blob) > 4096:
            raise ValueError("invalid private action record")
        item = json.loads(blob)
        if not isinstance(item, list) or len(item) != 2 or canonical_json(item) != blob:
            raise ValueError("invalid private action shape")
        if type(item[0]) is not str:
            raise ValueError("invalid actor")
        state = arena.transition(state, item[0], item[1])
    if (
        not _boundary(state)
        or state.completed != checkpoint.settled_rounds
        or not hmac.compare_digest(checkpoint.signature,
                                   _sign(arena, state, key, execution_binding))
    ):
        raise ValueError("private checkpoint attestation mismatch")
    return state
