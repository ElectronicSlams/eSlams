import json

import httpx
import pytest
from test_provider_wire_v06 import _agent, _fixture
from test_runner_artifact import _set_ed25519_artifact_signing_env

from eslams.artifacts import ArtifactValidator
from eslams.runner import RunConfig, Runner


def test_missing_official_case_id_is_named_without_blaming_complete_action_provenance(
    tmp_path,
    monkeypatch,
):
    _set_ed25519_artifact_signing_env(monkeypatch, key_id="case-regression-fixture")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    for case_id in (None, "case-complete"):
        actions = iter([0, 2, 4, 6])

        def post(*a, actions=actions, **k):
            payload = _fixture("openrouter_chat_completions_success.json")
            payload["choices"][0]["message"]["content"] = json.dumps({"action": next(actions)})
            return httpx.Response(200, json=payload)

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        result = Runner().run(
            RunConfig(
                arena_id="tic-tac-toe",
                execution_profile="official_eval",
                case_id=case_id,
                agents={
                    "player_1": _agent("openrouter", "openai/gpt-5-mini", "OPENROUTER_API_KEY")
                },
                output_dir=tmp_path / (case_id or "missing-case"),
            )
        )
        report = ArtifactValidator().validate_report(result.artifact_path, profile="official-case")
        assert result.score.match_valid_for_scoring and result.score.integrity_status == "valid"
        assert report.signature.verified
        manifest = json.loads((result.artifact_path / "manifest.json").read_text())
        assert manifest["proof_row_publication_eligible"] is bool(case_id)
        assert report.per_case_scoring_eligible is bool(case_id)
        if case_id is None:
            assert report.errors == ["case_id_missing"]
            assert not report.valid
        else:
            assert report.valid and report.errors == []
    for case_id in ("", " ", 1, True):
        with pytest.raises(ValueError, match="case_id"):
            RunConfig(arena_id="tic-tac-toe", case_id=case_id)


def test_local_game_validity_is_separate_from_provider_case_publication(tmp_path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path))
    report = ArtifactValidator().validate_report(result.artifact_path)
    assert report.valid and report.scoring_eligible and report.per_case_run_valid
    assert not report.per_case_scoring_eligible and not report.proof_row_publication_eligible
    assert result.score.aggregate_usage["receiptCount"] == 0
    assert result.score.aggregate_usage["unavailableReasonCodes"] == ["no_provider_calls"]
    assert result.score.aggregate_usage["usageComplete"] is False
    assert result.score.integrity_status == "incomplete"
