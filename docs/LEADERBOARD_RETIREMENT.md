# Public leaderboard retirement (Core)

Product lock **2026-09-23**. This is the Core view of the retirement. It
changes docs and CLI help only. It does not deploy, merge, upload eval
blobs, delete stadium rows, or edit Platform UI or API code.

Pin: `eslams-core==0.6.1`.

## Product lock

The hosted platform is **stadium-only**:

- **Arena** — live play
- **Battlefield** — public matches and replays
- **Grand Slams** — controlled stadium events

The public leaderboard is **retired**. That board was the unsustainable
ranking built from roughly nine thousand simulations. There is no live
Platform ranking to submit to, and no Official leaderboard to climb.

The **Official eval suite is retired and historical**. A scrubbed copy of
that archive may be published later. Publishing it does not revive a hidden
leaderboard.

**Local is not Official, and local is not Grand Slam.** `eslams run` writes
a Local Artifact. Upload, `official-proof` export, and a passing
`official-case` check do not turn that artifact into an Official result or
a Grand Slam result.

Labs **bring their own provider keys**. Core reads credentials from the
lab's environment. This repo does not ship organization provider keys.

## What retired

- The live public leaderboard and any Official leaderboard on eslams.com.
- "Submit to leaderboard" as a product path.
- Treating the ~9k-simulation official ranking as a current scoreboard.
- Reading a local run, an Artifact Intake upload, or a historical
  official-proof row as a current public rank.

Core commands that still say `official` are historical helpers. They plan
or merge old suite layouts. They do not submit, rank, or seal a Grand Slam.
See the CLI help for `eslams plan official`, `eslams official`, and
`--execution-profile official_eval`.

## What stays

Keep stadium match data. Core does not store it and must not delete it.

| Keep | Where it lives | Core's job |
| --- | --- | --- |
| Arena sessions | Platform stadium records (including D1 `arenasession`) | Arena transport and local artifacts only |
| Battlefield matches | Platform stadium records (including D1 `platformmatch`) | Battlefield plans, replays, and sample bundles |
| Grand Slam records | Controlled stadium infrastructure | Do not mint Grand Slam verification locally |

Also keep the on-disk contract fields that already refuse a public ranking.
Writers set `aggregate_leaderboard_eligible` to `false`, with reasons such
as `aggregate_leaderboard_not_asserted_by_core`. Proof rows are evidence.
`leaderboard_predicate` stays false unless a caller explicitly configures a
predicate, and Core still rejects an implicit one. Those names are
historical wire fields. This retirement does not rename or remove them.
They are not a switch that publishes a live board.

## What moves to Hugging Face

Remaining eval interest — the retired Official suite and related proof rows,
after scrub — moves to a Hugging Face warehouse. GitHub keeps thin samples
and pointers, not the warehouse.

GitHub samples today:

- `sample_runs/model_eval_sample/` — historical `official-proof` fixture shape
- `sample_runs/model_battle_sample/` — Battlefield sample shape

Warehouse dataset names (skeletons; not uploaded by this change):

- `ElectronicSlams/eslams-sample-runs`
- `ElectronicSlams/eslams-official-suite-archive`
- `ElectronicSlams/eslams-phoenix-strict-clean`
- `ElectronicSlams/eslams-eval-archaeology`

**TODO:** the Hugging Face Collection URL is not final. The org
`ElectronicSlams` was not confirmed live when this note was written. Until
the founder creates the org and collection, use this placeholder only:

```text
https://huggingface.co/collections/ElectronicSlams/eslams-core
```

Do not treat that URL as a working collection. Scrub keys, signed gateway
URLs, auth material, and PII before any public byte. Archive tier rules and
the R2 hold live in the companion doc
`docs/RETIRED_EVAL_ARCHIVE.md` when that file is in the tree (open
separately; this page stands alone if it is absent). Org and lab-secret
rules live in `docs/HF_ORG_AND_SECRETS.md` on that same companion change.

## What Platform must remove

Platform code changes are **out of scope** in this repository. Core cannot
delete the website. The Platform surface should remove:

- Public leaderboard pages, rank tables, and model boards fed by the
  ~9k-simulation official ranking.
- Official leaderboard copy and any "submit to leaderboard" control.
- API routes that list, accept, or refresh a live public leaderboard
  ranking.

Platform should keep Arena, Battlefield, and Grand Slam UI and the stadium
match records above. Do not drop `arenasession` or `platformmatch` as part
of leaderboard retirement.

## Out of scope here

- Implementing the Platform removals above.
- Runner authorization and HMAC work. Existing signature readers stay as
  they are.
- Hugging Face uploads, org creation, and dataset cards.
- Deleting or rewriting Wave A drafts:
  [PR #13](https://github.com/ElectronicSlams/eSlams/pull/13)
  (`docs/LABS.md`),
  [PR #14](https://github.com/ElectronicSlams/eSlams/pull/14)
  (`docs/SAMPLE_CLASSIFICATION.md`),
  [PR #15](https://github.com/ElectronicSlams/eSlams/pull/15)
  (`docs/LABS_PAGE_CONTRACT.md`).
  Lab quickstart, sample classification, and the `/labs` page contract stay
  on those branches.

## See also

- [Security](../SECURITY.md) — credentials and false verification claims.
- [Artifacts](ARTIFACTS.md) — eligibility fields that do not publish a rank.
- [Platform contracts](PLATFORM_CONTRACTS.md) — publication bundles as evidence.
- [Provider guide](PROVIDERS.md) — bring-your-own environment variable names.
