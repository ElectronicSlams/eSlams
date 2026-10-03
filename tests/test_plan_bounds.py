import json

import pytest

from eslams.cli import main
from eslams.planning import battlefield_plan, official_plan, public_match_plan


@pytest.mark.parametrize("kind", ["official", "battlefield", "public-match"])
@pytest.mark.parametrize("count", [0, -1, 1000000])
def test_cli_planners_refuse_unbounded_or_clamped_shard_counts(
    tmp_path, capsys, kind, count
):
    args = ["plan", kind, "--shard-count", str(count)]
    if kind == "official":
        args += ["--suite", "public-smoke", "--providers", "openai", "--arenas", "tic-tac-toe"]
    elif kind == "battlefield":
        args += ["--pairs", "mock:a,mock:b", "--arenas", "tic-tac-toe"]
    else:
        request = tmp_path / "request.json"
        request.write_text(json.dumps({"arena_id": "tic-tac-toe"}))
        args += ["--request", str(request)]
    assert main(args) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "shard_count must be an integer between" in captured.err


def test_plan_shards_are_bounded_by_workload_and_partition_cases(tmp_path):
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"arena_id": "tic-tac-toe", "models": ["mock:b", "mock:a"]}))
    plan = public_match_plan(request_path=request, shard_count=2)
    assert [row["case_count"] for row in plan["shards"]] == [1, 1]
    cases = [case for shard in plan["shards"] for case in shard["case_ids"]]
    assert sorted(cases) == ["public-match:tic-tac-toe:mock:a", "public-match:tic-tac-toe:mock:b"]
    for count in (3, True, 1.5):
        with pytest.raises(ValueError, match="between 1 and 2"):
            public_match_plan(request_path=request, shard_count=count)
    with pytest.raises(ValueError, match="between 1 and 1"):
        battlefield_plan(pairs=[], arenas=["tic-tac-toe"], shard_count=2)
    with pytest.raises(ValueError, match="between 1 and 1"):
        official_plan(suite="public-smoke", providers=[], arenas=["tic-tac-toe"], shard_count=2)
