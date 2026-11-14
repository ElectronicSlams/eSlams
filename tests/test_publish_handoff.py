"""Server-to-publisher integrity controls; synthetic files, no network or execution."""
import gzip
import io
import json
import runpy
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

V = runpy.run_path(str(Path(__file__).parents[1] / "scripts/verify_publish_bundle.py"))
COMMIT = "a" * 40


def archive_zip(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in files:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, contents)
    return data.getvalue()


def artifacts(*, version="0.8.1", commit=COMMIT):
    metadata = (f"Metadata-Version: 2.4\nName: eslams-core\nVersion: {version}\n"
                "Requires-Python: >=3.10\n\n")
    provenance = f'PACKAGED_CORE_COMMIT: str | None = "{commit}"\n'
    wheel = archive_zip([
        ("eslams_core-0.8.1.dist-info/METADATA", metadata),
        ("eslams/_build_provenance.py", provenance),
    ])
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:") as archive:
        for name, body in [("PKG-INFO", metadata),
                           ("src/eslams/_build_provenance.py", provenance)]:
            body = body.encode()
            entry = tarfile.TarInfo(f"eslams_core-0.8.1/{name}")
            entry.size = len(body)
            archive.addfile(entry, io.BytesIO(body))
    return {V["WHEEL"]: wheel, V["SDIST"]: gzip.compress(raw.getvalue(), mtime=0)}


def bundle(*, mutate=None, version="0.8.1", commit=COMMIT, extra=()):
    files = artifacts(version=version, commit=commit)
    manifest = {
        "schema_version": "eslams.pypi-handoff.v1", "project": "eslams-core",
        "version": "0.8.1", "tag": "v0.8.1", "source_commit": COMMIT,
        "verification": {"status": "passed", "receipt_sha256": "0" * 64},
        "artifacts": [{"filename": name, "sha256": V["digest"](data), "size": len(data)}
                      for name, data in files.items()],
    }
    if mutate:
        mutate(manifest)
    return archive_zip([(V["MANIFEST"], json.dumps(manifest)), *files.items(), *extra])


def verify(data):
    return V["verify_bundle"](data, expected_digest=V["digest"](data), commit=COMMIT)


def test_complete_hash_metadata_and_provenance_binding():
    assert verify(bundle()) == artifacts()


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(version="0.8.1rc1"),
    lambda m: m.update(source_commit="b" * 40),
    lambda m: m.update(tag="main"),
    lambda m: m.update(project="other-project"),
    lambda m: m.update(extra="unreviewed"),
    lambda m: m["verification"].update(status="not_run"),
    lambda m: m["verification"].update(receipt_sha256="bad"),
    lambda m: m["artifacts"][0].update(size=True),
    lambda m: m["artifacts"][0].update(sha256="f" * 64),
    lambda m: m["artifacts"][0].update(filename="../untrusted.whl"),
    lambda m: m["artifacts"].append(m["artifacts"][0]),
])
def test_manifest_corruption_fails_before_any_output(mutation):
    with pytest.raises(ValueError):
        verify(bundle(mutate=mutation))


@pytest.mark.parametrize("extra", [[("../escape", b"bad")], [("directory/", b"")],
                                    [(V["MANIFEST"], b"{}")]])
def test_extra_traversal_directory_duplicate_members_reject(extra):
    with pytest.raises(ValueError):
        verify(bundle(extra=extra))


def test_hash_and_source_identity_are_independent_fences():
    data = bundle()
    with pytest.raises(ValueError, match="hash mismatch"):
        V["verify_bundle"](data, expected_digest="f" * 64, commit=COMMIT)
    with pytest.raises(ValueError, match="provenance"):
        verify(bundle(commit="b" * 40))
    with pytest.raises(ValueError, match="metadata Version"):
        verify(bundle(version="0.8.1rc1"))


def test_symlink_member_never_becomes_a_filesystem_link():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        entry = zipfile.ZipInfo(V["MANIFEST"])
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "elsewhere")
        for name, body in artifacts().items():
            archive.writestr(name, body)
    with pytest.raises(ValueError, match="unsafe"):
        verify(data.getvalue())


def test_duplicate_nonfinite_json_and_expansion_limits(monkeypatch):
    with pytest.raises(ValueError, match="duplicate"):
        V["read_json"](b'{"version":"0.8.1","version":"evil"}')
    with pytest.raises(ValueError, match="non-finite"):
        V["read_json"](b'{"value":NaN}')
    monkeypatch.setitem(V["sdist_contents"].__globals__, "MAX_TAR_BYTES", 1024)
    with pytest.raises(ValueError, match="expanded byte limit"):
        verify(bundle())


def release():
    return {"id": 12, "tag_name": "v0.8.1", "draft": True, "prerelease": False,
            "url": "https://api.github.com/repos/ElectronicSlams/eSlams/releases/12",
            "assets": [{"id": 34, "name": V["BUNDLE_NAME"], "state": "uploaded", "size": 1000}]}


def validate(value, **overrides):
    kwargs = {"release_id": 12, "asset_id": 34, "tag": "v0.8.1", "commit": COMMIT,
              "remote_commit": COMMIT, **overrides}
    return V["validate_metadata"](value, **kwargs)


def test_release_asset_is_bound_to_reviewed_tag_repo_source_and_unpublished_draft():
    assert validate(release())["id"] == 34


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(draft=False), lambda r: r.update(prerelease=True),
    lambda r: r.update(tag_name="v0.6.2"), lambda r: r.update(id=13),
    lambda r: r.update(url="https://api.github.com/repos/attacker/other/releases/12"),
    lambda r: r["assets"][0].update(id=35),
    lambda r: r["assets"][0].update(name="unreviewed.zip"),
    lambda r: r["assets"][0].update(size=True),
    lambda r: r["assets"][0].update(size=6 * 1024 * 1024),
    lambda r: r["assets"][0].update(state="new"),
    lambda r: r["assets"].append(r["assets"][0]),
])
def test_asset_metadata_mismatch_rejects_before_download(mutation):
    value = release()
    mutation(value)
    with pytest.raises(ValueError):
        validate(value)


def test_moved_tag_and_wrong_dispatch_ref_reject():
    with pytest.raises(ValueError):
        validate(release(), remote_commit="b" * 40)
    with pytest.raises(ValueError):
        validate(release(), tag="main")


def server_receipt(files, required):
    return {"source_commit": COMMIT, "version": "0.8.1", "status": "passed",
            "steps": [{"name": name, "exit_code": 0} for name in sorted(required)],
            "pytest_counts": {"tests": 1253, "errors": 0, "failures": 0, "skipped": 0},
            "artifacts": [{"filename": name, "size": len(data), "sha256": V["digest"](data)}
                          for name, data in sorted(files.items())]}


@pytest.mark.parametrize("mutation", [
    None, lambda r: r.update(source_commit="b" * 40),
    lambda r: r.update(status="failed"), lambda r: r["steps"].pop(),
    lambda r: r["steps"][0].update(exit_code=1),
    lambda r: r["pytest_counts"].update(tests=0),
    lambda r: r["pytest_counts"].update(skipped=1),
    lambda r: r["pytest_counts"].update(errors=False),
    lambda r: r["artifacts"][0].update(sha256="f" * 64),
])
def test_server_seal_requires_all_checks_and_unchanged_artifacts(tmp_path, monkeypatch, mutation):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    builder = runpy.run_path(str(Path(__file__).parents[1] / "scripts/build_publish_bundle.py"))
    files = artifacts()
    dist = tmp_path / "dist"
    dist.mkdir()
    for name, data in files.items():
        (dist / name).write_bytes(data)
    receipt = server_receipt(files, builder["REQUIRED_CHECKS"])
    if mutation:
        mutation(receipt)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    if mutation:
        with pytest.raises(ValueError):
            builder["seal"](dist, receipt_path, COMMIT)
    else:
        sealed = builder["seal"](dist, receipt_path, COMMIT)
        assert verify(sealed) == files
