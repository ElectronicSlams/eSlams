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

## Runner HTTP and arena sessions

`eslams runner session-*` is an in-process local store. The network boundary is `eslams.runner_server:app`. That app requires HMAC request signatures from `sign_runner_request` (`ESLAMS_RUNNER_REQUEST_SECRET` and `ESLAMS_RUNNER_REQUEST_KEY_ID`). It does not ship a built-in secret. Rotate by setting `ESLAMS_RUNNER_REQUEST_SECRET_PREVIOUS` and `ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS` to the current values, installing the new secret and key id, restarting callers, then removing the previous pair. Do not log secrets.

`ESLAMS_ARENA_SESSION_SECRET` is required for arena `session_state` HMACs. A missing, empty, short, or development-constant secret fails closed. `ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET=1` is local-only and is ignored when `ESLAMS_ENV` is `production`, `prod`, or `staging`. Do not log or copy the development constant into docs.
