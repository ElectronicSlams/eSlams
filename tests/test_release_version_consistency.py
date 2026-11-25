from __future__ import annotations

import re
import runpy
from pathlib import Path

from eslams import __version__
from eslams.contracts.versions import CORE_PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_and_legacy_sealed_publisher_are_independent():
    match = re.search(r'^version = "([^"]+)"$',
                      (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__ == CORE_PACKAGE_VERSION == "0.9.1"
    verifier = runpy.run_path(str(ROOT / "scripts/verify_publish_bundle.py"))
    assert verifier["VERSION"] == "0.9.0"
    assert verifier["TAG"] == "v0.9.0"
    assert verifier["BUNDLE_NAME"] == "eslams-core-0.9.0-publish.zip"
    assert verifier["WHEEL"] == "eslams_core-0.9.0-py3-none-any.whl"
    assert verifier["SDIST"] == "eslams_core-0.9.0.tar.gz"


def test_legacy_publisher_is_bound_to_090_only():
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    assert "github.ref == 'refs/tags/v0.9.0'" in workflow
    assert '[[ "$GITHUB_REF" == refs/tags/v0.9.0 ]]' in workflow
    assert '[[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]]' in workflow
    assert '--tag v0.9.0 --commit "$GITHUB_SHA" --remote-commit "$remote_commit"' in workflow
    assert '[[ "$status" == 404 ]]' in workflow
    assert "skip-existing: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "refs/heads/main" not in workflow
    assert "v0.9.1" not in workflow
    assert "433491656" not in workflow  # Retired 0.7.0 draft asset identity.
    assert "708125397" not in workflow


def test_generated_core_lite_versions_match_python_authority():
    generator = runpy.run_path(str(ROOT / "scripts/generate_core_lite_versions.py"))
    assert generator["TARGET"].read_text(encoding="utf-8") == generator["generated_typescript"]()
    import json
    for package in ("core-lite", "core-contracts"):
        metadata = json.loads((ROOT / "packages" / package / "package.json").read_text())
        assert metadata["version"] == CORE_PACKAGE_VERSION
        if package == "core-lite":
            assert metadata["dependencies"]["@eslams/core-contracts"] == CORE_PACKAGE_VERSION
