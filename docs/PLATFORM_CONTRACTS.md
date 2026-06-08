# eSlams Platform Contracts

Core emits portable contracts and files that Platform can consume. Core does
not upload to R2, write D1 rows, run Wrangler, create Durable Objects, upload
video, call Stream or YouTube, or require Cloudflare credentials.

## Contract Schemas

Export deterministic JSON schemas:

```bash
eslams schemas export --out schemas/
```

Current schema versions include artifact manifests and validation summaries,
public replay events and manifests, provider receipts, eval plans, official
progress events, resume checkpoints, official results, publication bundle and
validation payloads, runner jobs, and catalogue rows.

## Artifact Validation

Validate runner bundles, official bundles, Battlefield bundles, or public
replay packages with one command:

```bash
eslams validate runs/latest.eslams --profile runner-bundle
eslams validate public_replay_package --profile public-replay-package --summary-json
```

Validation emits `eslams.artifact.validation.v1` with artifact hash, size,
artifact id, run id, verification level, replay status, scoring eligibility,
runner signature status, and safe high-level errors.

## Public Replay Export

Export a no-secret public replay package:

```bash
eslams artifact public-export runs/latest.eslams --out public_replay_package
eslams replay validate-public public_replay_package
```

Public packages include replay events, replay manifest, public result summary,
public manifest, and optional public reasoning. They do not include
`logs/agent_io.jsonl`, private traces, provider prompts, raw model responses,
request headers, tokens, or debug payloads.

## Provider Runtime

Provider receipts use `eslams.provider.receipt.v1` and include normalized
outcome, attempts, status code, request ids, gateway mode, usage, pricing
provenance, estimated cost status, and redaction version. Missing pricing is
reported as `cost_unavailable`; Core does not report zero cost unless a free
price is proven.

`ProviderRuntimeConfig` carries timeout, connect/read timeout, retry/backoff,
concurrency limit, rate limit, and generic gateway/base URL controls. Core
enforces the synchronous concurrency and rate controls at the provider call
boundary without adding a Platform-specific rate limiter dependency.

Preflight without requiring network calls or credentials:

```bash
eslams providers preflight --provider openai --model gpt-5-mini --arena tic-tac-toe
```

Generic gateway/base URL routing is configured through
`ProviderRuntimeConfig.gateway_base_url` and `gateway_mode`. Platform may map
Cloudflare AI Gateway or any other gateway to that generic route, but Core does
not import Cloudflare packages or own gateway auth.

Local CI can use `MockProviderAgent` to simulate success, timeout, parse error,
provider error, missing usage, and gateway auth failure.

## Plans, Resume, and Progress

Plan commands are no-secret and deterministic:

```bash
eslams plan official --suite public-smoke --providers openai,anthropic --arenas chess,tic-tac-toe --json
eslams plan battlefield --pairs openai:gpt-5-mini,anthropic:claude-sonnet-4-20250514 --arenas tic-tac-toe --json
eslams plan public-match --request request.json --json
```

Plans contain a stable `plan_hash`, suite fingerprint, registry hash, selected
models and arenas, expected case count, shard rows, environment variable names,
output references, and policy ids.

Resume checkpoints are keyed by case id, artifact digest, model id, suite
fingerprint, runner version, and plan hash. Progress events are JSONL rows with
current case, total cases, completed/failed/skipped counts, case rate, provider
latency rolling stats, and estimated remaining time.

```bash
eslams plan progress --plan plan.json --out progress.jsonl --current-case case-1 --completed-cases 1
eslams plan resume-check --checkpoint checkpoint.json --case-id case-1 --artifact-digest DIGEST --model-id MODEL --suite-fingerprint SUITE --runner-version RUNNER --plan-hash PLAN
```

## Runner and Arena Transport

Runner/container contracts use snake_case input and output fields. A completed
runner result without an artifact URI is invalid. Runner completion and scoring
eligibility are separate fields.

Core can smoke-test all registered arenas over JSON-serializable transport:

```bash
eslams arena smoke --all --json
eslams runner health --json
```

The stateless Arena helpers expose initial state, legal actions, step, public
state, state hash, serialize, and deserialize functions. Browser start/resume
contracts include idempotency key fields and response metadata, but Core does
not store browser sessions.

## Catalogue

Catalogue exports are public-safe:

```bash
eslams catalogue games --json
eslams catalogue models --json
eslams catalogue availability --json
eslams catalogue renderers --json
```

Models distinguish `official_eval`, `battlefield`, and `arena` capabilities.
Every model/game availability row has a status or absence reason.
Renderer rows classify all 50 arenas by renderer family, timeline
completeness, public safety, visible frames, state frames, move frames, and
state-hash status.

## Publication Bundles

Core produces deterministic publication inputs only:

```bash
eslams publish export --kind uploaded-replay --artifact runs/latest.eslams --out bundle
eslams publish export --kind official-proof --plan plan.json --artifacts runs --out bundle
eslams publish validate bundle --json
```

Bundles include public manifests, public replay files, proof index rows,
leaderboard rows, provider/model rows, aggregate usage, object manifests,
checkpoint manifests, and signature/readback manifests. Proof rows are marked
as evidence rows and are not leaderboard predicates by default. Bundle manifests
use `eslams.publication.bundle.v1`; validation emits
`eslams.publication.validation.v1` and checks object hashes, projection hashes,
public replay validity, aggregate usage shape, and proof-row publication policy.

## Fixtures

Generate fixtures without provider keys:

```bash
eslams fixtures artifact --kind local-tic-tac-toe --out fixtures/artifacts/local_tic_tac_toe.eslams
eslams fixtures artifact --kind official-signed --out fixtures/artifacts/official_signed.eslams
eslams fixtures artifact --kind official-unsigned --out fixtures/artifacts/official_unsigned.eslams
eslams fixtures replay --kind uploaded-smoke --out fixtures/artifacts/uploaded_replay_minimal.eslams.d
```

Text fixtures also cover provider receipt scenarios, public replay JSONL, a
sample official plan, and `fixtures/publication/battlefield_sample_bundle/`. CI
requires no provider API keys, no Cloudflare account, and no MP4 generation.
