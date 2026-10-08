# Backlog consolidation

The Core backlog is consolidated into [PR #218](https://github.com/ElectronicSlams/eSlams/pull/218). **148 of 149 inventoried issues and all 44 original PRs are verified closed.** Original branches are preserved. The complete [ledger](backlog-resolution.json) records each reviewed head, acceptance criterion, incorporated or declined proposal, implementation evidence and verified GitHub closure timestamp. Proposed changes have not been merged or released.

## Verified implementation

Checkpoint `96cc2154bbe700e453b62234e446c6520ec99f1f` passes every required native/distribution gate:

- [Core CI](https://github.com/ElectronicSlams/eSlams/actions/runs/37770400164): Linux Python 3.10–3.12, Windows/macOS Python 3.12; all-50-arena version fingerprints and initial-state budgets; exact native artifact/schema/publication byte parity; Python/TypeScript contracts and 22 initial states plus 1,401 complete Core-lite step responses.
- [Distribution consumers](https://github.com/ElectronicSlams/eSlams/actions/runs/37770400205): fresh wheel/sdist installs outside the checkout on Linux, Windows and macOS; console/module normal/debug/closed-pipe behavior, downstream mypy, keyless run/validate/replay/public export, metadata/schema provenance and the full extracted no-Git sdist suite.
- [Dependency audit](https://github.com/ElectronicSlams/eSlams/actions/runs/37770400095), [workflow lint](https://github.com/ElectronicSlams/eSlams/actions/runs/37770400069) and [CodeQL](https://github.com/ElectronicSlams/eSlams/actions/runs/37770400052).

Browser CI checks all 50 arenas at mobile, tablet and desktop sizes, including 300 initial/final viewport checks, keyboard/focus, target sizes, semantic labels and hostile embedded text. The version diagnostic explicitly normalizes floating values to ten decimal places for cross-libm portability; runtime state hashes and replay validation remain exact.

The final record commit changes documentation only and receives normal CI independently of this implementation checkpoint. The consolidation PR becomes ready for review after its final head passes.

## Test reduction

Frozen baseline `7f6bb418974739986e76049d45dfb7de2109a780` contains 275 cases and 85.332886% line coverage over `src/eslams`. Exactly 55 original cases (20%) are removed, mainly by consolidating redundant wrappers while retaining useful assertions. The ledger records baseline identities and retained assertion locations. No removed function is reintroduced; new behavioral/integrity regressions are tracked separately.

All 509 cases pass on local Python 3.12 and direct-dependency-floor Python 3.10. Both cover 11,851 / 13,368 lines (88.652005%), 3.319119 percentage points above baseline. Ruff and strict mypy pass. All eight published 0.6.1 keyless lab commands pass in a fresh external virtual environment. Current sample inventories record exact archive checksums and clean generation commits, honest Local status and no unverified mirrors.

## Sole remaining issue

[#219](https://github.com/ElectronicSlams/eSlams/issues/219) concerns the hosted Arena Shuffle control in the live `makriman/eSlamsPlatform` repository. Source and live UI inspection confirm that it selects another opponent without changing the rail's ordering seed. Core cannot repair that hosted UI. A separate Platform PR or transfer to the owning repository awaits the user's scope choice; the earlier instruction requires one Core PR. The ledger records concrete UI acceptance criteria. No Platform change is represented as completed.

No merge, new release, deployment, paid provider call, warehouse extraction or production data change has occurred. Existing v0.4.0/v0.5.1 release notes were corrected in place without creating a release.
