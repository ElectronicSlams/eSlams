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

The export also writes `schema_bundle_manifest.json`. The manifest is
deterministic and records Core package version, git commit when available,
schema bundle version, schema filenames, schema versions, SHA-256 hashes, byte
sizes, and a deterministic build id.

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

- trusted `session_state` JSON object for Platform-owned storage only
- `state_hash` and `state_hash_status`
- browser-safe `public_state`
- canonical live `display_frame` in the same shape as replay display frames
- `active_player`, `next_actor_kind`, terminal/outcome fields, and terminal scores
- legal action token strings and polished `legal_action_descriptors`
- paging metadata for large action sets
- public-safe Arena events
- phase timing fields and `total_core_ms`

`session_state` may include private or hidden game state. Platform must not
forward it to browsers or public streams. Browser-streamable fields are the
public state, display frame, action descriptors for the active actor, events,
actor metadata, terminal/outcome fields, and timing.

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
