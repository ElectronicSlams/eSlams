# Wave B census

R2 prefix census: **complete** (2026-09-21, ~08:17 PT).
D1 figures below are read-only snapshots from 2026-09-17 through 2026-09-21.
This page does not authorize a new query, export, or pull.

**Pull remains HOLD.** See [README.md](README.md).

## R2 `eslams-artifacts-prod`

Method: read-only `ListObjectsV2`. Elapsed 1703.7s.
Account id is omitted; the bucket name is the ops handle used here.
Listed bytes and the wrangler bucket-info label both describe the same object count.

| | Objects | Bytes |
| --- | ---: | ---: |
| Listed sum | **1,739,537** | **30,810,380,496** (~28.69 GiB) |
| Wrangler bucket-info label | 1,739,537 | ~31.6 GB |

### Top-level prefixes

| Prefix | Objects | Bytes | GiB |
| --- | ---: | ---: | ---: |
| `artifacts/` | 578,310 | 10,728,373,212 | 9.99 |
| `replays/` | 1,157,178 | 15,990,886,407 | 14.89 |
| `runs/` | 4,035 | 3,993,973,486 | 3.72 |
| `leaderboards/` | 3 | 96,991,369 | 0.09 |
| `artifact-replays/` | 4 | 36,703 | 0.00 |
| `incoming/` | 3 | 89,614 | 0.00 |
| `videos/` | 4 | 29,705 | 0.00 |
| `hidden-evals/` | 0 | 0 | 0.00 |
| **Sum** | **1,739,537** | **30,810,380,496** | **28.69** |

### Prefixes that map to tiers

S3 object counts are larger than D1 index rows: R2 stores many objects per case.
A future pull uses a tier manifest. It does not copy the bucket.

| Path | S3 objects | Bytes | GiB | D1 index (snapshot) |
| --- | ---: | ---: | ---: | --- |
| `runs/officialbenchmark/` | 3,877 | 3,984,497,105 | 3.71 | Tier A SUCCESS `.eslams` subset = **861** (~1.11 GiB) |
| `runs/platformmatch/` | 158 | 9,476,381 | 0.01 | KEEP `platformmatch` **108** |
| `artifacts/official-hidden-v2-cloud/` | 542,071 | 10,624,374,636 | 9.89 | score index ~14,750 |
| `artifacts/official-hidden-v2/` | 36,000 | 102,593,184 | 0.10 | score index ~500 |
| `artifacts/officialbenchmark/` | 223 | 1,344,338 | 0.00 | |
| `artifacts/battlefield-smoke/` | 16 | 61,054 | 0.00 | |
| `replays/official-hidden-v2-cloud/` | 1,084,142 | 15,367,661,626 | 14.31 | |
| `replays/official-hidden-v2/` | 72,000 | 596,509,580 | 0.56 | |
| `replays/official-hidden*` (both) | 1,156,142 | | ~14.87 | D1 `replays` table ~15.5k keys |
| `replays/officialbenchmark/` | 446 | 15,291,126 | 0.01 | |
| `replays/arena/` | 294 | 3,328,353 | 0.00 | KEEP `arenasession` **136** |
| `leaderboards/phoenix/` | 2 | 95,162,564 | 0.09 | Tier C has no dedicated run prefix. `strict-clean-v1` = **856** |
| `leaderboards/legacy/` | 1 | 1,828,805 | 0.00 | Archaeology / DUMP after A → B → C |

Per-id prefixes under `replays/` (two objects each) are omitted from this summary.

`hidden-evals/` listed empty. A July 2026 forensic note cited ~2,762 suite source bundles and ~3.6 GB. The completed prefix census did not re-list that set; treat those figures as historical until a future founder-cleared listing checks them.

## D1 `eslams-prod` index (snapshot, not a dump)

Database file size was about 5 GB (≈4.97 GB on 2026-09-17, ≈5.09 GB on 2026-09-20).
The `artifacts` table is a thin pointer index, not the R2 inventory: **16,363** rows, `SUM(sizebytes)` ≈ **1.39 GB**, against **1,739,537** R2 objects.

| Table | Rows | Snapshot note |
| --- | ---: | --- |
| `matches` | 16,355 | all `status=completed` in the post-prune snapshot |
| `artifacts` | 16,363 | R2 pointer index |
| `scores` | 15,255 | all `integritystatus=legacy`, `sourcevalidforscoring=0` |
| `replays` | 15,499 | keys under `replays/**` |
| `runjobs` | 969 | all `status=completed`; 2 retain a historical `lasterror` |
| `phoenix_runs` | 949 | all `status=ingested`, `assurancelevel=historical_recovered` |
| `runplandrafts` | 8,609 | |
| `leaderboardrows` | 128,830 | retired leaderboard bulk (DUMP) |
| `leaderboard_evidence` | 2,027 | retired leaderboard bulk (DUMP) |
| `queuefailures` | 6 | all `status=retrying` — A-EX candidate source, not a selection |
| `officialevalruns` / `officialrunquality` / `officialrunfinalizations` | 0 | empty |

`artifacts` by kind:

| `artifactkind` | Rows | `SUM(sizebytes)` |
| --- | ---: | ---: |
| score | 15,255 | 290,545,460 |
| run | 969 | 1,199,879,960 |
| replay | 136 | 283,335 |
| upload | 3 | 89,614 |

Indexed `r2key` families used for planning:

| Family | Kind | Rows | Bytes (approx) |
| --- | --- | ---: | --- |
| `artifacts/official-hidden-v2-cloud/` | score | 14,750 | ~276 MB |
| `artifacts/official-hidden-v2/` | score | 500 | ~1.4 MB |
| `runs/officialbenchmark/` + `%.eslams` SUCCESS filter | run | **861** | ~1.11 GB |
| other `runs/` | run | 108 | ~8.2 MB |
| `replays/` with `artifactkind=replay` | replay | 136 | ~277 KB |

Phoenix `sourcekind`: **856** `strict-clean-v1`, **93** `projected-single-audit-v1`. Tier C is the 856. All 949 phoenix rows were `status=ingested`.

Official-benchmark-linked artifacts in the index: **861** run + **15,255** score = **16,116**.

Score rows in this snapshot are legacy and not valid for current scoring. Public packs must not claim live Official eligibility.

## HOLD, restated

1. Founder go is still required. The census being finished does not open the pull.
2. Scrub checklist and the A-EX ≤50 cap are still open as planning gates.
3. Expect S3 object counts to stay far above D1 row counts for B and replays. Pull from tier manifests.
4. No full D1 dump. A sketched full `d1 export` of the ~5 GB database is not part of this plan.
5. R2 pull of tier A comes before any D1 delete. Delete waits on dual-home verify and the founder.
