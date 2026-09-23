# Retired eval archive — dataset lock

The official suite is retired and historical. A scrubbed public copy of the
former hidden suite is an accepted spoil. It is not a live leaderboard.
**Local Artifact ≠ Official / Grand Slam** on every archive card.

Tier criteria, the scrub checklist, manifest fields, and the GitHub sample
review are `docs/SAMPLE_CLASSIFICATION.md`
([PR #14](https://github.com/ElectronicSlams/eSlams/pull/14)). That doc
left the Hub layout open (one repo with prefixes, or sibling datasets).
This page locks sibling datasets. It does not restate classification.

The lab pack is only `ElectronicSlams/eslams-sample-runs` (A and A-EX).
Point newcomers there, not at the archive repos. See
[HF lab pack readiness](HF_ORG_AND_SECRETS.md).

## Where each tier goes

| Tier | Hub dataset | GitHub |
| --- | --- | --- |
| **A** — 861 success `.eslams`, tic-tac-toe-skewed canary, not the full suite | `ElectronicSlams/eslams-sample-runs` | Thin samples, not all 861 blobs |
| **A-EX** — ≤50 labeled teaching fails | same dataset | Thin labeled samples |
| **B** — ~15,250 score proofs (`artifacts/official-hidden%`) | `ElectronicSlams/eslams-official-suite-archive` | Manifest pointers only |
| **C** — 856 phoenix `strict-clean-v1` rows | `ElectronicSlams/eslams-phoenix-strict-clean` | Pointers only |
| **C-EX** and scrubbed **DUMP** (leaderboard leftovers) | `ElectronicSlams/eslams-eval-archaeology` | Index only |
| **KEEP** — `arenasession` (136), `platformmatch` (108) | Stay on D1 | Not an archive object |

Counts are the 2026-09-21 extract figures. Scrub before any public byte:
keys, signed gateway URLs, auth / Trinity material, PII. A row that cannot
be scrubbed stays a residual private scrap with a reason. Private Hub is
not the default for B or C.

`ElectronicSlams/eslams-retired-eval-dump` as a private default is not the
plan.

## Size, pull, D1

GitHub does not hold the R2 tree (~29 GiB; the same extract also cited
~32 GB).

R2 pull is **HOLD** until the founder says go. Order after that:
**A → A-EX → B → C → C-EX**, with scrubbed DUMP in the C-EX step.

No D1 deletes until dual-home is verified (scrubbed object on the public
Hub, and on GitHub when the tier has a sample or a pointer). KEEP rows
stay on D1 either way. Do not copy the warehouse back into stadium D1.

No blobs are uploaded in this change.
