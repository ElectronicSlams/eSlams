"""Generate keyless sample shapes in a new scratch directory for review.

Both samples are unsigned Local fixtures, including the official-proof wire
shape. Outputs retain the exact producer commit; no provider API is called.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from eslams._build_provenance import core_source_commit
from eslams.artifacts import ArtifactValidator
from eslams.fixtures import _without_signing_env, create_artifact_fixture
from eslams.hashing import canonical_json, sha256_file
from eslams.planning import battlefield_plan
from eslams.publication_export import export_publication_bundle, validate_publication_bundle
from eslams.runner import RunConfig, Runner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New scratch destination.")
    args = parser.parse_args()
    root = args.out
    root.mkdir(parents=True, exist_ok=False)
    with (
        _without_signing_env(),
        patch("eslams.artifacts.utc_now_iso", return_value="1970-01-01T00:00:00Z"),
    ):
        battle = (
            Runner()
            .run(
                RunConfig(
                    arena_id="chess",
                    agent_1="first-legal",
                    agent_2="first-legal",
                    seed=1,
                    run_id="sample_builtin_chess",
                    output_dir=root / "battle",
                    archive=True,
                )
            )
            .artifact_path
        )
        evaluation = create_artifact_fixture(
            "local-tic-tac-toe", root / "eval/local_eval_fixture.eslams"
        )
    samples = []
    for source, directory, arena, kind in (
        (battle, root / "battle", "chess", "battlefield-sample"),
        (evaluation, root / "eval", "tic-tac-toe", "official-proof"),
    ):
        report = ArtifactValidator().validate_report(source, profile="runner-bundle")
        if not report.valid:
            raise ValueError(report.errors)
        plan = battlefield_plan(pairs=["builtin:first-legal,builtin:first-legal"], arenas=[arena])
        (directory / "plan.json").write_text(canonical_json(plan) + "\n", encoding="utf-8")
        bundle = export_publication_bundle(
            kind=kind, artifact=source, output_dir=directory / "publication_bundle"
        )
        if not validate_publication_bundle(bundle)["valid"]:
            raise ValueError("generated sample publication bundle is invalid")
        samples.append(
            {
                "sample_id": report.run_id,
                "sha256": sha256_file(source),
                "artifact_id": report.artifact_id,
                "kind": kind,
                "classification": "LOCAL_FIXTURE",
                "producer_core_version": "0.6.1",
                "producer_commit": core_source_commit(),
                "dual_home": False,
                "hf_url": None,
                "validation_profile": "runner_bundle",
                "validation_valid": True,
                "official_trust": False,
            }
        )
    (root / "samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
    print("Generated two validated keyless sample archives and evidence-only publication bundles")


if __name__ == "__main__":
    main()
