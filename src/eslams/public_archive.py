"""Local checks for the public-archive plan.

The A-EX checker reads a candidate list the operator already has. It does not
contact R2, D1, Hugging Face, or the network. The lab-pack constants describe
the archives in this git checkout. They are not a live Hub dataset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

A_EX_CAP = 50
MAX_TTT_TIMEOUT = 1
READY_MAX_PER_ARENA = 15
READY_MIN_ARENAS = 3
MAX_CANDIDATE_ROWS = 200
MAX_CANDIDATE_BYTES = 256 * 1024

LAB_PACK_RELATIVE_PATHS: tuple[str, ...] = (
    "sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams",
    "sample_runs/model_eval_sample/official_signed.eslams",
)
PHANTOM_SAMPLE_ID = "run_d48ff364a0b949df"
HF_ORG_SLUG = "ElectronicSlams"
HF_LAB_DATASET_ID = "ElectronicSlams/eslams-sample-runs"
HF_ORG_LIVE = False
HF_ORG_CHECKED_ON = "2026-09-23"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+/-]{0,127}$")
_TTT_ARENAS = frozenset({"arena_tic_tac_toe", "tic-tac-toe", "tic_tac_toe"})
_OUTCOMES = frozenset({"partial", "failed"})
_BANNED_KEY_PARTS = ("secret", "token", "password", "authorization", "credential")
_SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "credential",
    "private-key",
    "private_key",
    "x-amz-",
    "presign",
    "signed-url",
)


@dataclass(frozen=True)
class AExIssue:
    """One reason a candidate list is not an acceptable A-EX plan."""

    code: str
    row_id: str | None
    message: str


def validate_a_ex_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    ready: bool = False,
) -> list[AExIssue]:
    """Return plan violations. An empty list is valid only while the plan is not locked.

    ``ready=True`` is the founder lock for a curated set: at most 50 rows, both
    teaching outcomes, at least three arenas, and no arena above the per-arena cap.
    """

    issues: list[AExIssue] = []
    if len(rows) > A_EX_CAP:
        issues.append(
            AExIssue(
                "cap",
                None,
                f"A-EX cap is {A_EX_CAP} rows; got {len(rows)}",
            )
        )
    if len(rows) > MAX_CANDIDATE_ROWS:
        issues.append(
            AExIssue(
                "truncated",
                None,
                f"refusing to scan more than {MAX_CANDIDATE_ROWS} rows",
            )
        )
        return issues

    seen_ids: set[str] = set()
    arenas: set[str] = set()
    outcomes: set[str] = set()
    arena_counts: dict[str, int] = {}
    ttt_timeout_ids: list[str] = []

    for row in rows:
        row_id = row.get("id")
        label = row_id if isinstance(row_id, str) else None
        for key in row:
            lowered = key.lower()
            if any(part in lowered for part in _BANNED_KEY_PARTS):
                issues.append(
                    AExIssue(
                        "forbidden_field",
                        label,
                        f"remove field {key}",
                    )
                )
        if not isinstance(row_id, str) or _ID_RE.fullmatch(row_id) is None:
            issues.append(AExIssue("id", label, "id must be a short token without slashes"))
            row_id = None
        elif row_id in seen_ids:
            issues.append(AExIssue("duplicate_id", row_id, "duplicate id"))
        else:
            seen_ids.add(row_id)

        outcome = row.get("outcome")
        if outcome not in _OUTCOMES:
            issues.append(
                AExIssue(
                    "outcome",
                    row_id if isinstance(row_id, str) else label,
                    "outcome must be partial or failed",
                )
            )
        elif isinstance(outcome, str):
            outcomes.add(outcome)

        arena = row.get("arena")
        if not isinstance(arena, str) or _TOKEN_RE.fullmatch(arena) is None:
            issues.append(
                AExIssue("arena", _row_label(row_id, label), "arena must be a short token")
            )
            arena = None
        else:
            arenas.add(arena)
            arena_counts[arena] = arena_counts.get(arena, 0) + 1

        failure_class = row.get("failure_class")
        if not isinstance(failure_class, str) or _TOKEN_RE.fullmatch(failure_class) is None:
            issues.append(
                AExIssue(
                    "failure_class",
                    _row_label(row_id, label),
                    "failure_class must be a short token",
                )
            )
            failure_class = None

        if row.get("scrub") != "clean":
            issues.append(
                AExIssue(
                    "scrub",
                    _row_label(row_id, label),
                    "scrub must be clean before a row can be selected",
                )
            )

        model = row.get("model")
        if model is not None and (not isinstance(model, str) or _MODEL_RE.fullmatch(model) is None):
            issues.append(
                AExIssue("model", _row_label(row_id, label), "model must be a short token")
            )

        r2key = row.get("r2key")
        if r2key is not None:
            r2_issue = _r2key_issue(r2key)
            if r2_issue is not None:
                issues.append(AExIssue("r2key", _row_label(row_id, label), r2_issue))

        digest = row.get("sha256")
        digest_ok = isinstance(digest, str) and _SHA256_RE.fullmatch(digest) is not None
        if digest is not None and not digest_ok:
            issues.append(
                AExIssue(
                    "sha256",
                    _row_label(row_id, label),
                    "sha256 must be 64 lowercase hex characters",
                )
            )

        notes = row.get("notes")
        if notes is not None:
            notes_issue = _notes_issue(notes)
            if notes_issue is not None:
                issues.append(AExIssue("notes", _row_label(row_id, label), notes_issue))

        if (
            isinstance(row_id, str)
            and isinstance(arena, str)
            and arena in _TTT_ARENAS
            and failure_class == "timeout"
        ):
            ttt_timeout_ids.append(row_id)

    for extra_id in sorted(ttt_timeout_ids)[MAX_TTT_TIMEOUT:]:
        issues.append(
            AExIssue(
                "near_duplicate_ttt_timeout",
                extra_id,
                "keep at most one tic-tac-toe timeout",
            )
        )

    if ready:
        if len(arenas) < READY_MIN_ARENAS:
            issues.append(
                AExIssue(
                    "diversity_arenas",
                    None,
                    f"a locked plan needs at least {READY_MIN_ARENAS} arenas",
                )
            )
        if not {"partial", "failed"} <= outcomes:
            issues.append(
                AExIssue(
                    "diversity_outcome",
                    None,
                    "a locked plan needs both partial and failed rows",
                )
            )
        for arena, count in sorted(arena_counts.items()):
            if count > READY_MAX_PER_ARENA:
                issues.append(
                    AExIssue(
                        "arena_cap",
                        None,
                        f"{arena} has {count} rows; the per-arena cap is {READY_MAX_PER_ARENA}",
                    )
                )
    return issues


def load_candidate_rows(path: Path) -> list[dict[str, Any]]:
    """Load a local JSONL candidate file. Rejects oversized files."""

    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > MAX_CANDIDATE_BYTES:
        raise ValueError("candidate file exceeds the A-EX plan size limit")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        row: dict[str, Any] = {}
        for key, value in parsed.items():
            if not isinstance(key, str):
                raise ValueError(f"line {line_number} has a non-string key")
            row[key] = value
        rows.append(row)
    return rows


def missing_lab_pack_files(root: Path) -> list[str]:
    """Return lab-pack paths that are not files under ``root``."""

    missing: list[str] = []
    for relative in LAB_PACK_RELATIVE_PATHS:
        if not (root / relative).is_file():
            missing.append(relative)
    return missing


def phantom_sample_paths(root: Path) -> list[str]:
    """Return tracked-looking paths whose name contains the absent battle id."""

    hits: list[str] = []
    if not root.is_dir():
        return hits
    for path in root.rglob(f"*{PHANTOM_SAMPLE_ID}*"):
        if ".git" in path.parts:
            continue
        hits.append(path.relative_to(root).as_posix())
    return hits


def _row_label(row_id: str | None, fallback: str | None) -> str | None:
    if isinstance(row_id, str):
        return row_id
    return fallback


def _r2key_issue(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 512:
        return "r2key must be a relative object key"
    lowered = value.lower()
    if value.startswith("/") or "\\" in value or ".." in value.split("/"):
        return "r2key must be a relative object key"
    if "://" in value or "?" in value or any(marker in lowered for marker in _SECRET_KEY_MARKERS):
        return "r2key must not be a URL or a secret path"
    return None


def _notes_issue(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 240:
        return "notes must be a short string"
    lowered = value.lower()
    if "://" in value or "x-amz-" in lowered or "token=" in lowered:
        return "notes must not carry URLs or token material"
    return None


def main(argv: list[str] | None = None) -> int:
    """Check one local JSONL file. Exit 0 when the plan checks pass."""

    parser = argparse.ArgumentParser(
        prog="python -m eslams.public_archive",
        description=(
            "Check an A-EX teaching-fail candidate list. "
            "Reads one local JSONL file. Does not contact R2, D1, or Hugging Face."
        ),
    )
    parser.add_argument("candidates", type=Path)
    parser.add_argument(
        "--ready",
        action="store_true",
        help="Apply the locked diversity gates in addition to the cap of 50.",
    )
    args = parser.parse_args(argv)
    path: Path = args.candidates
    try:
        rows = load_candidate_rows(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    issues = validate_a_ex_candidates(rows, ready=bool(args.ready))
    if issues:
        for issue in issues:
            where = issue.row_id or "-"
            print(f"{issue.code}\t{where}\t{issue.message}")
        return 1
    print(f"ok\t{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
