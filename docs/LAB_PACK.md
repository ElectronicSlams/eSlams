# Lab pack

The lab pack is the two archives already in this repository. Hugging Face
org `ElectronicSlams` is **not live**. Hub check **2026-09-23**: the
organization page and `GET /api/organizations/ElectronicSlams` returned
**404**. Unauthenticated dataset and Space responses of 401 do not prove a
repo exists.

Do not run:

```text
hf download ElectronicSlams/eslams-sample-runs
```

`ElectronicSlams/eslams-sample-runs` is a reserved name for a later warehouse.
It is not a working download. This checkout has no Hub token and must not
gain one. Do not upload a dataset, Space, or Collection from this PR.

## What is on disk

| Path | What it is |
| --- | --- |
| `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams` | Short built-in `first-legal` versus `first-legal` chess run |
| `sample_runs/model_eval_sample/official_signed.eslams` | Signed official **fixture** from `eslams fixtures artifact --kind official-signed` |

`run_d48ff364a0b949df` is not in this tree. The battle archive is not a
`composer-2.5` versus `grok-build-0.1` match.

`official_signed` is a fixture. It is not a live Official result and it is
not a Grand Slam result. The directory README has the validate commands for
that fixture.

Both files are Local Artifact examples for inspection. They are not the
861-row canary, not tier A-EX, and not a public leaderboard.

## Until a dataset exists

Use the paths above. Classification of what may later be dual-published stays
in [PR #14](https://github.com/ElectronicSlams/eSlams/pull/14). The lab
quickstart stays in [PR #13](https://github.com/ElectronicSlams/eSlams/pull/13).
Neither of those drafts makes `hf download` succeed today.
