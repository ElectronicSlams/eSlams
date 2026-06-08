import json
from pathlib import Path

from eslams.agents import MockProviderAgent, ModelProviderAgent
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
from eslams.contracts.provider import no_secret_examples as provider_examples
from eslams.contracts.publication import no_secret_examples as publication_examples
from eslams.contracts.replay import no_secret_examples as replay_examples
from eslams.contracts.runner_job import no_secret_examples as runner_job_examples
from eslams.hashing import canonical_json, sha256_file, sha256_json
from eslams.public_replay import export_public_replay
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
    ):
        examples.update(provider())

    assert set(schema_versions()) <= set(examples)
    assert "prompt" not in canonical_json(examples).lower()
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
    assert public_manifest is not None
    assert public_manifest["replay_events_path"] == "replay/replay_events.jsonl"
    assert provider_usage["receipt_count"] == 0

    manifest = json.loads((result.expanded_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == "eslams.artifact.manifest.v1"
    assert manifest["artifact_profile"] == "runner_bundle"
    assert manifest["artifact_kind"] == "local_match"
    assert manifest["public_exports"]["public_reasoning"] == "public_reasoning/reasoning.jsonl"
    assert manifest["validation_summary_path"] == "validation/validation_summary.json"

    replay = _read_jsonl(result.expanded_path / "replay/replay_events.jsonl")
    assert replay[1]["actor_player"] == "player_1"
    assert replay[1]["seat"] == "player_1"
    assert replay[1]["state_hash_before"] == replay[0]["state_hash"]
    assert replay[1]["state_hash_after"] == replay[1]["state_hash"]
    assert replay[1]["public_safe"] is True


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

    assert public_report.valid is True
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


def test_cli_schema_export_validate_and_public_replay_commands(tmp_path: Path, capsys):
    result = Runner().run(RunConfig(arena_id="tic-tac-toe", seed=9, output_dir=tmp_path))

    assert main(["schemas", "export", "--out", str(tmp_path / "schemas")]) == 0
    assert (tmp_path / "schemas" / "eslams.artifact.validation.v1.schema.json").exists()

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
