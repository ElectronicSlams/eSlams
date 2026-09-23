# Agents

This repository is the public eSlams Core monorepo (`eslams-core`): arenas, the `/act` protocol, artifacts, replays, and provider adapters for PyPI, Hugging Face, and local lab use. It is not the hosted Platform and it does not contain Workers. Do not review or change Platform trees from this checkout.

## Pin

When a task depends on a published Core build, pin `eslams-core==0.6.1`. The version in `pyproject.toml` is the source of truth for this checkout.

A local run, a self-signed artifact, or a `--verification-level` string is not an Official result and is not a Grand Slam result. Official leaderboard runs stay on server-controlled infrastructure.

## Secrets and GitHub

Do not commit secrets, tokens, credentials, or `.env` contents.

Do not invite `cursoragent`, or any other Cursor bot, as a GitHub collaborator.

## Cloudflare

This tree has no Workers app and no Cloudflare deploy. If a note must mention Cloudflare, limit it to the Berkeley Cloudflare account. Do not treat any other account as in scope here.
