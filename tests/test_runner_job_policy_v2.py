"""Versioned runner carrier defaults; no executor or provider invocation."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eslams.contracts.json_schema import schema_for_version
from eslams.contracts.runner_job import RunnerJobRequest
from eslams.contracts.versions import RUNNER_JOB_REQUEST_SCHEMA_VERSION, RUNNER_JOB_SCHEMA_VERSION
from eslams.execution_policy import model_execution_policy, model_execution_policy_schema


def request(**options):
    return RunnerJobRequest(job_id="synthetic-job", arena_id="tic-tac-toe", seed=1,
        agents={"player_1": {"kind": "builtin", "id": "first-legal"}},
        artifact_output={"kind": "local_path", "path": "synthetic.eslams"}, **options)


def test_runner_job_default_is_explicit_versioned_unbounded_and_roundtrips():
    body = request().to_dict()
    assert body["schema_version"] == RUNNER_JOB_REQUEST_SCHEMA_VERSION
    assert body["time_budget_ms"] is None
    assert body["metadata"]["model_execution_policy"] == model_execution_policy(None)
    assert RunnerJobRequest.from_mapping(body).to_dict() == body
    Draft202012Validator(schema_for_version(RUNNER_JOB_REQUEST_SCHEMA_VERSION)).validate(body)


def test_legacy_request_keeps_explicit_finite_policy_without_a_hidden_default():
    body = request(schema_version=RUNNER_JOB_SCHEMA_VERSION, time_budget_ms=30000).to_dict()
    assert RunnerJobRequest.from_mapping(body).time_budget_ms == 30000
    with pytest.raises(ValueError, match="explicit finite"):
        request(schema_version=RUNNER_JOB_SCHEMA_VERSION)


def test_finite_operator_v2_request_preserves_matching_policy():
    body = request(time_budget_ms=1800000).to_dict()
    assert RunnerJobRequest.from_mapping(body).time_budget_ms == 1800000
    assert body["metadata"]["model_execution_policy"]["thinking"]["duration_ms"] == 1800000


@pytest.mark.parametrize("mutation", ["missing-null", "missing-policy", "contradiction",
                                     "hidden-cap", "wrong-version", "boolean", "wrong-placement"])
def test_invalid_raw_job_policy_is_rejected_before_any_executor_exists(mutation):
    body = deepcopy(request().to_dict())
    if mutation == "missing-null":
        body.pop("time_budget_ms")
    elif mutation == "missing-policy":
        body.pop("metadata")
    elif mutation == "contradiction":
        body["time_budget_ms"] = 1
    elif mutation == "hidden-cap":
        body["metadata"]["model_execution_policy"]["output"]["max_tokens"] = 1024
    elif mutation == "wrong-version":
        body["schema_version"] = "unknown"
    elif mutation == "boolean":
        body["time_budget_ms"] = True
    else:
        body["execution_policy"] = {"mode": "none"}
    with pytest.raises(ValueError):
        RunnerJobRequest.from_mapping(body)


def test_exported_policy_schema_matches_frozen_neutral_contract_without_aliasing():
    expected = json.loads((Path(__file__).parents[1] /
        "fixtures/model_execution_policy/policy.v1.schema.json").read_text())
    assert model_execution_policy_schema() == expected
    mutated = model_execution_policy_schema()
    mutated["additionalProperties"] = True
    assert model_execution_policy_schema()["additionalProperties"] is False
