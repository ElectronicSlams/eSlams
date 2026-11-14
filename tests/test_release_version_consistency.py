from __future__ import annotations

import re
import runpy
from pathlib import Path

from eslams import __version__
from eslams.contracts.versions import CORE_PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_package_and_sealed_publisher_versions_agree():
    match = re.search(r'^version = "([^"]+)"$',
                      (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__ == CORE_PACKAGE_VERSION == "0.8.1"
    verifier = runpy.run_path(str(ROOT / "scripts/verify_publish_bundle.py"))
    assert verifier["VERSION"] == CORE_PACKAGE_VERSION
    assert verifier["TAG"] == f"v{CORE_PACKAGE_VERSION}"
    assert verifier["BUNDLE_NAME"] == f"eslams-core-{CORE_PACKAGE_VERSION}-publish.zip"
    assert verifier["WHEEL"] == f"eslams_core-{CORE_PACKAGE_VERSION}-py3-none-any.whl"
    assert verifier["SDIST"] == f"eslams_core-{CORE_PACKAGE_VERSION}.tar.gz"


def test_publisher_is_bound_to_exact_new_tag_and_verified_bundle():
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    assert "github.ref == 'refs/tags/v0.8.1'" in workflow
    assert '[[ "$GITHUB_REF" == refs/tags/v0.8.1 ]]' in workflow
    assert '[[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]]' in workflow
    assert '--tag v0.8.1 --commit "$GITHUB_SHA" --remote-commit "$remote_commit"' in workflow
    assert '[[ "$status" == 404 ]]' in workflow
    assert "skip-existing: false" in workflow
    assert "persist-credentials: false" in workflow
    assert "refs/heads/main" not in workflow
    assert "433491656" not in workflow  # Retired 0.7.0 draft asset identity.
    assert "708125397" not in workflow
