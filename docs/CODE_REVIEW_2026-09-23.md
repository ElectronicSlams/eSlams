# eSlams Core review (2026-09-23)

Review-only pass of `ElectronicSlams/eSlams` at `main` (`7f6bb41`, Core `0.6.1`). No application code was changed. No Critical issue had a tiny safe patch that would not also change a trust boundary.

## Scope

In scope: `src/eslams`, `src/eslams_core`, `packages/core-contracts`, `packages/core-lite`, `tests`, `.github/workflows`, `scripts`, fixtures, and the docs already on the default branch.

Out of scope:

- Hosted Platform (`eSlamsPlatformv1` / `v2`) and any Cloudflare Workers deploy. This tree has no Worker, Wrangler config, or Pages project.
- Open docs drafts #13 (`docs/LABS.md`), #14 (`docs/SAMPLE_CLASSIFICATION.md`), and #15 (`docs/LABS_PAGE_CONTRACT.md`). They were not modified, closed, or used as a base.
- Runtime execution of the full pytest matrix. Findings below are from static reading of the default-branch tree.

## Summary

No committed live credentials were found (no provider keys, cloud tokens, or private key material). Official-profile artifact checks do fail closed on an unverified or legacy HMAC signature. Public replay export copies a fixed member list and does not copy auditor or judge traces.

The serious gaps are in the runner HTTP surface and in arena session MACs: both can expose or forge hidden state when the library is used the way its own docstrings describe. Eligibility flags and `verification_level` are also copied out of the manifest even when validation failed, so a local artifact can look Official without being one.

| ID | Severity | Topic |
| --- | --- | --- |
| F1 | High | Unauthenticated runner API returns full private state |
| F2 | High | Arena session MAC falls open to a built-in secret |
| F3 | Medium | Manifest paths are not confined to the artifact root |
| F4 | Medium | Invalid artifacts still echo scoring and Official labels |
| F5 | Medium | Runner bundles uploaded by the README contain hidden state |
| F6 | Medium | PyPI workflow interpolates `workflow_dispatch` ref into the shell |
| F7 | Low | Replay zip extract and replay HTML trust archive content |
| F8 | Low | Sample `/act` server binds all interfaces with no auth |
| F9 | Low | CI supply-chain and secret-file hygiene |
| F10 | Low | Contract doc drift and `core-lite` version skew |

No Critical findings. No merge blockers in the sense of a broken default-branch build that this pass could prove; F1 and F2 are the items to fix before this runner API or session envelope is treated as a network trust boundary.

## Findings

### F1 — High: runner HTTP API has no authz and returns hidden state

`src/eslams/runner_server.py` builds a FastAPI app with `POST /runner/session/create`, `POST /runner/session/{session_id}/step`, snapshot, and close. Nothing checks a caller. `app = create_runner_app()` is importable as `eslams.runner_server:app`.

`RunnerSessionStore.create` (`src/eslams/runner_session.py`) accepts a client `sessionId` and a raw `snapshot`, then `deserialize_state`s that snapshot with no session MAC. The same id overwrites any existing session. `snapshot` returns `serialize_state`, which is `ArenaState.to_dict()` and includes `private_state_by_player` (`src/eslams/state.py`). `step` returns the raw `core_step` response. `core_step` always sets `state` to that same full snapshot (`src/eslams/core_contract.py`).

Hidden-info arenas (poker hands, Battleship ships, Hanabi) keep secrets in `private_state_by_player`. Any client that can reach this process can read them, replace them, or take over a session id.

`observationView=debug` is gated by `ESLAMS_ENABLE_DEBUG_OBSERVATION`. That gate does not cover the `state` field.

Next step: do not expose this app on a network. Require a runner credential, reject client-chosen ids or unsigned snapshots, and return the signed session envelope plus the public step fields. Keep `private_state_by_player` server-side. Add a regression that a step response has no private-state key.

### F2 — High: session envelopes verify with a public fallback secret

`src/eslams/arena_transport.py` signs `session_state` with HMAC-SHA256. `_session_secret()` uses `ESLAMS_ARENA_SESSION_SECRET` when set, and otherwise a constant development secret. An empty value takes the same path. Verification does not reject key id `development-unconfigured`, does not check timestamp age, and does not record nonce use. The nonce is the state hash, so any previously signed envelope stays valid.

`derive_seed` in `src/eslams/contracts/security.py` fails closed in production. The session path does not. `docs/PLATFORM_CONTRACTS.md` tells operators to set the secret, but a forgotten variable still produces MACs that verify.

Whoever shares that process can mint a `session_state` whose payload contains every player's private state. With a real secret, a captured envelope can still be replayed later because nothing expires it.

Next step: fail closed when the env var is missing, ignore the development constant unless an explicit dev flag is set, and reject stale timestamps. Do not put the constant in new docs or logs.

### F3 — Medium: artifact validation hashes paths outside the archive

`_materialize` and `read_member` refuse absolute paths and `..` (`_safe_artifact_subpath` in `src/eslams/artifacts.py`). `_validate_file_table` and `_validate_unhashed_file_table` do not. They open `artifact_dir / entry["path"]`. On POSIX, an absolute manifest path drops `artifact_dir`. `sha256_file` follows symlinks.

`eslams validate` on an untrusted archive or expanded directory can therefore read a host file and, if the manifest hash matches, treat that outside file as part of the artifact. Mismatch text includes the path, not the bytes. Official zip extraction strips `..` before files are written, so this is a validator join bug, not a classic zip-slip write in `_materialize`.

Next step: run every manifest path through `_safe_artifact_subpath`, then resolve and require the real path to stay under the artifact root. Refuse symlinks. Test with an absolute path and a `..` entry.

### F4 — Medium: local runs can look Official after a failed check

`ArtifactValidationReport` copies `per_case_scoring_eligible`, `proof_row_publication_eligible`, `per_case_run_valid`, and `verification_level` from the manifest (`_validation_report` in `src/eslams/artifacts.py`). `scoring_eligible` is forced false only when `profile == "official_case"` and there are errors. The other flags stay as written. `valid` is still `not errors`, but `eslams official merge` counts `per_case_scoring_eligible` from the report without requiring `valid`.

The CLI accepts any `--verification-level` string and `--execution-profile official_eval` (`src/eslams/cli.py`). Neither is tied to an Ed25519 verify key. A local match can stamp an Official-looking label and still be a runner bundle. Official profiles do add `runner_signature_missing` / `runner_signature_untrusted` when the signature is not a verified Ed25519 signature, so `valid` stays false there. Consumers that read the echoed booleans and skip `valid` will not.

`_runner_artifact_verify_key` derives the verify key from `RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY` when the public verify key is unset. A process that still has the signer will mark its own signatures verified.

Next step: if `errors` is non-empty, force scoring and publication booleans false. Treat `verification_level` as untrusted display text. Reserve Official / Grand Slam for a pinned verify key id. On auditors, set only `RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY`.

### F5 — Medium: the documented upload archive contains hidden state in plaintext

`README.md` tells users to upload `runs/latest.eslams`. That runner bundle includes:

- `traces/auditor_trace.jsonl` with `state_before` and `state_after` equal to `ArenaState.to_dict()` (`src/eslams/runner.py`)
- `traces/private_judge_trace.jsonl` and `logs/agent_io.jsonl` with the act request, observation, and response

`export_public_replay` does not copy those members. Receipt redaction in `src/eslams/agents.py` is separate and does not cover this trace.

For hidden-info games, the zip is a full reveal to whoever stores or republishes it. That may be what a private intake needs for audit. It is not a public artifact.

Next step: say so in the upload section. Publish `eslams artifact public-replay` output when the audience is public. Keep auditor traces on the intake server.

### F6 — Medium: publish workflow shell-interpolates the dispatch ref

`.github/workflows/publish.yml` is otherwise in good shape: `contents: read`, `id-token: write`, PyPI trusted publishing, and a version check that reads the ref from the environment. The ref selection step does not. `github.event.inputs.ref` is inserted into the bash script that writes `$GITHUB_OUTPUT`. `workflow_dispatch` is limited to people who can already run it, and that job can mint a PyPI publish token.

Next step: pass the ref only through `env:`, as the version-check step already does, and keep the tag check in front of `pypa/gh-action-pypi-publish`.

### F7 — Low: replay rendering trusts archive contents

`src/eslams/replay.py` calls `ZipFile.extractall` with no in-repo path check. `_materialize` has one. CPython 3.12 strips `..` and drive prefixes inside `ZipFile._extract_member`, so a normal zip-slip write is mitigated on that interpreter. The replay path still depends on the interpreter.

The generated HTML puts event JSON in a `script type="application/json"` block and escapes `</`. Most UI strings go through `escapeHtml`. Chess FEN pieces that are not in the glyph map are inserted into `innerHTML` raw. A crafted local replay file can run script in the browser that opens it.

Next step: extract replay archives with the same confinement as `_materialize`. Escape FEN characters before HTML insertion.

### F8 — Low: sample agent server listens on all interfaces

`eslams agent serve` defaults `--host` to `0.0.0.0` (`src/eslams/cli.py`, `src/eslams/agent/server.py`). `/act` and `/health` have no authentication. The sample handler is first-legal, so this is not a hidden-eval leak. It is still an open local agent if the host is reachable.

Next step: default the host to `127.0.0.1`.

### F9 — Low: CI hygiene

`.github/workflows/ci.yml` checks out with a default token and floating tags (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`). It does not set `permissions: contents: read`. It has no dependency lock, Dependabot, or CodeQL. Pull requests are `pull_request`, not `pull_request_target`, and CI does not receive provider secrets. That part is sound.

`.gitignore` does not ignore `.env`. Nothing in the tree is a live secret today.

`provider_models_live` sends the Google/Gemini key as a `key` query parameter (`src/eslams/provider_preflight.py`). The call swallows `httpx` errors, but the URL can still show up in client or proxy logs. Prefer a header.

Next step: pin Actions to SHAs, set read-only CI permissions, ignore `.env`, and stop putting API keys in query strings.

### F10 — Low: docs and package metadata drift

`docs/PROTOCOL.md` says provider receipts use `eslams.provider.receipt.v1` and that `fallback` is the smoke/demo default. Code uses `eslams.provider.receipt.v2` (`src/eslams/contracts/versions.py`) and the CLI default for `--on-agent-error` / `--on-illegal-action` is `invalid-match`.

`packages/core-lite/package.json` is `0.4.0` and depends on `@eslams/core-contracts` `0.4.0`. `packages/core-contracts/package.json` is `0.6.1`. Typecheck uses a path alias, so CI does not notice. A published `core-lite` package would not track current contracts.

`src/eslams_core` is a star-import shim. `POST /runner/session/{id}/ping` returns a snapshot, same as the snapshot route.

Next step: correct the protocol sentences when those docs are next touched. Bump or stop publishing `core-lite` until it matches `0.6.1`.

## What held up

- Official and official-case profiles reject missing, unverified, and legacy HMAC signatures (`_profile_specific_errors`).
- Run ids are confined to the output directory (`_validate_run_id`, `_artifact_output_path`). `latest.eslams` replaces only symlinks.
- Provider receipt keys and bearer/URL secrets are stripped before receipts are stored. Tests cover that redaction.
- Public payload key scanning denies secret-like names, with a narrow allowlist for action-descriptor `token` and `prompt_label`.
- Seed derivation fails closed unless a secret or an explicit development fallback is set.
- Debug observations require `ESLAMS_ENABLE_DEBUG_OBSERVATION=1`.
- No Cloudflare Worker or credential file is in this checkout.

## Suggested order

1. F1 and F2 before any shared runner or live arena session uses this tree as its edge.
2. F4 so local labels cannot be read as Official eligibility.
3. F3 and F6 as small containment patches.
4. F5 as a docs correction on the upload path.
5. F7–F10 as follow-ups.

Do not merge this review PR as a behavior change. It only adds `AGENTS.md`, `docs/DECISIONS.md`, and this report.
