# `/labs` page contract — handoff to Core Platform

> Wave A · pin `eslams-core==0.6.1` · Local Artifact ≠ Official/Grand Slam · LB retired as lab product

---

## 1. One-liner

Platform builds a **real `/labs`** landing (today: SPA “Player Not Found”). OSS supplies Quickstart URL, pin, sample catalog fields, and (when live) HF URLs. `/labs` = **onboarding + samples + upload→viz**. **Battlefield** stays the theater. **Do not rebuild NOW SHOWING.**

---

## 2. Platform must build

1. **Real `/labs` route** — replace dead SPA fallback.
2. **Fixed sections:**
   - **Quickstart** — embed or link `docs/LABS.md` + `pip install eslams-core==0.6.1` + BYO keys table + **Local ≠ Official** banner.
   - **Samples** — gallery of curated sample ids with “Open replay / proof” actions.
   - **Upload → visualize** — wire Artifact Intake / Trinity upload; show replay / score / proof after upload.
3. **Sample sources (either or both):**
   - **A. Pull from HF (primary)** — Hub API / resolve URLs from `ElectronicSlams/eslams-sample-runs`.
   - **B. Slim stadium D1 sample copies (secondary)** — **allowlisted** metadata + artifact pointers only (not retired trash dump).
4. **Reuse Battlefield NOW SHOWING** — link/embed for “see how results look”.
5. **Messaging** — no live LB CTA as product; Local Artifact ≠ Official / Grand Slam; labs BYO secrets only.

---

## 3. OSS inputs (contract fields)

| Artifact | Location | Contract field | Status |
| --- | --- | --- | --- |
| Lab Quickstart | GitHub [`docs/LABS.md`](./LABS.md) | `quickstart_url` | Wave A |
| Sample catalog | GitHub + HF dataset README / JSON | `sample_ids[]` | Schema in [`SAMPLE_CLASSIFICATION.md`](./SAMPLE_CLASSIFICATION.md) |
| HF samples dataset | `https://huggingface.co/datasets/ElectronicSlams/eslams-sample-runs` | `hf_samples_url` | **PENDING Wave B** |
| Static docs Space | `https://huggingface.co/spaces/ElectronicSlams/eslams-docs` | `hf_docs_url` | **PENDING Wave B** |
| Collection | HF Collection slug `eslams-core` | `hf_collection_url` | **PENDING Wave B** |
| PyPI pin | `eslams-core==0.6.1` | `pypi_pin` | Locked |
| Dual-home rule | Same bytes / same `sample_id` on GH + HF | `dual_home: true` | After Wave B dual-publish |

**Interim (pre-HF):** Platform may ship `/labs` with Quickstart + Battlefield embeds + known GitHub sample paths + upload→viz; show HF fields as “coming soon” or omit until Hub live.

---

## 4. Sample pull: HF primary, slim D1 secondary

| Approach | Role | Notes |
| --- | --- | --- |
| **HF pull** | **Primary** for downloadable packs | Single source with OSS; depends on Wave B |
| **Slim D1 copies** | **Secondary** mirror | Allowlisted sample metadata only; **never** full retired dump |
| GitHub raw | Docs + small fixtures | Not ideal for many binaries |

**API shape (recommendation):** `/labs` API returns allowlist rows: `id`, `title`, `game`, `proof_url` / replay link, `hf_path`, `github_path`, `kind`, `core_pin`, `sha256`.

---

## 5. Reuse Battlefield — don’t rebuild

- Live demos: [eslams.com/battlefield](https://eslams.com/battlefield) — NOW SHOWING + verified `replay_*` embeds.
- `/labs` “See how results look” → embed/link Battlefield.
- Prefer Battlefield match URLs over broken sitemap `/artifacts/artifact_run_*`.

---

## 6. Upload → visualize — auth reality

| Fact | Implication |
| --- | --- |
| Artifact Intake / Trinity upload exists | CTA: validate locally → upload `.eslams` → viz |
| `/trinity/developer` requires sign-in | Upload→viz is **auth-gated**, not anonymous public seal |
| Visualization ≠ Official seal | Copy must say Local Artifact visualize only |
| Dead routes today | `/intake`, `/upload`, `/replay`, `/artifact` currently SPA “Player Not Found” — Platform must attach real handlers or redirect into Trinity |

---

## 7. Messaging locks

- **Leaderboard product:** retired / retiring — **no** live LB CTA as primary lab pitch.
- **Local ≠ Official / Grand Slam** — banner on Quickstart, Samples, Upload.
- **Secrets:** labs BYO only; never eSlams org keys.
- **Leave-behind:** hello@eslams.com · eslams.com · SECURITY.md from Quickstart.
- Autopsy / retired-LB narrative blogs: **not** near-term.

---

## 8. Acceptance criteria (Platform implementation — separate ticket)

- [ ] `/labs` returns a real landing (not “Player Not Found”).
- [ ] Quickstart shows pin `eslams-core==0.6.1`, BYO env table, Local≠Official banner, link to `LABS.md`.
- [ ] Samples section lists allowlisted ids with open replay/proof actions.
- [ ] Sample blobs resolve from HF when live; else interim GH/Battlefield without claiming HF.
- [ ] Slim D1 (if used) contains **only** allowlisted sample metadata.
- [ ] Upload → visualize reaches Intake/Trinity with clear auth UX.
- [ ] Copy states visualize ≠ Official/Grand Slam.
- [ ] NOW SHOWING linked/embedded — Battlefield not reimplemented.
- [ ] No live leaderboard product CTA as primary.
- [ ] No org provider keys required for any lab path on the page.
- [ ] HF URL fields marked pending or wired only after Wave B.
- [ ] Contact: hello@eslams.com / eslams.com.

---

## 9. Handoff

| To | Ask |
| --- | --- |
| **Core Platform** | Consume this contract; interim ship OK with Battlefield + Quickstart + upload; HF fields pending Wave B |
| **OSS** | Keep LABS.md + classification + manifest ready; dual-publish in Wave B |
| **Founder** | HF org; `/labs` + LB retirement brand timing |

This PR lands the **contract doc only**. Platform implements the page in a separate ticket.

See also: [`docs/LABS.md`](./LABS.md) (Lab Quickstart) · [`docs/SAMPLE_CLASSIFICATION.md`](./SAMPLE_CLASSIFICATION.md) (GOOD vs dump plan).
