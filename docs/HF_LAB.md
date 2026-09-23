# Hugging Face lab pack

> Pin `eslams-core==0.6.1` · lab secrets are bring-your-own · **Local Artifact ≠ Official / Grand Slam**
>
> Checked **2026-09-23** with no Hub token: the `ElectronicSlams` org and user both 404. Nothing on this page is a live Hugging Face download.

This page is the lab-pack map for Core. It tells a newcomer where samples live, which Hub URLs are reserved but absent, and how to run one smoke game against the pinned PyPI release. It does not create the org, upload a dataset, or deploy a Space.

The longer BYO Quickstart is [`docs/LABS.md`](https://github.com/ElectronicSlams/eSlams/blob/docs/labs-quickstart/docs/LABS.md) (open PR [#13](https://github.com/ElectronicSlams/eSlams/pull/13)). If that file is not in your checkout yet, use the smoke section below and the [README Quick Start](../README.md#quick-start).

---

## What you can run today

No Hugging Face account. No eSlams provider keys.

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install eslams-core==0.6.1

eslams init
eslams run \
  --arena tic-tac-toe \
  --agent random \
  --opponent first-legal \
  --execution-profile smoke
eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

That package is a **Local Artifact**. `--execution-profile smoke` is a bounded lab run. It is not Official scoring and not a Grand Slam.

One model smoke, only if you already have a key for that provider:

```bash
export OPENAI_API_KEY=...   # your key. Never an eSlams org key.
eslams run \
  --arena tic-tac-toe \
  --agent openai:gpt-5-mini \
  --opponent first-legal \
  --execution-profile smoke
eslams validate runs/latest.eslams --profile runner-bundle
```

Set only the env var for the provider you call (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, or `AWS_BEARER_TOKEN_BEDROCK`). Credentials stay in the environment. Do not put them in CLI args, Spaces, GitHub Actions, fixtures, or artifacts. See [`SECURITY.md`](../SECURITY.md).

---

## Where samples live

| Home | What it is | Status |
| --- | --- | --- |
| GitHub [`sample_runs/`](../sample_runs/) | Small curated samples and publication bundles in this repo | In git now |
| Hugging Face dataset `ElectronicSlams/eslams-sample-runs` | Public warehouse for scrubbed bulk samples | **Not published** |
| GitHub pointers / manifests | Ids, paths, and hashes once the warehouse exists | Not a second copy of the warehouse |

The **Official suite is retired / historical**. It is not `sample_runs/`, and it is not a live hidden board you can pull. Hidden official-eval proofs, if they are published later, belong in the public warehouse only after scrub, labeled historical. GitHub keeps representative samples and catalogs, not that bulk.

Files that are actually in this tree:

| Path | What it is |
| --- | --- |
| `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams` | Deterministic chess sample, built-in `first-legal` vs `first-legal`. Local runner bundle. |
| `sample_runs/model_eval_sample/official_signed.eslams` | Deterministic tic-tac-toe **fixture**. A shape example. Not a live Official seal. `eslams validate --profile official-bundle` on `eslams-core==0.6.1` is **invalid** with `runner_signature_legacy_untrusted` (legacy HMAC, key id `fixture-key`). Trust `valid: false`. |

Inspect the battle sample with no API key:

```bash
eslams validate sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams --profile runner-bundle
```

Tier vocabulary, scrub rules, and the dual-home manifest live in [`docs/SAMPLE_CLASSIFICATION.md`](https://github.com/ElectronicSlams/eSlams/blob/docs/sample-classification-plan/docs/SAMPLE_CLASSIFICATION.md) (open PR [#14](https://github.com/ElectronicSlams/eSlams/pull/14)). This page does not restate that plan. Platform `/labs` fields live in [`docs/LABS_PAGE_CONTRACT.md`](https://github.com/ElectronicSlams/eSlams/blob/docs/labs-page-contract/docs/LABS_PAGE_CONTRACT.md) (open PR [#15](https://github.com/ElectronicSlams/eSlams/pull/15)).

---

## Hub surfaces (reserved, not live)

Checked 2026-09-23, unauthenticated:

| Check | Result |
| --- | --- |
| `GET https://huggingface.co/api/organizations/ElectronicSlams/overview` | **404** |
| `GET https://huggingface.co/api/users/ElectronicSlams/overview` | **404** (`This user does not exist`) |
| Dataset and Space API paths under that name | **401** `Invalid username or password` (Hub response for an unknown or private repo when no token is sent). There is no public org to attach them to. |

Do not run `hf download` against these ids yet. The 401 means there is no public repo to fetch.

| Surface | Reserved id | When it exists, it must |
| --- | --- | --- |
| Org | `ElectronicSlams` | Be the only namespace for the rows below |
| Dataset (warehouse) | `ElectronicSlams/eslams-sample-runs` | Be public. README pins `eslams-core==0.6.1`. Card text is [`docs/hf/eslams-sample-runs.README.md`](./hf/eslams-sample-runs.README.md). When you publish, delete the paragraph that says the card is not on the Hub yet |
| Collection | slug stem `eslams-core` | List the dataset, the docs Space, this GitHub repo, and the PyPI pin. Hugging Face appends an id to collection URLs at creation time, so this page does not invent `hf_collection_url` |
| Docs Space | `ElectronicSlams/eslams-docs` | Stay static. **Secrets empty.** No org provider keys. Viewers read docs; they do not run on eSlams credentials |

PyPI pin that the card and Space must show: <https://pypi.org/project/eslams-core/0.6.1/> (`eslams-core==0.6.1`, published).

A future Gradio Space, if one is added, is a Duplicate-and-bring-your-own-keys template. Upstream Secrets stay empty. This repo does not ship that app.

---

## Lab-pack checklist

Ready only when every row is true. This pull request does not check them off.

- [ ] Org `ElectronicSlams` resolves on the Hub.
- [ ] Dataset `ElectronicSlams/eslams-sample-runs` is public and its README is the template in `docs/hf/`, including the pin, BYO rule, and Local ≠ Official banner.
- [ ] Collection slug stem `eslams-core` exists and its real URL (with the Hub-assigned id) is written back into `docs/LABS_PAGE_CONTRACT.md` as `hf_collection_url`.
- [ ] Space `ElectronicSlams/eslams-docs` is public, static, and has no Secrets.
- [ ] No Space, dataset, or GitHub Action in the lab path contains an eSlams org provider key.
- [ ] GitHub `sample_runs/` stays the small sample set; the dataset is the warehouse; the Official suite is labeled retired / historical.
- [ ] A stranger can run the keyless smoke above and validate `run_eeab67d58b994ca7.eslams` without a Hub login.
- [ ] `docs/LABS.md` is on the default branch so the Quickstart link is in-tree.

---

## Secrets

Labs bring their own keys. Never request or paste eSlams organization provider keys, Platform worker secrets, or Hugging Face write tokens into a lab, a Space, or a pull request.

Static docs Spaces must not hold secrets. Report credential leaks to `security@eslams.com`, not in a public issue. Product contact: `hello@eslams.com`.
