# Hugging Face org and lab secrets

Docs only. This file names the target org, dataset skeleton, and where lab
credentials are allowed to live. It does not create the org, upload datasets,
or store any credential value.

Pin: `eslams-core==0.6.1`. Install stays `pip install eslams-core`. Hugging Face
is for datasets, a Collection, and docs — not a second package index. A local
Core run is a Local Artifact. It is not an Official or Grand Slam result.

## Org

Target Hugging Face organization: **`ElectronicSlams`**. The founder creates
it. Do not attach the GitHub org, a bot user, or a shared CI token as a
stand-in owner.

Hub check **2026-09-23**: `GET /api/organizations/ElectronicSlams` returned
404, `GET /api/users/ElectronicSlams/overview` returned 404, and a dataset
search for `eslams` returned no rows. Re-check the Hub immediately before
create in case the name is taken between this note and the click. Unrelated
`eslam*` user accounts are not this project.

Nothing in this repository is an upload. Dataset and Space names below are
skeletons for the founder standup.

## Dataset skeleton

Public warehouse (Hugging Face, after scrub). GitHub does not hold these
trees.

| Hugging Face dataset | What it is for | GitHub |
| --- | --- | --- |
| `ElectronicSlams/eslams-sample-runs` | Tier **A** canary runs and tier **A-EX** teaching fails | Thin samples only. Today that is `sample_runs/model_battle_sample/` and `sample_runs/model_eval_sample/`. A later extract may add `sample_runs/success/` and `sample_runs/examples/`. |
| `ElectronicSlams/eslams-official-suite-archive` | Tier **B** historical score proofs | `sample_runs/manifests/` pointers only, when that directory exists. Not the proof blobs. |
| `ElectronicSlams/eslams-phoenix-strict-clean` | Tier **C** phoenix `strict-clean-v1` | Pointers / manifest rows only. |
| `ElectronicSlams/eslams-eval-archaeology` | Tier **C-EX** plus scrubbed leaderboard **DUMP** | An index or manifest only. |

Optional later, still public and tiny: `ElectronicSlams/eslams-lab-smoke` for
a bring-your-own case pack. It is not the warehouse.

`ElectronicSlams/eslams-retired-eval-dump` as a private default dump is
retired. Private Hub storage is only for rows that cannot be scrubbed, each
with a reason. See [Retired eval archive](RETIRED_EVAL_ARCHIVE.md).

Dataset cards, when the repos exist, should say: samples are MIT where the
GitHub license applies; pin `eslams-core==0.6.1`; the official suite is
historical; Local Artifact is not Official or Grand Slam. Contact for paid
official work: `hello@eslams.com`.

## Collection and Static docs Space

MVP Hub surface, after the org exists:

```text
ElectronicSlams/
  collections/eslams-core          # Collection: Core + datasets + docs Space
  datasets/eslams-sample-runs
  datasets/eslams-official-suite-archive
  datasets/eslams-phoenix-strict-clean
  datasets/eslams-eval-archaeology
  spaces/eslams-docs               # Static Space (free). No compute.
  spaces/eslams-lab-runner         # Later / optional. Not part of standup.
```

Collection `eslams-core` should link GitHub `ElectronicSlams/eSlams`, PyPI
`eslams-core`, the datasets above, and `spaces/eslams-docs`.

Static Space `eslams-docs` outline:

1. What Core is, and `pip install eslams-core==0.6.1`.
2. Banner: Local Artifact is not Official or Grand Slam.
3. Bring-your-own keys: environment variable **names** only, same set as
   [the provider guide](PROVIDERS.md). No values.
4. Links to the public datasets once they exist, plus the GitHub sample
   paths.
5. Retired-suite line: historical archive, former hidden proofs may be
   public after scrub, not a live leaderboard.
6. Link back to this repository’s docs.

Static Spaces expose variables in the browser. Do not put secrets, tokens,
or signed URLs in that Space.

## Gradio runner (later / optional)

`spaces/eslams-lab-runner` is not required for the org standup. If it is
built later:

- Ship it with **no** organization secrets.
- Labs use **Duplicate this Space**, then add **their** keys under
  Settings → Variables and secrets. Hub does not copy Secrets onto a
  duplicate.
- The app should refuse live provider calls until those Secrets exist.
  Built-in `random` / `first-legal` agents do not need a key.
- Organization Gradio Spaces generally need a paid Hub plan. Do not block
  the Static docs Space or the dataset skeleton on that plan.

## Where lab secrets live

Two allowed places, both owned by the lab:

1. **Local environment.** `pip install eslams-core==0.6.1`, then the lab
   exports only the variables for the providers they call
   (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
   `OPENROUTER_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`). Names match
   [SECURITY.md](../SECURITY.md) and [docs/PROVIDERS.md](PROVIDERS.md).
   Core reads credentials from the environment. It does not take them as
   CLI arguments.
2. **Secrets on a duplicated Space.** Only after a lab duplicates
   `eslams-lab-runner` (when that Space exists) and sets Secrets on the
   copy. The template Space stays empty.

eSlams organization provider keys do **not** go in:

- GitHub Actions (Core CI is tests, schema export, and lint; PyPI publish
  uses trusted publishing, not a provider key)
- Platform / eslams.com worker or dashboard secrets, for lab or demo burns
- a shared Space, including `eslams-docs` and any unduplicated runner

Variables on a Space are public and are copied on duplicate. Never put a
key in a Variable.

## No live credentials in the repo

This repository must not contain live API keys, Hub tokens, Cloudflare or
GitHub tokens, signing private keys, session secrets, pre-signed or signed
gateway URLs, or auth / Trinity material. Documentation may name environment
variables. It must not assign them values. Placeholder ellipses in the
README (`export OPENAI_API_KEY=...`) are not credentials and must stay
empty.

Do not commit `.env` files, Space secret exports, or eval blobs pulled from
R2. Archive hosting rules are in
[Retired eval archive](RETIRED_EVAL_ARCHIVE.md).

## See also

- [Retired eval archive](RETIRED_EVAL_ARCHIVE.md) — tiers, scrub, R2 hold.
- [Provider guide](PROVIDERS.md) — adapter and environment-variable names.
- [Security](../SECURITY.md) — credentials stay out of artifacts and receipts.
- Companion docs on other open PRs, not in this change:
  [Lab quickstart](https://github.com/ElectronicSlams/eSlams/pull/13)
  (`docs/LABS.md`),
  [sample classification](https://github.com/ElectronicSlams/eSlams/pull/14)
  (`docs/SAMPLE_CLASSIFICATION.md`),
  [`/labs` contract](https://github.com/ElectronicSlams/eSlams/pull/15)
  (`docs/LABS_PAGE_CONTRACT.md`).
