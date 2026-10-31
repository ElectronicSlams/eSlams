"""Versioned model execution intent, separate from rules and operator admission."""
from __future__ import annotations

import copy
from typing import Any

POLICY_VERSION = "eslams.model-execution-policy.v1"


def model_execution_policy(
    time_budget_ms: int | None, output_tokens: int | None = None,
) -> dict[str, Any]:
    for name, value in (("time_budget_ms", time_budget_ms), ("output_tokens", output_tokens)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValueError(f"{name} must be a positive explicit operator choice or null")
    return {
        "schema_version": POLICY_VERSION,
        "thinking": ({"mode": "unbounded"} if time_budget_ms is None
                     else {"mode": "bounded", "duration_ms": time_budget_ms}),
        "output": ({"mode": "provider_default"} if output_tokens is None
                   else {"mode": "bounded", "max_tokens": output_tokens}),
    }


def validate_model_execution_policy(
    protocol: str, budget: int | None, metadata: dict[str, Any],
) -> dict[str, Any] | None:
    value = metadata.get("model_execution_policy")
    if value is None and protocol == "eslams-act-v1":
        return None  # Historical finite requests remain readable without new metadata.
    if not isinstance(value, dict) or set(value) != {"schema_version", "thinking", "output"}:
        raise ValueError("v2 requires exact metadata.model_execution_policy fields")
    if value["schema_version"] != POLICY_VERSION:
        raise ValueError("unsupported model execution policy version")
    thinking, output = value["thinking"], value["output"]
    expected = model_execution_policy(budget)["thinking"]
    if not isinstance(thinking, dict) or thinking != expected:
        raise ValueError("thinking policy contradicts time_budget_ms")
    if budget is not None and (
        isinstance(thinking.get("duration_ms"), bool)
        or not isinstance(thinking.get("duration_ms"), int)
    ):
        raise ValueError("finite thinking duration must be an integer")
    if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int)):
        raise ValueError("finite thinking duration must be an integer")
    if not isinstance(output, dict):
        raise ValueError("output policy must be an object")
    if output == {"mode": "provider_default"}:
        return value
    count = output.get("max_tokens")
    if (set(output) != {"mode", "max_tokens"} or output.get("mode") != "bounded"
            or isinstance(count, bool) or not isinstance(count, int) or count < 1):
        raise ValueError("output requires provider_default or a positive explicit operator limit")
    return value


_POLICY_SCHEMA: dict[str, Any] = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
 '$id': 'https://eslams.com/schemas/model-execution-policy.v1.json',
 'title': 'eSlams model execution policy v1',
 'type': 'object',
 'additionalProperties': False,
 'required': ['schema_version', 'thinking', 'output'],
 'properties': {'schema_version': {'const': 'eslams.model-execution-policy.v1'},
                'thinking': {'oneOf': [{'type': 'object',
                                        'additionalProperties': False,
                                        'required': ['mode'],
                                        'properties': {'mode': {'const': 'unbounded'}}},
                                       {'type': 'object',
                                        'additionalProperties': False,
                                        'required': ['mode', 'duration_ms'],
                                        'properties': {'mode': {'const': 'bounded'},
                                                       'duration_ms': {'type': 'integer',
                                                                       'minimum': 1}}}]},
                'output': {'oneOf': [{'type': 'object',
                                      'additionalProperties': False,
                                      'required': ['mode'],
                                      'properties': {'mode': {'const': 'provider_default'}}},
                                     {'type': 'object',
                                      'additionalProperties': False,
                                      'required': ['mode', 'max_tokens'],
                                      'properties': {'mode': {'const': 'bounded'},
                                                     'max_tokens': {'type': 'integer',
                                                                    'minimum': 1}}}]}}}

def model_execution_policy_schema() -> dict[str, Any]:
    """Return the versioned closed policy schema without sharing mutable state."""
    return copy.deepcopy(_POLICY_SCHEMA)
