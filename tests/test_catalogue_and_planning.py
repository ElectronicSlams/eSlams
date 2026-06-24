import json
from pathlib import Path

import eslams.catalogue as catalogue_module
from eslams.arenas import registry
from eslams.catalogue import availability_rows, game_catalogue_rows, model_catalogue_rows
from eslams.cli import main
from eslams.eval_runtime import (
    ResumeCheckpointRecord,
    ResumeInvariant,
    append_progress_event,
    load_resume_checkpoint,
    plan_case_ids,
    progress_event,
    should_skip_case,
    write_resume_checkpoint,
)
from eslams.planning import official_plan
from eslams.providers import load_provider_registry
from eslams.public_catalogue import PUBLIC_CATEGORY_LABELS, PUBLIC_GAME_CATALOGUE_BY_ID
from eslams.rendering import renderer_vocabulary_hash, renderer_vocabulary_rows


def test_catalogue_exports_games_models_and_availability_rows():
    games = game_catalogue_rows()
    models = model_catalogue_rows()
    availability = availability_rows()

    assert len(games) == 50
    assert all(game["schema_version"] == "eslams.catalogue.game.v1" for game in games)
    assert any(game["game_id"] == "tic-tac-toe" for game in games)
    assert models
    assert all(model["schema_version"] == "eslams.catalogue.model.v1" for model in models)
    assert all("official_eval" in model["capability_flags"] for model in models)
    assert availability
    assert all(row["schema_version"] == "eslams.catalogue.availability.v1" for row in availability)
    assert all("reason" in row for row in availability)
    assert all("timeline_completeness" in game for game in games)
    assert all("render_hints_version" in game for game in games)
    by_game = {row["game_id"]: row for row in games}
    assert by_game["blackjack"]["variant_token"] == "core_hit_stand_s17"
    assert by_game["blackjack"]["variant_label"] == "Hit Stand S17"
    assert by_game["cartpole"]["display_name"] == "CartPole"
    assert by_game["cartpole"]["public_display_group"] == "Control & Arcade"
    assert by_game["chess"]["public_display_group"] == "Board & Strategy"
    assert by_game["liars-dice"]["public_display_group"] == "Card & Hidden-Info"


def test_game_catalogue_skips_missing_renderer_rows(monkeypatch):
    monkeypatch.setattr(catalogue_module, "renderer_vocabulary_rows", lambda: [])

    assert catalogue_module.game_catalogue_rows() == []


def test_game_catalogue_matches_transcribed_platform_identity_for_all_games():
    games = game_catalogue_rows()
    by_game = {row["game_id"]: row for row in games}

    assert set(by_game) == set(PUBLIC_GAME_CATALOGUE_BY_ID)
    for game_id, expected in PUBLIC_GAME_CATALOGUE_BY_ID.items():
        row = by_game[game_id]
        assert row["public_display_name"] == expected.name
        assert row["public_game_label"] == expected.name
        assert row["public_category_key"] == expected.category
        assert row["public_category_label"] == PUBLIC_CATEGORY_LABELS[expected.category]
        assert row["public_display_group"] == PUBLIC_CATEGORY_LABELS[expected.category]
        assert row["variant_token"] == expected.variant
        assert row["variant_slug"] == expected.variant
        assert row["public_variant_label"] == expected.variant_label


def test_game_catalogue_non_solo_topology_matches_registered_arena_players():
    for row in game_catalogue_rows():
        arena = registry.create(row["game_id"])
        topology = row["topology"]
        controlled_players = tuple(topology["controlledPlayers"])
        if topology["mode"] == "solo_score":
            assert controlled_players == ("player_1",)
            assert controlled_players[0] in arena.players
            continue

        assert controlled_players == arena.players
        assert row["default_players"] == len(arena.players)
        assert row["player_count"] == len(arena.players)


def test_renderer_vocabulary_classifies_all_arenas_as_safe_or_explicit_absence():
    rows = renderer_vocabulary_rows()
    by_game = {row["game_id"]: row for row in rows}

    assert len(rows) == 50
    assert renderer_vocabulary_hash()
    assert all(row["schema_version"] == "eslams.catalogue.renderer.v1" for row in rows)
    assert by_game["tic-tac-toe"]["timeline_completeness"] == "playable"
    assert by_game["connect-four"]["timeline_completeness"] == "playable"
    assert by_game["tic-tac-toe"]["move_frame_count"] >= 1
    assert by_game["connect-four"]["visible_frame_count"] >= 2
    assert all(row["public_safe"] is True for row in rows)
    assert all(
        row["timeline_completeness"]
        in {"playable", "partial", "setup_only", "metadata_only", "unavailable"}
        for row in rows
    )
    assert all(row["renderer_family"] for row in rows)


def test_official_plan_is_deterministic_and_conservative():
    first = official_plan(
        suite="public-smoke",
        providers=["openai"],
        arenas=["tic-tac-toe"],
        shard_count=2,
    )
    second = official_plan(
        suite="public-smoke",
        providers=["openai"],
        arenas=["tic-tac-toe"],
        shard_count=2,
    )

    assert first == second
    assert first["schema_version"] == "eslams.eval.plan.v1"
    assert first["plan_hash"]
    assert first["selected_arenas"] == ["tic-tac-toe"]
    assert len(first["shards"]) == 2
    openai_game_agents = [
        record
        for record in load_provider_registry().list_models(provider="openai")
        if record.game_agent_supported
    ]
    assert len(first["selected_models"]) < len(openai_game_agents)
    shard_cases = [case_id for shard in first["shards"] for case_id in shard["case_ids"]]
    assert sorted(shard_cases) == plan_case_ids(first)
    assert len(shard_cases) == len(set(shard_cases))


def test_resume_checkpoint_requires_full_invariant_match(tmp_path: Path):
    plan = official_plan(
        suite="public-smoke",
        providers=["openai"],
        arenas=["tic-tac-toe"],
        shard_count=1,
    )
    invariant = ResumeInvariant(
        case_id="case-1",
        artifact_digest="artifact-digest",
        model_id="openai:gpt-test",
        suite_fingerprint=plan["suite_fingerprint"],
        runner_version=plan["runner_version"],
        plan_hash=plan["plan_hash"],
    )
    checkpoint_path = write_resume_checkpoint(
        tmp_path / "checkpoint.json",
        [ResumeCheckpointRecord(invariant=invariant, artifact_path="runs/case-1.eslams")],
    )
    checkpoint = load_resume_checkpoint(checkpoint_path)

    assert should_skip_case(checkpoint, invariant) is True
    changed_artifact = ResumeInvariant(
        case_id=invariant.case_id,
        artifact_digest="different-artifact",
        model_id=invariant.model_id,
        suite_fingerprint=invariant.suite_fingerprint,
        runner_version=invariant.runner_version,
        plan_hash=invariant.plan_hash,
    )
    assert should_skip_case(checkpoint, changed_artifact) is False


def test_progress_event_is_jsonl_machine_readable(tmp_path: Path):
    plan = official_plan(
        suite="public-smoke",
        providers=["openai"],
        arenas=["tic-tac-toe"],
        shard_count=1,
    )
    event = progress_event(
        plan=plan,
        current_case="case-1",
        completed_cases=2,
        failed_cases=1,
        skipped_cases=1,
        elapsed_seconds=2.0,
        provider_latencies_ms=[100, 300],
    )
    progress_path = append_progress_event(tmp_path / "progress.jsonl", event)
    row = json.loads(progress_path.read_text(encoding="utf-8").strip())

    assert row["schema_version"] == "eslams.eval.progress.v1"
    assert row["completed_cases"] == 2
    assert row["case_rate"] == 2.0
    assert row["provider_latency_rolling_stats"]["mean_ms"] == 200.0


def test_cli_catalogue_and_plan_commands(tmp_path: Path, capsys):
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"arena_id": "tic-tac-toe", "models": ["mock:model-a", "mock:model-b"]}),
        encoding="utf-8",
    )

    assert main(["catalogue", "games", "--json"]) == 0
    games = json.loads(capsys.readouterr().out)
    assert len(games) == 50
    assert main(["catalogue", "renderers", "--json"]) == 0
    renderers = json.loads(capsys.readouterr().out)
    assert len(renderers) == 50

    assert (
        main(
            [
                "plan",
                "official",
                "--suite",
                "public-smoke",
                "--providers",
                "openai",
                "--arenas",
                "tic-tac-toe",
                "--json",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["kind"] == "official"

    assert main(["plan", "public-match", "--request", str(request), "--json"]) == 0
    public_plan = json.loads(capsys.readouterr().out)
    assert public_plan["case_count_expected"] == 2


def test_cli_plan_progress_and_resume_check(tmp_path: Path, capsys):
    plan = official_plan(
        suite="public-smoke",
        providers=["openai"],
        arenas=["tic-tac-toe"],
        shard_count=1,
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    invariant = ResumeInvariant(
        case_id="case-1",
        artifact_digest="artifact-digest",
        model_id="openai:gpt-test",
        suite_fingerprint=plan["suite_fingerprint"],
        runner_version=plan["runner_version"],
        plan_hash=plan["plan_hash"],
    )
    checkpoint = write_resume_checkpoint(
        tmp_path / "checkpoint.json",
        [ResumeCheckpointRecord(invariant=invariant, artifact_path="runs/case-1.eslams")],
    )

    assert (
        main(
            [
                "plan",
                "progress",
                "--plan",
                str(plan_path),
                "--out",
                str(tmp_path / "progress.jsonl"),
                "--current-case",
                "case-1",
                "--completed-cases",
                "1",
                "--elapsed-seconds",
                "2",
            ]
        )
        == 0
    )
    assert (tmp_path / "progress.jsonl").exists()
    progress_payload = json.loads(capsys.readouterr().out)
    assert progress_payload["schema_version"] == "eslams.eval.progress.v1"

    assert (
        main(
            [
                "plan",
                "resume-check",
                "--checkpoint",
                str(checkpoint),
                "--case-id",
                invariant.case_id,
                "--artifact-digest",
                invariant.artifact_digest,
                "--model-id",
                invariant.model_id,
                "--suite-fingerprint",
                invariant.suite_fingerprint,
                "--runner-version",
                invariant.runner_version,
                "--plan-hash",
                invariant.plan_hash,
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["skip"] is True
