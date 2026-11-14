"""Verify a maintainer-sealed server build without executing package/build code.

Used only by the publisher job. GitHub CLI fetches authenticated release metadata
and bytes; this verifier has no network or credential access requirements.
"""
from __future__ import annotations

import argparse
import email.policy
import gzip
import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any

PROJECT = "eslams-core"
VERSION = "0.8.1"
TAG = "v0.8.1"
REPOSITORY = "ElectronicSlams/eSlams"
BUNDLE_NAME = "eslams-core-0.8.1-publish.zip"
WHEEL = "eslams_core-0.8.1-py3-none-any.whl"
SDIST = "eslams_core-0.8.1.tar.gz"
MANIFEST = "release-manifest.json"
MAX_BUNDLE_BYTES = 5 * 1024 * 1024
MAX_TAR_BYTES = 64 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def read_json(data: bytes) -> dict[str, Any]:
    result = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)
    require(isinstance(result, dict), "JSON object required")
    return result


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_metadata(
    release: dict[str, Any], *, release_id: int, asset_id: int,
    tag: str, commit: str, remote_commit: str,
) -> dict[str, Any]:
    require(tag == TAG, "unexpected release tag")
    require(COMMIT.fullmatch(commit) is not None and remote_commit == commit,
            "tag/source commit mismatch")
    require(type(release_id) is int and release_id > 0
            and type(asset_id) is int and asset_id > 0, "invalid release/asset id")
    require(type(release.get("id")) is int and release.get("id") == release_id
            and release.get("tag_name") == TAG,
            "release identity mismatch")
    require(release.get("url") ==
            f"https://api.github.com/repos/{REPOSITORY}/releases/{release_id}",
            "release repository mismatch")
    require(release.get("draft") is True and release.get("prerelease") is False,
            "expected unpublished stable-release draft")
    assets = release.get("assets")
    require(isinstance(assets, list), "release assets missing")
    matches = [row for row in assets if isinstance(row, dict) and row.get("id") == asset_id]
    require(len(matches) == 1, "asset does not belong uniquely to release")
    asset = matches[0]
    require(asset.get("name") == BUNDLE_NAME and asset.get("state") == "uploaded",
            "unexpected asset name/state")
    size = asset.get("size")
    require(type(size) is int and 0 < size <= MAX_BUNDLE_BYTES, "asset byte limit")
    return asset


def package_metadata(data: bytes) -> None:
    require(len(data) <= 1024 * 1024, "package metadata byte limit")
    metadata = BytesParser(policy=email.policy.default).parsebytes(data)
    for key, expected in (("Name", PROJECT), ("Version", VERSION), ("Requires-Python", ">=3.10")):
        values = metadata.get_all(key, [])
        require(len(values) == 1 and str(values[0]) == expected,
                f"unexpected package metadata {key}")


def provenance(data: bytes, commit: str) -> None:
    require(len(data) <= 64 * 1024, "provenance byte limit")
    matches = re.findall(rb'^PACKAGED_CORE_COMMIT: str \| None = "([0-9a-f]{40})"$',
                         data, flags=re.MULTILINE)
    require(matches == [commit.encode("ascii")], "embedded source provenance mismatch")


def wheel_contents(data: bytes, commit: str) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate wheel members")
        for name, limit in ((f"eslams_core-{VERSION}.dist-info/METADATA", 1024 * 1024),
                            ("eslams/_build_provenance.py", 64 * 1024)):
            member = archive.getinfo(name)
            require(member.file_size <= limit and not member.is_dir(), "wheel member byte limit")
        package_metadata(archive.read(f"eslams_core-{VERSION}.dist-info/METADATA"))
        provenance(archive.read("eslams/_build_provenance.py"), commit)


def sdist_contents(data: bytes, commit: str) -> None:
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        unpacked = compressed.read(MAX_TAR_BYTES + 1)
    require(len(unpacked) <= MAX_TAR_BYTES, "sdist expanded byte limit")
    with tarfile.open(fileobj=io.BytesIO(unpacked), mode="r:") as archive:
        members = archive.getmembers()
        require(len(members) <= 4000 and len({m.name for m in members}) == len(members),
                "duplicate/excessive sdist members")
        contents = []
        for suffix, limit in (("PKG-INFO", 1024 * 1024),
                              ("src/eslams/_build_provenance.py", 64 * 1024)):
            member = archive.getmember(f"eslams_core-{VERSION}/{suffix}")
            require(member.isfile() and member.size <= limit, "sdist member type/byte limit")
            stream = archive.extractfile(member)
            require(stream is not None, "sdist member missing")
            assert stream is not None
            contents.append(stream.read(limit + 1))
        package_metadata(contents[0])
        provenance(contents[1], commit)


def verify_bundle(data: bytes, *, expected_digest: str, commit: str) -> dict[str, bytes]:
    require(SHA.fullmatch(expected_digest) is not None, "invalid bundle digest")
    require(COMMIT.fullmatch(commit) is not None, "invalid source commit")
    require(0 < len(data) <= MAX_BUNDLE_BYTES and digest(data) == expected_digest,
            "bundle byte/hash mismatch")
    expected = {MANIFEST, WHEEL, SDIST}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        require(len(members) == 3 and {m.filename for m in members} == expected,
                "unexpected/duplicate bundle members")
        for member in members:
            mode = member.external_attr >> 16
            require(not member.is_dir() and not stat.S_ISLNK(mode)
                    and not member.flag_bits & 1, "unsafe bundle member")
            require(0 <= member.file_size <= MAX_BUNDLE_BYTES, "bundle member byte limit")
        require(sum(m.file_size for m in members) <= MAX_BUNDLE_BYTES,
                "expanded bundle byte limit")
        contents = {name: archive.read(name) for name in expected}
    require(len(contents[MANIFEST]) <= 64 * 1024, "manifest byte limit")
    manifest = read_json(contents[MANIFEST])
    require(set(manifest) == {"schema_version", "project", "version", "tag", "source_commit",
                              "verification", "artifacts"}, "manifest fields")
    require(manifest["schema_version"] == "eslams.pypi-handoff.v1"
            and manifest["project"] == PROJECT and manifest["version"] == VERSION
            and manifest["tag"] == TAG and manifest["source_commit"] == commit,
            "manifest identity mismatch")
    verification = manifest["verification"]
    require(isinstance(verification, dict)
            and set(verification) == {"status", "receipt_sha256"}
            and verification["status"] == "passed"
            and isinstance(verification["receipt_sha256"], str)
            and SHA.fullmatch(verification["receipt_sha256"]) is not None,
            "verification receipt missing")
    artifacts = manifest["artifacts"]
    require(isinstance(artifacts, list) and len(artifacts) == 2, "artifact list")
    seen: set[str] = set()
    for row in artifacts:
        require(isinstance(row, dict) and set(row) == {"filename", "sha256", "size"},
                "artifact fields")
        name = row["filename"]
        require(isinstance(name, str) and name in {WHEEL, SDIST} and name not in seen,
                "unexpected/duplicate artifact")
        seen.add(name)
        require(type(row["size"]) is int and row["size"] == len(contents[name])
                and row["sha256"] == digest(contents[name]), "artifact byte/hash mismatch")
    wheel_contents(contents[WHEEL], commit)
    sdist_contents(contents[SDIST], commit)
    return {name: contents[name] for name in (WHEEL, SDIST)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-id", type=int, required=True)
    parser.add_argument("--asset-id", type=int, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--remote-commit", required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    require(args.release_json.stat().st_size <= 1024 * 1024, "release metadata byte limit")
    asset = validate_metadata(read_json(args.release_json.read_bytes()),
                              release_id=args.release_id, asset_id=args.asset_id,
                              tag=args.tag, commit=args.commit, remote_commit=args.remote_commit)
    if args.bundle is None:
        require(args.out is None and args.bundle_sha256 is None, "incomplete bundle arguments")
        print("Release and asset metadata verified; no package downloaded or executed")
        return
    require(args.out is not None and args.bundle_sha256 is not None, "bundle output required")
    require(args.bundle.stat().st_size == asset["size"], "download/asset size mismatch")
    require(args.bundle.stat().st_size <= MAX_BUNDLE_BYTES, "download byte limit")
    artifacts = verify_bundle(args.bundle.read_bytes(),
                              expected_digest=args.bundle_sha256, commit=args.commit)
    assert args.out is not None
    args.out.mkdir(parents=True, exist_ok=False)
    for name, data in artifacts.items():
        (args.out / name).write_bytes(data)
    print(json.dumps({"source_commit": args.commit, "version": VERSION,
                      "verified_artifacts": {
                          name: digest(data) for name, data in artifacts.items()
                      }}))


if __name__ == "__main__":
    main()
