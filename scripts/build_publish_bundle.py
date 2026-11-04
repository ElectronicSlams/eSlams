"""Seal already verified server artifacts for the isolated trusted publisher."""
from __future__ import annotations

import argparse
import io
import json
import stat
import subprocess
import zipfile
from pathlib import Path

from verify_publish_bundle import (
    BUNDLE_NAME,
    MANIFEST,
    PROJECT,
    SDIST,
    TAG,
    VERSION,
    WHEEL,
    digest,
    read_json,
    require,
    verify_bundle,
)

REQUIRED_CHECKS = {
    "ruff", "mypy", "typescript-contracts", "typescript-lite", "pytest", "arena-versions",
    "portable-bytes", "build", "twine", "distribution-consumers",
}


def seal(dist: Path, receipt_path: Path, commit: str) -> bytes:
    receipt_bytes = receipt_path.read_bytes()
    require(len(receipt_bytes) <= 128 * 1024, "verification receipt byte limit")
    receipt = read_json(receipt_bytes)
    require(receipt.get("status") == "passed" and receipt.get("source_commit") == commit
            and receipt.get("version") == VERSION, "server verification identity/status")
    steps = receipt.get("steps")
    require(isinstance(steps, list) and len(steps) == len(REQUIRED_CHECKS), "required check count")
    require(all(isinstance(row, dict) and type(row.get("exit_code")) is int
                and row["exit_code"] == 0 for row in steps), "server check failed")
    require({row.get("name") for row in steps} == REQUIRED_CHECKS, "missing server check")
    counts = receipt.get("pytest_counts")
    require(isinstance(counts, dict) and type(counts.get("tests")) is int
            and counts["tests"] > 0 and all(type(counts.get(key)) is int and counts[key] == 0
                                           for key in ("errors", "failures", "skipped")),
            "server pytest acceptance missing")
    require({p.name for p in dist.iterdir()} == {WHEEL, SDIST}, "unexpected distribution files")
    require(all((dist / name).is_file() and not (dist / name).is_symlink()
                for name in (WHEEL, SDIST)), "distribution must be a regular file")
    files = {name: (dist / name).read_bytes() for name in (WHEEL, SDIST)}
    rows = [{"filename": name, "size": len(data), "sha256": digest(data)}
            for name, data in sorted(files.items())]
    require(receipt.get("artifacts") == rows, "artifacts changed after verification")
    manifest = {"schema_version": "eslams.pypi-handoff.v1", "project": PROJECT,
                "version": VERSION, "tag": TAG, "source_commit": commit,
                "verification": {"status": "passed", "receipt_sha256": digest(receipt_bytes)},
                "artifacts": rows}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entries = {MANIFEST: (json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                              + "\n").encode(), **files}
        for name, data in sorted(entries.items()):
            member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o444) << 16
            archive.writestr(member, data)
    data = output.getvalue()
    verify_bundle(data, expected_digest=digest(data), commit=commit)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=root,
                                        text=True).strip(), "source changed after verification")
    require(args.out.name == BUNDLE_NAME, "unexpected bundle filename")
    data = seal(args.dist, args.receipt, commit)
    with args.out.open("xb") as output:
        output.write(data)
    print(json.dumps({"source_commit": commit, "version": VERSION,
                      "bundle": args.out.name, "sha256": digest(data), "size": len(data)}))


if __name__ == "__main__":
    main()
