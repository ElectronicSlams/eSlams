import json
from pathlib import Path

import pytest

from eslams.artifacts import ArtifactValidator, _file_entries
from eslams.hashing import canonical_json, sha256_json
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize("cap", [0, -1, True, 1.5])
def test_invalid_turn_cap_is_rejected_before_creating_output(tmp_path: Path, cap):
    with pytest.raises(ValueError, match="max_turns must be a positive integer"):
        Runner().run(RunConfig(arena_id="tic-tac-toe", max_turns=cap, output_dir=tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_truncated_run_retains_valid_diagnostic_artifact_but_cannot_score(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", max_turns=1, output_dir=tmp_path))
    assert result.replay_events[-1].terminal is False
    assert result.score.outcome is None
    assert result.score.match_valid_for_scoring is False
    assert result.score.invalid_reason == "run_truncated"
    assert result.score.invalid_reason_codes == ["run_truncated"]
    assert result.score.metrics["run_status"] == "truncated"
    manifest = json.loads((result.artifact_path / "manifest.json").read_text())
    for key in ("match_valid_for_scoring", "per_case_scoring_eligible",
                "proof_row_publication_eligible", "aggregate_leaderboard_eligible"):
        assert manifest[key] is False
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid is True
    assert report.scoring_eligible is False
    assert report.deterministic_replay.verified is True


@pytest.mark.parametrize("claim", ["score", "manifest", "publication"])
def test_validator_rejects_refreshed_scoring_claim_on_nonterminal_replay(tmp_path: Path, claim):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", max_turns=1, output_dir=tmp_path))
    path = result.artifact_path / "manifest.json"
    manifest = json.loads(path.read_text())
    if claim == "score":
        score_path = result.artifact_path / "scores/score.json"
        score = json.loads(score_path.read_text())
        score["match_valid_for_scoring"] = True
        score_path.write_text(canonical_json(score) + "\n")
        manifest["files"] = _file_entries(result.artifact_path)
        manifest["artifact_id"] = sha256_json(manifest["files"])
    else:
        key = "match_valid_for_scoring" if claim == "manifest" else "proof_row_publication_eligible"
        manifest[key] = True
    path.write_text(canonical_json(manifest) + "\n")
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid is False
    assert report.scoring_eligible is False
    assert "nonterminal replay cannot be eligible for scoring or publication" in report.errors


def test_declared_arena_horizon_remains_a_completed_scoring_valid_run(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="mountain-car", agent_1="first-legal",
                                   output_dir=tmp_path))
    assert result.replay_events[-1].terminal is True
    assert result.score.outcome is not None
    assert result.score.match_valid_for_scoring is True
    assert result.score.metrics["run_status"] == "completed"
    assert "run_truncated" not in result.score.invalid_reason_codes
    assert ArtifactValidator().validate(result.artifact_path) == []
