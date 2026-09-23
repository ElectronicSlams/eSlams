# Lab run — smoke suite and pre-HF pack

Runnable gap beside the open Wave A drafts. This page does not replace them.

| Draft | Owns |
| --- | --- |
| [PR #13](https://github.com/ElectronicSlams/eSlams/pull/13) `docs/LABS.md` | Pin, BYO provider table, keyed smoke variants, upload → visualize, **Local Artifact ≠ Official / Grand Slam** |
| [PR #14](https://github.com/ElectronicSlams/eSlams/pull/14) `docs/SAMPLE_CLASSIFICATION.md` | HF warehouse tiers and the dual-publish manifest |
| [PR #15](https://github.com/ElectronicSlams/eSlams/pull/15) `docs/LABS_PAGE_CONTRACT.md` | Platform `/labs` page contract |

**Local Artifact ≠ Official / Grand Slam.** A lab run is not a public leaderboard (that product is retired / retiring). Bring your own provider keys. Never use eSlams org keys. Rules that already exist on `main`: [SECURITY.md](../SECURITY.md), [docs/PROVIDERS.md](PROVIDERS.md).

---

## Keyless suite

`suites/lab-smoke/` is not in the PyPI wheel. From a checkout of this repo:

```bash
python -m venv .venv
. .venv/bin/activate
pip install eslams-core==0.6.1
python suites/lab-smoke/run_keyless.py
```

That runs 10 builtin cases (tic-tac-toe, connect-four, othello, chess) with `--execution-profile smoke` and `--verification-level "Local Artifact"`, then validates each archive. The runner refuses `provider:model` agents. Case list and flags: [suites/lab-smoke/README.md](../suites/lab-smoke/README.md).

One keyed smoke (your key only) is the provider guide on `main`, not this suite: [docs/PROVIDERS.md](PROVIDERS.md). PR #13 repeats those one-liners inside the Quickstart.

---

## Pre-HF lab pack

Do not run `hf download` yet. The dataset id those drafts already use, `ElectronicSlams/eslams-sample-runs`, is not live (Wave B, after a founder HF org). This repo does not upload to Hugging Face, R2, or D1.

Until that dataset exists, use what is already in git:

```bash
eslams validate \
  sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams \
  --profile runner-bundle
eslams publish validate sample_runs/model_battle_sample/publication_bundle --json

eslams validate \
  sample_runs/model_eval_sample/official_signed.eslams \
  --profile runner-bundle
eslams publish validate sample_runs/model_eval_sample/publication_bundle --json
```

`run_eeab67d58b994ca7.eslams` is the battle archive on disk. `run_d48ff364a0b949df` is not in this tree.

`official_signed` is an Official **Fixture**. `runner-bundle` validation passes. `official-bundle` does not (`runner_signature_legacy_untrusted`). Do not read it as current Official or Grand Slam trust. Which rows are fit to dual-publish is PR #14, not this page.

Archives from `run_keyless.py` land in `runs/lab-smoke/` (gitignored). They are local smoke output. They are not the future HF warehouse and not a dual-home sample.
