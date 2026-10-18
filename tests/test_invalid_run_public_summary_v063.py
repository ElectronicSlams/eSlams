"""Regression: an invalid (fallback) run must not publish a winner or a score.

Reported against 0.6.2: a seat that never produced a legal action was shown as
winner with primary_score 1.0, and score.json reported best_score 1.0 with a
[1.0, 1.0] confidence interval, even though match_valid_for_scoring was false.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import eslams.arenas  # noqa: F401
from eslams.agents import FunctionAgent
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner


def _no_action(_request):
    return ActResponse(action=None)


def _run(tmp_path: Path, agents, **kwargs):
    return Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents=agents,
            output_dir=tmp_path,
            execution_profile="interactive",
            **kwargs,
        )
    )


def test_fallback_seat_is_not_published_as_winner(tmp_path: Path):
    result = _run(
        tmp_path,
        {"player_1": FunctionAgent(_no_action, id="no-action"), "player_2": "first-legal"},
        on_agent_error="fallback",
    )
    assert result.score.match_valid_for_scoring is False
    assert result.score.fallback_action_count_by_player["player_1"] > 0

    public = json.loads(
        (result.artifact_path / "public/public_result_summary.json").read_text(encoding="utf-8")
    )
    assert public["valid_for_scoring"] is False
    assert public["winner"] is None
    assert public["outcome"] is None or public["outcome"]["winner"] is None
    assert public["score"]["primary_score"] is None
    assert public["score"]["scores_by_player"] is None
    assert public["score"]["scoring_status"] == "excluded_invalid_run"
    assert public["score"]["fallback_action_count_by_player"]["player_1"] > 0

    score = json.loads((result.artifact_path / "scores/score.json").read_text(encoding="utf-8"))
    metrics = score["metrics"]
    assert metrics["best_score"] is None
    assert metrics["confidence_interval"] is None
    assert metrics["sample_size"] == 0
    assert metrics["scoring_status"] == "excluded_invalid_run"


def test_valid_run_still_publishes_winner_and_score(tmp_path: Path):
    result = _run(tmp_path, {"player_1": "first-legal", "player_2": "first-legal"})
    assert result.score.match_valid_for_scoring is True
    public = json.loads(
        (result.artifact_path / "public/public_result_summary.json").read_text(encoding="utf-8")
    )
    assert public["winner"] == result.score.winner
    assert public["score"]["primary_score"] == result.score.primary_score
    assert public["score"]["scoring_status"] == "scored"
    score = json.loads((result.artifact_path / "scores/score.json").read_text(encoding="utf-8"))
    assert score["metrics"]["best_score"] is not None
    assert score["metrics"]["confidence_interval"] is not None


def _illegal(_request):
    return ActResponse(action="not-a-legal-action")


@pytest.mark.parametrize("policy", ["fallback", "forfeit", "invalid-match"])
@pytest.mark.parametrize("failure", ["agent_error", "illegal_action"])
def test_invalid_run_never_publishes_winner_or_win_score_under_any_policy(
    tmp_path: Path, policy: str, failure: str
):
    if failure == "agent_error":
        agent = FunctionAgent(_no_action, id="no-action")
        kwargs = {"on_agent_error": policy}
    else:
        agent = FunctionAgent(_illegal, id="illegal-action")
        kwargs = {"on_illegal_action": policy}
    result = _run(tmp_path, {"player_1": agent, "player_2": "first-legal"}, **kwargs)
    public = json.loads(
        (result.artifact_path / "public/public_result_summary.json").read_text(encoding="utf-8")
    )
    score = json.loads((result.artifact_path / "scores/score.json").read_text(encoding="utf-8"))
    # Since 0.6.0 every one of these failure policies makes the run unscoreable.
    assert public["valid_for_scoring"] is False
    assert public["winner"] is None, (policy, failure)
    assert public["outcome"] is None or public["outcome"].get("winner") is None
    assert public["score"]["primary_score"] is None
    assert public["score"]["scores_by_player"] is None
    assert score["metrics"]["best_score"] is None
    assert score["metrics"]["confidence_interval"] is None
