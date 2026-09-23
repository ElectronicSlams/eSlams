"""A-EX plan checks and in-repo lab-pack honesty. No network."""

from __future__ import annotations

import json
from pathlib import Path

from eslams.public_archive import (
    A_EX_CAP,
    HF_LAB_DATASET_ID,
    HF_ORG_LIVE,
    LAB_PACK_RELATIVE_PATHS,
    MAX_TTT_TIMEOUT,
    PHANTOM_SAMPLE_ID,
    READY_MAX_PER_ARENA,
    READY_MIN_ARENAS,
    load_candidate_rows,
    main,
    missing_lab_pack_files,
    phantom_sample_paths,
    validate_a_ex_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def _row(
    index: int,
    *,
    arena: str,
    outcome: str,
    failure_class: str = "invalid",
) -> dict[str, object]:
    return {
        "id": f"row-{index:03d}",
        "outcome": outcome,
        "arena": arena,
        "failure_class": failure_class,
        "scrub": "clean",
        "sha256": "ab" * 32,
    }


def _locked_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    index = 0
    for arena, count in (
        ("chess", 15),
        ("connect-four", 15),
        ("othello", 10),
        ("arena_tic_tac_toe", 10),
    ):
        for offset in range(count):
            outcome = "partial" if offset % 2 == 0 else "failed"
            failure_class = "timeout" if arena == "arena_tic_tac_toe" and offset == 0 else "invalid"
            rows.append(_row(index, arena=arena, outcome=outcome, failure_class=failure_class))
            index += 1
    return rows


def test_locked_plan_accepts_fifty_diverse_rows() -> None:
    rows = _locked_rows()
    assert len(rows) == A_EX_CAP
    assert validate_a_ex_candidates(rows, ready=True) == []


def test_cap_rejects_the_fifty_first_row() -> None:
    rows = _locked_rows()
    rows.append(_row(999, arena="chess", outcome="failed"))
    codes = [issue.code for issue in validate_a_ex_candidates(rows)]
    assert "cap" in codes
    assert "arena_cap" not in codes


def test_second_tic_tac_toe_timeout_is_rejected() -> None:
    rows = [
        _row(1, arena="arena_tic_tac_toe", outcome="failed", failure_class="timeout"),
        _row(2, arena="tic-tac-toe", outcome="failed", failure_class="timeout"),
    ]
    issues = validate_a_ex_candidates(rows)
    assert [issue.code for issue in issues] == ["near_duplicate_ttt_timeout"]
    assert issues[0].row_id == "row-002"
    assert MAX_TTT_TIMEOUT == 1


def test_secret_material_and_success_rows_are_rejected() -> None:
    rows = [
        {
            "id": "bad-1",
            "outcome": "success",
            "arena": "chess",
            "failure_class": "invalid",
            "scrub": "pending",
            "api_token": "nope",
            "r2key": "https://bucket.example/object?X-Amz-Signature=abc",
            "notes": "see https://example.invalid/signed",
            "sha256": "ABCD",
        }
    ]
    codes = {issue.code for issue in validate_a_ex_candidates(rows)}
    assert codes >= {"outcome", "scrub", "forbidden_field", "r2key", "notes", "sha256"}


def test_ready_lock_requires_diversity() -> None:
    rows = [_row(index, arena="chess", outcome="partial") for index in range(3)]
    codes = {issue.code for issue in validate_a_ex_candidates(rows, ready=True)}
    assert "diversity_arenas" in codes
    assert "diversity_outcome" in codes
    assert validate_a_ex_candidates([], ready=False) == []
    assert {issue.code for issue in validate_a_ex_candidates([], ready=True)} >= {
        "diversity_outcome",
        "diversity_arenas",
    }


def test_ready_arena_cap() -> None:
    rows = [
        _row(index, arena="chess", outcome="partial" if index % 2 == 0 else "failed")
        for index in range(READY_MAX_PER_ARENA + 1)
    ]
    rows.extend(_row(100 + index, arena="othello", outcome="failed") for index in range(1))
    rows.extend(_row(200 + index, arena="connect-four", outcome="partial") for index in range(1))
    codes = {issue.code for issue in validate_a_ex_candidates(rows, ready=True)}
    assert "arena_cap" in codes
    assert READY_MIN_ARENAS == 3


def test_candidate_loader_and_cli(tmp_path: Path) -> None:
    path = tmp_path / "candidates.jsonl"
    path.write_text(json.dumps(_row(1, arena="chess", outcome="failed")) + "\n", encoding="utf-8")
    assert load_candidate_rows(path)[0]["id"] == "row-001"
    assert main([str(path)]) == 0

    huge = tmp_path / "huge.jsonl"
    huge.write_bytes(b"x" * (256 * 1024 + 1))
    assert main([str(huge)]) == 2


def test_checker_source_has_no_remote_client() -> None:
    source = (ROOT / "src/eslams/public_archive.py").read_text(encoding="utf-8")
    for banned in ("httpx", "urllib", "requests", "socket", "subprocess", "wrangler", "boto3"):
        assert banned not in source


def test_lab_pack_matches_disk_and_docs() -> None:
    assert HF_ORG_LIVE is False
    assert missing_lab_pack_files(ROOT) == []
    assert phantom_sample_paths(ROOT) == []
    for relative in LAB_PACK_RELATIVE_PATHS:
        assert (ROOT / relative).is_file()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sample_readme = (ROOT / "sample_runs/README.md").read_text(encoding="utf-8")
    lab_pack = (ROOT / "docs/LAB_PACK.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs/A_EX_PLAN.md").read_text(encoding="utf-8")

    assert "run_eeab67d58b994ca7.eslams" in readme
    assert PHANTOM_SAMPLE_ID not in readme
    assert "composer-2.5" not in sample_readme
    assert PHANTOM_SAMPLE_ID in sample_readme
    assert "not in this tree" in sample_readme
    assert "first-legal" in sample_readme
    assert HF_LAB_DATASET_ID in lab_pack
    assert "not live" in lab_pack
    assert "Do not run:" in lab_pack
    assert "hf download ElectronicSlams/eslams-sample-runs" in lab_pack
    assert "404" in lab_pack

    assert "eslams-core==0.6.1" in agents
    assert "Do not pull R2" in agents
    assert "Do not query, export, or delete D1" in agents
    assert "Do not invite `cursoragent`" in agents
    assert "cap: 50" in plan
    assert f"ttt_timeout_keep: {MAX_TTT_TIMEOUT}" in plan
    assert f"ready_max_per_arena: {READY_MAX_PER_ARENA}" in plan
    assert f"ready_min_arenas: {READY_MIN_ARENAS}" in plan
    assert "Do not pull R2" in plan
    assert "Do not query, export, or delete D1" in plan
    assert "PR #21" in agents
    assert "no review comments" in agents
