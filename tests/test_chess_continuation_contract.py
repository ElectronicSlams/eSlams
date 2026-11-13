"""Compatibility coverage for reconstructed chess provenance wire contracts."""

import ast
from dataclasses import MISSING, fields
from pathlib import Path

import jsonschema
import pytest

from eslams.continuation import ChessContinuation
from eslams.contracts.integrity import (
    ACTION_PROVENANCE_VALUES,
    ActionProvenance,
    ActionProvenanceRecord,
)
from eslams.contracts.json_schema import schema_for_version
from eslams.contracts.versions import ACTION_PROVENANCE_SCHEMA_VERSION


@pytest.mark.parametrize("provenance", list(ActionProvenance))
def test_action_provenance_schema_preserves_old_and_reconstructed_values(provenance):
    row = ActionProvenanceRecord(
        event_id="child:action:000000",
        run_id="child",
        episode_id="episode_001",
        turn_id=0,
        seat_id="player_1",
        provenance=provenance,
        logical_action_id="child:episode_001:player_1:000000",
    ).to_dict()
    jsonschema.validate(row, schema_for_version(ACTION_PROVENANCE_SCHEMA_VERSION))
    assert row["successfulAttemptEventId"] is None


def test_provenance_schema_and_typescript_cover_the_python_values():
    schema = schema_for_version(ACTION_PROVENANCE_SCHEMA_VERSION)
    assert schema["properties"]["provenance"]["enum"] == list(ACTION_PROVENANCE_VALUES)
    typescript = (
        Path(__file__).parents[1] / "packages/core-contracts/src/generated/integrity.ts"
    ).read_text()
    union = typescript.split("export type ActionProvenance =", 1)[1].split(";", 1)[0]
    for value in ACTION_PROVENANCE_VALUES:
        assert f'"{value}"' in union


def test_continuation_requires_explicit_child_platform_identity():
    contract = {field.name: field for field in fields(ChessContinuation)}
    for name in ("child_platform_run_id", "match_id"):
        assert contract[name].default is MISSING
        assert contract[name].default_factory is MISSING


def test_documented_python_example_has_explicit_platform_run_binding():
    documentation = (
        Path(__file__).parents[1] / "docs/CHESS_CONTINUATION.md"
    ).read_text()
    example = documentation.split("```python\n", 1)[1].split("```", 1)[0]
    tree = ast.parse(example)
    calls = {
        node.func.id: node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    continuation_keywords = {item.arg: item.value for item in calls["ChessContinuation"].keywords}
    assert set(continuation_keywords) >= {"child_platform_run_id", "match_id"}
    assert isinstance(continuation_keywords["match_id"], ast.Name)
    assert continuation_keywords["match_id"].id == "child_platform_match_id"
    config_keywords = {item.arg: item.value for item in calls["RunConfig"].keywords}
    for key in ("case_id", "run_job_id"):
        assert isinstance(config_keywords[key], ast.Name)
        assert config_keywords[key].id == "child_platform_run_id"
