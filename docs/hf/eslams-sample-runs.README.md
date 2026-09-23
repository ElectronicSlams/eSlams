---
license: mit
language:
  - en
tags:
  - eslams
  - evaluation
  - games
pretty_name: eSlams sample runs
---

# eSlams sample runs

Scrubbed lab samples for **eslams-core==0.6.1**. This dataset is the public warehouse. GitHub [`sample_runs/`](https://github.com/ElectronicSlams/eSlams/tree/main/sample_runs) keeps a few small samples and, later, manifests that point here.

**Local Artifact ≠ Official / Grand Slam.** Files here are lab and historical material. They are not a live Official board and not a Grand Slam seal. The Official suite is **retired / historical**.

This card is the text to publish as the dataset `README.md` after the `ElectronicSlams` org exists. It is not on the Hub yet. Instructions for that hold are in [docs/HF_LAB.md](https://github.com/ElectronicSlams/eSlams/blob/main/docs/HF_LAB.md).

## Install

```bash
pip install eslams-core==0.6.1
```

Python 3.9–3.12. Use a virtualenv.

## Secrets

Bring your own provider keys if you run a model. This dataset contains **no** eSlams org keys and must never gain any. Credentials belong in your environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK`), not in files, Spaces, or discussions.

## One smoke game

No key required:

```bash
eslams init
eslams run --arena tic-tac-toe --agent random --opponent first-legal --execution-profile smoke
eslams validate runs/latest.eslams --profile runner-bundle
```

Reserved Collection and Space ids, and the lab-pack checklist: [docs/HF_LAB.md](https://github.com/ElectronicSlams/eSlams/blob/main/docs/HF_LAB.md).

Longer BYO Quickstart (open until merged): [docs/LABS.md on PR #13](https://github.com/ElectronicSlams/eSlams/blob/docs/labs-quickstart/docs/LABS.md).
