# Wave B SUCCESS / EXTRACT tiers

Revised **2026-09-21** under the public-archive founder lock.
See [founder-locks.md](founder-locks.md) and the runbook in [README.md](README.md).

**861** run `.eslams` packages are a tic-tac-toe-skewed canary (860 tic-tac-toe
+ 1 connect-four). The retired suite inventory is the 50-arena match and score
set, the score proofs, and phoenix strict-clean. The suite is historical.
Spoil is accepted. Publish waits on the HOLD gates.

## Tiers (public only after scrub)

| Tier | What | Count / shape | After scrub | Notes |
| --- | --- | --- | --- | --- |
| **A** | SUCCESS run packages: `officialbenchmark` + `artifactkind=run` + `%.eslams` | **861**, TTT-heavy, ~1.110 GiB | GitHub `sample_runs/` samples + public HF | Canary slice. Label it as a canary. |
| **A-EX** | Curated partial / fail examples | **≤50** unless the founder raises the cap | GitHub `sample_runs/` examples + public HF | Teaching fails. They may fail SUCCESS validate. **Not curated yet.** |
| **B** | `artifactkind=score` under `artifacts/official-hidden%` | **~15,250** / 50 arenas | Public HF warehouse. GitHub pointers / manifest only | Spoil accepted. Scrub gateway URLs and secrets. |
| **C** | phoenix `strict-clean-v1` sources | **856** / 26 models | Public HF + GitHub pointers | Resolve the R2 key, then scrub. |
| **C-EX** | Bulk fail / partial archaeology | long tail | Public HF archaeology dataset + GitHub index | Full scraps stay off GitHub blobs. |
| **KEEP** | `arenasession` (136) + `platformmatch` (108) | Stadium / Battlefield | Stay on D1 | Live product. Out of every delete list. |
| **DUMP→PUBLIC** | score-only official benchmark rows + `leaderboardrows` / evidence | leaderboard bulk | Public HF when scrubbed | If a row cannot be scrubbed, residual private scraps with a reason. Prefer public. |

**GitHub pack:** A samples + A-EX samples + thin manifests that point at HF for B, C, C-EX, and DUMP.

**HF warehouse (org ElectronicSlams, names are the plan):**

| Dataset | Contents |
| --- | --- |
| `eslams-sample-runs` | A + A-EX |
| `eslams-official-suite-archive` | B score proofs (scrubbed) |
| `eslams-phoenix-strict-clean` | C |
| `eslams-eval-archaeology` | C-EX + scrubbed leaderboard DUMP |

HF free tier: stage uploads. The full tree is on the order of the R2 listing (~28.7 GiB). Stage A first. A grant or a paid tier may be required before B and the replay-heavy prefixes.

## A-EX selection (cap ≤50)

Include a row when it teaches something, scrubs clean, is labeled
`outcome=partial|failed`, and adds diversity. Mine `resultsummary`, the
`queuefailures` rows (6, status `retrying` at the 2026-09-20 snapshot), and
phoenix audit rows only when they scrub clean. Exclude raw secret paths and
near-duplicate tic-tac-toe timeouts.

## Locked SQL

Recorded filters from the read-only inventory. **Do not execute these
statements from CI, from this repository's workflows, or as a production
wrangler call attached to this PR.** The tier A count is **861**.

### A — SUCCESS `.eslams` (locked)

```sql
SELECT m.id AS match_id, m.arenaid, a.id AS artifact_id, a.artifactkind, a.r2key, a.contentsha256, a.sizebytes
FROM matches m
JOIN artifacts a ON a.matchid = m.id AND a.artifactkind = 'run' AND LOWER(a.r2key) LIKE '%.eslams'
WHERE m.matchtype = 'officialbenchmark' AND m.status = 'completed'
  AND IFNULL(m.agenterrorcount,0)=0 AND IFNULL(m.fallbackactioncount,0)=0;
-- 861
```

### B — score proofs (public warehouse after scrub)

```sql
SELECT m.id, m.arenaid, a.r2key, a.contentsha256, a.sizebytes
FROM matches m
JOIN artifacts a ON a.matchid = m.id AND a.artifactkind = 'score'
WHERE m.matchtype = 'officialbenchmark' AND a.r2key LIKE 'artifacts/official-hidden%';
```

### C — phoenix strict-clean

```sql
SELECT runid, requestedmodelid, sourcekind, assurancelevel, sourceartifactkey, artifactsha256
FROM phoenix_runs
WHERE sourcekind = 'strict-clean-v1' AND sourceartifactkey IS NOT NULL;
```

## Scrub checklist

Apply to every public tier before publish:

- [ ] Provider / API keys, Cloudflare / GitHub tokens, signing private keys
- [ ] Signed gateway and pre-signed URLs
- [ ] Auth / Trinity / session material
- [ ] PII (emails, IPs, account join keys)
- [ ] Card labels: historical / retired Official suite; local runs are not a live Grand Slam
- [ ] Manifest fields: sha256, tier, arena, model, scrub notes

A failure that cannot be scrubbed is a residual-private scrap: record the path
and the reason. Do not publish it and do not omit it silently.

## Hosting sketch

```text
GitHub ElectronicSlams/eSlams
  sample_runs/            # existing samples; future A / A-EX additions are a later PR
  docs/wave-b/manifests/  # short counts only — not the 861-row jsonl

HF public (org ElectronicSlams)
  eslams-sample-runs
  eslams-official-suite-archive
  eslams-phoenix-strict-clean
  eslams-eval-archaeology
```

This PR does not create those directories of blobs and does not upload to HF.
