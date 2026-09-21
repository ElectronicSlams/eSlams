# Sample classification — public-by-default SUCCESS-EXTRACT tiers

> Wave A · pin `eslams-core==0.6.1` · no prod D1 deletes · **R2 pull = HOLD** · HF uploads = Wave B  
> Founder lock **2026-09-20/21** (public-by-default). Founder/Jev prefer **PR #13** Lab Quickstart merge first; **this PR stays draft**.

---

## 1. Purpose

Classify run artifacts for a **Hugging Face public warehouse** (Wave B) with **GitHub samples + pointers/manifests only**. Default is **public after scrub**. Private HF exists only for **residual scraps that cannot be scrubbed**, with a reason log — not as the dump destination.

This supersedes the earlier GOOD-vs-private-dump plan. Old tags (`GOOD` / `BAD` / `FAULT` / `RETIRED`) map onto the SUCCESS-EXTRACT tiers below; do not invent a parallel vocabulary.

**This PR (Wave A) is docs only:** classify/plan here. **No** R2 pull, **no** HF publish, **no** prod D1 deletes, **no** deploy, **no** merge until founder confirm (and #13 first).

---

## 2. Hosting and scrub (always)

| Surface | Role |
| --- | --- |
| **Hugging Face public warehouse** | Canonical bulk store for scrubbed A / A-EX / B / C / C-EX / DUMP-LB |
| **GitHub** | Curated **samples** (A dual-home + labeled A-EX) and **pointers/manifests** only — not the warehouse |
| **D1 KEEP** | `arenasession` + `platformmatch` stay on Platform D1 |
| **Private HF scraps** | Only residuals that fail scrub, plus a **reason log** |
| **R2** | **HOLD** — do not pull, do not publish from R2 in this wave |

**Scrub always (every public byte):** API keys and secrets, signed gateway URLs, auth / Trinity material, PII. Drop raw provider bodies and live hidden seeds from GitHub samples. Residual risk that cannot be scrubbed → private scraps + reason log, never public GH/HF.

Prefer HF over R2 for warehouse hosting. R2 remains the Platform proof store; this lock does **not** authorize an R2 extract.

---

## 3. SUCCESS-EXTRACT tiers (lock)

| Tier | Inventory (plan counts) | Disposition | GitHub | Notes |
| --- | --- | --- | --- | --- |
| **A** | **861** success-run `.eslams` | **Public** GH samples + **public HF** | Dual-home representative samples in `sample_runs/` + pointer to HF warehouse of the 861 | **TTT-skewed canary. NOT a full suite.** Do not market as complete Official coverage. |
| **A-EX** | Curated **≤50** partial/fail examples | **Public** (labeled) | May live in GH as labeled examples + HF | **May not pass SUCCESS validate** — document the **expected failure** on every row. Not a silent BAD dump. |
| **B** | **~15250** score proofs under `artifacts/official-hidden%` | **Public HF after scrub** | Pointers/manifests only | **Spoil accepted.** Suite = **retired / historical**. Not a live hidden Official board. |
| **C** | **856** phoenix **strict-clean-v1** | **Public HF after scrub** | Pointers/manifests only | Phoenix clean subset; still scrub before publish. |
| **C-EX** | Bulk archaeology | **Public HF** after scrub | **Pointers / manifests only** — no bulk in git | Warehouse-only; GH catalogs ids/paths/hashes. |
| **KEEP** | `arenasession` + `platformmatch` | **Stay on D1** | n/a | Read-only for this plan. **No D1 deletes.** |
| **DUMP LB** | Retired leaderboard bulk | **Public HF if scrubbed**; else **residual private scraps + reason log only** | Pointers/manifests if public | Private is the exception, not the default. |

Counts above are **SUCCESS-EXTRACT plan figures**, not a completed byte inventory. Reconcile at Wave B export time; do not block this doc on exact D1/R2 listings.

### 3.1 Mapping from the old GOOD/BAD vocabulary

| Old tag | Maps to |
| --- | --- |
| **GOOD** dual-home candidate | **A** (and existing GH `sample_runs/` rows pending validate) |
| **BAD** / **FAULT** / **INCOMPLETE** (curated teaching examples) | **A-EX** (≤50, labeled, expected validate failure documented) |
| **RETIRED** official-hidden score proofs | **B** (public HF after scrub; spoil accepted) |
| Phoenix strict-clean | **C** |
| Bulk archaeology / uncurated retired eval | **C-EX** |
| Retired LB dump | **DUMP LB** |
| Live Arena / match rows | **KEEP** |
| **SECRET_RISK** after scrub still unsafe | Residual **private scraps** + reason log |

---

## 4. Inventory sources

| Source | What to list | Owner | Notes |
| --- | --- | --- | --- |
| **GitHub `sample_runs/`** | Known curated packages (A / A-EX samples) | OSS (R) | See table below |
| **GitHub `fixtures/`** | Test / signed fixtures | OSS (R) | Fixture key caveats — not warehouse |
| **Battlefield live demos** | ~108 `replay_*` embeds · NOW SHOWING | Platform URLs; OSS catalogs ids | Prefer live URLs for stranger demos; optional HF mirror later |
| **SUCCESS-EXTRACT A/B/C** | 861 / ~15250 / 856 (plan) | Platform export (R) + OSS warehouse (R) | Wave B; **R2 pull HOLD** until founder lifts it |
| **Platform D1 KEEP** | `arenasession`, `platformmatch` | Platform (R) | Stay on D1 |
| **Platform D1 DUMP LB** | Retired leaderboard bulk | Platform (R) read-only export | Public HF after scrub, else scraps + reason log |
| **Scratch / local harness** | Exploratory runs, CI temp | OSS | Default **omit** from GH samples |

### 4.1 Known GitHub `sample_runs/` entries

| Path / id | Role | Proposed tier | README vs disk |
| --- | --- | --- | --- |
| `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams` | Battlefield-sample shape; best OSS ingest/viz fixture | **A** candidate | On-disk first-legal. README still cites `run_d48ff364a0b949df` — **id drift** |
| `sample_runs/model_eval_sample/official_signed.eslams` | Official-proof shape for docs/CI | **A** **REVIEW** | Fixture key caveats — review before public-export claims |
| README mention `run_d48ff364…` | Documented battle sample | **REVIEW** | **Drift** — fix README in a follow-up |

### 4.2 Platform / extract (placeholder until Wave B)

| Bucket | Tier | Status |
| --- | --- | --- |
| 861 success-run `.eslams` (TTT-skewed canary) | **A** | Plan count; not full suite |
| ≤50 labeled partial/fail | **A-EX** | Curate at export; document expected SUCCESS-validate failure |
| ~15250 `artifacts/official-hidden%` score proofs | **B** | Public HF after scrub; spoil accepted; suite retired/historical |
| 856 phoenix strict-clean-v1 | **C** | Public HF after scrub |
| Bulk archaeology | **C-EX** | Public HF; GH pointers/manifests only |
| `arenasession` + `platformmatch` | **KEEP** | Remain on D1 |
| Retired LB bulk | **DUMP LB** | Public HF if scrubbed; else private scraps + reason log |
| Slim stadium sample copies (future) | Allowlist of **A** (and labeled **A-EX**) metadata only | Never import warehouse bulk into D1 |

---

## 5. GitHub sample criteria (A / A-EX)

**A** (dual-home GitHub sample) should satisfy:

1. **Validates** under intended profile (`eslams validate` / publish validate / runner-bundle as appropriate).
2. **Deterministic replay** passes.
3. **No recorded error-log** entries.
4. **Model-battle samples:** must **not** rely on missing-key **fallback** actions (fail-closed / no fallback pollution).
5. **Public-exportable** after scrub (see §2).
6. **Stable `sample_id`**, reproducible bytes (or documented pin), `eslams-core==0.6.1`.
7. **Messaging-safe:** Local / fixture / historical demo / **canary** — never implied as live Official LB score or as a full suite.

**A-EX** (labeled public fail/partial, ≤50):

- Same scrub as A.
- **Labeled** `A-EX` in the manifest (`expected_validate: fail` or equivalent).
- **May not pass SUCCESS validate** — that is expected; document the failure class (`INCOMPLETE`, error-log, fallback, truncated receipt, etc.).
- Teaching / autopsy examples, not silent trash and not dual-home “good samples.”

Warehouse tiers **B / C / C-EX / DUMP LB** are not required to pass GitHub sample criteria. They still **must scrub**. **B** is historical; spoil of `official-hidden` paths is **accepted** because the suite is retired.

---

## 6. Process steps

```
0  R2 pull HOLD — do not pull R2, do not publish
   Founder/Jev: merge PR #13 Quickstart first; this PR stays draft
1  Inventory  →  ids / paths / sizes / tier (plan counts in §3)
2  Classify   →  A | A-EX | B | C | C-EX | KEEP | DUMP_LB | HELD | SECRET_RESIDUAL
3  Scrub always (keys, signed gateway URLs, auth/Trinity, PII)
4a Dual-home A (+ labeled A-EX) samples → GitHub sample_runs/ + public HF (Wave B)
4b Warehouse B / C / C-EX / DUMP-LB → public HF after scrub (Wave B)
4c Unscrubbable remainder → private HF scraps + reason log only
5  Record dual-publish / warehouse manifest (sha256, paths, core_pin, tier, status)
6  KEEP arenasession + platformmatch on D1 (no delete)
7  Optional: Platform slim D1 allowlist of A / A-EX sample metadata only
```

**No D1 deletes.** Export is read-only. Warehouse lives on **public HF** after scrub. Slim D1 never re-imports B/C/C-EX/DUMP bulk.

---

## 7. Dual-publish / warehouse manifest schema (draft)

```json
{
  "sample_id": "run_eeab67d58b994ca7",
  "sha256": "<hex of .eslams bytes or publication root>",
  "github_path": "sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams",
  "hf_path": "A/model_battle_sample/run_eeab67d58b994ca7.eslams",
  "hf_repo": "ElectronicSlams/eslams-sample-runs",
  "kind": "battlefield-sample",
  "tier": "A",
  "core_pin": "eslams-core==0.6.1",
  "status": "A",
  "dual_home": true,
  "validate_profile": "runner-bundle",
  "expected_validate": "pass",
  "notes": "prefer on-disk id over README run_d48ff364…; TTT-skewed canary not full suite",
  "updated_at": "2026-09-21T00:00:00Z"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `sample_id` | yes | Stable public id |
| `sha256` | yes | Drift detection GH ↔ HF |
| `github_path` | yes for dual-home samples | Omit for warehouse-only B/C/C-EX/DUMP |
| `hf_path` | yes when HF live | Path inside dataset |
| `hf_repo` | yes when HF live | Samples: `ElectronicSlams/eslams-sample-runs`. Warehouse may share that repo with prefixes `A/` `A-EX/` `B/` `C/` `C-EX/` `DUMP/` or a sibling public dataset — decide at Wave B org standup. Residual scraps: private repo + reason log, **not** the default dump. |
| `kind` | yes | e.g. `battlefield-sample`, `official-proof`, `phoenix-strict-clean`, `official-hidden-historical` |
| `tier` | yes | `A` \| `A-EX` \| `B` \| `C` \| `C-EX` \| `KEEP` \| `DUMP_LB` \| `SECRET_RESIDUAL` |
| `core_pin` | yes | `eslams-core==0.6.1` |
| `status` | yes | Same as `tier`, or `REVIEW` / `HELD` before export |
| `dual_home` | yes | `true` only when GH + HF bytes agree (A / small A-EX) |
| `validate_profile` | recommended | Profile used to certify A |
| `expected_validate` | **required for A-EX** | `fail` (plus failure class in `notes`). A rows: `pass`. |
| `notes` | optional | Id drift, fixture caveats, spoil/historical, canary-not-suite |

Warehouse-only rows set `dual_home: false` and omit `github_path` (GH carries pointers/manifests, not blobs). **KEEP** rows are D1 pointers, not HF objects. **SECRET_RESIDUAL** rows live only on private HF with a reason-log field.

---

## 8. Initial classification table

| sample_id / path | kind | Proposed tier | Rationale / next check |
| --- | --- | --- | --- |
| `run_eeab67d58b994ca7` · `model_battle_sample/` | battlefield-sample | **A** (candidate) | Confirm validate + no fallback + public-export before dual-publish |
| `official_signed` · `model_eval_sample/` | official-proof | **A** **REVIEW** | Fixture key caveats — do not over-claim Official trust |
| README `run_d48ff364a0b949df` | (stale doc) | **REVIEW** | Id drift vs `run_eeab67d58b994ca7`; fix README in a follow-up |
| Battlefield ~108 `replay_*` | live demo | **REVIEW** (Platform theater) | Link from `/labs`; HF mirror optional |
| 861 success-run `.eslams` | canary (TTT-skewed) | **A** | Public GH samples + public HF; **not full suite** |
| ≤50 partial/fail examples | labeled fail/partial | **A-EX** | Public labeled; **expected SUCCESS-validate failure** |
| ~15250 `artifacts/official-hidden%` | historical score proofs | **B** | Public HF after scrub; spoil accepted; suite retired |
| 856 phoenix strict-clean-v1 | phoenix clean | **C** | Public HF after scrub |
| Bulk archaeology | archaeology | **C-EX** | Public HF; GH pointers/manifests only |
| `arenasession` + `platformmatch` | live Platform | **KEEP** | Stay on D1; no delete |
| Retired LB bulk | dump | **DUMP LB** | Public HF if scrubbed; else private scraps + reason log |
| Scratch harness / exploratory | n/a | omit | Not public GH samples |

Statuses above are **plan tags**, not a completed validate or extract pass.

---

## 9. RACI

| Workstream | Platform | OSS | Founder |
| --- | --- | --- | --- |
| Inventory GitHub samples/fixtures | I | **R** | A |
| SUCCESS-EXTRACT inventory (A/B/C counts) | **R** (export when unlocked) | C | A |
| Classification criteria + manifest | C | **R** | A |
| Dual-home A / A-EX (GH + public HF) | I | **R** | A |
| Public HF warehouse B / C / C-EX / DUMP | **R** (export) | **R** (upload) | A |
| Residual private scraps + reason log | C | **R** | A |
| KEEP `arenasession` + `platformmatch` | **R** | I | A |
| README id-drift fix | I | **R** | A |
| Slim D1 sample allowlist | **R** | C | A |
| Scrub (keys, signed gateway URLs, auth/Trinity, PII) | **R** | **R** | A |
| **R2 pull HOLD** | I | I | **A** (lift only) |
| Wave A merge order (#13 then this draft) | I | I | **A** |

---

## 10. Status

| Item | State |
| --- | --- |
| This document | Wave A **draft** (PR #14). Founder/Jev prefer **[#13 Quickstart](https://github.com/ElectronicSlams/eSlams/pull/13)** merge first. |
| HF org / uploads | Wave B — not this PR |
| **R2 pull** | **HOLD** — do not pull, do not publish |
| Prod D1 | No deletes; KEEP tables stay |
| Counts 861 / ~15250 / 856 | Plan figures from SUCCESS-EXTRACT lock 2026-09-20/21; not byte-verified here |

Contact: hello@eslams.com · eslams.com

See also: [`docs/LABS.md`](./LABS.md) (Lab Quickstart) · [`docs/LABS_PAGE_CONTRACT.md`](./LABS_PAGE_CONTRACT.md) (Platform `/labs` contract).
