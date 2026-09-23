# Agents

This repository is the public eSlams Core monorepo (`eslams-core`): arenas, the `/act` protocol, artifacts, replays, and provider adapters. It is not the hosted Platform and it does not contain Workers. Do not review or change Platform trees from this checkout.

## Pin

When a task depends on a published Core build, pin `eslams-core==0.6.1`. The version in `pyproject.toml` is the source of truth for this checkout.

A local run, a self-signed artifact, or a `--verification-level` string is not an Official result and is not a Grand Slam result.

## Secrets and GitHub

Do not commit secrets, tokens, credentials, or `.env` contents.

Do not invite `cursoragent`, or any other Cursor bot, as a GitHub collaborator.

## Cloudflare and archives

This tree has no Workers app and no Cloudflare deploy. If a note must mention Cloudflare, limit it to the Berkeley Cloudflare account. Do not treat any other account as in scope here.

Do not pull R2. Do not query, export, or delete D1. Do not run wrangler against production. Do not upload to Hugging Face. Draft PRs only until the founder says otherwise. Do not merge. Do not deploy.

## Lab pack

Hugging Face org `ElectronicSlams` is not live (404 on 2026-09-23). `hf download ElectronicSlams/eslams-sample-runs` is not a working command. The lab pack in this repo is only:

- `sample_runs/model_battle_sample/run_eeab67d58b994ca7.eslams`
- `sample_runs/model_eval_sample/official_signed.eslams`

`run_d48ff364a0b949df` is not in this tree. `official_signed` is a fixture, not current Official or Grand Slam trust. Details: [docs/LAB_PACK.md](docs/LAB_PACK.md).

## A-EX

The teaching-fail cap is 50 rows. Selection rules and the local checker are in [docs/A_EX_PLAN.md](docs/A_EX_PLAN.md). Do not select, pull, or publish A-EX objects from this checkout. `python -m eslams.public_archive` reads a local JSONL file only.

## Runner HTTP

`eslams.runner_server:app` on this branch has no request authentication. Do not bind it to a network interface. The authz draft is [PR #21](https://github.com/ElectronicSlams/eSlams/pull/21). That PR had no review comments on 2026-09-23, so this branch does not change runner HTTP behavior. Do not log session secrets. Do not add a response field that copies `private_state_by_player`.
