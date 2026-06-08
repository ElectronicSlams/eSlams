import json
from pathlib import Path

from eslams.cli import main
from eslams.official import merge_official_results
from eslams.runner import RunConfig, Runner


def test_official_merge_writes_leaderboard_ready_summary(tmp_path: Path):
    Runner().run(RunConfig(arena_id="tic-tac-toe", seed=1, output_dir=tmp_path, archive=True))
    Runner().run(RunConfig(arena_id="connect-four", seed=2, output_dir=tmp_path, archive=True))

    output = merge_official_results(tmp_path, tmp_path / "official_result.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "eslams.official.result.v1"
    assert payload["case_counts"]["total"] == 2
    assert payload["proof_counts"]["artifacts"] == 2
    assert payload["aggregate_cost"]["status"] == "cost_unavailable"
    assert len(payload["rows"]) == 2


def test_cli_official_merge(tmp_path: Path):
    Runner().run(RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path, archive=True))

    assert (
        main(["official", "merge", str(tmp_path), "--out", str(tmp_path / "official.json")])
        == 0
    )
    assert (tmp_path / "official.json").exists()
