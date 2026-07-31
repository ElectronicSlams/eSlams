import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from eslams.contracts.json_schema import export_schemas

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_wheel_export_matches_source_without_git_checkout(tmp_path: Path):
    expected_commit = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source_export = tmp_path / "source-export"
    export_schemas(source_export)
    source_manifest = json.loads(
        (source_export / "schema_bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert source_manifest["core_commit"] == expected_commit

    dist_dir = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist_dir.glob("*.whl"))
    source_distribution = next(dist_dir.glob("*.tar.gz"))
    with tarfile.open(source_distribution, "r:gz") as archive:
        provenance_member = next(
            member
            for member in archive.getmembers()
            if member.name.endswith("/src/eslams/_build_provenance.py")
        )
        extracted = archive.extractfile(provenance_member)
        assert extracted is not None
        assert f'PACKAGED_CORE_COMMIT: str | None = "{expected_commit}"' in (
            extracted.read().decode("utf-8")
        )
    install_dir = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-compile",
            "--no-deps",
            "--target",
            str(install_dir),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    outside_checkout = tmp_path / "outside-checkout"
    outside_checkout.mkdir()
    first_export = tmp_path / "wheel-export-a"
    second_export = tmp_path / "wheel-export-b"
    script = """
import json
import sys
from importlib.metadata import version
from pathlib import Path

import eslams
from eslams._build_provenance import PACKAGED_CORE_COMMIT, core_source_commit
from eslams.contracts.json_schema import export_schemas

install_dir, first, second = map(Path, sys.argv[1:])
assert Path(eslams.__file__).resolve().is_relative_to(install_dir.resolve())
assert eslams.__version__ == version("eslams-core") == "0.6.1"
assert PACKAGED_CORE_COMMIT is not None
export_schemas(first)
export_schemas(second)
print(json.dumps({"commit": core_source_commit(), "module": eslams.__file__}))
"""
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(install_dir),
        }
    )
    installed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(install_dir),
            str(first_export),
            str(second_export),
        ],
        cwd=outside_checkout,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    installed_metadata = json.loads(installed.stdout)

    assert installed_metadata["commit"] == expected_commit
    assert str(install_dir) in installed_metadata["module"]

    source_files = {
        path.relative_to(source_export): path.read_bytes()
        for path in source_export.iterdir()
    }
    first_files = {
        path.relative_to(first_export): path.read_bytes()
        for path in first_export.iterdir()
    }
    second_files = {
        path.relative_to(second_export): path.read_bytes()
        for path in second_export.iterdir()
    }
    assert first_files == second_files == source_files
