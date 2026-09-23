# Retired eval archive

The official evaluation suite is **retired and historical**. Publishing a
scrubbed copy of the former hidden suite is an accepted spoil: those rows
are not a live hidden leaderboard and must not be labeled as one. A Local
Artifact is still not an Official or Grand Slam result.

This document is the archive posture. It does not pull R2, upload to the
Hub, or delete D1. Pin: `eslams-core==0.6.1`.

Row-level classification and the manifest schema live in
`docs/SAMPLE_CLASSIFICATION.md` when that file is in the tree (open
separately as
[PR #14](https://github.com/ElectronicSlams/eSlams/pull/14)). This page
stands alone if that file is absent.

## Still scrub

Every public byte, including the spoiled former hidden proofs, is scrubbed
before it leaves Platform storage:

- provider and API keys, Cloudflare or GitHub tokens, signing private keys
- signed gateway URLs and pre-signed URLs
- auth, Trinity, and session material
- PII (emails, IPs, account join keys)

Also drop raw provider bodies and live hidden seeds from anything that
lands in GitHub `sample_runs/`. A row that cannot be scrubbed does not go
public. Record it as a residual private scrap with a path and a reason.
Do not omit it silently, and do not invent a private dump as the default
destination.

Cards and READMEs for published tiers say the suite is historical, and
that a Local Artifact is not a live Grand Slam.

## Tiers

Counts are plan figures from the 2026-09-21 extract, not a fresh byte
inventory. The **861** success `.eslams` packages are a tic-tac-toe-skewed
canary (860 tic-tac-toe, 1 connect-four). They are not the full 50-arena
suite.

| Tier | What | After scrub | GitHub |
| --- | --- | --- | --- |
| **A** | 861 success run packages (`officialbenchmark`, `artifactkind=run`, `*.eslams`). TTT-skewed canary, not the full suite. | Public `ElectronicSlams/eslams-sample-runs` | Thin samples only, not all 861 blobs. |
| **A-EX** | Curated teaching fails and partials. Cap **≤50** unless the founder raises it. | Same public dataset, labeled `outcome=partial` or `failed`. They may fail SUCCESS validation; say so. | Thin labeled samples, same cap. |
| **B** | Score proofs, `artifactkind=score` under `artifacts/official-hidden%`. **~15,250** rows (~15k), 50 arenas. | Public `ElectronicSlams/eslams-official-suite-archive`. Spoil accepted. | Manifest / pointers only. |
| **C** | Phoenix `strict-clean-v1`. **856** rows, 26 models. | Public `ElectronicSlams/eslams-phoenix-strict-clean` | Pointers only. |
| **C-EX** | Bulk fail and partial archaeology. | Public `ElectronicSlams/eslams-eval-archaeology` | Index / pointers only. Not every scrap as a git blob. |
| **KEEP** | Stadium rows: `arenasession` (136) and `platformmatch` (108). | Stay on D1. Live product. | Not an archive object. |
| **DUMP** | Score-only official-benchmark leftovers, `leaderboardrows`, and evidence. | Public Hugging Face **if scrubbed** (with C-EX on `eslams-eval-archaeology`). Otherwise residual private scraps plus a reason. | Pointers only when the row is public. |

GitHub’s public pack is A and A-EX samples, plus manifests that point at
the Hub for B, C, C-EX, and scrubbed DUMP. The public warehouse is all of
those tiers. KEEP never moves.

Existing tracked samples (`sample_runs/model_battle_sample/`,
`sample_runs/model_eval_sample/`) are small fixtures already in git. They
are not this archive. `sample_runs/README.md` still names battle id
`run_d48ff364a0b949df`; the file on disk is
`run_eeab67d58b994ca7.eslams`. Reconcile that in the classification doc,
not by copying archive bytes into this pull request.

## Hosting

Hugging Face under org `ElectronicSlams` is the public warehouse. GitHub
holds thin samples and manifests or pointers only. Do not commit the R2
tree (on the order of **~29 GiB**; the 2026-09-21 extract also cited
~32 GB). Org creation, dataset names, and the Static docs Space are in
[Hugging Face org and lab secrets](HF_ORG_AND_SECRETS.md).

Free public Hub storage is best-effort. Stage uploads when the founder
unlocks the pull. Start with A. A private Hub dataset is not the plan for
tiers that scrub clean.

## R2 pull

**HOLD** until the founder says go. Do not pull R2, and do not publish
from R2, in this change.

When the hold lifts, work in this order:

1. **A** — validate, replay, scrub.
2. **A-EX** — curate at most 50 teaching fails.
3. **B** — scrub score proofs, then public Hub.
4. **C** — scrub phoenix strict-clean, then public Hub.
5. **C-EX** — scrub archaeology, and scrubbed **DUMP** with it, then
   public Hub. Anything that cannot be scrubbed stays a residual private
   scrap with a reason.

GitHub at the end of that sequence still receives samples and pointers,
not the warehouse.

## D1

No D1 deletes until dual-home is verified: the scrubbed object is on the
public Hub (and on GitHub, for rows that are supposed to have a sample or
a pointer) and someone has checked the manifest hashes. Founder and
Platform confirm that step. KEEP rows (`arenasession`, `platformmatch`)
stay on D1 either way. Export for the archive is read-only. Do not copy
the warehouse back into stadium D1; a later slim sample allowlist is a
different, smaller set.

## Status

| Item | State |
| --- | --- |
| Official suite | Retired / historical. Spoil of the former hidden suite accepted. |
| Scrub | Required: keys, signed gateway URLs, auth / Trinity, PII. |
| R2 pull | HOLD until the founder says go. Order A → A-EX → B → C → C-EX. |
| D1 | No deletes until dual-home is verified. KEEP stays. |
| This pull request | Docs only. No blobs, no Hub upload, no secrets. |

Contact: `hello@eslams.com`.
