import json
from pathlib import Path

from eslams.cli import main
from eslams.hashing import canonical_json
from eslams.planning import battlefield_plan
from eslams.publication_export import export_publication_bundle, validate_publication_bundle
from eslams.runner import RunConfig, Runner


def test_publication_bundle_export_is_deterministic_and_storage_free(tmp_path: Path):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=3, output_dir=tmp_path, archive=True)
    )
    plan = battlefield_plan(
        pairs=["builtin:first-legal,builtin:first-legal"],
        arenas=["tic-tac-toe"],
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    first = export_publication_bundle(
        kind="battlefield-sample",
        artifact=result.artifact_path,
        plan_path=plan_path,
        output_dir=tmp_path / "bundle_a",
    )
    second = export_publication_bundle(
        kind="battlefield-sample",
        artifact=result.artifact_path,
        plan_path=plan_path,
        output_dir=tmp_path / "bundle_b",
    )

    first_manifest = json.loads((first / "bundle_manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "bundle_manifest.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((first / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    proof_rows = _read_jsonl(first / "proof_index.jsonl")
    validation = validate_publication_bundle(first)

    assert first_manifest == second_manifest
    assert validation["valid"] is True
    assert first_manifest["schema_version"] == "eslams.publication.bundle.v1"
    assert first_manifest["kind"] == "battlefield-sample"
    assert first_manifest["plan_hash"] == plan["plan_hash"]
    assert first_manifest["suite_fingerprint"] == plan["suite_fingerprint"]
    assert first_manifest["statement_projection_hash"]
    assert checkpoint["statement_projection_hash"] == first_manifest["statement_projection_hash"]
    assert first_manifest["artifact_count"] == 1
    assert proof_rows[0]["evidence_row"] is True
    assert proof_rows[0]["leaderboard_predicate"] is False
    assert (first / "checkpoint_manifest.json").exists()
    assert (first / "signature_readback_manifest.json").exists()


def test_publication_bundle_validation_rejects_implicit_leaderboard_predicate(tmp_path: Path):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=4, output_dir=tmp_path, archive=True)
    )
    bundle = export_publication_bundle(
        kind="uploaded-replay",
        artifact=result.artifact_path,
        output_dir=tmp_path / "bundle",
    )
    proof_path = bundle / "proof_index.jsonl"
    proof_rows = _read_jsonl(proof_path)
    proof_rows[0]["leaderboard_predicate"] = True
    _write_jsonl(proof_path, proof_rows)

    validation = validate_publication_bundle(bundle)

    assert validation["valid"] is False
    assert any("leaderboard predicate" in error for error in validation["errors"])


def test_publication_battlefield_sample_fixture_validates():
    fixture = Path("fixtures/publication/battlefield_sample_bundle")

    assert fixture.exists()
    assert validate_publication_bundle(fixture)["valid"] is True


def test_cli_publish_export_and_validate(tmp_path: Path):
    result = Runner().run(
        RunConfig(arena_id="tic-tac-toe", seed=4, output_dir=tmp_path, archive=True)
    )

    assert (
        main(
            [
                "publish",
                "export",
                "--kind",
                "uploaded-replay",
                "--artifact",
                str(result.artifact_path),
                "--out",
                str(tmp_path / "bundle"),
            ]
        )
        == 0
    )
    assert (tmp_path / "bundle" / "object_manifest.json").exists()
    assert main(["publish", "validate", str(tmp_path / "bundle"), "--json"]) == 0


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")
