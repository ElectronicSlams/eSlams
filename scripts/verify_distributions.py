"""Verify built distributions using isolated installs outside the checkout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path


def clean_environment() -> dict[str, str]:
    sensitive = (
        "SECRET",
        "TOKEN",
        "API_KEY",
        "ESLAMS",
        "SIGNING",
        "HF_",
        "CLOUDFLARE",
        "RUNNER_",
        "AWS_",
        "BEDROCK",
        "R2_",
        "D1_",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in sensitive)
        and key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def run(
    command: list[str],
    cwd: Path,
    *,
    expected: int = 0,
    source: Path | None = None,
) -> str:
    environment = clean_environment()
    if source is not None:
        environment["PYTHONPATH"] = str(source / "src")
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"{command[0]} failed with exit {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
    if expected and "Traceback" in result.stdout + result.stderr:
        raise RuntimeError("expected CLI error leaked a traceback")
    return result.stdout


def smoke(distribution: Path, root: Path, expected_commit: str) -> None:
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(environment)
    binaries = environment / ("Scripts" if os.name == "nt" else "bin")
    python = binaries / ("python.exe" if os.name == "nt" else "python")
    console = binaries / ("eslams.exe" if os.name == "nt" else "eslams")
    run([str(python), "-m", "pip", "install", str(distribution)], root)
    version = run([str(console), "--version"], root)
    assert version == run([str(python), "-m", "eslams.cli", "--version"], root)
    assert version == run([str(console), "-V"], root)
    error = run([str(console), "run", "--arena", "no-such-arena"], root, expected=2)
    assert "Traceback" not in error
    run([str(console), "run", "--agent", "no-such-agent"], root, expected=1)
    for entry in ([str(console)], [str(python), "-m", "eslams.cli"]):
        for debug in (False, True):
            diagnostic_environment = clean_environment()
            diagnostic_environment["ESLAMS_DEBUG"] = "1" if debug else "0"
            diagnostic = subprocess.run(
                [*entry, "validate", str(root / "missing.eslams")],
                cwd=root,
                env=diagnostic_environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            assert diagnostic.returncode == 1
            assert ("Traceback (most recent call last)" in diagnostic.stderr) is debug
            assert "missing.eslams" in diagnostic.stderr
        with subprocess.Popen(
            [*entry, "catalogue", "games", "--json"],
            cwd=root,
            env=clean_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ) as process:
            assert process.stdout is not None and process.stderr is not None
            assert process.stdout.readline()
            process.stdout.close()
            assert process.wait(timeout=30) == 0
            assert process.stderr.read() == ""
    typing_example = root / "consumer.py"
    typing_example.write_text(
        "from eslams.runner import RunConfig\n"
        'config = RunConfig(arena_id="tic-tac-toe")\n'
        "arena: str = config.arena_id\n",
        encoding="utf-8",
        newline="\n",
    )
    typing_command = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        "--no-incremental",
        "--python-executable",
        str(python),
        str(typing_example),
    ]
    run(typing_command, root)
    typing_example.write_text(
        "from eslams.runner import RunConfig\nconfig = RunConfig(arena_id=123)\n",
        encoding="utf-8",
        newline="\n",
    )
    typing_error = run(typing_command, root, expected=1)
    assert 'incompatible type "int"; expected "str"' in typing_error
    assert "import-untyped" not in typing_error
    source = run(
        [
            str(python),
            "-c",
            (
                "import json,eslams; from eslams._build_provenance import core_source_commit;"
                "print(json.dumps({'module':eslams.__file__,'commit':core_source_commit()}))"
            ),
        ],
        root,
    )
    identity = json.loads(source)
    assert Path(identity["module"]).resolve().is_relative_to(environment.resolve())
    assert identity["commit"] == expected_commit
    schemas = root / "schemas"
    run([str(console), "schemas", "export", "--out", str(schemas)], root)
    manifest = json.loads((schemas / "schema_bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["core_commit"] == expected_commit
    result = json.loads(
        run(
            [
                str(console),
                "run",
                "--arena",
                "tic-tac-toe",
                "--output-dir",
                str(root / "runs"),
            ],
            root,
        )
    )
    artifact = result["artifact"]
    run([str(console), "validate", artifact], root)
    replay = root / "replay.html"
    run([str(console), "replay", artifact, "--output", str(replay)], root)
    assert "Content validated. Signature: unsigned." in replay.read_text(encoding="utf-8")
    public = root / "public"
    run([str(console), "artifact", "public-export", artifact, "--out", str(public)], root)
    run([str(console), "validate", str(public), "--profile", "public-replay-package"], root)
    run([str(console), "core", "golden", "--out", str(root / "golden.json")], root)
    print(json.dumps({"distribution": distribution.name, "consumer_checks": "passed"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    arguments = parser.parse_args()
    distribution = arguments.dist.resolve()
    (wheel,) = distribution.glob("*.whl")
    (sdist,) = distribution.glob("*.tar.gz")
    with tempfile.TemporaryDirectory(prefix="eslams-consumer-") as temporary:
        root = Path(temporary)
        for name, package in (("wheel", wheel), ("sdist", sdist)):
            consumer = root / name
            consumer.mkdir()
            smoke(package, consumer, arguments.expected_commit)
        unpacked = root / "source"
        unpacked.mkdir()
        with tarfile.open(sdist) as archive:
            for member in archive.getmembers():
                path = unpacked / member.name
                if not path.resolve().is_relative_to(unpacked.resolve()) or not (
                    member.isfile() or member.isdir()
                ):
                    raise RuntimeError("unexpected source distribution member")
            for member in archive.getmembers():
                path = unpacked / member.name
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    stream = archive.extractfile(member)
                    assert stream is not None
                    with stream, path.open("wb") as output:
                        shutil.copyfileobj(stream, output, length=1024 * 1024)
        (source,) = unpacked.iterdir()
        # The host supplies dev tools, but imports must come from this sdist.
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(source / "tests"),
                "--basetemp",
                str(root / "pytest"),
            ],
            root,
            source=source,
        )
        print(json.dumps({"sdist_suite_without_git": "passed"}))


if __name__ == "__main__":
    main()
