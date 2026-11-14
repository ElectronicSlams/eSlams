"""Finite keyless release checks on a dedicated server workspace, not a publisher."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tsc", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(out).free < 5 * 1024**3:
        raise RuntimeError("release workspace disk guard")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise RuntimeError("release source must be clean")
    guard = out / "guards"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys,json,os\n"
        "def guard(event,args):\n"
        " if event in {'socket.bind','socket.connect','socket.getaddrinfo'}:\n"
        "  with open(os.environ['CORE_NETWORK_ATTEMPT_LOG'],'a') as f:\n"
        "   f.write(json.dumps({'event':event,'blocked_before_OS_operation':True})+'\\n')\n"
        "  raise AssertionError('No network/listeners in keyless release checks')\n"
        "sys.addaudithook(guard)\n"
    )
    (guard / "release_offline.py").write_text(
        "import subprocess,pytest\n"
        "@pytest.fixture(autouse=True)\n"
        "def offline(request,monkeypatch):\n"
        " if request.node.name.startswith(('test_cli_summary_prints_no_winner_for_invalid_run',"
        "'test_cli_fallback_failing_seat_board_win_is_only_a_board_result')):\n"
        "  from eslams.agents import HttpAgent\n"
        "  def failed(*args,**kwargs):raise ConnectionError('synthetic offline refusal')\n"
        "  monkeypatch.setattr(HttpAgent,'act',failed)\n"
        " if request.node.name=='test_wheel_export_matches_source_without_git_checkout':\n"
        "  original=subprocess.run\n"
        "  def run(args,*pos,**kwargs):\n"
        "   if isinstance(args,list) and args[1:3]==['-m','build']:\n"
        "    args=[*args[:3],'--no-isolation',*args[3:]]\n"
        "   return original(args,*pos,**kwargs)\n"
        "  monkeypatch.setattr(subprocess,'run',run)\n"
    )
    sensitive = ("SECRET", "TOKEN", "API_KEY", "SIGNING", "CLOUDFLARE", "AWS_",
                 "BEDROCK", "ESLAMS", "RUNNER_", "R2_", "D1_", "HF_")
    env = {key: value for key, value in os.environ.items()
           if not any(part in key.upper() for part in sensitive)
           and key not in {"PYTHONPATH", "PYTHONHOME", "SSH_AUTH_SOCK"}}
    env.update(PYTHONPATH=os.pathsep.join(map(str, [guard, root / "src"])),
               PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               CORE_NETWORK_ATTEMPT_LOG=str(out / "NETWORK_ATTEMPTS.log"))
    python = sys.executable
    node = shutil.which("node")
    if node is None or not args.tsc.is_file():
        raise RuntimeError("provide reviewed Node/TypeScript build tools")
    steps = [
        ("ruff", [python, "-m", "ruff", "check", "."], 60),
        ("mypy", [python, "-m", "mypy", "--cache-dir", str(out / "mypy-cache"), "src"], 180),
        ("typescript-contracts", [node, str(args.tsc), "--project",
                                  "packages/core-contracts/tsconfig.json"], 60),
        ("typescript-lite", [node, str(args.tsc), "--project",
                             "packages/core-lite/tsconfig.json"], 60),
        ("pytest", [python, "-m", "pytest", "-q", "-o", "addopts=", "-p", "release_offline",
                    "tests", "--ignore=tests/test_elapsed_deadline_regressions.py",
                    f"--junitxml={out}/pytest.xml", f"--basetemp={out}/test-temp"], 300),
        ("arena-versions", [python, "scripts/verify_arena_versions.py"], 90),
        ("portable-bytes", [python, "scripts/verify_portable_bytes.py", "--output",
                            str(out / "portable-bytes.json")], 90),
        ("build", [python, "-m", "build", "--no-isolation", "--outdir", str(out / "dist")], 90),
    ]
    receipt: dict[str, object] = {"source_commit": commit, "version": "0.8.1",
        "platform": platform.platform(), "python": sys.version,
        "steps": [], "status": "in_progress",
        "excluded": "previously denied elapsed-deadline listener fixtures not opened or retried"}
    for name, command, limit in steps:
        start = time.monotonic()
        with (out / f"{name}.log").open("w") as stream:
            try:
                result = subprocess.run(command, cwd=root, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=limit)
                code: int | None = result.returncode
            except subprocess.TimeoutExpired:
                code = None
        row = {"name": name, "argv": command, "exit_code": code,
               "seconds": round(time.monotonic() - start, 3)}
        assert isinstance(receipt["steps"], list)
        receipt["steps"].append(row)
        receipt["status"] = "failed" if code != 0 else "in_progress"
        (out / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if code != 0:
            raise SystemExit(f"release check failed: {name}; inspect its retained log")
    suites = ElementTree.parse(out / "pytest.xml").getroot()
    receipt["pytest_counts"] = {
        key: sum(int(suite.get(key, "0")) for suite in suites.iter("testsuite"))
        for key in ("tests", "errors", "failures", "skipped")
    }
    # Downloads/installing declared dependencies for isolated consumers is allowed.
    # The consumer script clears source paths and sensitive environment variables.
    consumer_env = dict(env)
    consumer_env.pop("PIP_NO_INDEX", None)
    consumer_env.pop("PYTHONPATH", None)
    for name, command in [
        ("twine", [python, "-m", "twine", "check", *map(str, sorted((out / "dist").iterdir()))]),
        ("distribution-consumers", [python, "scripts/verify_distributions.py", "--dist",
                                    str(out / "dist"), "--expected-commit", commit,
                                    "--offline-suite-guard", str(guard)]),
    ]:
        start = time.monotonic()
        with (out / f"{name}.log").open("w") as stream:
            try:
                result = subprocess.run(command, cwd=root, env=consumer_env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=300)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = None
        row = {"name": name, "argv": command, "exit_code": code,
               "seconds": round(time.monotonic() - start, 3)}
        assert isinstance(receipt["steps"], list)
        receipt["steps"].append(row)
        (out / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if code != 0:
            receipt["status"] = "failed"
            (out / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
            raise SystemExit(f"release check failed: {name}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise RuntimeError("source changed during release checks")
    receipt["source_tree"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip()
    receipt["artifacts"] = [{"filename": p.name, "size": p.stat().st_size,
                              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                             for p in sorted((out / "dist").iterdir())]
    receipt["status"] = "passed"
    (out / "RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("All admitted server checks passed; no publication attempted", flush=True)


if __name__ == "__main__":
    main()
