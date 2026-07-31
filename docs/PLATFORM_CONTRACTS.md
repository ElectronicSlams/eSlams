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
validation payloads, runner jobs, catalogue rows, and live Arena start/step,
event, action descriptor, and legal-action page payloads.

Core 0.6 adds these shared integrity contracts:

- `eslams.run-integrity.v2`
- `eslams.provider-attempt.v2`
- `eslams.action-provenance.v1`
- `eslams.usage-summary.v2`
- `eslams.provider.receipt.v2`
- `eslams.price-card-reference.v1`

Matching TypeScript types are exported by `@eslams/core-contracts` from
`packages/core-contracts/src/generated/integrity.ts`. Python and TypeScript
field names intentionally follow their respective wire contracts; provider
attempt events are camelCase inter-service events, while persisted Core receipt
rows remain snake_case. The package uses NodeNext-compatible ESM specifiers and
its checked compile includes a package self-reference consumer.

The export also writes `schema_bundle_manifest.json`. The manifest is
deterministic and records Core package version, git commit when available,
schema bundle version, schema filenames, schema versions, SHA-256 hashes, byte
sizes, and a deterministic build id.

## Core Step v2

Core v0.4.0 exposes a pure step contract for Platform hot paths. It is additive
to the older Arena transport helpers and uses `coreContractVersion: "2.0"`.

```python
from eslams.arena import registry
from eslams.arena_transport import serialize_state
from eslams.core_contract import CORE_CONTRACT_VERSION, core_step

arena = registry.create("tic-tac-toe")
state = arena.initial_state(seed=1)

response = core_step({
    "coreContractVersion": CORE_CONTRACT_VERSION,
    "gameId": "tic-tac-toe",
    "rulesetVersion": "standard",
    "state": serialize_state(state),
    "action": {"actionId": "4"},
    "actorId": "player_1",
    "requestId": "arena-turn-1",
    "deadlineMs": 2000,
    "includeObservation": True,
    "includeLegalActions": "compact",
    "includeReplayEvent": True,
})
```

Responses include `coreVersion`, `coreContractVersion`, `rulesetVersion`,
`promptVersion`, `actionSchemaVersion`, `replaySchemaVersion`, canonical
`previousStateHash`, `actionHash`, `nextStateHash`,
`legalActionHashBefore`, `legalActionHashAfter`, optional state,
observation, compact/full legal-action views, replay event, terminal summary,
structured error, and `timingsMs`.

`timingsMs` always includes `receivedAt` and `totalMs`; successful responses
also report stage timings such as `initMs`, `deserializeMs`, `legalActionsMs`,
`validateMs`, `applyMs`, `scoringMs`, `observationMs`, `replayEventMs`, and
`serializeMs`.

CLI equivalent:

```bash
eslams core step --request core_step_request.json
```

## Prompt and Model Action Contract

Core owns game-specific prompt packaging, but not provider routing:

```python
from eslams.core_contract import prompt_package

package = prompt_package(arena=arena, state=state, actor_id=state.active_player)
```

The package has cache-friendly `stablePrefix` blocks first, then dynamic
`moveHistory`, `currentObservation`, and `legalActions` blocks. It also carries
the per-turn `outputSchema`, parser version, `promptHash`, and approximate
`tokenEstimate`.

Shared model-action helpers live in `eslams.model_actions`:

- `parse_model_action(text, legal_actions)` accepts both
  `{"action": {"action_id": "..."}}` and legacy `{"action": ...}`.
- `action_output_schema(legal_actions)` generates the structured-output JSON
  schema with `action` as the first required field.
- `streaming_action_status(buffer, legal_actions)` reports `action_ready`
  before the public explanation has finished streaming.
- `invalid_action_retry_prompt(...)` gives Arena and official evals the same
  one-retry invalid-action repair behavior.

Invalid action taxonomy values are:
`invalid_json`, `schema_mismatch`, `unknown_action_id`,
`illegal_action_for_state`, `action_valid_but_wrong_actor`, `empty_output`,
`timeout_before_action`, and `provider_error`.

## Persistent Runner Sessions

For heavier games where Python Core stays in the hot path, v0.4.0 provides a
session-affine runner store and FastAPI app:

```python
from eslams.runner_session import RunnerSessionStore

store = RunnerSessionStore()
store.create(game_id="chess", session_id="arena_123", initial_seed=1)
store.step(session_id="arena_123", action={"actionId": "e2e4"})
store.snapshot("arena_123")
store.ping()
store.close("arena_123")
```

FastAPI routes are available from `eslams.runner_server:app`:

- `POST /runner/session/create`
- `POST /runner/session/{id}/step`
- `POST /runner/session/{id}/snapshot`
- `POST /runner/session/{id}/ping`
- `POST /runner/session/{id}/close`
- `GET /runner/session/ping`

`eslams runner health --json` now includes `ok`, `loadedGames`, `warm`, and
`uptimeMs` in addition to the existing registry/action/renderer hashes.

## Benchmarks, Budgets, and Golden Fixtures

Core v0.4.0 adds a repeatable benchmark harness:

```bash
python -m eslams_core.bench arena-step --games all --positions fixture --iterations 1000 --json out/core-step-bench.json
eslams bench arena-step --games tic-tac-toe,connect-four --iterations 100 --json out/smoke-bench.json
```

The report captures stage p95 timings, state bytes, compact observation bytes,
legal-action bytes, and approximate prompt tokens. Use
`eslams core budgets --json` to check compact observation and prompt budgets,
and `eslams core golden --games tic-tac-toe,connect-four --out fixtures/core_golden.json`
to write deterministic state/action/observation hash fixtures.

## Generated TypeScript and Core-lite

Platform-facing TypeScript artifacts are checked in under:

- `packages/core-contracts/src/generated/core-step.ts`
- `packages/core-contracts/src/generated/actions.ts`
- `packages/core-contracts/src/generated/replay.ts`
- `packages/core-contracts/src/generated/prompt.ts`
- `packages/core-contracts/src/generated/integrity.ts`

`packages/core-lite` contains a small TypeScript runtime for tic-tac-toe and
connect-four. Python Core remains the official authority; Core-lite promotion
is gated by Python parity fixtures and engine capability metadata from
`eslams core capabilities --game GAME`.

## Seed and Request Security

`eslams.contracts.security.derive_seed(...)` fails closed in production when a
secret is missing. Development public fallback must be explicitly enabled and
returns a `mode` that should be recorded in replay metadata.

Runner request signing helpers canonicalize method, path, body SHA-256,
timestamp, nonce, and request id:

```python
from eslams.contracts.security import sign_runner_request, verify_runner_request_signature

signature = sign_runner_request(
    secret="runner-secret",
    method="POST",
    path="/runner/session/arena_123/step",
    body={"action": {"actionId": "4"}},
    timestamp="2026-06-11T00:00:00Z",
    nonce="nonce",
    request_id="req_123",
    key_id="runner-key-1",
)
assert verify_runner_request_signature(secret="runner-secret", signature_payload=signature)
```

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

Canonical validation summary shape:

```json
{
  "schema_version": "eslams.artifact.validation.v1",
  "artifact": "runs/run_example.eslams",
  "profile": "runner_bundle",
  "valid": true,
  "validation_status": "valid",
  "errors": [],
  "artifact_id": "sha256:artifact",
  "run_id": "run_example",
  "verification_level": "Local Artifact",
  "verification_level_key": "local_artifact",
  "verification_level_label": "Local Artifact",
  "artifact_profile_key": "runner_bundle",
  "artifact_profile_label": "Runner Bundle",
  "archive_sha256": "sha256:archive",
  "artifact_size_bytes": 12345,
  "replay_status": "verified",
  "scoring_eligible": true,
  "per_case_run_valid": true,
  "per_case_scoring_eligible": true,
  "proof_row_publication_eligible": true,
  "aggregate_leaderboard_eligible": false,
  "aggregate_ineligibility_reason": "single_case_not_full_suite",
  "runner_signature_status": "unsigned",
  "signature": { "status": "unsigned", "verified": false },
  "deterministic_replay": {
    "status": "verified",
    "verified": true,
    "arena_id": "tic-tac-toe",
    "action_event_count": 5,
    "replay_event_count": 6
  }
}
```

Machine keys ending in `_key` are lowercase, version-stable policy inputs.
Labels ending in `_label` are display text and may change for presentation.
Core separates per-case run validity, per-case scoring eligibility, proof-row
publication eligibility, and aggregate leaderboard eligibility. A valid
one-case proof row is evidence by default; it does not imply public ranked
leaderboard eligibility.

## Public Replay Export

Export a no-secret public replay package:

```bash
eslams artifact public-export runs/latest.eslams --out public_replay_package
eslams replay validate-public public_replay_package
```

Public packages include replay events, `display_frames.jsonl`, replay manifest,
public result summary, public manifest, and optional public reasoning. The
package manifest includes optional-file rows with `path`, `kind`, `present`,
`sha256`, `size_bytes`, and `absent_reason`; `public_reasoning/reasoning.jsonl`
is explicitly present or absent.

Display frames include frame id, renderer family, visibility, actor, action
label, public display cells/summary, and source replay event id. They do not
include prompts, raw responses, private observations, provider receipts, hidden
eval material, or private reasoning.

Public packages do not include `logs/agent_io.jsonl`, private traces, provider
prompts, raw model responses, request headers, tokens, or debug payloads.

## Provider Runtime

Provider receipts written by Core 0.6 use `eslams.provider.receipt.v2` and
include normalized failure class, physical-attempt identity and kind, status
code, request IDs, gateway mode, requested/resolved model evidence,
endpoint/parser versions, normalized usage, pricing provenance, estimated cost,
application/scoring flags, and redaction version. Historical v1 receipts remain
readable at the HTTP-agent boundary, but are normalized before Core writes them.
Missing pricing is `cost_unavailable`; Core does not report zero cost unless a
complete price-card reference proves it.

`ProviderRuntimeConfig` carries timeout, connect/read timeout, retry/backoff,
concurrency limit, rate limit, reasoning mode/budgets, OpenRouter provider pins,
Bedrock region, reviewed price-card reference, and generic gateway/base URL
controls. Core enforces synchronous concurrency and rate controls at the
provider call boundary without adding a Platform-specific rate limiter
dependency. Official execution rejects nonzero adapter retries because the
official orchestrator owns whole-case retry policy.

Preflight without requiring network calls or credentials:

```bash
eslams providers preflight --provider openai --model gpt-5-mini --arena tic-tac-toe
```

This returns `preflight_mode: registry_only` and is never an account
availability claim. Add `--live` for account model discovery where supported,
one minimal inference, action parsing, and usage extraction. Platform must gate
launches on the individual live checks it requires, not on registry metadata.

## Provider Attempt v2

Every physical provider request has one deterministic event identity derived
from `physicalRunId`, `caseId`, `caseAttemptIndex`, `logicalActionId`, and
`attemptIndex`. `physicalRunId` is the unique Core execution identity and maps
exactly to artifact receipt `run_id`; it is distinct from the external
`officialRunId` and `runJobId`. The public lifecycle event includes
environment/lane/job/shard identity, route/parser/wrapper identity, request
timestamps and IDs, status and failure class, canonical usage/cost fields,
parse status, and action/scoring flags. It contains no prompt, hidden
observation, credentials, request headers, raw response, or private reasoning.

Core also supplies the frozen join context to agents in `ActRequest.metadata`:
`state_hash`, `physical_run_id`, `case_id`, `case_attempt_index`,
`shard_index`, and `logical_action_id`. Artifact receipts repeat the physical,
official-run, model-lane, run-job, case-attempt, and shard identities at the
top level; `run_id` and `physical_run_id` must be identical.

Emit a `started` event before the network request, followed by one terminal
`completed` or `failed` event with the same `eventId`. `attemptIndex` is
positive and gap-free within a logical action; `caseAttemptIndex` is positive
and scopes whole-case retries. `parentAttemptId` links repair/retry lineage.
Valid attempt kinds are `primary`, `case_retry`, `action_repair`, and `canary`.
For `caseAttemptIndex > 1`, the first physical provider attempt is
`case_retry`; an action-repair request remains `action_repair`.

`caseValidForScoring` describes the game action only: a completed applied
action with trusted model identity and successful wire/action parsing. Usage
or cost can still be incomplete. Incomplete accounting remains visible and
forces `per_case_scoring_eligible` and `proof_row_publication_eligible` false,
without rewriting the underlying gameplay verdict.

Canonical usage semantics are explicit:

- `cachedInputTokens` is a subset of `inputTokens`.
- `reasoningIncludedInOutput` declares whether reasoning is already in
  `outputTokens`.
- `totalTokens = inputTokens + outputTokens` when reasoning is inclusive.
- Separately reported reasoning is added exactly once when it is not inclusive.
- Provider-reported totals are retained but must reconcile with the canonical
  derivation.
- negative, non-finite, missing, or incoherent values make usage/cost
  incomplete.

Cost completeness requires a finite non-negative value, `costSource`, and a
complete provider/model-matching `eslams.price-card-reference.v1`. A bare
`rateCardId` is not proof.

Generic gateway/base URL routing is configured through
`ProviderRuntimeConfig.gateway_base_url` and `gateway_mode`. Platform may map
Cloudflare AI Gateway or any other gateway to that generic route, but Core does
not import Cloudflare packages or own gateway auth.

Local CI can use `MockProviderAgent` to simulate success, timeout, parse error,
provider error, missing usage, and gateway auth failure.

Runner metrics normalize provider status as:

- `provider_ok`
- `provider_receipt_missing`
- `provider_usage_unavailable`
- `local_agent`
- `agent_error`

HTTP agents are classified as provider-backed when configured with provider and
model endpoint metadata. Provider receipts preserve no-secret summaries for
model id, provider id, request ids, finish status, latency, usage, and
cost/pricing provenance. Missing, stripped, or redacted usage always carries an
unavailable reason.

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
eslams runner result --artifact runs/latest.eslams --artifact-uri URI --job-id JOB
```

The legacy stateless Arena helpers expose initial state, legal actions, step,
public state, state hash, serialize, and deserialize functions. Core v0.3.0
also exposes a lightweight live Arena session transport for trusted Platform
orchestration:

```python
from eslams.arena_transport import legal_actions_page, start_session, step_session

players = {
    "player_1": {"kind": "human", "label": "Human"},
    "player_2": {"kind": "model", "label": "AI"},
}

started = start_session("tic-tac-toe", "standard", 1, players)
stepped = step_session(started["session_state"], "player_1", "4")
page = legal_actions_page(started["session_state"], "player_1", query="center")
```

CLI equivalents:

```bash
eslams arena start --game tic-tac-toe --variant standard --seed 1 \
  --players-json '{"player_1":{"kind":"human"},"player_2":{"kind":"model"}}'
eslams arena step --state session_state.json --player-id player_1 --action-token 4
eslams arena legal-actions-page --state session_state.json --player-id player_1 --query center
```

Start and step results emit:

- signed opaque `session_state` envelope for Platform/server storage only
- `state_hash` and `state_hash_status`
- browser-safe `public_state`
- canonical live `display_frame` in the same shape as replay display frames
- `active_player`, `next_actor_kind`, terminal/outcome fields, and terminal scores
- legal action token strings and polished `legal_action_descriptors`
- paging metadata for large action sets
- public-safe Arena events
- phase timing fields and `total_core_ms`

`session_state` is verified with `ESLAMS_ARENA_SESSION_SECRET`; set that secret
in every production runner/container that creates or steps live Arena sessions.
Platform must not forward the envelope to browsers or public streams.
Browser-streamable fields are the public state, display frame, action
descriptors for the active actor, events, actor metadata, terminal/outcome
fields, and timing.

Action descriptor rows use `eslams.arena.action_descriptor.v1` and include
stable `token`, `label`, `short_label`, `verb`, `object`, `category`, `group`,
`sort_key`, `prompt_label`, `confirm`, and `disabled_reason`. Tokens are stable
strings: string actions pass through unchanged, while numeric/list/object
actions use canonical JSON text.

Events use `eslams.arena.event.v1`. Core emits `session.started`,
`human.action.accepted`, `model.action.accepted`, `state.applied`,
`model.action.requested`, `turn.ready_for_human`, `match.completed`, and
`turn.failed`; `arena.auto_advanced` is reserved for future automatic Arena
transitions. Events, descriptors, and display frames are public-safe and never
include prompts, raw responses, private observations, provider receipts, hidden
eval material, or private reasoning.

Large action sets use `legal_actions_page(session_state, player_id, query,
limit, cursor)`, which returns `total_legal_actions`,
`total_matching_actions`, `has_more`, `next_cursor`, and descriptor rows.
Limits are bounded to 200 rows per page.

`deserialize_state(payload, strict_hash=True)` is strict by default and raises
on stale hashes for artifact and replay validation. Trusted server-owned
interactive state may use `strict_hash=False` to repair the canonical hash and
inspect safe mismatch diagnostics on the returned state object.

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

Game rows transcribe Platform public identity fields: display names, category
labels, variants, difficulty, maturity, and player counts. Category labels are:
`board` -> `Board & Strategy`, `card` -> `Card & Hidden-Info`, `gametheory` ->
`Social & Economic`, and `rl` -> `Control & Arcade`.

Model rows expose provider-control capabilities, supported reasoning modes,
accepted control fields, default reasoning track, whether the track is
provider-controlled or provider-native, unsupported-control reasons, and HTTP
agent payload guidance.

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
also carry publication kind key/label and aggregate leaderboard eligibility.
They use `eslams.publication.bundle.v1`; validation emits
`eslams.publication.validation.v1` and checks object hashes, projection hashes,
public replay validity, aggregate usage shape, and proof-row publication policy.

## Release v0.3.2

`v0.3.2` is the follow-up patch release for the Core Arena transport contract
line. The package version is `0.3.2`, and runner defaults emit
`eslams-runner:0.3.2`.

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.2 -m "eSlams Core v0.3.2"
git push origin main v0.3.2
```

## Release v0.3.1

`v0.3.1` is the patch release for the Core Arena transport contract line. The
package version is `0.3.1`, and runner defaults emit `eslams-runner:0.3.1`.

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.1 -m "eSlams Core v0.3.1"
git push origin main v0.3.1
```

## Release v0.3.0

`v0.3.0` is the named Core Arena transport contract release. The package
version is `0.3.0`.
After validation, tag and publish from main:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy src
git tag -a v0.3.0 -m "eSlams Core v0.3.0"
git push origin main v0.3.0
```

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
