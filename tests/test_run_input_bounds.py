import json

import pytest

from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("options", [
    {"time_budget_ms": 0}, {"time_budget_ms": -1}, {"time_budget_ms": True},
    {"time_budget_ms": 1.5}, {"time_budget_ms": None},
    {"case_attempt_index": 1.5}, {"case_attempt_index": None},
    {"shard_index": -1}, {"shard_index": True}, {"shard_index": 1.5},
    {"shard_count": 0}, {"shard_count": -1}, {"shard_count": True},
    {"shard_count": 1.5}, {"shard_index": 5, "shard_count": 2},
])
def test_invalid_runner_numbers_fail_before_output(tmp_path, options):
    with pytest.raises(ValueError):
        Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path, **options))
    assert list(tmp_path.iterdir()) == []


def test_valid_shard_and_time_budget_are_recorded_without_clamping(tmp_path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path,
                                   shard_index=1, shard_count=2, time_budget_ms=5000))
    manifest = json.loads((result.artifact_path / "manifest.json").read_text())
    assert manifest["run_metadata"]["shard_index"] == 1
    assert manifest["run_metadata"]["shard_count"] == 2
    assert manifest["run_metadata"]["requested_time_budget_ms"] == 5000
    assert manifest["run_metadata"]["effective_time_budget_ms"] == 5000
    assert ArtifactValidator().validate(result.artifact_path) == []
