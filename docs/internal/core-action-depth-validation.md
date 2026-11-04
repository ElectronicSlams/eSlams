# Shared action JSON depth and receipt custody

Date: 2026-11-04. Follow-up for draft PR #268. Prior PR head:
`3c6f3b9eece11eb2d96b569e207ac95c53a462d2`.
Implementation tested: `4801cda05e4a4e2a55b97cd1f37013d3f5bd3901`.
The final documentation-only commit records these results; shipped code and tests
are identical to the tested implementation. Python remains 0.7.0. Checks ran on Codex cloud Linux x86_64, Python 3.12.14,
Node 24.19.0 and TypeScript 5.5.4.

## Reproduction and boundary

Verified the prior shared parser and agent code from the prior PR head in an
isolated, socket-guarded local import. A valid shallow HTTP 200 provider envelope
contained a deeply nested JSON action *string*, with observed 12 input / 4 output
tokens. No HTTP listener or provider was contacted.

- At action-text nesting depth 12,000, the original decoder raised untyped
  `RecursionError` after the adapter had published one receipt with 16 total tokens.
- With a recursive credential scanner between provider completion and returning
  its `(text, receipt)` pair, depth 1,200 raised untyped `RecursionError` with
  **zero published receipts**. The scanner shape matches recursive traversal of
  the shared `extract_json(text)` result in available adapter branch snapshots.
- Failure depth varies by decoder/interpreter stack behavior; relying on Python's
  eventual recursion exception cannot safely bound an adapter's earlier scanner.

The outer HTTP JSON was valid and shallow in both reproductions. The issue is the
separate model-action text decoder/consumer boundary, rather than transport failure
or evidence that the completed generation can be replayed.

## Change

`model_actions.py` now checks JSON object/array nesting iteratively before decoding,
with a maximum structural depth of 128. JSON quotes and escaped quotes/backslashes
are accounted for; quoted brackets do not count. Ordinary JSON, code fences and
existing prose/JSON recovery remain supported. Excessive depth is rejected before
salvaging any nested inner action. Defensive decoder `RecursionError` and numeric
resource `ValueError` become a static, sanitized typed error as well.

The public extraction helper retains its existing unparseable-input `None`
convention for depth/resource exhaustion. Consequently, scanners using it never
receive an excessively deep decoded object and can return the observed receipt
before the action parser reports failure. `parse_model_action` reports
`InvalidModelAction(code="invalid_json", repair_permitted=False)` for those resource
failures. Existing wire error codes and `to_dict()` fields are unchanged.

`ModelProviderAgent` retains the observed receipt, marks it
`action_response_unparseable`, preserves usage/cost and gap-free attempt identity,
and includes it in the final `ProviderCallError`. It does not send another request
for depth/decoder exhaustion, even when transport retries and action repair are
configured. Existing ordinary invalid-action repair remains operator-controlled.
Streaming parse status also reports invalid before accepting a partial action-id
hint when the nesting bound is exceeded.

This is a JSON format/resource bound, not an output-token/thinking-time budget.
No provider dispatch, native controls, identity claims, pricing, arena rules or
public schema format are changed.

## Verification

- Added **106 regression cases**, covering all five existing provider raw-wire
  envelopes at nested-array depths 1, 32, 126, 127, 400, 1,200 and 4,000, both with
  and without a pre-return recursive scanner. Positive controls reach structural
  depth 128; depth 129 fails. Checks require one submission, one observed receipt,
  16 total tokens, preserved request ID/status and OpenRouter native cost.
- Added object/array, fenced/prose, quoted/escaped bracket, nested-action salvage,
  decoder-resource and streaming checks. Five Runner artifact cases verify no
  applied action, retained usage, scoring exclusion, no private leaf text and
  successful artifact validation.
- **198 focused parser/provider/custody tests passed** under the socket guard.
- An additional depth-12,000 stress run invoked the same receipt/no-replay
  assertions for all **10 provider/scanner combinations**; all passed.
- The full admitted source suite passed: **1,369 tests**, zero failures/skips.
  Two warnings remain: Starlette/HTTPX TestClient deprecation and the intentional
  duplicate ZIP member fixture.
- Ruff, strict mypy (103 source files), both TypeScript checks and Core-lite parity
  passed (22 initial states / 1,401 deterministic step cases).
- All 50 arena fingerprints, portable bytes, wheel/sdist build and Twine passed.
- Two schema exports are byte-identical; inspected manifest pins the tested
  implementation commit and existing Core 0.7.0 identity. All 50 initial-state
  prompt budgets and the arena-step benchmark smoke pass.
- Both isolated wheel/sdist consumers and the extracted-sdist admitted suite
  without Git passed. The finite release runner reports `status=passed` for its
  admitted scope. Its receipt summary, source identity, artifact hashes, baseline
  reproduction and depth-12,000 stress result are retained in
  [core-action-depth-checks.json](core-action-depth-checks.json).
- Source and nested-sdist suites each retained one `socket.bind` audit event
  blocked before the OS operation. The network/listener guard was not weakened.

Finite release invocation:

```sh
/workspace/core-venv/bin/python scripts/server_release_check.py \
  --out /tmp/core-depth-release-checks \
  --tsc /workspace/core-tools/node_modules/typescript/bin/tsc
```

## Scope and remaining gates

This branch does not import or merge any pending provider adapter. Available
DeepSeek, Inception and Arcee snapshots use the shared extraction helper before
recursive credential scans and therefore need this shared change integrated.
The regression scanner models that call position; these are not claims that all
of those independent branches have been rebased or fully tested. A scanner that
uses its own decoder, recursively processes an unrelated provider object, or
changes the recursion limit still needs its own iterative/bounded handling.

The established listener-fixture restriction remains: the denied elapsed-deadline
file was not opened, edited or executed. Its previously reported timeout-expectation
mismatch remains a separate unresolved gate. Browser replay assertions were not
retried: the prior run encountered HTTP 403 on the browser download and administrator
blocking of local-file navigation. Native Windows/macOS, Python 3.10/3.11,
minimum-dependency resolution and security audits are not claimed.

All execution was in Codex cloud with synthetic provider fixtures. No real provider
credentials, paid inference, deployment, merge, publication, release or Platform
mutation. Commits include `[skip ci]`; PR #268 remains a draft. GitHub's PR workflow
runs and branch head are checked after push. Earlier baseline findings and their
historical receipt remain in `core-071-baseline-validation.md` and
`core-071-baseline-checks.json`.
