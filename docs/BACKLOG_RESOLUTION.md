# Backlog consolidation

This work consolidates the original backlog into [PR #218](https://github.com/ElectronicSlams/eSlams/pull/218). No release has been published. Individual implementation evidence, acceptance criteria and verified GitHub closures are recorded in [the complete ledger](backlog-resolution.json).

## Verified closures

104 of 149 inventoried issues and 18 of 44 original PRs are closed. The consolidation PR remains draft while the remaining work is completed. Implemented entries awaiting integration checks are separate from verified closures.

The latest verified native/distribution checkpoint is `2d3aafb`. The native matrix passes Linux Python 3.10–3.12 and Windows/macOS Python 3.12. The TypeScript job compiles Core-lite and checks 22 initial states and 1,401 complete deterministic step responses against Python authority fixtures. Fresh wheel and sdist consumers verify console/module normal/debug/closed-pipe behavior, downstream mypy, keyless run/validate/replay/public export, schema provenance, metadata and the full extracted no-Git sdist suite.

- [Core CI](https://github.com/ElectronicSlams/eSlams/actions/runs/37756648047)
- [Distribution consumers](https://github.com/ElectronicSlams/eSlams/actions/runs/37756648060)
- [Dependency audit](https://github.com/ElectronicSlams/eSlams/actions/runs/37756648057)
- [Workflow lint](https://github.com/ElectronicSlams/eSlams/actions/runs/37756648045)

## Test reduction

The frozen baseline `7f6bb418974739986e76049d45dfb7de2109a780` contains 275 cases and 85.332886% line coverage over `src/eslams`. All 55 required original cases (20%) have been removed, mainly by consolidating redundant wrappers while preserving useful assertions. Baseline identities and retained assertion locations are recorded in the ledger. New behavioral/integrity regressions are tracked separately.

At the latest measured checkpoint, 479 cases pass on Python 3.12 and 11,281 / 12,849 lines are covered (87.796716%). The earlier direct dependency-floor Python 3.10 checkpoint passes 475 cases at 87.441571%. New changes require the final full suite and same-scope coverage gate.

## Remaining work

Remaining entries include provider lifecycle/discovery and deadlines, further game-rule corrections, replay accessibility/rendering, publication correctness and coherent lab/sample documentation. The hosted Platform issue requires an explicit scoped disposition. No merge, new release, deployment or paid provider call has occurred.
