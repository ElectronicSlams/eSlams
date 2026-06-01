from pathlib import Path

from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


def test_runner_generates_valid_connect_four_artifact(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="connect-four", seed=7, output_dir=tmp_path))
    assert result.artifact_path.exists()
    assert result.score.run_id == result.run_id
    assert ArtifactValidator().validate(result.artifact_path) == []


def test_runner_generates_replay_events(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path))
    assert result.replay_events[0].action is None
    assert result.replay_events[-1].terminal is True
