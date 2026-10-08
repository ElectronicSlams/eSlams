# Backlog consolidation

This work consolidates the original backlog into [PR #218](https://github.com/ElectronicSlams/eSlams/pull/218). No release has been published. Issues and original PRs close only after their resolution and verification are recorded in [the individual ledger](backlog-resolution.json).

## Verified closures

86 of the 149 inventoried issues and 16 of the 44 original PRs are closed.
The consolidation PR remains draft. The remaining entries include implemented
changes awaiting integration checks and unresolved work; neither is complete.

The latest verified distribution checkpoint is `f5971d7`. Native full-suite,
Ruff, strict typing and TypeScript checks pass on Linux Python 3.10–3.12 and
Windows/macOS Python 3.12. Separate fresh wheel and sdist installations pass
console/module normal and debug errors, closed-pipe behavior, downstream mypy,
keyless run/validate/replay/public export, schema provenance and metadata checks.
The extracted sdist runs its full suite outside a Git checkout.

- [Core CI](https://github.com/ElectronicSlams/eSlams/actions/runs/37751738060)
- [Distribution consumers](https://github.com/ElectronicSlams/eSlams/actions/runs/37751738110)
- [Dependency audit](https://github.com/ElectronicSlams/eSlams/actions/runs/37751738120)
- [Workflow lint](https://github.com/ElectronicSlams/eSlams/actions/runs/37751738093)

## Test reduction

The frozen baseline at `7f6bb418974739986e76049d45dfb7de2109a780` has
275 passing cases and 85.332886% line coverage over `src/eslams`.
All 55 required original cases (20% of 275) have been removed, mainly by combining
redundant wrappers and preserving their assertions in retained tests.
No further removals are needed. New behavioral, privacy and integrity regressions are
tracked separately from the baseline removals.

The last measured consolidation checkpoint has 471 passing cases on current
Python 3.12 and direct-floor Python 3.10, covering 11,182 / 12,802 lines
(87.345727%). This is an intermediate checkpoint; new changes still require
a final full-suite and same-scope coverage gate.

## Remaining work

The JSON ledger records every issue and original PR, captured original heads,
acceptance criteria, implementation evidence and actual closure state. Remaining
work includes Core-lite/Python contract parity, provider lifecycle/discovery and
deadlines, further game-rule corrections, replay accessibility/rendering,
publication correctness and coherent lab/sample documentation. The hosted
Platform issue must receive an explicit scoped disposition.

No merge, new release, deployment or paid provider call has been performed.
