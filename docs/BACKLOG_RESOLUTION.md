# Backlog consolidation

The backlog is addressed in [Core PR #218](https://github.com/ElectronicSlams/eSlams/pull/218) and one focused [Platform PR #580](https://github.com/makriman/eSlamsPlatform/pull/580), under the user's amended allowance for a reasonable number of PRs. **All 149 inventoried issues and all 44 original PRs are verified closed.** Original heads and branches are preserved, including the two fork branches. The complete [ledger](backlog-resolution.json) records each reviewed head, acceptance criterion, incorporated or declined proposal, implementation evidence and verified GitHub closure timestamp. The two proposed replacement PRs remain open for review; changes have not been merged or released.

## Verified implementation

Checkpoint `08fb8a4ef07778eca149f235162cc0a1372fe297` passes every required native/distribution gate:

- [Core CI](https://github.com/ElectronicSlams/eSlams/actions/runs/37771327882): Linux Python 3.10–3.12, Windows/macOS Python 3.12; all-50-arena version fingerprints and initial-state budgets; exact native artifact/schema/publication byte parity; Python/TypeScript contracts and 22 initial states plus 1,401 complete Core-lite step responses.
- [Distribution consumers](https://github.com/ElectronicSlams/eSlams/actions/runs/37771327695): fresh wheel/sdist installs outside the checkout on Linux, Windows and macOS; console/module normal/debug/closed-pipe behavior, downstream mypy, keyless run/validate/replay/public export, metadata/schema provenance and the full extracted no-Git sdist suite.
- [Dependency audit](https://github.com/ElectronicSlams/eSlams/actions/runs/37771327692), [workflow lint](https://github.com/ElectronicSlams/eSlams/actions/runs/37771327859) and [CodeQL](https://github.com/ElectronicSlams/eSlams/actions/runs/37771327694).

Browser CI checks all 50 arenas at mobile, tablet and desktop sizes, including 300 initial/final viewport checks, keyboard/focus, target sizes, semantic labels and hostile embedded text. The version diagnostic explicitly normalizes floating values to ten decimal places for cross-libm portability; runtime state hashes and replay validation remain exact.

The final closure-record update changes documentation only and receives normal CI independently of this checkpoint. Both replacement PRs must pass their final-head gates before completion is reported.

## Test reduction

Frozen baseline `7f6bb418974739986e76049d45dfb7de2109a780` contains 275 cases and 85.332886% line coverage over `src/eslams`. Exactly 55 original cases (20%) are removed, mainly by consolidating redundant wrappers while retaining useful assertions. The ledger records baseline identities and retained assertion locations. No removed function is reintroduced; new behavioral/integrity regressions are tracked separately.

All 509 cases pass on local Python 3.12 and direct-dependency-floor Python 3.10. Both cover 11,851 / 13,368 lines (88.652005%), 3.319119 percentage points above baseline. Ruff and strict mypy pass. All eight published 0.6.1 keyless lab commands pass in a fresh external virtual environment. Current sample inventories record exact archive checksums and clean generation commits, honest Local status and no unverified mirrors.

## Hosted Shuffle resolution

[#219](https://github.com/ElectronicSlams/eSlams/issues/219) is closed after verified implementation in [Platform PR #580](https://github.com/makriman/eSlamsPlatform/pull/580), commit `2e4a4f56fd206872ef3434da7139babbb48188ea`. Shuffle now permutes every displayed eligible opponent while preserving the selected model, side and launch parameters. Repeated clicks change the order; zero/one-option rails remain disabled. Catalog changes retain only current eligible rows, and a different game resets the local ordering. The existing rail limit, full roster picker and table autofill remain intact.

The browser regression reproduces the bug on unchanged main. Six new and four existing browser checks pass across desktop/mobile, including keyboard/focus and all six multi-seat game autofills. Frozen install, lint, full typecheck/build and complete `pnpm test` pass: 1,268 root cases and all 18 workspace test tasks, including 715 web cases and 109 Workerd runtime cases. [Native offline React Doctor](https://github.com/makriman/eSlamsPlatform/actions/runs/38114322660) passes on the exact Platform head; the local scan covers 568 files with zero diagnostics. A stale unchanged-main release assertion is aligned with the existing offline CI policy, retaining its exact-source guard and all 68 policy/release-identity checks. Three-way composition with separate Arena setup PR #466 is conflict-free. The Platform source remains proposed, unmerged and undeployed.

No merge, new release, deployment, paid provider call, warehouse extraction or production data change has occurred. Existing v0.4.0/v0.5.1 release notes were corrected in place without creating a release.
