import json
from pathlib import Path

from eslams.agents import HttpAgent, MockProviderAgent, ModelProviderAgent
from eslams.artifacts import (
    ArtifactValidator,
    extract_provider_usage,
    extract_public_manifest,
    extract_validation_summary,
)
from eslams.cli import main
from eslams.contracts import schema_versions
from eslams.contracts.artifact import no_secret_examples as artifact_examples
from eslams.contracts.catalogue import no_secret_examples as catalogue_examples
from eslams.contracts.eval_plan import no_secret_examples as eval_plan_examples
from eslams.contracts.json_schema import export_schemas
from eslams.contracts.json_schema import no_secret_examples as schema_examples
from eslams.contracts.provider import no_secret_examples as provider_examples
from eslams.contracts.publication import no_secret_examples as publication_examples
from eslams.contracts.replay import no_secret_examples as replay_examples
from eslams.contracts.runner_job import no_secret_examples as runner_job_examples
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.public_replay import create_uploaded_smoke_fixture, export_public_replay
from eslams.runner import RunConfig, Runner


def test_schema_versions_have_no_secret_examples_and_export_deterministically(tmp_path: Path):
    examples = {}
    for provider in (
        artifact_examples,
        replay_examples,
        provider_examples,
        publication_examples,
        eval_plan_examples,
        catalogue_examples,
        runner_job_examples,
        schema_examples,
    ):
        examples.update(provider())

    assert set(schema_versions()) <= set(examples)
    assert '"prompt":' not in canonical_json(examples).lower()
    assert "api_key" not in canonical_json(examples).lower()

    first = tmp_path / "schemas_a"
    second = tmp_path / "schemas_b"
    first_paths = export_schemas(first)
    second_paths = export_schemas(second)

    assert [path.name for path in first_paths] == [path.name for path in second_paths]
    for left in first_paths:
        right = second / left.name
        assert left.read_bytes() == right.read_bytes()


def test_runner_artifact_includes_public_sidecars_and_archive_helpers(tmp_path: Path):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path, archive=True)
    )

    report = ArtifactValidator().validate_report(result.artifact_path, profile="runner-bundle")
    validation_summary = extract_validation_summary(result.artifact_path)
    public_manifest = extract_public_manifest(result.artifact_path)
    provider_usage = extract_provider_usage(result.artifact_path)

    assert report.valid is True
    assert report.to_dict()["schema_version"] == "eslams.artifact.validation.v1"
    assert validation_summary is not None
    assert validation_summary["schema_version"] == "eslams.artifact.validation.v1"
    assert validation_summary["verification_level_key"] == "local_artifact"
    assert validation_summary["per_case_scoring_eligible"] is True
    assert validation_summary["aggregate_leaderboard_eligible"] is False
    assert public_manifest is not None
    assert public_manifest["replay_events_path"] == "replay/replay_events.jsonl"
    assert public_manifest["display_frames_path"] == "replay/display_frames.jsonl"
    assert provider_usage["receipt_count"] == 0

    manifest = json.loads((result.expanded_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == "eslams.artifact.manifest.v1"
    assert manifest["artifact_profile"] == "runner_bundle"
    assert manifest["artifact_kind"] == "local_match"
    assert manifest["verification_level_key"] == "local_artifact"
    assert manifest["verification_level_label"] == "Local Artifact"
    assert manifest["artifact_profile_key"] == "runner_bundle"
    assert manifest["artifact_profile_label"] == "Runner Bundle"
    assert manifest["scoring_policy_key"] == "tic_tac_toe_score"
    assert manifest["per_case_run_valid"] is True
    assert manifest["per_case_scoring_eligible"] is True
    assert manifest["proof_row_publication_eligible"] is True
    assert manifest["aggregate_leaderboard_eligible"] is False
    assert manifest["public_exports"]["public_reasoning"] == "public_reasoning/reasoning.jsonl"
    assert manifest["public_exports"]["public_display_frames"] == "replay/display_frames.jsonl"
    assert manifest["validation_summary_path"] == "validation/validation_summary.json"

    replay = _read_jsonl(result.expanded_path / "replay/replay_events.jsonl")
    display_frames = _read_jsonl(result.expanded_path / "replay/display_frames.jsonl")
    assert replay[1]["actor_player"] == "player_1"
    assert replay[1]["seat"] == "player_1"
    assert replay[1]["state_hash_before"] == replay[0]["state_hash"]
    assert replay[1]["state_hash_after"] == replay[1]["state_hash"]
    assert replay[1]["public_safe"] is True
    assert display_frames[0]["schema_version"] == "eslams.replay.display_frame.v1"
    assert display_frames[0]["source_replay_event_id"] == replay[0]["event_id"]


def test_validation_profiles_distinguish_runner_public_and_official(tmp_path: Path):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=5, output_dir=tmp_path, archive=True)
    )
    public_dir = export_public_replay(result.artifact_path, tmp_path / "public_package")

    public_report = ArtifactValidator().validate_report(
        public_dir,
        profile="public-replay-package",
    )
    runner_report = ArtifactValidator().validate_report(public_dir, profile="runner-bundle")
    official_report = ArtifactValidator().validate_report(
        result.artifact_path,
        profile="official-bundle",
    )
    package_manifest = json.loads((public_dir / "manifest.json").read_text(encoding="utf-8"))
    optional_reasoning = package_manifest["optional_files"][0]

    assert public_report.valid is True
    assert (public_dir / "replay/display_frames.jsonl").exists()
    assert optional_reasoning["path"] == "public_reasoning/reasoning.jsonl"
    assert optional_reasoning["present"] is True
    assert optional_reasoning["sha256"]
    assert runner_report.valid is False
    assert any(
        item == "missing required file: traces/public_trace.jsonl"
        for item in runner_report.errors
    )
    assert official_report.valid is False
    assert "runner_signature_missing" in official_report.errors


def test_public_safety_scanner_rejects_nested_raw_provider_response(tmp_path: Path):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=7, output_dir=tmp_path))
    public_dir = export_public_replay(result.artifact_path, tmp_path / "public_package")
    replay_path = public_dir / "replay/replay_events.jsonl"
    rows = _read_jsonl(replay_path)
    rows[0]["nested"] = {"raw_provider_response": {"debug": "not public"}}
    _write_jsonl(replay_path, rows)
    _refresh_public_manifest_hashes(public_dir)

    report = ArtifactValidator().validate_report(public_dir, profile="public-replay-package")

    assert report.valid is False
    assert any("raw_provider_response" in error for error in report.errors)


def test_public_replay_optional_file_rows_record_absence(tmp_path: Path):
    source = create_uploaded_smoke_fixture(tmp_path / "uploaded")
    exported = export_public_replay(source, tmp_path / "exported")
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    optional_reasoning = manifest["optional_files"][0]

    assert optional_reasoning["path"] == "public_reasoning/reasoning.jsonl"
    assert optional_reasoning["present"] is False
    assert optional_reasoning["sha256"] is None
    assert optional_reasoning["size_bytes"] is None
    assert optional_reasoning["absent_reason"] == "not_emitted_by_source_artifact"


def test_failed_provider_attempt_writes_redacted_receipt(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": ModelProviderAgent(
                    provider="openai",
                    model="gpt-test",
                    api_key_env="MISSING_PROVIDER_KEY",
                )
            },
            seed=11,
            max_turns=1,
            output_dir=tmp_path,
        )
    )

    receipts = _read_jsonl(result.artifact_path / "receipts/provider_receipts.jsonl")

    assert receipts
    receipt = receipts[0]
    assert receipt["schema_version"] == "eslams.provider.receipt.v1"
    assert receipt["outcome"] == "unavailable"
    assert receipt["usage_unavailable_reason"] == "provider_not_called_missing_api_key"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "raw_output_preview" not in receipt
    assert "api_key_env" not in receipt


def test_runner_persists_mock_provider_failure_receipts(tmp_path: Path):
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": MockProviderAgent(scenario="gateway_auth_failed")},
            seed=12,
            max_turns=1,
            output_dir=tmp_path,
        )
    )

    receipts = _read_jsonl(result.artifact_path / "receipts/provider_receipts.jsonl")

    assert receipts
    assert receipts[0]["outcome"] == "gateway_auth_failed"
    assert receipts[0]["schema_version"] == "eslams.provider.receipt.v1"
    assert receipts[0]["estimated_cost"]["status"] == "cost_unavailable"


def test_runner_persists_each_provider_retry_receipt(tmp_path: Path, monkeypatch):
    import httpx

    from eslams.contracts.provider import ProviderRuntimeConfig

    calls = {"count": 0}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, text="temporary provider failure")
        return httpx.Response(
            200,
            json={
                "id": "resp_retry",
                "output_text": '{"action": 0}',
                "usage": {"input_tokens": 4, "output_tokens": 1},
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": ModelProviderAgent(
                    provider="openai",
                    model="gpt-test",
                    api_key_env="OPENAI_API_KEY",
                    runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0),
                )
            },
            seed=13,
            max_turns=1,
            output_dir=tmp_path,
        )
    )
    receipts = _read_jsonl(result.artifact_path / "receipts/provider_receipts.jsonl")

    assert calls["count"] == 2
    assert [receipt["attempt"] for receipt in receipts] == [1, 2]
    assert [receipt["outcome"] for receipt in receipts] == ["provider_error", "ok"]


def test_runner_persists_http_agent_provider_receipts(tmp_path: Path, monkeypatch):
    import httpx

    receipt = {
        "schema_version": "eslams.provider.receipt.v1",
        "provider": "openai",
        "model": "gpt-test",
        "outcome": "ok",
        "usage": {"input_tokens": 4, "output_tokens": 1, "total_tokens": 5},
        "estimated_cost": {"status": "cost_unavailable"},
    }

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> httpx.Response:
        assert url == "https://agent.example/act"
        return httpx.Response(
            200,
            json={"action": 0, "metadata": {"provider_receipt": receipt}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": HttpAgent(url="https://agent.example/act")},
            seed=14,
            max_turns=1,
            output_dir=tmp_path,
        )
    )
    receipts = _read_jsonl(result.artifact_path / "receipts/provider_receipts.jsonl")
    metrics = json.loads((result.artifact_path / "scores/metrics.json").read_text())

    assert receipts
    assert receipts[0]["provider"] == "openai"
    assert receipts[0]["usage"]["total_tokens"] == 5
    assert receipts[0]["run_id"] == result.run_id
    assert metrics["provider_status_by_player"]["player_1"] == "provider_ok"


def test_runner_provider_status_cases(tmp_path: Path, monkeypatch):
    import httpx

    responses = [
        {"action": 0},
        {
            "action": 0,
            "metadata": {
                "provider_receipt": {
                    "schema_version": "eslams.provider.receipt.v1",
                    "provider": "openai",
                    "model": "gpt-test",
                    "outcome": "ok",
                    "usage": {},
                }
            },
        },
    ]

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: int,
    ) -> httpx.Response:
        payload = responses.pop(0)
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    missing_receipt = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": HttpAgent(
                    url="https://agent.example/act",
                    provider="openai",
                    model="gpt-test",
                )
            },
            seed=15,
            max_turns=1,
            output_dir=tmp_path / "missing",
        )
    )
    usage_missing = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={
                "player_1": HttpAgent(
                    url="https://agent.example/act",
                    provider="openai",
                    model="gpt-test",
                )
            },
            seed=16,
            max_turns=1,
            output_dir=tmp_path / "usage",
        )
    )
    local = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=17, max_turns=1, output_dir=tmp_path / "local")
    )
    error = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": MockProviderAgent(scenario="provider_error")},
            seed=18,
            max_turns=1,
            output_dir=tmp_path / "error",
        )
    )

    assert _metrics(missing_receipt)["provider_status_by_player"]["player_1"] == (
        "provider_receipt_missing"
    )
    assert _metrics(usage_missing)["provider_status_by_player"]["player_1"] == (
        "provider_usage_unavailable"
    )
    assert _metrics(local)["provider_status_by_player"]["player_1"] == "local_agent"
    assert _metrics(error)["provider_status_by_player"]["player_1"] == "agent_error"


def test_cli_schema_export_validate_and_public_replay_commands(tmp_path: Path, capsys):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=9, output_dir=tmp_path))

    assert main(["schemas", "export", "--out", str(tmp_path / "schemas")]) == 0
    assert (tmp_path / "schemas" / "eslams.artifact.validation.v1.schema.json").exists()
    manifest = json.loads(
        (tmp_path / "schemas" / "schema_bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "eslams.schema.bundle_manifest.v1"
    assert manifest["core_package_version"] == "0.4.0"
    assert manifest["schema_bundle_version"] == "eslams-schema-bundle-v2"
    assert any(
        row["schema_version"] == "eslams.catalogue.renderer.v1"
        for row in manifest["schemas"]
    )
    assert any(
        row["schema_version"] == "eslams.replay.display_frame.v1"
        for row in manifest["schemas"]
    )

    assert main(["validate", str(result.artifact_path), "--profile", "runner-bundle"]) == 0
    assert main(["validate", str(result.artifact_path), "--summary-json"]) == 0
    summary_line = capsys.readouterr().out.splitlines()[-1]
    assert json.loads(summary_line)["schema_version"] == "eslams.artifact.validation.v1"

    public_dir = tmp_path / "public_cli"
    assert (
        main(["artifact", "public-export", str(result.artifact_path), "--out", str(public_dir)])
        == 0
    )
    assert main(["replay", "validate-public", str(public_dir)]) == 0
    assert (
        main(["fixtures", "replay", "--kind", "uploaded-smoke", "--out", str(tmp_path / "fixture")])
        == 0
    )
    assert (
        main(
            [
                "providers",
                "preflight",
                "--provider",
                "openai",
                "--model",
                "gpt-test",
                "--arena",
                "tic-tac-toe",
            ]
        )
        == 0
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def _metrics(result: object) -> dict[str, object]:
    artifact_path = result.artifact_path
    return json.loads((artifact_path / "scores/metrics.json").read_text(encoding="utf-8"))


def _refresh_public_manifest_hashes(public_dir: Path) -> None:
    manifest_path = public_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = []
    for path in sorted(public_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": path.relative_to(public_dir).as_posix(),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    manifest["files"] = files
    manifest["artifact_id"] = sha256_json(files)
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
