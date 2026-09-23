# Wave B public archive — HOLD runbook

**Status: HOLD.** Draft ops notes only. Do not merge until the founder says so.
Do not deploy. Do not pull R2. Do not dump, query, or delete production D1.
Do not run wrangler against production from this repository.

Founder lock **2026-09-21**: the Official suite is **retired / historical**.
Scrubbed `official-hidden` proofs may go **public**. Spoil is accepted.
Hugging Face is the warehouse. This GitHub repo keeps **samples and pointers**.

Pin: `eslams-core==0.6.1`.

Sample-classification vocabulary is a separate draft. This directory records
the Wave B ops gates, the completed R2 census, the locked 861 filter, and the
pull stub. It does not add eval blobs.

## Locked facts

| Fact | Value |
| --- | --- |
| Tier A SUCCESS `.eslams` filter | **861** rows (SQL in [tiers.md](tiers.md)) |
| Arena mix inside those 861 | 860 tic-tac-toe, 1 connect-four |
| What 861 is | TTT-skewed canary / rerun packages |
| Retired suite inventory | 50-arena matches and scores, score proofs, phoenix strict-clean |
| KEEP on D1 | `arenasession` **136** + `platformmatch` **108** |
| R2 bucket | `eslams-artifacts-prod` |
| R2 census | **1,739,537** objects / **30,810,380,496** bytes (**~28.69 GiB** listed). Wrangler bucket label ~31.6 GB. Census is **complete**. |
| Pull | **HOLD** until explicit founder go, the scrub checklist is accepted, and the A-EX cap (≤50) is locked |
| D1 | No full dump. Delete only after dual-home verify **and** a separate founder delete gate |

Details: [founder-locks.md](founder-locks.md), [tiers.md](tiers.md), [census.md](census.md), [manifests/SUMMARY.md](manifests/SUMMARY.md).

## Gates still closed

1. **Founder go** for an R2 pull. Census-complete does not open this gate.
2. **Scrub checklist** accepted before any publish (keys, signed gateway URLs, auth / Trinity material, PII).
3. **A-EX cap** locked at **≤50** unless the founder raises it. Curation itself runs after tier A is in hand.
4. **Dual-home verify** before any delete: manifest `sha256` matches the pulled object and the published Hugging Face object (and the GitHub sample, when a sample was published).
5. **Founder delete gate**, separate from the pull go. KEEP stadium rows stay on D1.

Until gate 1 is open, [`scripts/wave-b/pull-861-r2.sh`](../../scripts/wave-b/pull-861-r2.sh) stays a dry-run.

## Sequence after founder go

Work tier A first. The pull script copies only the 861 manifest keys. It is not a bucket sync.

1. **A — pull the canary.** On the ops box, outside CI, pull the 861 SUCCESS `.eslams` objects. Validate and replay offline against `eslams-core==0.6.1`. Label the set as a canary, not the retired 50-arena suite.
2. **Scrub.** Run the checklist in [tiers.md](tiers.md) on every byte that might be published. Rows that cannot be scrubbed go to a residual-private log (path + reason). They are not dropped silently and they are not published.
3. **Dual-home.** Publish scrubbed tier A samples and a short manifest to GitHub, and the scrubbed warehouse copy to Hugging Face. Verify `sha256` on both homes against the D1 manifest. Leave R2 and D1 in place.
4. **A-EX ≤50.** Curate partial and failed examples. Each row is labeled `outcome=partial|failed` and may fail SUCCESS validate. Do not exceed 50 without the founder. Skip raw secret paths and near-duplicate tic-tac-toe timeouts.
5. **Stop for the founder delete gate.** D1 delete is allowed only after step 3 has been shown for the rows being removed, and only after a new explicit founder instruction. `arenasession` (136) and `platformmatch` (108) stay.

Later warehouse tiers use the same scrub and the same delete rule. They are not part of the 861 pull:

- **B** — ~15,250 `artifactkind=score` proofs under `artifacts/official-hidden%`. Public Hugging Face after scrub. GitHub gets pointers only.
- **C** — 856 phoenix `strict-clean-v1` sources. Public Hugging Face after the R2 key is resolved and scrubbed. GitHub gets pointers only.
- **C-EX** — bulk fail / partial archaeology, plus scrubbed leaderboard dump when it scrubs clean. Hugging Face archaeology dataset. GitHub gets an index.

Order those after A has a verified dual-home: **B proofs → C phoenix → C-EX archaeology**.

## CI

**Forbidden in GitHub Actions and every other CI system:**

- `scripts/wave-b/pull-861-r2.sh` (any arguments, including dry-run jobs that could later be flipped)
- `wrangler` against production, including `r2 object get`, `d1 execute`, `d1 export`, and `d1 delete`
- R2, S3, or D1 credentials in workflow env
- Hugging Face uploads of Wave B packs
- Any delete of D1 rows or R2 objects

The pull script exits immediately when it sees `CI` or `GITHUB_ACTIONS`. Do not bypass that check in a workflow. A green docs review does not authorize a pull.

## What is not in git

- `extract-861.jsonl` (full row extract)
- the 861-line r2key list
- pulled `.eslams` objects
- Cloudflare account ids and D1 database UUIDs

Operators keep the key list on the ops box and pass it with `KEYS_FILE` when a future founder go allows a real pull. Counts for that extract are in [manifests/SUMMARY.md](manifests/SUMMARY.md).
