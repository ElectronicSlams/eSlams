import json
import shutil

import httpx
import pytest
from test_provider_wire_v06 import _agent, _fixture

from eslams.cli import main
from eslams.official import merge_official_results
from eslams.planning import battlefield_plan, validate_plan
from eslams.publication_export import export_publication_bundle, validate_publication_bundle
from eslams.runner import RunConfig, Runner


def _files(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_duplicate_aliases_copies_and_relocation_export_one_identical_bundle(tmp_path):
    runs = tmp_path / "runs"
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", run_id="portable-run", output_dir=runs, archive=True)
    )
    shutil.copyfile(result.artifact_path, runs / "copy.eslams")
    first = export_publication_bundle(
        kind="uploaded-replay", artifacts_dir=runs, output_dir=tmp_path / "first"
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    renamed = elsewhere / "renamed.eslams"
    shutil.copyfile(result.artifact_path, renamed)
    second = export_publication_bundle(
        kind="uploaded-replay", artifact=renamed, output_dir=tmp_path / "second"
    )
    assert _files(first) == _files(second)
    manifest = json.loads((first / "bundle_manifest.json").read_text())
    assert manifest["artifact_count"] == 1
    proofs = [json.loads(line) for line in (first / "proof_index.jsonl").read_text().splitlines()]
    assert len(proofs) == 1 and proofs[0]["artifact"] == proofs[0]["artifact_id"]
    assert str(tmp_path) not in (first / "proof_index.jsonl").read_text()
    merged = merge_official_results(runs, tmp_path / "merged.json")
    assert json.loads(merged.read_text())["case_counts"]["total"] == 1
    assert validate_publication_bundle(first)["valid"]
    for archive in (False, True):
        expanded = tmp_path / f"expanded-{archive}"
        Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=expanded, archive=archive))
        bundle = export_publication_bundle(
            kind="uploaded-replay",
            artifacts_dir=expanded,
            output_dir=tmp_path / f"expanded-bundle-{archive}",
        )
        assert json.loads((bundle / "bundle_manifest.json").read_text())["artifact_count"] == 1


def test_explicit_bad_plans_artifacts_and_numeric_inputs_fail_without_output(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", output_dir=tmp_path / "runs"))
    for index, contents in enumerate((None, "{bad", "[]", "{}")):
        plan = tmp_path / f"plan-{index}.json"
        if contents is not None:
            plan.write_text(contents)
        output = tmp_path / f"bundle-{index}"
        assert (
            main(
                [
                    "publish",
                    "export",
                    "--kind",
                    "official-proof",
                    "--plan",
                    str(plan),
                    "--artifact",
                    str(result.artifact_path),
                    "--out",
                    str(output),
                ]
            )
            == 1
        )
        assert not output.exists()
        assert "error:" in capsys.readouterr().err
    for directory in (empty, tmp_path / "missing"):
        with pytest.raises(ValueError):
            merge_official_results(directory, tmp_path / "merge.json")
        assert not (tmp_path / "merge.json").exists()
    invalid = tmp_path / "invalid.eslams"
    invalid.write_bytes(b"not a ZIP")
    assert (
        main(
            [
                "publish",
                "export",
                "--kind",
                "uploaded-replay",
                "--artifact",
                str(invalid),
                "--out",
                str(tmp_path / "invalid-bundle"),
            ]
        )
        == 1
    )
    for args in (
        ["official", "--suite", "nonsense"],
        ["official", "--suite", "public-smoke", "--providers", "openai", "--arenas", "zz"],
        ["battlefield", "--pairs", "zz"],
    ):
        assert main(["plan", *args, "--json"]) == 1
    plan = battlefield_plan(pairs=["mock:a"], arenas=["tic-tac-toe"])
    validate_plan(plan)
    plan["selected_arenas"] = ["chess"]
    with pytest.raises(ValueError, match="plan_hash"):
        validate_plan(plan)
    path = tmp_path / "progress-plan.json"
    path.write_text(json.dumps(battlefield_plan(pairs=["mock:a"], arenas=["tic-tac-toe"])))
    for options in (
        ["--elapsed-seconds", "nan"],
        ["--elapsed-seconds", "inf"],
        ["--completed-cases", "-1"],
    ):
        assert (
            main(
                [
                    "plan",
                    "progress",
                    "--plan",
                    str(path),
                    "--out",
                    str(tmp_path / "progress.jsonl"),
                    *options,
                ]
            )
            == 1
        )
        assert not (tmp_path / "progress.jsonl").exists()


def test_provider_publication_preserves_per_model_usage_and_complete_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    actions = iter([0, 2, 4, 6])

    def post(*a, **k):
        payload = _fixture("openrouter_chat_completions_success.json")
        payload["choices"][0]["message"]["content"] = json.dumps({"action": next(actions)})
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": _agent("openrouter", "openai/gpt-5-mini", "OPENROUTER_API_KEY")},
            output_dir=tmp_path / "runs",
        )
    )
    bundle = export_publication_bundle(
        kind="uploaded-replay", artifacts_dir=tmp_path / "runs", output_dir=tmp_path / "bundle"
    )
    receipts = [
        json.loads(line)
        for line in (result.artifact_path / "receipts/provider_receipts.jsonl")
        .read_text()
        .splitlines()
    ]
    rows = [
        json.loads(line) for line in (bundle / "provider_model_rows.jsonl").read_text().splitlines()
    ]
    aggregate = json.loads((bundle / "aggregate_usage.json").read_text())
    assert len(rows) == 1 and rows[0]["provider"] == "openrouter"
    assert rows[0]["model"] == "openai/gpt-5-mini" and rows[0]["resolved_model"]
    assert rows[0]["receipt_count"] == len(receipts) == 4
    assert rows[0]["usage"] == aggregate["usage"]
    assert aggregate["pricing"]["status"] == rows[0]["pricing"]["status"] == "ok"
    assert aggregate["pricing"]["cost_usd"] == pytest.approx(
        sum(row["estimated_cost"]["cost_usd"] for row in receipts)
    )
    assert not rows[0]["aggregate_leaderboard_eligible"]
    assert validate_publication_bundle(bundle)["valid"]
    from eslams.publication_export import _receipt_pricing

    incomplete = _receipt_pricing([*receipts, {"estimated_cost": {"status": "cost_unavailable"}}])
    assert incomplete["status"] == "cost_unavailable" and incomplete["cost_usd"] is None
    assert incomplete["known_cost_usd"] == aggregate["pricing"]["cost_usd"]
    assert not incomplete["cost_complete"]


def test_saved_arena_start_and_step_results_work_as_next_cli_input(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_SECRET", "s" * 32)
    assert (
        main(
            [
                "arena",
                "start",
                "--game",
                "tic-tac-toe",
                "--seed",
                "1",
                "--players-json",
                json.dumps({"player_1": {"kind": "human"}, "player_2": {"kind": "human"}}),
            ]
        )
        == 0
    )
    path = tmp_path / "session.json"
    path.write_text(capsys.readouterr().out)
    assert (
        main(["arena", "legal-actions-page", "--state", str(path), "--player-id", "player_1"]) == 0
    )
    page = json.loads(capsys.readouterr().out)
    assert page["total_matching_actions"] == 9
    assert (
        main(
            [
                "arena",
                "step",
                "--state",
                str(path),
                "--player-id",
                "player_1",
                "--action-token",
                "4",
            ]
        )
        == 0
    )
    stepped = capsys.readouterr().out
    assert json.loads(stepped)["accepted"]
    path.write_text(stepped)
    assert (
        main(
            [
                "arena",
                "step",
                "--state",
                str(path),
                "--player-id",
                "player_2",
                "--action-token",
                "0",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["accepted"]
