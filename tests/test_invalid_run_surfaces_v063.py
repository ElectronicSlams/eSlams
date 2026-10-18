"""Regression (#225): every surface of an invalid run follows the public result summary.

The public summary (``public/public_result_summary.json``) is the single source of
the published winner. CLI output, the replay viewer, publication bundle rows and
merged official rows must never show a winner or a win score the summary does
not publish, and must label excluded runs.

Scope note: forfeit-specific behaviour is frozen pending a founder decision (see
the PR body). These tests deliberately do not pin forfeit semantics; they assert
"surface == public summary", so they keep passing whichever way forfeit is
decided. ``score.json`` top-level ``winner``/``primary_score``/``scores_by_player``
are also held and intentionally not asserted here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import eslams.arenas  # noqa: F401
from eslams.agents import FunctionAgent
from eslams.cli import main
from eslams.official import merge_official_results
from eslams.protocol import ActResponse
from eslams.publication_export import export_publication_bundle
from eslams.replay import render_replay_html
from eslams.runner import RunConfig, Runner

# Forfeit is intentionally absent: frozen pending founder decision (#226 body).
NON_FORFEIT_POLICIES = ["fallback", "invalid-match"]
FAILURES = ["no_move", "illegal_move"]


def _no_action(_request):
    return ActResponse(action=None)


def _illegal(_request):
    return ActResponse(action="not-a-legal-action")


def _failing_agent(failure: str) -> tuple[FunctionAgent, str]:
    if failure == "no_move":
        return FunctionAgent(_no_action, id="no-action"), "on_agent_error"
    return FunctionAgent(_illegal, id="illegal-action"), "on_illegal_action"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _public(result) -> dict[str, Any]:
    return _json(result.artifact_path / "public/public_result_summary.json")


def _run(tmp_path: Path, arena_id: str = "tic-tac-toe", **kwargs):
    kwargs.setdefault("execution_profile", "interactive")
    return Runner().run(RunConfig(arena_id=arena_id, output_dir=tmp_path, **kwargs))


def _assert_excluded(public: dict[str, Any]) -> None:
    assert public["valid_for_scoring"] is False
    assert public["winner"] is None
    assert public["outcome"] is None or public["outcome"].get("winner") is None
    assert public["score"]["primary_score"] is None
    assert public["score"]["scores_by_player"] is None
    assert public["score"]["scoring_status"] == "excluded_invalid_run"


def _assert_metrics_excluded(result) -> None:
    metrics = _json(result.artifact_path / "scores/score.json")["metrics"]
    assert metrics["best_score"] is None
    assert metrics["confidence_interval"] is None
    assert metrics["sample_size"] == 0
    assert metrics["scoring_status"] == "excluded_invalid_run"


# --- every non-forfeit policy x failure type ---------------------------------


@pytest.mark.parametrize("policy", NON_FORFEIT_POLICIES)
@pytest.mark.parametrize("failure", FAILURES)
def test_policy_and_failure_matrix_publishes_no_winner(tmp_path: Path, policy, failure):
    agent, option = _failing_agent(failure)
    result = _run(
        tmp_path, agents={"player_1": agent, "player_2": "first-legal"}, **{option: policy}
    )
    assert result.score.match_valid_for_scoring is False
    public = _public(result)
    _assert_excluded(public)
    _assert_metrics_excluded(result)
    # The board result stays available, explicitly labelled, for audit.
    assert public["score"]["board_scores_by_player"] == result.score.scores_by_player
    if public["outcome"] is not None:
        assert public["outcome"]["board_winner"] == result.score.winner
    official = _json(result.artifact_path / "scores/official_result.json")
    assert official["winner"] is None
    assert official["score"]["primary_score"] is None


def test_fallback_seat_that_never_moved_is_not_published_as_winner(tmp_path: Path):
    agent, _ = _failing_agent("no_move")
    result = _run(
        tmp_path, agents={"player_1": agent, "player_2": "first-legal"}, on_agent_error="fallback"
    )
    # The reported defect: on substituted moves the failing seat "wins" on the board.
    assert result.score.winner == "player_1"
    public = _public(result)
    _assert_excluded(public)
    assert public["outcome"]["board_winner"] == "player_1"
    assert public["score"]["fallback_action_count_by_player"]["player_1"] > 0


def test_illegal_move_fallback_seat_is_not_published_as_winner(tmp_path: Path):
    agent, _ = _failing_agent("illegal_move")
    result = _run(
        tmp_path,
        agents={"player_1": agent, "player_2": "first-legal"},
        on_illegal_action="fallback",
    )
    public = _public(result)
    _assert_excluded(public)
    assert public["score"]["fallback_action_count_by_player"]["player_1"] > 0


# --- truncation, solo and multi-seat arenas -----------------------------------


def test_truncated_run_publishes_no_winner(tmp_path: Path):
    result = _run(
        tmp_path, agents={"player_1": "first-legal", "player_2": "first-legal"}, max_turns=2
    )
    assert result.score.match_valid_for_scoring is False
    assert "run_truncated" in result.score.invalid_reason_codes
    _assert_excluded(_public(result))
    _assert_metrics_excluded(result)


@pytest.mark.parametrize("failure", FAILURES)
def test_solo_arena_invalid_run_publishes_no_score(tmp_path: Path, failure):
    agent, option = _failing_agent(failure)
    result = _run(tmp_path, arena_id="cartpole", agents={"player_1": agent}, **{option: "fallback"})
    assert result.score.match_valid_for_scoring is False
    _assert_excluded(_public(result))
    _assert_metrics_excluded(result)


def test_solo_arena_valid_run_still_scores(tmp_path: Path):
    result = _run(tmp_path, arena_id="cartpole", agents={"player_1": "first-legal"})
    assert result.score.match_valid_for_scoring is True
    public = _public(result)
    assert public["score"]["scoring_status"] == "scored"
    assert public["score"]["primary_score"] == result.score.primary_score


@pytest.mark.parametrize("arena_id", ["bridge", "dou-dizhu", "leduc-holdem"])
@pytest.mark.parametrize("policy", NON_FORFEIT_POLICIES)
def test_multi_seat_arena_invalid_run_publishes_no_winner(tmp_path: Path, arena_id, policy):
    agent, option = _failing_agent("no_move")
    from eslams.arenas import registry

    seats = registry.create(arena_id).players
    assert len(seats) > 2
    agents = dict.fromkeys(seats, "first-legal") | {"player_1": agent}
    result = _run(tmp_path, arena_id=arena_id, agents=agents, **{option: policy})
    assert result.score.match_valid_for_scoring is False
    _assert_excluded(_public(result))
    _assert_metrics_excluded(result)


# --- best_score is the evaluated player's, not the best seat's ------------------


def test_best_score_is_evaluated_players_score_when_opponent_wins(tmp_path: Path):
    # A valid run that player_2 wins: best_score must not report player_2's 1.0.
    result = _run(
        tmp_path,
        arena_id="tic-tac-toe",
        agents={"player_1": "random", "player_2": "first-legal"},
        seed=3,
    )
    assert result.score.match_valid_for_scoring is True
    assert result.score.winner == "player_2"
    metrics = _json(result.artifact_path / "scores/score.json")["metrics"]
    assert metrics["evaluated_player"] == "player_1"
    assert metrics["best_score"] == result.score.scores_by_player["player_1"]
    assert metrics["raw_best_score"] == result.score.scores_by_player["player_1"]
    assert metrics["best_score"] == 0.0
    assert metrics["confidence_interval"] == [0.0, 0.0]


def test_raw_best_score_for_invalid_run_is_evaluated_players_board_score(tmp_path: Path):
    agent, _ = _failing_agent("no_move")
    result = _run(
        tmp_path, agents={"player_1": "first-legal", "player_2": agent}, on_agent_error="fallback"
    )
    metrics = _json(result.artifact_path / "scores/score.json")["metrics"]
    assert metrics["best_score"] is None
    assert metrics["raw_best_score"] == result.score.scores_by_player["player_1"]


# --- bundle and merged rows -------------------------------------------------------


def test_bundle_and_merged_rows_carry_no_winner_for_invalid_runs(tmp_path: Path):
    runs = tmp_path / "runs"
    agent, _ = _failing_agent("no_move")
    invalid = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            run_id="invalid-fallback",
            agents={"player_1": agent, "player_2": "first-legal"},
            on_agent_error="fallback",
            output_dir=runs,
            archive=True,
            execution_profile="interactive",
        )
    )
    valid = Runner().run(
        RunConfig(arena_id="tic-tac-toe", run_id="valid-run", output_dir=runs, archive=True)
    )
    assert invalid.score.match_valid_for_scoring is False
    assert valid.score.match_valid_for_scoring is True

    bundle = export_publication_bundle(
        kind="uploaded-replay", artifacts_dir=runs, output_dir=tmp_path / "bundle"
    )
    rows = {
        row["run_id"]: row
        for row in map(json.loads, (bundle / "leaderboard_rows.jsonl").read_text().splitlines())
        if row
    }
    assert rows["invalid-fallback"]["winner"] is None
    assert rows["invalid-fallback"]["valid_for_scoring"] is False
    assert rows["valid-run"]["winner"] == valid.score.winner

    merged = _json(merge_official_results(runs, tmp_path / "merged.json"))
    merged_rows = {row["run_id"]: row for row in merged["rows"]}
    assert merged_rows["invalid-fallback"]["winner"] is None
    assert merged_rows["invalid-fallback"]["valid_for_scoring"] is False
    assert merged_rows["valid-run"]["winner"] == valid.score.winner


# --- CLI output -----------------------------------------------------------------


def _cli_run(tmp_path: Path, capsys, *extra: str) -> dict[str, Any]:
    code = main(
        [
            "run",
            "--arena",
            "tic-tac-toe",
            "--agent",
            "http://127.0.0.1:9/act",
            "--opponent",
            "first-legal",
            "--output-dir",
            str(tmp_path),
            *extra,
        ]
    )
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :])
    payload["_exit_code"] = code
    return payload


@pytest.mark.parametrize("policy", NON_FORFEIT_POLICIES)
def test_cli_summary_prints_no_winner_for_invalid_run(tmp_path: Path, capsys, policy):
    payload = _cli_run(tmp_path, capsys, "--on-agent-error", policy, "--run-id", f"cli-{policy}")
    summary = payload["summary"]
    public = _json(Path(payload["expanded_artifact"]) / "public/public_result_summary.json")
    assert summary["match_valid_for_scoring"] is False
    assert summary["winner"] is None
    assert summary["winner"] == public["winner"]
    assert summary["scoring_status"] == "excluded_invalid_run"
    assert summary["board_winner"] == payload["score"]["winner"]


def test_cli_fallback_failing_seat_board_win_is_only_a_board_result(tmp_path: Path, capsys):
    payload = _cli_run(tmp_path, capsys, "--on-agent-error", "fallback", "--run-id", "cli-fb")
    assert payload["summary"]["winner"] is None
    assert payload["summary"]["board_winner"] == "player_1"


def test_cli_summary_for_valid_run_is_unchanged(tmp_path: Path, capsys):
    code = main(
        [
            "run",
            "--arena",
            "tic-tac-toe",
            "--agent",
            "first-legal",
            "--opponent",
            "first-legal",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "cli-valid",
        ]
    )
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :])
    assert code == 0
    assert payload["summary"]["winner"] == payload["score"]["winner"]
    assert payload["summary"]["scoring_status"] == "scored"
    assert "board_winner" not in payload["summary"]


# --- replay viewer ----------------------------------------------------------------


def _scoring_block(html_text: str) -> dict[str, Any]:
    marker = '<script type="application/json" id="scoring">'
    start = html_text.index(marker) + len(marker)
    return json.loads(html_text[start : html_text.index("</script>", start)])


@pytest.mark.parametrize("policy", NON_FORFEIT_POLICIES)
def test_replay_viewer_labels_invalid_run_as_excluded(tmp_path: Path, policy):
    agent, _ = _failing_agent("no_move")
    result = _run(
        tmp_path,
        agents={"player_1": agent, "player_2": "first-legal"},
        on_agent_error=policy,
        archive=True,
    )
    public = _public_from_expanded(result)
    embedded = (result.expanded_path / "replay/index.html").read_text(encoding="utf-8")
    rendered = render_replay_html(result.artifact_path).read_text(encoding="utf-8")
    for text in (embedded, rendered):
        block = _scoring_block(text)
        assert block["source"] == "public_result_summary"
        assert block["scoring_status"] == "excluded_invalid_run"
        assert block["public_winner"] == public["winner"] is None
        assert "excluded from scoring" in text
        assert "function winnerRow(" in text


def test_replay_viewer_valid_run_shows_scored(tmp_path: Path):
    result = _run(
        tmp_path, agents={"player_1": "first-legal", "player_2": "first-legal"}, archive=True
    )
    block = _scoring_block(render_replay_html(result.artifact_path).read_text(encoding="utf-8"))
    assert block["scoring_status"] == "scored"
    assert block["public_winner"] == result.score.winner


def _public_from_expanded(result) -> dict[str, Any]:
    return _json(result.expanded_path / "public/public_result_summary.json")


def test_replay_viewer_follows_public_summary_not_board(tmp_path: Path):
    """The viewer shows whatever winner the public summary publishes (decision-neutral)."""
    from eslams.replay import _scoring_from_public_summary

    summary = {
        "valid_for_scoring": False,
        "winner": "player_2",
        "outcome": {"winner": "player_2", "reason": "example"},
        "score": {"scoring_status": "excluded_invalid_run"},
        "scoring_safety_reason": "example",
    }
    block = _scoring_from_public_summary(summary)
    assert block["public_winner"] == "player_2"
    assert block["scoring_status"] == "excluded_invalid_run"
    summary["winner"] = None
    assert _scoring_from_public_summary(summary)["public_winner"] is None
    assert _scoring_from_public_summary(None) == {"source": "unknown"}
