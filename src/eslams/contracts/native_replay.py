"""Public native replay structural schemas. ZIP and sequence proof remain verifier duties."""

from __future__ import annotations

import json
from typing import Any

from eslams.contracts.versions import NATIVE_EVENT_SCHEMA_VERSION, NATIVE_MANIFEST_SCHEMA_VERSION
from eslams.native_public_facts import shared_fact_schema
from eslams.native_rounds_demo import NativeProfile
from eslams.native_runner import run_local_native
from eslams.native_scope_demo import NATIVE_SCOPE

Schema = dict[str, Any]
_SEAT = {"enum": ["player_1", "player_2", "player_3", "player_4"]}
_TEXT = {"type": "string"}
_NUM = {"type": "integer"}
_COUNT = {"type": "integer", "minimum": 0}
_CARD = {"type": "string", "pattern": "^[2-9TJQKA][CDHS]$"}
_KINDS = ["round_opened", "sealed_action", "action", "redacted_unit_action",
          "round_settled", "match_finalized", "match_invalid"]
_ACTIONS = ["check", "bet", "call", "fold", "raise", "bet:2", "bet:4", "raise:4", "all-in",
            "rock", "paper", "scissors", "cooperate", "defect"]


def obj(properties: dict[str, Schema]) -> Schema:
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties)}


def many(items: Schema, limit: int) -> Schema:
    return {"type": "array", "maxItems": limit, "items": items}


def nullable(item: Schema) -> Schema:
    return {"anyOf": [item, {"type": "null"}]}


def native_contract_definitions() -> dict[str, Schema]:
    return {
        "NativeMatchManifest": obj({
            "kind": {"const": NATIVE_MANIFEST_SCHEMA_VERSION},
            "run_id": {**_TEXT, "minLength": 1, "maxLength": 64},
            "arena_id": {"enum": sorted(NATIVE_SCOPE)},
            "rules_version": {**_TEXT, "minLength": 1, "maxLength": 32},
            "blocks": {**_NUM, "minimum": 1, "maximum": 20},
            "planned_rounds": {**_NUM, "minimum": 3, "maximum": 60, "multipleOf": 3},
            "completed_rounds": {**_COUNT, "maximum": 60},
            "status": {"enum": ["complete", "invalid"]},
            "score_quanta": nullable(many(_NUM, 4)),
            "seat_ids": {**many(_SEAT, 4), "minItems": 1, "uniqueItems": True},
            "position_policy": {"enum": ["fixed", "rotation"]},
            "utility_policy": {"enum": sorted({a.score_basis for a in NATIVE_SCOPE.values()})},
            "utility_quanta_per_point": {"enum": sorted(
                {a.denominator for a in NATIVE_SCOPE.values()}
            )},
            "history_gate": {"enum": sorted({a.history_gate for a in NATIVE_SCOPE.values()})},
            "history_policy": {"enum": ["full_authorized", "memoryless_across_hands"]},
            "event_stream_sha256": {**_TEXT, "pattern": "^sha256:[a-f0-9]{64}$"},
        }),
        "NativeMatchEvent": obj({
            "event_seq": _COUNT,
            "kind": {"enum": _KINDS},
            "round_index": {**_NUM, "minimum": 1, "maximum": 60},
            "global_action_index": _COUNT,
            "round_turn": _COUNT,
            "actor": nullable(_SEAT),
            "action": nullable({"enum": _ACTIONS}),
            "street": nullable({"enum": ["preflop", "board", "flop", "turn", "river", "showdown"]}),
            "pot": nullable(_COUNT),
            "board": many(_CARD, 5),
            "stacks": many(_COUNT, 4),
            "committed": many(_COUNT, 4),
            "folded": many(_SEAT, 4),
            "utility": many(_NUM, 4),
            "revealed": many({"enum": ["rock", "paper", "scissors", "cooperate", "defect"]}, 4),
            "reason": nullable({"enum": [
                "beats", "draw", "payoff_matrix", "fold", "showdown", "settled_native_unit",
                "invalid_action", "policy_error", "interrupted",
            ]}),
            "game_facts": shared_fact_schema(),
        }),
    }


def native_replay_schemas() -> dict[str, Schema]:
    d = native_contract_definitions()

    def schema(version: str, fields: Schema) -> Schema:
        return {"$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://eslams.com/schemas/{version}.json", "title": version, **fields}

    manifest = d["NativeMatchManifest"]
    manifest["allOf"] = [
        {"if": {"properties": {"arena_id": {"const": "first-price-sealed-bid-auction"}}},
         "then": {"properties": {"score_quanta": {"type": "null"}}}},
        {"if": {"properties": {"status": {"const": "invalid"}}},
         "then": {"properties": {"score_quanta": {"type": "null"}}}},
    ]
    event = d["NativeMatchEvent"]
    event["allOf"] = [
        {"if": {"properties": {"kind": {"const": k}}},
         "then": {"properties": {
            "game_facts": shared_fact_schema(k),
            "action": {"enum": _ACTIONS} if k == "action" else {"type": "null"},
        }}} for k in _KINDS
    ]
    return {NATIVE_MANIFEST_SCHEMA_VERSION: schema(NATIVE_MANIFEST_SCHEMA_VERSION, manifest),
            NATIVE_EVENT_SCHEMA_VERSION: schema(NATIVE_EVENT_SCHEMA_VERSION, event)}


def native_replay_examples() -> dict[str, Schema]:
    # Public, local-only scripted run. No seed/state/seat authority is serialized.
    from eslams.native_artifact import verify_native_replay

    artifact = run_local_native(NativeProfile("rock-paper-scissors"), "native-example")
    replay = verify_native_replay(artifact.contents)
    event = json.loads(json.dumps(replay.events[0]))
    return {NATIVE_MANIFEST_SCHEMA_VERSION: replay.manifest, NATIVE_EVENT_SCHEMA_VERSION: event}
