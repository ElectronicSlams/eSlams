# Sample classification — GOOD vs BAD/FAULT/RETIRED

> Wave A · pin `eslams-core==0.6.1` · no prod D1 deletes · HF uploads = Wave B

---

## 1. Purpose

Decide which run artifacts become **dual-homed curated samples** (GitHub `sample_runs/` + fixtures **and** public HF `ElectronicSlams/eslams-sample-runs`) versus which go to a **scrubbed private HF dump** (`eslams-retired-eval-dump`) or stay Platform-internal theater only.

**Constraints:** classify/plan in this doc; **no prod D1 deletes**; HF org not live yet (Wave B).

---

## 2. Inventory sources

| Source | What to list | Owner | Notes |
| --- | --- | --- | --- |
| **GitHub `sample_runs/`** | Known curated packages | OSS (R) | See table below |
| **GitHub `fixtures/`** | Test / signed fixtures | OSS (R) | Fixture key caveats |
| **Battlefield live demos** | ~108 `replay_*` embeds · NOW SHOWING | Platform URLs; OSS catalogs ids | Prefer live URLs for stranger demos |
| **Platform D1 retired LB / eval** | Retired leaderboard + eval rows | Platform (R) read-only export | **Inventory TBD** — Wave B; no delete |
| **Scratch / local harness** | Exploratory runs, CI temp | OSS | Default **omit** from public dual-home |

### 2.1 Known GitHub `sample_runs/` entries

| Path / id | Role | README vs disk |
| --- | --- | --- |
| `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams` | Battlefield-sample shape; best OSS ingest/viz fixture | On-disk first-legal. README still cites `run_d48ff364a0b949df` — **id drift** |
| `sample_runs/model_eval_sample/official_signed.eslams` | Official-proof shape for docs/CI | Fixture key caveats — review before public-export claims |
| README mention `run_d48ff364…` | Documented battle sample | **Drift** — REVIEW until reconciled with `run_eeab67d58b994ca7` |

### 2.2 Platform D1 (placeholder)

| Bucket | Status |
| --- | --- |
| Retired LB tables | Platform inventory TBD |
| Retired / failed eval rows | Platform inventory TBD |
| Slim stadium sample copies (future) | Allowlist-only after GOOD dual-publish — not trash |

---

## 3. GOOD criteria

A candidate is **GOOD** (dual-home eligible) only if **all** apply:

1. **Validates** under intended profile (`eslams validate` / publish validate / runner-bundle as appropriate).
2. **Deterministic replay** passes.
3. **No recorded error-log** entries.
4. **Model-battle samples:** must **not** rely on missing-key **fallback** actions (fail-closed / no fallback pollution).
5. **Public-exportable:** survives public-export / publication-bundle hygiene — no secrets, PII, raw provider bodies, or live hidden seeds.
6. **Dual-home candidate:** stable `sample_id`, reproducible bytes (or documented pin), suitable for GitHub + public HF under `eslams-core==0.6.1`.
7. **Messaging-safe:** can be labeled Local / fixture / historical demo — never implied as live Official LB score.

---

## 4. BAD / FAULT / RETIRED criteria

Tag **BAD**, **FAULT**, or **RETIRED** (dump path) if **any** apply:

| Tag | Meaning | Examples |
| --- | --- | --- |
| **BAD** | Broken or unsafe for public | Broken LB rows, incomplete traces, trash sims, validation fail |
| **FAULT** | Failed eval / error-path pollution | Provider failures recorded as success, fallback-heavy battles |
| **RETIRED** | Obsolete product surface | Retired leaderboard suite rows, superseded suites |
| **SECRET_RISK** | Must not go public | Secret seeds, PII, unredacted provider payloads, org key material |
| **INCOMPLETE** | Partial artifact | Missing joins, truncated receipts, Replay Not Found corpses |

**Default disposition:** scrub minimum → **private HF** `eslams-retired-eval-dump` (≤100GB free). Scrubbed **public** mirror only with founder sign-off. Prefer HF over R2.

---

## 5. Process steps

```
0  Founder locks (HF org, dump visibility) — Wave B gate for uploads
1  Inventory  →  manifest of ids / paths / sizes
2  Classify   →  GOOD | BAD | FAULT | RETIRED | SECRET_RISK | INCOMPLETE | REVIEW
3  Scrub
     GOOD  → public-export / drop secrets·PII·raw provider·hidden seeds
     BAD*  → same redaction minimum; residual risk → private HF only
4a Dual-publish GOOD → GitHub sample_runs/ + HF eslams-sample-runs (after Wave B)
4b Dump BAD* → HF eslams-retired-eval-dump (private default)
5  Record dual-publish manifest (sha256, paths, core_pin, status)
6  Optional: Platform slim D1 allowlist sync (sample metadata only — not trash)
```

**No D1 deletes.** Export is read-only. Full trash lives on HF after scrub; slim D1 never re-imports retired dump wholesale.

---

## 6. Dual-publish manifest schema (draft)

```json
{
  "sample_id": "run_eeab67d58b994ca7",
  "sha256": "<hex of .eslams bytes or publication root>",
  "github_path": "sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams",
  "hf_path": "model_battle_sample/run_eeab67d58b994ca7.eslams",
  "hf_repo": "ElectronicSlams/eslams-sample-runs",
  "kind": "battlefield-sample",
  "core_pin": "eslams-core==0.6.1",
  "status": "GOOD",
  "dual_home": true,
  "validate_profile": "runner-bundle",
  "notes": "prefer on-disk id over README run_d48ff364…",
  "updated_at": "2026-09-10T00:00:00Z"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `sample_id` | yes | Stable public id |
| `sha256` | yes | Drift detection GH ↔ HF |
| `github_path` | yes for dual-home | Repo-relative |
| `hf_path` | yes when HF live | Path inside dataset |
| `hf_repo` | yes when HF live | Default `ElectronicSlams/eslams-sample-runs` |
| `kind` | yes | e.g. `battlefield-sample`, `official-proof` |
| `core_pin` | yes | `eslams-core==0.6.1` |
| `status` | yes | `GOOD` \| `REVIEW` \| `BAD` \| `FAULT` \| `RETIRED` \| `HELD` |
| `dual_home` | yes | `true` only when GH + HF bytes agree |
| `validate_profile` | recommended | Profile used to certify GOOD |
| `notes` | optional | Id drift, fixture caveats |

Dump-only rows may set `dual_home: false`, `hf_repo: ElectronicSlams/eslams-retired-eval-dump`, omit `github_path`.

---

## 7. Initial classification table

| sample_id / path | kind | Proposed status | Rationale / next check |
| --- | --- | --- | --- |
| `run_eeab67d58b994ca7` · `model_battle_sample/` | battlefield-sample | **GOOD** (candidate) | Confirm validate + no fallback + public-export before dual-publish |
| `official_signed` · `model_eval_sample/` | official-proof | **REVIEW** | Fixture key caveats — do not over-claim Official trust |
| README `run_d48ff364a0b949df` | (stale doc) | **REVIEW** | Id drift vs `run_eeab67d58b994ca7`; fix README in a follow-up |
| Battlefield ~108 `replay_*` | live demo | **REVIEW** (Platform theater) | Link from `/labs`; HF mirror optional |
| Platform D1 retired LB/eval | retired / trash | **RETIRED** (pending inventory) | Export → scrub → private HF |
| Scratch harness / exploratory | n/a | **BAD** / omit | Not public dual-home |

Statuses above are **plan tags**, not a completed validate pass.

---

## 8. RACI

| Workstream | Platform | OSS | Founder |
| --- | --- | --- | --- |
| Inventory GitHub samples/fixtures | I | **R** | A |
| Inventory D1 retired LB/eval | **R** | I | A |
| Classification criteria + manifest | C | **R** | A |
| Dual-publish GOOD (GH + HF) | I | **R** | A |
| Dump BAD → private HF | R (export) | **R** (upload) | A |
| README id-drift fix | I | **R** | A |
| Slim D1 sample allowlist | **R** | C | A |
| Secrets / seeds never in goods | **R** | **R** | A |

---

## 9. Status

Wave A docs only. No HF uploads until Wave B. No prod D1 mutations.

Contact: hello@eslams.com · eslams.com

See also: [`docs/LABS.md`](./LABS.md) (Lab Quickstart) · [`docs/LABS_PAGE_CONTRACT.md`](./LABS_PAGE_CONTRACT.md) (Platform `/labs` contract).
