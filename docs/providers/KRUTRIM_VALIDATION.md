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

## Independent privacy and admission follow-up

Reviewed the initial draft head
`a6812ddb4f2d9051c9f6c9abe02ab98b35677850` against the cross-provider findings.
The original model/reasoning validation passed independent admission checks.
The review reproduced a privacy defect: inactive primary or secondary Krutrim
credentials could enter identifiers, partial/error receipts and action text
when a different custom credential environment authenticated the request.
Twenty-seven of the initial 56 independent cases failed on that original head.

The fix captures an action-scoped snapshot of selected and other configured
Krutrim credentials, filters every such credential from receipt values/keys and
identity evidence, rejects echoes throughout decoded action JSON (including
unused fields), and suppresses raw private transport/JSON exception chains.
Filtering survives key rotation during a response. Secondary credentials are
redaction inputs only; authentication still uses exactly the selected key.

The 56 independent cases now pass alongside the original 64 provider cases
(120 provider cases total). They cover primary, secondary and custom active
keys; success/error/malformed/partial-response IDs; plain and escaped action,
explanation and unused JSON fields; removal of a secondary key during transport;
exception formatting; absent discovery; blank IDs; and explicit reasoning
controls including zero budgets. Both actual `act` dispatch and direct dispatch
reject invalid settings before the transport can run. HTTP failures remain
single attempts even with an explicit nonzero retry maximum. The existing full
history assertion continues to pass.

The same inherited offline guard, listener exclusion and CLI mocks apply to
the follow-up checks. All **1,374 admitted tests passed**, with zero failures,
errors or skips (105.860 seconds), along with whole-repository Ruff, strict
mypy for 104 source files and `git diff --check`. The full suite includes the
packaged-provenance build/schema check. Follow-up logs are retained in
`/tmp/krutrim-review-before.log`, `/tmp/krutrim-review-after.log` and
`/tmp/krutrim-review-full.log`.

No live credential or inference service was used; no
listener was opened. The follow-up commit also uses `[skip ci]` and updates
only the proposed revision for draft PR #282; remote publication remains subject
to approval. No merge, release or hosted workflow dispatch is authorized.
