#!/usr/bin/env python3
"""Run the keyless lab-smoke suite.

Local Artifact is not Official or Grand Slam. This runner only allows the
builtin agents ``random`` and ``first-legal``. It never calls a provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

SUITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUITE_DIR.parents[1]
ALLOWED_AGENTS = frozenset({"random", "first-legal"})
ALLOWED_ARENAS = frozenset({"tic-tac-toe", "connect-four", "othello", "chess"})
CASE_KEYS = ("id", "arena", "agent", "opponent", "seed", "execution_profile")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run keyless lab-smoke cases.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print eslams commands without running them.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "runs" / "lab-smoke",
        help="Directory for .eslams archives (default: runs/lab-smoke).",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Run only this case id. Repeat to select several.",
    )
    args = parser.parse_args(argv)

    try:
        from eslams.contracts.versions import CORE_PACKAGE_VERSION
    except ImportError:
        print(
            "eslams-core is not installed. From a venv: pip install eslams-core==0.6.1",
            file=sys.stderr,
        )
        return 1

    manifest = _load_yaml(SUITE_DIR / "manifest.yaml")
    suite_cases = _load_cases(manifest)
    pin = str(manifest["core_pin"])
    if pin != CORE_PACKAGE_VERSION:
        print(
            f"installed eslams-core {CORE_PACKAGE_VERSION} does not match suite pin {pin}",
            file=sys.stderr,
        )
        return 1
    selected = set(args.case)
    cases = suite_cases
    if selected:
        known = {str(case["id"]) for case in suite_cases}
        missing = sorted(selected - known)
        if missing:
            print(f"unknown case id(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        cases = [case for case in suite_cases if str(case["id"]) in selected]

    fingerprint = _fingerprint(suite_cases)
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    print(
        f"lab-smoke pin={pin} cases={len(cases)} "
        f"verification={manifest['verification_level']} profile=smoke"
    )
    print("Local Artifact != Official / Grand Slam. No provider keys are used.")
    failures = 0
    for case in cases:
        command = _run_command(
            case,
            manifest=manifest,
            fingerprint=fingerprint,
            output_dir=output_dir,
        )
        print("$ " + shlex.join(command), flush=True)
        if args.dry_run:
            continue
        outcome = _run_case(command, case)
        if outcome != 0:
            failures += 1
    if failures:
        print(f"lab-smoke failed: {failures} case(s)", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"dry-run ok: {len(cases)} case(s)")
    else:
        print(f"lab-smoke ok: {len(cases)} Local Artifact case(s)")
    return 0


def _load_cases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    package = manifest.get("package")
    profile = manifest.get("execution_profile")
    level = manifest.get("verification_level")
    if package != "eslams-core":
        raise SystemExit(f"manifest package must be eslams-core, found {package!r}")
    if profile != "smoke":
        raise SystemExit(f"manifest execution_profile must be smoke, found {profile!r}")
    if level != "Local Artifact":
        raise SystemExit(f"manifest verification_level must be Local Artifact, found {level!r}")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SystemExit("manifest cases must be a non-empty list")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in raw_cases:
        path = SUITE_DIR / str(rel)
        case = _load_yaml(path)
        for key in CASE_KEYS:
            if key not in case:
                raise SystemExit(f"{path.name} missing {key}")
        case_id = str(case["id"])
        if case_id in seen:
            raise SystemExit(f"duplicate case id {case_id}")
        seen.add(case_id)
        if str(case["arena"]) not in ALLOWED_ARENAS:
            raise SystemExit(f"{case_id} arena is outside lab-smoke: {case['arena']}")
        if str(case["agent"]) not in ALLOWED_AGENTS or str(case["opponent"]) not in ALLOWED_AGENTS:
            raise SystemExit(
                f"{case_id} must use random or first-legal only "
                "(provider agents are not part of keyless lab-smoke)"
            )
        if case["execution_profile"] != "smoke":
            raise SystemExit(f"{case_id} execution_profile must be smoke")
        if not isinstance(case["seed"], int):
            raise SystemExit(f"{case_id} seed must be an integer")
        if "max_turns" in case and not isinstance(case["max_turns"], int):
            raise SystemExit(f"{case_id} max_turns must be an integer")
        cases.append(case)
    if not 8 <= len(cases) <= 12:
        raise SystemExit(f"lab-smoke expects 8-12 cases, found {len(cases)}")
    return cases


def _run_command(
    case: dict[str, Any],
    *,
    manifest: dict[str, Any],
    fingerprint: str,
    output_dir: Path,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "eslams.cli",
        "run",
        "--arena",
        str(case["arena"]),
        "--agent",
        str(case["agent"]),
        "--opponent",
        str(case["opponent"]),
        "--seed",
        str(case["seed"]),
        "--execution-profile",
        "smoke",
        "--verification-level",
        str(manifest["verification_level"]),
        "--on-agent-error",
        "invalid-match",
        "--on-illegal-action",
        "invalid-match",
        "--eval-suite-version",
        str(manifest["eval_suite_version"]),
        "--suite-id",
        str(manifest["id"]),
        "--case-id",
        str(case["id"]),
        "--suite-fingerprint",
        fingerprint,
        "--output-dir",
        str(output_dir),
    ]
    if "max_turns" in case:
        command.extend(["--max-turns", str(case["max_turns"])])
    return command


def _run_case(command: list[str], case: dict[str, Any]) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        sys.stderr.write(completed.stdout)
        print(f"FAIL {case['id']}: eslams run exited {completed.returncode}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(completed.stdout)
        print(f"FAIL {case['id']}: eslams run did not return JSON", file=sys.stderr)
        return 1
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if not isinstance(summary, dict) or summary.get("match_valid_for_scoring") is not True:
        print(f"FAIL {case['id']}: match was not valid for scoring: {summary}", file=sys.stderr)
        return 1
    expanded = Path(str(payload.get("expanded_artifact", "")))
    manifest_path = expanded / "manifest.json"
    if not manifest_path.is_file():
        print(f"FAIL {case['id']}: missing {manifest_path}", file=sys.stderr)
        return 1
    artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if artifact_manifest.get("verification_level") != "Local Artifact":
        print(
            f"FAIL {case['id']}: verification_level="
            f"{artifact_manifest.get('verification_level')!r}",
            file=sys.stderr,
        )
        return 1
    run_metadata = artifact_manifest.get("run_metadata")
    if not isinstance(run_metadata, dict) or run_metadata.get("execution_profile") != "smoke":
        print(f"FAIL {case['id']}: execution_profile was not smoke", file=sys.stderr)
        return 1
    if run_metadata.get("case_id") != case["id"] or run_metadata.get("suite_id") != "lab-smoke":
        print(f"FAIL {case['id']}: suite case_id was not recorded", file=sys.stderr)
        return 1
    artifact = str(payload["artifact"])
    validate = subprocess.run(
        [
            sys.executable,
            "-m",
            "eslams.cli",
            "validate",
            artifact,
            "--profile",
            "runner-bundle",
            "--summary-json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if validate.returncode != 0:
        sys.stderr.write(validate.stderr)
        sys.stderr.write(validate.stdout)
        print(f"FAIL {case['id']}: validate exited {validate.returncode}", file=sys.stderr)
        return 1
    print(f"ok {case['id']} -> {artifact}")
    return 0


def _fingerprint(cases: list[dict[str, Any]]) -> str:
    body = "\n".join(str(case["id"]) for case in cases).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"missing suite file: {path}")
    data: dict[str, Any] = {}
    list_key: str | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- "):
            if list_key is None:
                raise SystemExit(f"{path}:{line_number}: list item without a key")
            data[list_key].append(_scalar(line.split("- ", 1)[1].strip()))
            continue
        if ":" not in line:
            raise SystemExit(f"{path}:{line_number}: expected key: value")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            list_key = key
            continue
        list_key = None
        data[key] = _scalar(value)
    return data


def _scalar(value: str) -> Any:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    if value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
