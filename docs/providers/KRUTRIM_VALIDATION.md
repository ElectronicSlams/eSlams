# Krutrim adapter cloud validation

Date: 2026-11-04. Repository: `ElectronicSlams/eSlams`.
Base: `270a863d10d57a0953f21924f1a0dd50159e6cf1`.
Execution: isolated Codex cloud Python 3.12.14 environment; package version 0.7.0.
No `AGENTS.md` or `.agents/skills` exists in Core or the workspace root.
The preloaded Platform checkout was not modified.

| Check | Result |
| --- | --- |
| New provider tests | 64 passed, with in-process raw-wire stubs only. |
| Final admitted Python suite | 1,318 passed; JUnit reports zero failures/errors/skips, 92.155 seconds. |
| Ruff | Passed for the whole repository. |
| Mypy | Passed, 104 source files. |
| Schema exports | Two exports byte-identical, including the manifest; 46 files each. |
| Arena version fingerprints | All 50 verified. |
| Initial-state prompt/observation budgets | Passed. |
| Wheel and sdist | Built using the installed declared backend with `--no-isolation`. |
| Twine metadata | Both distributions passed. |
| Whitespace | `git diff --check` passed. |

The suite uses the exact audit guard and offline pytest fixture plugin extracted
from `scripts/server_release_check.py`, including its existing two CLI failure
mocks, no-isolation package-build wrapper and exclusion of
`tests/test_elapsed_deadline_regressions.py`. That inherited listener exclusion
was retained; no listener fixture was executed. The guard blocks `socket.bind`,
`socket.connect` and `socket.getaddrinfo` before their OS operation and removes
credential-bearing environment variables from test subprocesses.

The audit recorded two `socket.bind` attempts blocked before the OS operation
across the two broader suite runs. No connection or DNS audit events were
recorded. No listener/network acceptance is claimed. Adapter tests neither
start servers nor contact an inference service.

The first broader run (1,309 collected tests, before the last nine added cases)
had one packaged-provenance subprocess-build failure while the environment
lacked Hatchling. Installing the already-declared backend (`hatchling` 1.33.0)
resolved it: the targeted provenance test and the final entire admitted suite
passed. No inherited source failure remains in the admitted suite. Existing
warnings are Starlette's HTTPX TestClient deprecation and an intentional ZIP
duplicate-member fault-injection warning.

Commands used the existing offline policy:

```text
python -m pytest -q -p release_offline tests/test_krutrim_provider.py
python -m pytest -q -p release_offline tests --ignore=tests/test_elapsed_deadline_regressions.py
python -m ruff check .
python -m mypy src
eslams schemas export --out <first-new-directory>
eslams schemas export --out <second-new-directory>
diff -qr <first-new-directory> <second-new-directory>
python scripts/verify_arena_versions.py
eslams core budgets --json
python -m build --no-isolation --outdir <new-dist-directory>
python -m twine check <wheel> <sdist>
```

Cloud logs/JUnit are retained under `/tmp/krutrim-checks`,
`/tmp/krutrim-focused.log`, `/tmp/krutrim-full-final.log` and
`/tmp/krutrim-build-final.log`; final local build outputs are in
`/tmp/krutrim-dist-final`. These are review artifacts, not release outputs.

No paid inference, real provider credential use, server deployment, merge,
release, version bump or hosted workflow dispatch was performed. TypeScript,
browser and cross-interpreter release matrices were not rerun for this Python
adapter change. A draft PR uses a `[skip ci]` head commit to suppress the
repository's `push`/`pull_request` workflows, consistent with its documented
server-side verification policy; there are no `pull_request_target` or
`workflow_run` triggers in the checked-in workflows.

Live account access, inference residency, current model inventory, detailed
reasoning/usage/cost semantics and unavailable API-reference pages remain the
limits described in [the research report](KRUTRIM.md).
