# Ant Ling cloud validation

Date: 2026-11-04. Interpreter: Python 3.12.14.
Base: `270a863d10d57a0953f21924f1a0dd50159e6cf1` (Core 0.7.0).
Branch: `codex/ant-ling-direct-adapter`.

The selected environment initially contained the Platform checkout. Core was
cloned separately into `/workspace/eSlams`; no Platform files were edited.
`/workspace/.agents` and `/workspace/.codex` were empty. Core contained no
`AGENTS.md`, `.agents/skills`, or `SKILL.md`; `CONTRIBUTING.md` supplied the
provider fixture and verification requirements. No unrelated design skill was
applied.

## Completed checks

| Check | Outcome |
| --- | --- |
| Pristine base full pytest suite | 1,258 passed; 2 failed; 2 warnings |
| Base Ruff and mypy | Passed |
| Full suite after adding the adapter | 1,341 passed; same 2 inherited failures; 2 warnings |
| New Ant Ling tests plus provider integration regressions | 132 passed, including 83 Ant Ling cases |
| Final Ruff | Passed |
| Final mypy, `src` | Passed, 104 source files |
| Both TypeScript 5.5.4 projects | Passed |
| Wheel and sdist build, unchanged 0.7.0 package version | Passed |
| `twine check` for both distributions | Passed |
| New adapter and provider catalogue data present in wheel | Verified |
| Two schema exports compared byte-for-byte | Identical |
| `verify_arena_versions.py` | Passed, all 50 arena fingerprints |
| `eslams core budgets --json` | Passed, all 50 initial-state checks |
| `verify_portable_bytes.py` | Passed in this Linux/Python environment |
| `git diff --check` | Passed |

TypeScript's first attempt could not create npm's default cache under
`/home/agent`. It passed after configuring a cache under `/tmp`; no sandbox
permissions were expanded. Multi-OS/Python matrix jobs, browser tooling, hosted
CI, release, deployment, and live provider inference were not run.

## Inherited full-suite failures

Both failures reproduced before adapter changes and in subsequent full suites.
Final provider review adjustments were revalidated with the complete 132-test
provider regression group; shared transport and arena behavior were unchanged.

1. `tests/test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
   expects a timeout exception, but the shared OpenAI response-observation path
   raises `ProviderCallError` once headers have been observed. The new provider
   does not change this shared behavior.
2. `tests/test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`
   expects `summary.board_winner == "player_1"`; the observed value is null.

The two inherited warnings concern Starlette's HTTPX TestClient deprecation
and an intentional duplicate-ZIP-member test. These failures were disclosed,
not suppressed or repaired in a provider adapter change.

## Boundaries and publication

All provider tests use documented public example data or explicit synthetic
fault injection. The CLI live-preflight path is tested with a mocked transport;
no live request, provider credential, balance, or paid inference is involved.
No production service, external test server, merge, release, or deployment was
used.

The owner's established instruction is to avoid GitHub runs. Repository
workflows were inspected: PR-related triggers use `pull_request`, with no
`pull_request_target` or `workflow_run` trigger. The draft head commit retains
`[skip ci]` and `[skip actions]`, following
[GitHub's documented skip semantics](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).
No workflow files or repository settings are changed. Attempts to inspect
repository/Actions permission metadata through the cloud shell returned
`Forbidden`; they did not change settings or trigger a job.

Current direct-contract limitations and exact official evidence are in
[ANT_LING.md](ANT_LING.md). Account access, region availability/data residency,
server-selected deployment identity beyond response `model`, reasoning-token
inclusion, and complete pricing remain unverified. Non-streaming calls retain
the provider's documented 90-second upstream limit.

## Cross-cutting review of draft #275

Reviewed the existing draft at
`b8aeb738c0b0227c9aaa1c70ed497f214b51c2b5`. Initial new regressions reproduced
56 failures across 94 cases: normalized preflight aliases bypassed explicit
model/reasoning validation, and only the active bearer was recognized during
credential-echo scrubbing. Both gaps were fixed with provider-specific changes
and two lines of shared preflight normalization.

The completed review adds 100 regression cases, bringing Ant Ling coverage to
183 cases. All 232 Ant Ling/provider integration checks pass, including:

- Missing/blank models and unsupported explicit reasoning budgets in live and
  offline preflight, including case, whitespace, and underscore variants.
- Revalidation immediately before transport after model/runtime mutation.
- Primary and additional configured credentials in response/request/gateway
  IDs, HTTP and HTTP-200 body errors, malformed and partial responses, raw and
  JSON-escaped action fields, and percent-encoded text.
- Real bounded partial-body transport with both credential values present.
- No fallback authentication from configured compatibility environment names.
- Keyless, network-free discovery (no documented direct Models API).
- Unbounded default engine read/total timeouts, omitted output caps, preserved
  history, and a documented provider-enforced 90-second synchronous constraint.

The complete suite finished with 1,441 passed, the same two inherited failures
listed above, and the same two warnings. Ruff, mypy, wheel/sdist builds, and
Twine checks passed again. These checks use
synthetic credentials and mocked provider transport only. No live provider
credentials, paid inference, hosted CI, merge, or release were used.
