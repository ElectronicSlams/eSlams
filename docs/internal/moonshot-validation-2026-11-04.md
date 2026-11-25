# Moonshot adapter cloud validation — 2026-11-04

Base: `270a863d10d57a0953f21924f1a0dd50159e6cf1` (Core 0.7.0).
Scope: native Moonshot/Kimi adapter proposed for 0.7.1, without a version bump,
registry regeneration, release, merge, paid inference, or real provider keys.
Official API research and fixture provenance: [provider guide](../PROVIDER_MOONSHOT.md).

The Core repository had no `AGENTS.md`, `.agents` directory, or local skill
instructions; `/workspace/.agents` was empty. `CONTRIBUTING.md` governed raw-wire
fixture coverage, receipt privacy, source identity, and validation.

## Environment and results

Codex cloud Linux, Python 3.12.14; pytest 9.2.0, HTTPX 0.28.1,
Ruff 0.17.3, mypy 1.19.1, FastAPI 0.162.0, Starlette 1.10.0.
Dependencies were installed from the declared dev extra into an isolated venv.

| Check | Result |
| --- | --- |
| `python -m pytest tests/test_moonshot_adapter.py` | **69 passed** |
| Full branch `python -m pytest --basetemp=/tmp/kimi-final-tests` | **1327 passed, 2 failed**, 2 warnings, 54.56 seconds |
| Untouched base in a separate checkout, full pytest | **1258 passed, 2 failed**, 2 warnings, 60.50 seconds |
| `ruff check .` | Passed |
| `mypy src` | Passed, 104 source files |
| TypeScript 5.5.4 `tsc --noEmit`, core-contracts and core-lite | Both passed |
| `python scripts/verify_arena_versions.py` | 50 arena fingerprints verified |
| `eslams core budgets --json` | All 50 initial-state budgets passed |
| Two `eslams schemas export` runs and `diff -qr` | All 45 schemas and bundle manifest byte-identical; manifest inspected |
| `python -m build` and `python -m twine check` | Wheel and sdist built; both metadata checks passed |
| `git diff --check` | Passed |

The full suite is **not passing**. The same failures reproduce on untouched base:

1. `tests/test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
   receives `ProviderCallError: provider response body could not be verified`.
2. `tests/test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`
   expects `board_winner == "player_1"` but observes `None`.

The untouched checkout used its own working directory and
`PYTHONPATH=/workspace/eslams-baseline/src`, ensuring it imported base sources.
Earlier setup attempts made before dependency installation completed, and an
initial mixed-working-directory baseline attempt, are not counted as evidence.
The npm cache was explicitly placed in `/tmp` after the default cache proved
unwritable. No product code was changed to address these setup constraints.

The two warnings concern Starlette's deprecated HTTPX test-client integration
and an intentionally duplicated ZIP member in the publish-handoff fault test.
Python 3.10/3.11 and macOS/Windows were not run here. Tests demonstrate offline
adapter behavior; they do not establish account visibility, hosted model
availability, cost completeness, ZDR, or Official eligibility.

## PR and CI handling

The proposed commit includes `[skip ci]` and a `skip-checks: true` trailer.
The repository's PR workflows use `pull_request` and have no
`pull_request_target` trigger. GitHub's
[skip documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)
specifies that the head commit marker suppresses push/PR workflow runs. No
workflow files are changed, disabled, or dispatched. Validation above ran in
Codex cloud; the eventual draft PR head is reported separately by the task.
