# Founder gates and open Core drafts

Status as of **2026-09-23 PT**. This page indexes Core holds and the open
Core pull requests. It is for humans deciding what may happen next.

This file is not a merge queue. It does not order, approve, or perform a
merge. It is not an R2, D1, or Hugging Face execute runbook. It is not
Platform: no Workers, no stadium, no live ops, and no `eSlamsPlatformv1` /
`v2` work.

Do not invent a live Hugging Face URL from this page. Do not treat any local
artifact, sample, or draft as Official or Grand Slam. Those verification
levels come only from controlled eSlams infrastructure.

## Hard holds

Agents do not lift these. They stay closed until the founder says otherwise.

| Hold | Closed means |
| --- | --- |
| Merge, deploy, DNS | No merge, deploy, or DNS change from agents. |
| R2 pull | No R2 pull until an explicit founder go. Tier A is first if that go is given. |
| D1 delete | No D1 delete until dual-home is verified and the founder gives a separate delete go. |
| Hugging Face | No org, dataset, Collection, Space, or Gradio create or upload from agents. |
| Live stadium | No live stadium operations. |

## Founder-only unlocks

Listing an unlock does not perform it. Only the founder may:

1. Create the Hugging Face org `ElectronicSlams` and the sample dataset. On 2026-09-23 the org was 404 (see [#17](https://github.com/ElectronicSlams/eSlams/pull/17)).
2. Give an explicit R2 Tier-A pull go, and only after scrub, with A-EX capped at ≤50.
3. Give an explicit D1 delete go, and only after dual-home verification. KEEP `arenasession` and `platformmatch`.
4. Call merge order among Wave A ([#13](https://github.com/ElectronicSlams/eSlams/pull/13)–[#15](https://github.com/ElectronicSlams/eSlams/pull/15)), security ([#21](https://github.com/ElectronicSlams/eSlams/pull/21)), and OSS honesty ([#17](https://github.com/ElectronicSlams/eSlams/pull/17), [#18](https://github.com/ElectronicSlams/eSlams/pull/18), [#22](https://github.com/ElectronicSlams/eSlams/pull/22)).

Secrets stay in the environment only. Do not commit, paste, or upload them.

## Open Core pull requests

Checked 2026-09-23. [#13](https://github.com/ElectronicSlams/eSlams/pull/13)–[#15](https://github.com/ElectronicSlams/eSlams/pull/15) are open and not drafts. [#16](https://github.com/ElectronicSlams/eSlams/pull/16)–[#22](https://github.com/ElectronicSlams/eSlams/pull/22) are drafts. The role column is a label, not a new scope. Do not rewrite [#19](https://github.com/ElectronicSlams/eSlams/pull/19), [#20](https://github.com/ElectronicSlams/eSlams/pull/20), [#21](https://github.com/ElectronicSlams/eSlams/pull/21), or [#22](https://github.com/ElectronicSlams/eSlams/pull/22) from this page.

| PR | Title | State | Role |
| --- | --- | --- | --- |
| [#13](https://github.com/ElectronicSlams/eSlams/pull/13) | [oss][feature] Add LABS.md Quickstart for BYO-key lab runs | Open | LABS Quickstart (Wave A) |
| [#14](https://github.com/ElectronicSlams/eSlams/pull/14) | [oss][chore] Classify samples: public-by-default SUCCESS-EXTRACT tiers | Open | SAMPLE_CLASSIFICATION (Wave A; A-EX still gated) |
| [#15](https://github.com/ElectronicSlams/eSlams/pull/15) | [oss][chore] Add /labs page contract for Platform | Open | LABS page contract (Wave A) |
| [#16](https://github.com/ElectronicSlams/eSlams/pull/16) | docs: AGENTS.md and 2026-09-23 Core review | Draft | AGENTS + CODE_REVIEW F1–F10 (review only) |
| [#17](https://github.com/ElectronicSlams/eSlams/pull/17) | [oss][docs] P0 HF org/secrets + retired-eval archive clarity (burn wave) | Draft | HF org/secrets + retired-eval archive (Hub org 404 until founder) |
| [#18](https://github.com/ElectronicSlams/eSlams/pull/18) | [oss][docs] P0 lab-smoke + pre-HF lab run (burn wave; complements #13) | Draft | lab-smoke + LAB_RUN (complements #13) |
| [#19](https://github.com/ElectronicSlams/eSlams/pull/19) | [oss][docs] Retire public leaderboard + Official suite (Core) | Draft | Core LB + Official retirement (do not duplicate) |
| [#20](https://github.com/ElectronicSlams/eSlams/pull/20) | [ops][docs] Wave B public-archive + R2 pull HOLD runbook | Draft | Wave B HOLD runbook (do not execute) |
| [#21](https://github.com/ElectronicSlams/eSlams/pull/21) | fix: runner HTTP authz and fail-closed arena HMAC | Draft | F1–F6 runner/HMAC harden (do not merge casually) |
| [#22](https://github.com/ElectronicSlams/eSlams/pull/22) | fix: A-EX ≤50 plan and honest in-repo lab pack | Draft | A-EX≤50 + lab-pack honesty (do not merge casually) |

Wave A, the security draft, and the OSS honesty drafts are separate tracks.
Which of them merges first is the founder merge-order call above. This table
does not choose.

## Low findings still separate

F7–F10 from the 2026-09-23 Core review ([#16](https://github.com/ElectronicSlams/eSlams/pull/16)) stay on their own track. [#21](https://github.com/ElectronicSlams/eSlams/pull/21) and [#22](https://github.com/ElectronicSlams/eSlams/pull/22) do not absorb them.

| ID | Topic |
| --- | --- |
| F7 | Replay trust |
| F8 | Agent bind |
| F9 | CI hygiene |
| F10 | PROTOCOL / core-lite |
