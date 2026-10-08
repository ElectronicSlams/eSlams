"""Compare real deterministic artifact/schema/export bytes across native CI hosts.

The artifact file table excludes measured timing diagnostics. Fix the manifest's
wall clock for this fixture; production archives retain their real diagnostics.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from eslams.artifacts import ArtifactValidator
from eslams.contracts.json_schema import export_schemas
from eslams.hashing import canonical_json, sha256_file
from eslams.publication_export import export_publication_bundle
from eslams.runner import RunConfig, Runner


def generate() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with patch("eslams.artifacts.utc_now_iso", return_value="1970-01-01T00:00:00Z"):
            run = Runner().run(
                RunConfig(
                    arena_id="tic-tac-toe",
                    seed=23,
                    run_id="portable-byte-fixture",
                    output_dir=root / "runs",
                )
            )
        report = ArtifactValidator().validate_report(run.artifact_path)
        if not report.valid:
            raise ValueError(report.errors)
        manifest = json.loads((run.artifact_path / "manifest.json").read_text(encoding="utf-8"))
        schemas = root / "schemas"
        export_schemas(schemas)
        bundle = export_publication_bundle(
            kind="uploaded-replay",
            artifact=run.artifact_path,
            output_dir=root / "bundle",
        )
        hashes = {}
        for prefix, directory in (("schemas", schemas), ("publication", bundle)):
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    hashes[f"{prefix}/{path.relative_to(directory).as_posix()}"] = sha256_file(path)
        return {
            "artifact_id": report.artifact_id,
            "artifact_files": manifest["files"],
            "export_hashes": hashes,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.compare is not None:
        paths = sorted(args.compare.rglob("hashes.json"))
        if len(paths) != 5:
            raise ValueError(f"expected five native Python/OS hash manifests, got {len(paths)}")
        reference = paths[0].read_bytes()
        for path in paths[1:]:
            if path.read_bytes() != reference:
                raise ValueError(
                    f"native byte hashes differ: {paths[0].parent.name}, {path.parent.name}"
                )
        print("Five native environments produced identical artifact/schema/publication hashes")
    elif args.output is not None:
        payload = generate()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(canonical_json(payload) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote deterministic byte hashes: {args.output.name}")
    else:
        parser.error("provide --output or --compare")


if __name__ == "__main__":
    main()
