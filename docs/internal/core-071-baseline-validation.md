# Core 0.7.1 baseline investigation

This is the initial investigation record. The later shared action-depth repair
and its newer implementation/check identity are recorded in
[core-action-depth-validation.md](core-action-depth-validation.md).

Date: 2026-11-04. Base: `270a863d10d57a0953f21924f1a0dd50159e6cf1`.
The final documentation-only commit adds this report and receipt; the tested
implementation is unchanged.

Implementation tested: `c618696c1641dce1430c4e9bba2b7edb8afa0c70`.
Codex cloud Linux x86_64, Python 3.12.14, Node 24.19.0, TypeScript 5.5.4.
Python package remains **0.7.0**. This branch contains no adapter implementation,
arena change, schema-format change or release publication.

## Findings and changes

### Observed-response timeout custody

Verified `bounded_post`, `_post_json`, `_raise_observed_transport_failure`, the
adapter retry loop and Runner exception handling. Before response headers,
HTTP timeouts surface as `TimeoutError`. Once bounded response-header evidence
exists, the adapter raises `ProviderCallError(error_kind="provider_timeout")`
with the observed status and sanitized request IDs. Its receipt records unknown
usage/cost, and `retry_permitted` remains false, including for observed 429/503
headers. Runner makes neither a scoring result nor a fallback action from this
failure. Changing it to a bare timeout would discard the exception's evidence.

Kept this runtime behavior. Added socket-free exception-contract cases for no
headers and status 200/429/503, single-attempt/no-replay assertions, and finite
rate/concurrency-admission deadline cases. Existing actual bounded-reader tests
also pass with HTTPX MockTransport, including partial timeout/reset/size errors,
artifact receipt custody, privacy, no applied action and no fallback.

The parent reported a `TimeoutError` expectation in
`test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`.
The established restriction in `docs/internal/release-0.7.0.md` excludes its
listener-fixture file. **That file was not opened, edited or executed here.**
Its reported assertion remains unresolved; the fixture-specific diagnosis is
not independently claimed. A permitted follow-up should review the observed-
header assertion against the documented receipt-carrying exception contract,
retaining its elapsed, queue/retry and receipt checks.

### CLI local fallback versus transport failure

Reproduced the board-winner assertion failure on untouched base behavior through
real `HttpAgent`/`bounded_post` code with an HTTPX MockTransport ConnectError:
3 CLI tests passed, 1 failed (`board_winner` was null rather than `player_1`).
No socket or listener was opened for that reproduction.

The runtime correctly fails closed for transport failure. The old fixture used
an HTTP URL to stand in for a generic failing local agent. Replaced that fixture
with a local FunctionAgent returning no action, preserving its diagnostic board-
win/public-winner-null check. Added separate CLI refused-transport cases for
fallback, invalid-match and forfeit: one submission, no board/public winner,
no fallback action, and `provider_transport_error` retained.

The release checker's autouse `HttpAgent.act` replacement raised a generic
ConnectionError and therefore concealed this distinction. Removed it. The
network audit hook remains, as does the explicit offline build-isolation policy
for the wheel-export test. Validation assertions and exclusions were not relaxed.

### Core-lite (#243)

Compiled unmodified Core-lite with TypeScript 5.5.4 and reproduced parity failure
at step 0: Core 0.6.2/prompt v2 versus Python 0.7.0/prompt v3. Aligned step
metadata and the private TypeScript package manifests/dependency to the existing
Python 0.7.0 identity. This does not advance Python to 0.7.1.

Core-lite has no prompt-construction API to port. Python still owns full-history
prompt-v3 construction and explicit legacy-v2 behavior. With the stale labels
corrected, all deterministic response fields match Python for 22 initial states
and 1,401 step cases, both winners/draws, legal-action wrappers, safe seeds and
contained malformed states. Added manifest identity checks to the parity script
and made compiled runtime parity a required server-release-check step.

## Validation

The reviewed finite release runner was invoked on a clean implementation commit:

```sh
/workspace/core-venv/bin/python scripts/server_release_check.py \
  --out /tmp/core-071-checks \
  --tsc /workspace/core-tools/node_modules/typescript/bin/tsc
```

- Focused regressions: **58 passed** under a socket audit guard.
- Source admitted suite: **1,263 passed**, zero failures/skips, two warnings:
  Starlette's HTTPX TestClient deprecation and an intentional duplicate ZIP
  member in a malformed-publication fixture.
- Ruff, strict mypy (103 source files), both TypeScript checks, compiled Core-lite
  parity, all-50-arena versioned fingerprints and portable byte generation pass.
- Prompt budgets pass for all 50 initial arena states; 10-iteration arena-step
  benchmark smoke passes.
- Two schema exports compare byte-for-byte. Inspected manifest:
  `core_package_version=0.7.0`, source commit matches the implementation above,
  deterministic build ID
  `sha256:3e96537e1281014ed747f58a9f9f12733a063f0cb09b4ec9ed160669a13f983b`.
- Wheel/sdist build, Twine, both isolated distribution consumers and the
  extracted-sdist admitted suite without Git all pass. Consumer checks cover
  import isolation, packaged commit provenance, typing, CLI errors, schemas,
  deterministic games, artifacts, replay and public export.
- The finite release runner reports `status=passed` for its admitted checks.
  Its exact receipt, artifact hashes and explicit scope are retained in
  [core-071-baseline-checks.json](core-071-baseline-checks.json). The source
  and nested sdist suites each logged one `socket.bind` event blocked before
  the OS operation. These audit records remain visible; no successful network
  operation or listener is claimed for either guarded suite.
- Generated 50 validated replay pages and the adversarial embedding fixture.
  Browser assertions did **not** complete. Playwright's Chromium download was
  blocked by HTTP 403 `Domain forbidden`; system Chromium 151.0.7922.173 then
  rejected the first local replay file with `ERR_BLOCKED_BY_ADMINISTRATOR`.
  No browser policy was bypassed and no listener was opened as a workaround.

## Limits and handoff

The listener regression file remains excluded under the inherited denial.
Native macOS/Windows, Python 3.10/3.11, minimum-dependency resolution, advisory
security audits and completed browser replay checks are not claimed. No real
provider credentials, paid inference, Platform/server mutation, deployment,
merge, npm/PyPI publication or release was performed.

The implementation and documentation commits contain `[skip ci]`. Inspected
all repository workflows: their PR triggers use `pull_request`; none uses
`pull_request_target` or `workflow_run`. GitHub documents this marker for
suppressing push/PR runs; required checks can stay pending:
https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs

A future integrated adapter release must rerun the applicable checks on its
combined source, including the outstanding authorized transport/runtime gates.
