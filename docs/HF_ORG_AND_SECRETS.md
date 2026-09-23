# HF lab pack readiness

A newcomer cannot use Hugging Face for eSlams yet. Core installs from PyPI
(`pip install eslams-core==0.6.1`). The run path, provider env-var names, and
`hf download` command live in the lab quickstart
([PR #13](https://github.com/ElectronicSlams/eSlams/pull/13), `docs/LABS.md`).
This page is the Hub gap that quickstart does not close: the org, which
dataset is the lab pack, and how Space secrets work.

**Local Artifact ≠ Official / Grand Slam.** Put that sentence on the lab-pack
dataset card and on the Static docs Space. A visitor who lands on the Hub
never opens the GitHub quickstart.

## Org is missing

Target organization: **`ElectronicSlams`**. The founder creates it. Do not
substitute a personal account, a bot, or a GitHub Actions token.

Hub check **2026-09-23**:

- `https://huggingface.co/ElectronicSlams` and
  `GET /api/organizations/ElectronicSlams` → **404**
- Public dataset search `eslams` → no rows
- Unauthenticated `GET /api/datasets/...` and `GET /api/spaces/...` return
  401 for nonsense names as well, so 401 is not evidence that a repo exists

Re-check the Hub the day the org is created. Unrelated `eslam*` users are
not this project. This repository has no Hub token and must not gain one.

Until the org exists there is no Collection, no dataset, and no Space.

## Lab pack pointer

The lab sample pack is one dataset:

`https://huggingface.co/datasets/ElectronicSlams/eslams-sample-runs`

It is reserved for tier **A** (the 861 tic-tac-toe-skewed canary — not the
full 50-arena suite) and tier **A-EX** (≤50 labeled teaching fails). Archive
datasets are a different page:
[Retired eval archive](RETIRED_EVAL_ARCHIVE.md). Do not send a first-time
lab user to those repos.

That dataset does not exist yet. Until it does, the only pack in git is:

| Path | What it is |
| --- | --- |
| `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams` | Battlefield-sample fixture on disk |
| `sample_runs/model_eval_sample/official_signed.eslams` | Official-proof fixture |

`sample_runs/README.md` and the root README still name battle id
`run_d48ff364a0b949df`. That file is not in the tree. Use
`run_eeab67d58b994ca7`.

When `eslams-sample-runs` exists, the download line in `docs/LABS.md` is the
one to follow (`hf download ElectronicSlams/eslams-sample-runs --repo-type
dataset`). There is no sample manifest in git yet (id, sha256, Hub path).
Classification schema is
[PR #14](https://github.com/ElectronicSlams/eSlams/pull/14).

## Collection and Static Space

Also absent. After the org exists, the lab-facing Hub surface is:

- Collection **`eslams-core`** — GitHub `ElectronicSlams/eSlams`, PyPI
  `eslams-core`, dataset `eslams-sample-runs`, Space `eslams-docs`
- Space **`ElectronicSlams/eslams-docs`** — Static, no compute

Static Space copy, in order: pin `eslams-core==0.6.1`; Local Artifact ≠
Official / Grand Slam; bring your own keys (names only, see
[docs/PROVIDERS.md](PROVIDERS.md)); link `eslams-sample-runs`; link this
repo. Static Space variables are visible in the browser. No secrets, tokens,
or signed URLs on that Space.

`ElectronicSlams/eslams-lab-runner` (Gradio) is optional and later. It is
not required to download the lab pack or to run Core.

## Space secrets are BYO on a duplicate

Local runs do not need a Space. Keys stay in the lab's own environment
(quickstart + [SECURITY.md](../SECURITY.md)).

If the Gradio runner is published, the shared template ships with **no**
organization provider keys:

1. The lab uses **Duplicate this Space**. Hub copies public Variables. It
   does not copy Secrets.
2. On the duplicate: Settings → Variables and secrets → New secret, with
   **the lab's** provider keys.
3. The template does not call a live provider until those Secrets exist.
   `random` and `first-legal` need no key.

A Variable is public and is copied onto duplicates. A key does not go in a
Variable. eSlams organization provider keys do not go in GitHub Actions,
Platform, `eslams-docs`, or the unduplicated runner. Core CI does not use
provider keys; PyPI publish uses trusted publishing.

Organization Gradio Spaces generally need a paid Hub plan. That plan does
not gate the Static Space or `eslams-sample-runs`.

## Nothing secret in this repo

Docs may name env vars and Hub repo ids. They must not contain API keys,
Hub tokens, signing private keys, or signed gateway URLs.
