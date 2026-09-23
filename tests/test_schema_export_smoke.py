"""Offline smoke for the documented schema export command.

CI (`.github/workflows/ci.yml`) and the README both invoke:

    eslams schemas export --out <directory>

This test runs that same argv into a temp directory and checks that the
manifest and schema files exist and parse. It does not call Hugging Face,
R2, or D1, and planted network credentials must not appear in the export.
"""

import json
import socket
import subprocess
from pathlib import Path

from eslams.cli import main
from eslams.contracts.json_schema import SCHEMA_BUNDLE_MANIFEST_FILENAME
from eslams.contracts.versions import (
    ACTION_PROVENANCE_SCHEMA_VERSION,
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    CATALOGUE_RENDERER_SCHEMA_VERSION,
    CORE_PACKAGE_VERSION,
    PRICE_CARD_REFERENCE_SCHEMA_VERSION,
    PROVIDER_ATTEMPT_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
    REPLAY_DISPLAY_FRAME_SCHEMA_VERSION,
    RUN_INTEGRITY_SCHEMA_VERSION,
    SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION,
    SCHEMA_BUNDLE_VERSION,
    USAGE_SUMMARY_SCHEMA_VERSION,
    schema_versions,
)
from eslams.hashing import sha256_file

# Public contract names called out in docs/PLATFORM_CONTRACTS.md and README.md.
_DOCUMENTED_SCHEMA_VERSIONS = (
    ARTIFACT_VALIDATION_SCHEMA_VERSION,
    RUN_INTEGRITY_SCHEMA_VERSION,
    PROVIDER_ATTEMPT_SCHEMA_VERSION,
    ACTION_PROVENANCE_SCHEMA_VERSION,
    USAGE_SUMMARY_SCHEMA_VERSION,
    PROVIDER_RECEIPT_SCHEMA_VERSION,
    PRICE_CARD_REFERENCE_SCHEMA_VERSION,
    CATALOGUE_RENDERER_SCHEMA_VERSION,
    REPLAY_DISPLAY_FRAME_SCHEMA_VERSION,
)

# Sentinels stand in for credentials the export must ignore.
_SECRET_ENV = {
    "HF_TOKEN": "hf_schema_export_smoke_sentinel",
    "HUGGING_FACE_HUB_TOKEN": "hfhub_schema_export_smoke_sentinel",
    "R2_ACCESS_KEY_ID": "r2_schema_export_smoke_sentinel",
    "R2_SECRET_ACCESS_KEY": "r2secret_schema_export_smoke_sentinel",
    "CLOUDFLARE_API_TOKEN": "cf_schema_export_smoke_sentinel",
    "CLOUDFLARE_ACCOUNT_ID": "cfacct_schema_export_smoke_sentinel",
    "D1_DATABASE_ID": "d1_schema_export_smoke_sentinel",
    "OPENAI_API_KEY": "sk-schema-export-smoke-sentinel",
    "ANTHROPIC_API_KEY": "sk-ant-schema-export-smoke-sentinel",
    "GEMINI_API_KEY": "gemini_schema_export_smoke_sentinel",
}


def test_schema_export_smoke_writes_parseable_json_offline(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    for name, value in _SECRET_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    monkeypatch.setattr(socket, "create_connection", _refuse_network)

    output_dir = tmp_path / "schemas"
    assert main(["schemas", "export", "--out", str(output_dir)]) == 0
    first = _assert_export(output_dir, capsys.readouterr().out)

    repeat_dir = tmp_path / "schemas-repeat"
    assert main(["schemas", "export", "--out", str(repeat_dir)]) == 0
    capsys.readouterr()
    repeat = _exported_bytes(repeat_dir)
    assert repeat == first


def _assert_export(output_dir: Path, stdout: str) -> dict[str, bytes]:
    reported = json.loads(stdout)
    written = [Path(item) for item in reported["schemas"]]
    assert written
    assert {path.resolve().parent for path in written} == {output_dir.resolve()}
    assert all(path.is_file() for path in written)

    assert not any(path.is_dir() for path in output_dir.iterdir())
    files = _exported_bytes(output_dir)
    assert sorted(files) == sorted(path.name for path in written)
    assert SCHEMA_BUNDLE_MANIFEST_FILENAME in files
    assert all(name.endswith(".json") for name in files)

    manifest = json.loads(files[SCHEMA_BUNDLE_MANIFEST_FILENAME])
    assert manifest["schema_version"] == SCHEMA_BUNDLE_MANIFEST_SCHEMA_VERSION
    assert manifest["core_package_version"] == CORE_PACKAGE_VERSION
    assert manifest["schema_bundle_version"] == SCHEMA_BUNDLE_VERSION
    assert manifest["generated_at"] == "1970-01-01T00:00:00Z"
    assert manifest["core_commit"] == _head_commit()
    assert _is_sha256(manifest["deterministic_build_id"])

    rows = manifest["schemas"]
    expected_versions = set(schema_versions())
    assert isinstance(rows, list)
    assert len(rows) == len(expected_versions)
    assert {row["schema_version"] for row in rows} == expected_versions
    assert [row["name"] for row in rows] == sorted(row["name"] for row in rows)

    seen_versions = set()
    for row in rows:
        name = row["name"]
        version = row["schema_version"]
        assert name == f"{version}.schema.json"
        assert name in files
        payload = json.loads(files[name])
        assert isinstance(payload, dict)
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["title"] == version
        assert payload["type"] == "object"
        path = output_dir / name
        assert row["sha256"] == sha256_file(path)
        assert _is_sha256(row["sha256"])
        assert row["bytes"] == path.stat().st_size == len(files[name])
        seen_versions.add(version)

    assert set(_DOCUMENTED_SCHEMA_VERSIONS) <= seen_versions

    blob = b"\n".join(files.values())
    for sentinel in _SECRET_ENV.values():
        assert sentinel.encode() not in blob
    return files


def _exported_bytes(output_dir: Path) -> dict[str, bytes]:
    paths = sorted(path for path in output_dir.iterdir() if path.is_file())
    assert paths
    assert all(path.parent == output_dir for path in paths)
    return {path.name: path.read_bytes() for path in paths}


def _head_commit() -> str:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _refuse_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("schema export smoke must not open a network connection")
