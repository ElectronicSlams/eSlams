# ESLamscore Core change implementation plan

## Goal

Make eSlams Core the stable evaluation and artifact contract layer that the eSlams Platform can implement against, without forcing Platform-specific Cloudflare, D1, R2, Wrangler, Stream, YouTube, Durable Object, or Next.js concerns into Core.

The correct direction is not to rebuild the whole Platform inside Core. The correct direction is to make Core produce deterministic, safe, versioned contracts, artifacts, replay exports, provider receipts, eval plans, and fixtures that Platform can consume without glue code.

## Current repo assessment

The current repo is a compact Python package named `eslams-core`. It already has a strong base:

- CLI commands for `init`, `arenas`, `models`, `run`, `validate`, `replay`, and `agent` helpers.
- A deterministic single-match runner with per-action `time_budget_ms`, failure policies, traces, replay events, scores, provider receipts, and artifact writing.
- A strict `/act` protocol with `protocol_version`, legal actions, observations, history, and a time budget.
- 50 registered public arenas.
- A v1 `.eslams` artifact writer and validator with manifest hashes, required trace/log/receipt/environment/broadcast files, optional runner signature, and deterministic replay validation.
- Direct provider adapters for OpenAI, Anthropic, and Gemini.
- A provider registry with model metadata and a single `game_agent_supported` flag.

Main gaps:

- Core does not yet own stable Platform-facing export contracts.
- The runner is single-match oriented, not suite/shard/resume oriented.
- Provider runtime lacks first-class concurrency, retry, timeout, rate-limit, gateway mode, normalized cost, and failure receipt semantics.
- Public replay exports are too thin. They need actor metadata, public safety validation, participant metadata, timeline completeness, renderability, reasoning references, and state-hash status.
- Artifact validation has only one full-runner profile. Upload/public replay packages need a separate validation profile.
- Current provider receipts can include implementation/debug fields and do not normalize usage/cost across providers.
- The registry does not distinguish `official_eval`, `battlefield`, and `arena` eligibility.
- Broadcast/VOD metadata exists, but Core should not generate MP4s. Core should emit metadata and let Platform or a renderer pipeline create video if needed.

## Platform follow-up after `ed3def64` integration - 2026-06-09

Platform has now pinned and deployed Core commit `ed3def64da73978f2fd6bea0f1256d530cfec01c` and aligned the runner with `eslams validate --profile runner-bundle --summary-json`. The remaining Core asks from this integration pass are:

1. **Cut a named Core release or contract bundle version for `ed3def64`.** Platform audits and deploy notes should be able to reference a stable Core release/tag plus schema bundle version, not only an unreleased commit SHA.
2. **Publish exact `eslams.artifact.validation.v1` summary fixtures.** Include at least one runner bundle, one official bundle, one Battlefield bundle, and one public replay package. The fixture should show the canonical snake_case top-level fields such as `schema_version`, `archive_sha256`, `artifact_size_bytes`, `artifact_id`, `run_id`, `verification_level`, `replay_status`, `scoring_eligible`, and `runner_signature_status`.
3. **Ship a canonical runner result fixture/helper.** Platform still has to tolerate historical `artifact_key` and nested compatibility fields. Core should provide a single `RunnerJobResult` JSON fixture/helper that uses canonical `artifact_uri`/artifact location semantics, makes completed-without-artifact invalid, and cleanly separates runner completion from scoring eligibility.
4. **Expose public variant labels in the game catalogue export.** Platform alignment currently passes with a warning because Core runtime `variant_token` is still `default` for 23 non-standard Platform variants. Platform keeps buildplan labels for public display until Core exports the public label and canonical runtime token together.
5. **Document public replay optional-file guarantees.** Core public replay exports now include optional public reasoning. Platform needs the manifest to explicitly say whether `public_reasoning/reasoning.jsonl` exists, which events reference it, and whether missing reasoning means unavailable, redacted, or not applicable.

## Product and architecture decisions

### Accepted into Core

Core should own these because they are evaluation, artifact, schema, replay, provider-runtime, or deterministic-planning concerns:

1. Versioned no-secret artifact, replay, validation, public proof, official result, provider receipt, eval plan, runner job, and catalogue contracts.
2. Public-safe replay export and validation.
3. Archive-aware artifact extraction and summary helpers.
4. Provider runtime controls and normalized receipts.
5. Model and arena eligibility classifications.
6. Official eval planning, sharding, resume checkpoints, progress events, and merge summaries.
7. Deterministic fixtures and CI coverage.
8. Runner/container input and output schemas, including stateless Arena start/step contracts.
9. Public catalogue metadata for games, models, eligibility, renderability, and coming-soon reasons.
10. Documentation and examples for direct providers, generic gateway/base-url routing, and local mock providers.

### Rejected or moved out of Core

These should not be implemented as Core dependencies:

| Recommendation type | Decision | Replacement in Core |
|---|---:|---|
| Generate MP4/VOD files | Reject | Emit replay and broadcast metadata only. Platform or renderer jobs may produce MP4 externally. |
| Cloudflare AI Gateway as mandatory dependency | Reject as mandatory | Add optional generic `gateway_base_url`, `gateway_mode`, and redacted gateway metadata. Platform owns Cloudflare auth/binding specifics. |
| Wrangler, R2 object upload loops, D1 writes, D1 activation windows | Reject | Core emits deterministic publication bundles, object manifests, hashes, and checkpoints. Platform applies them to storage/database. |
| D1 table creation and migration logic | Reject | Core publishes projection schemas and field mappings only. |
| Cloudflare Durable Object browser session implementation | Reject | Core publishes stateless Arena start/step/resume contracts and fixtures. Platform owns session persistence. |
| Browser rate limiter implementation | Reject | Core publishes idempotency keys, telemetry field definitions, and safe start/resume response schema. Platform owns enforcement. |
| Cloudflare Stream or YouTube upload implementation | Reject | Core publishes optional destination metadata fields and failure reasons. |
| Next.js generated route/type artifact lifecycle | Reject | Platform build tooling concern. |
| Profile database 404/migration behavior | Reject | Platform public-data concern. |
| Public web copy for Platform pages | Mostly reject | Core should lint only Core-generated public manifest/display strings. |

## Canonical design rules

1. **Core emits contracts, not Platform infrastructure.** No Cloudflare SDK, Wrangler shellouts, D1 writes, R2 uploads, YouTube uploads, or Stream uploads in Core.
2. **No raw prompt/response leakage in public outputs.** Public exports must be structurally incapable of containing provider prompts, raw model responses, API headers, tokens, private traces, or debug blobs.
3. **One canonical schema, compatibility projections allowed.** Core uses snake_case in artifact contracts. Platform-specific compact/camelCase/D1 names are generated projections, not the source of truth.
4. **Artifacts remain portable.** `.eslams` stays zip-compatible and locally validatable.
5. **Broadcast video is optional.** Replay is the authoritative public timeline. Video is a separate optional media export with metadata only in Core.
6. **Every absence has a reason.** Untested, private-only, not replay-ready, not arena-ready, provider-unavailable, unsupported-modality, and coming-soon states must be explicit.
7. **All expensive work has a dry-run plan hash.** Official evals, Battlefield smoke, publication export, and proof-index export must produce deterministic no-secret plans before execution.

## Implementation waves

### Wave 0 - Contract foundation and compatibility map

**Purpose:** Create a stable schema layer before changing runner behavior.

Files/modules to add:

- `src/eslams/contracts/__init__.py`
- `src/eslams/contracts/versions.py`
- `src/eslams/contracts/artifact.py`
- `src/eslams/contracts/replay.py`
- `src/eslams/contracts/provider.py`
- `src/eslams/contracts/eval_plan.py`
- `src/eslams/contracts/publication.py`
- `src/eslams/contracts/runner_job.py`
- `src/eslams/contracts/catalogue.py`
- `src/eslams/contracts/safety.py`
- `src/eslams/contracts/json_schema.py`

Actions:

- Add explicit schema version constants:
  - `eslams.artifact.manifest.v1`
  - `eslams.artifact.validation.v1`
  - `eslams.replay.public.v1`
  - `eslams.replay.manifest.v1`
  - `eslams.provider.receipt.v1`
  - `eslams.eval.plan.v1`
  - `eslams.official.result.v1`
  - `eslams.runner.job.v1`
  - `eslams.catalogue.game.v1`
  - `eslams.catalogue.model.v1`
- Publish a compatibility map from old artifact fields to canonical fields.
- Keep current v1 artifacts valid. Do not force a breaking artifact version bump unless unavoidable.
- Generate JSON schema files under `schemas/` during tests or release.
- Add `eslams schemas export --out schemas/`.

Acceptance criteria:

- `pytest` validates that every contract has a schema version and a no-secret example fixture.
- Existing artifacts produced by the current runner still validate.
- New generated schemas are deterministic byte-for-byte across repeated runs.

### Wave 1 - Artifact v1.1, validation profiles, and public-safe exports

**Purpose:** Make artifacts safe and easy for Platform to consume without parsing private internals.

Actions:

- Extend `ArtifactManifest` additively with:
  - `manifest_schema_version`
  - `artifact_profile`: `runner_bundle | public_replay_package | official_bundle | battlefield_bundle`
  - `artifact_kind`: `local_match | official_eval_case | battlefield_match | arena_session | uploaded_replay`
  - `model_identity_by_player`
  - `run_metadata`
  - `scoring_safety_reason`
  - `runner_signature_status`
  - `public_exports`
  - `validation_summary_path`
- Add validation profiles:
  - `runner_bundle`: current full required file set.
  - `official_bundle`: full runner bundle plus signature and official result requirements.
  - `battlefield_bundle`: full runner bundle plus public match/replay projection requirements.
  - `public_replay_package`: only `manifest.json`, `replay/replay_events.jsonl`, `replay/replay_manifest.json`, and optional public trace/reasoning files.
- Add `scores/official_result.json` for official runs.
- Add `public/public_manifest.json` sidecar for no-secret public artifact summary.
- Add `public/public_result_summary.json` with stable top-level keys:
  - `schema_version`
  - `run_id`
  - `arena_id`
  - `winner`
  - `outcome`
  - `score`
  - `reason`
  - `valid_for_scoring`
  - `scoring_safety_reason`
- Add archive-aware helpers:
  - `open_artifact(path)`
  - `read_member(path, member)`
  - `extract_validation_summary(path)`
  - `extract_provider_usage(path)`
  - `extract_public_manifest(path)`
- Update `eslams validate`:
  - `--profile runner-bundle|official-bundle|battlefield-bundle|public-replay-package|auto`
  - `--summary-json`
  - output `eslams.artifact.validation.v1`
  - include archive hash, artifact size, artifact id, run id, verification level, validation status, replay status, scoring eligibility, runner signature status, safe errors.
- Keep safe errors high-level. No raw provider payloads, prompts, responses, internal storage paths, or secrets.

Acceptance criteria:

- Current artifacts validate under `runner_bundle`.
- Minimal public replay packages validate under `public_replay_package` and fail under `official_bundle`.
- Unsigned official artifacts produce a deterministic `runner_signature_missing` rejection.
- Validation output is stable enough for Platform signing and publication.

### Wave 2 - Public replay contract and safety scanner

**Purpose:** Make replay the reliable in-page product surface. Do not make MP4 the core product surface.

Actions:

- Extend `ReplayEvent` additively:
  - `schema_version`
  - `actor_player`
  - `seat`
  - `state_hash_before`
  - `state_hash_after`
  - `action_label`
  - `public_reasoning_ref`
  - `visibility`: `public | trinity | private`
  - `public_safe`: bool
  - `state_hash_valid`: bool | null
  - `state_hash_invalid_reason`: string | null
- Update runner replay generation so the event after an action carries the actor who made that action, not only the next active player.
- Add `PublicReplayManifest` with:
  - `schema_version`
  - `replay_id`
  - `run_id`
  - `arena_id`
  - `variant_id`
  - `event_count`
  - `visible_frame_count`
  - `state_frame_count`
  - `move_frame_count`
  - `setup_only`
  - `timeline_completeness`: `playable | partial | setup_only | metadata_only | unavailable`
  - `renderer_kind`
  - `render_hints_version`
  - `public_state_shape_version`
  - `has_public_state`
  - `state_hash_valid`
  - `participants`
  - `showcase_ready`
  - `minimum_autoplay_frames`
  - `autoplay_ready`
  - `reasoning_frame_coverage`
- Add canonical render hint vocabulary for all 50 game families.
- Add public reasoning export:
  - `public_reasoning/reasoning.jsonl`
  - fields: `turn`, `seat`, `actor_player`, `action`, `state_hash_before`, `state_hash_after`, `public_explanation`, `source_event_id`.
- Add public replay safety scanner:
  - recursively deny keys matching private/provider/prompt/response/token/request/header/secret/API-key/debug/raw patterns in public replay outputs.
  - scan replay events, replay manifests, public traces, public reasoning, live event snapshots, and public match projections.
- Add CLI:
  - `eslams artifact public-export ARTIFACT --out DIR`
  - `eslams replay validate-public ARTIFACT_OR_DIR`
  - `eslams fixtures replay --kind uploaded-smoke --out DIR`
- Replace MP4-oriented recommendations with metadata-only broadcast contract:
  - `broadcast/broadcast_manifest.json`
  - `broadcast/vod_metadata.json`
  - `broadcastVideoAvailable`: bool
  - optional `r2_key`, `stream_uid`, `youtube_id`, `status`, `hash`, `failure_reason`
  - no MP4 generation in Core.

Acceptance criteria:

- Tic-Tac-Toe and Connect Four replay exports include actor seat, visible frames, legal actions, public reasoning, and state hash status.
- All 50 arenas have either a safe visible timeline fixture or an explicit `setup_only` classification.
- Safety scanner fails a fixture containing nested raw provider response data.
- Public exports never contain `logs/agent_io.jsonl`, private traces, provider prompts, raw responses, API headers, tokens, or provider debug previews.

### Wave 3 - Provider runtime hardening

**Purpose:** Make model-backed runs predictable and auditable without tying Core to Cloudflare.

Actions:

- Add `ProviderRuntimeConfig`:
  - `timeout_ms`
  - `connect_timeout_ms`
  - `read_timeout_ms`
  - `max_retries`
  - `retry_backoff_ms`
  - `concurrency_limit`
  - `rate_limit_per_minute`
  - `gateway_base_url`
  - `gateway_mode`: `disabled | generic_base_url | platform_gateway | direct_provider`
  - `gateway_auth_mode`: `disabled | provided_header | platform_owned | unknown`
- Add provider-specific defaults for OpenAI, Anthropic, Gemini, but keep them configurable.
- Replace hard-coded 60-second provider HTTP timeout with request/runtime config.
- Add provider preflight:
  - `eslams providers preflight --provider openai --model MODEL --arena tic-tac-toe`
  - validates model registry entry, API availability if configured, one legal action, response parsing, usage extraction, timeout behavior, and redacted receipt shape.
- Add generic gateway/base-url support, not Cloudflare-specific dependency:
  - Allow base URL override and redacted gateway metadata in receipts.
  - Do not import Cloudflare packages or require Cloudflare credentials.
  - Platform can map its Cloudflare Gateway binding to this generic route.
- Normalize provider receipts to `eslams.provider.receipt.v1`:
  - `provider`
  - `model`
  - `locked_model_id`
  - `agent_id`
  - `agent_version`
  - `turn_id`
  - `attempt`
  - `outcome`: `ok | provider_error | provider_timeout | parse_error | no_action | gateway_auth_failed | unavailable`
  - `status_code`
  - `request_id`
  - `gateway_mode`
  - `gateway_request_id`
  - `latency_ms`
  - `usage`
  - `usage_unavailable_reason`
  - `pricing`
  - `estimated_cost`
  - `redaction_version`
- Persist receipts for failed and partially attempted provider turns, including safe failure metadata and any available usage.
- Remove or quarantine debug-only fields from public/aggregate receipts:
  - no raw output preview in public receipts.
  - no raw prompt, raw response, request headers, tokens, or provider keys.
- Add usage aggregation:
  - per-turn usage
  - per-run usage
  - official aggregate usage by model
  - Battlefield aggregate usage summary
  - `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`, `total_tokens`
  - explicit unavailable reasons when provider usage is absent.
- Add provider-neutral pricing provenance:
  - pricing table version
  - currency
  - billable token categories
  - source
  - unavailable reason

Acceptance criteria:

- Mock providers can simulate success, timeout, parse error, provider error, missing usage, and gateway auth failure.
- Every provider attempt produces a safe receipt row.
- Cost is never reported as `0` unless it is proven free. Missing pricing becomes `cost_unavailable`.
- Gateway support is optional and generic. Cloudflare-specific route/auth behavior remains Platform-owned.

### Wave 4 - Registry, catalogue, and eligibility split

**Purpose:** Stop treating every text model as launch-safe.

Actions:

- Extend `ModelCapabilities`:
  - `capability_flags`: `official_eval`, `battlefield`, `arena`, each with bool and reason.
  - `allowed_games`
  - `unsupported_games`
  - `launch_status`: `ready | coming_soon | not_supported | retired | provider_unavailable | private_only | not_evaluated`
  - `eligibility_reasons`
  - `source_model_id`
  - `public_slug`
  - `display_name`
  - `modality_summary`
- Keep `game_agent_supported` for backward compatibility, but do not use it as the sole launch gate.
- Add catalogue exports:
  - `eslams catalogue games --json`
  - `eslams catalogue models --json`
  - `eslams catalogue availability --json`
- Add generated 50-game catalogue metadata:
  - display group
  - display name
  - variant token
  - scenario levels
  - action schema version
  - renderer family
  - browser play availability
  - replay availability
  - official eval availability
  - coming-soon reason
- Add per-game public rules/scoring metadata for all 50 games, starting with concise safe copy and machine-readable scoring summaries.
- Add public model catalogue export with provider label, public slug, source model id, modality, launch status, and explicit absence reasons.

Acceptance criteria:

- Official eval planning cannot accidentally select every text model from a public model feed.
- Public Battlefield cannot use official-only hidden-suite eligibility as arena eligibility.
- Every model/game intersection has a status or absence reason.
- Platform can render coming-soon states without inventing dummy scores.

### Wave 5 - Eval planning, sharding, resume, and progress

**Purpose:** Make official and showcase evals reproducible, resumable, and cheap to supervise.

Actions:

- Add `eslams plan` command family:
  - `eslams plan official --suite SUITE --providers openai,anthropic --arenas chess,tic-tac-toe --json`
  - `eslams plan battlefield --pairs PAIRS --arenas ARENAS --json`
  - `eslams plan public-match --request REQUEST.json --json`
- Output no-secret deterministic plan envelope:
  - `schema_version`
  - `kind`
  - `generated_at`
  - `plan_hash`
  - `suite_fingerprint`
  - `core_version`
  - `runner_version`
  - `registry_hash`
  - `selected_providers`
  - `selected_models`
  - `selected_arenas`
  - `case_count_expected`
  - `shards`
  - `required_environment_names`
  - `output_references`
  - `policy_ids`
- Add shard support:
  - `shard_index`
  - `shard_count`
  - deterministic case partitioning by case id.
- Add resume support keyed by:
  - `case_id`
  - `artifact_digest`
  - `model_id`
  - `suite_fingerprint`
  - `runner_version`
  - `plan_hash`
- Add structured progress JSONL events:
  - current case
  - total cases
  - completed cases
  - failed cases
  - skipped cases
  - case rate
  - provider latency rolling stats
  - estimated remaining time
- Add official result merge:
  - `eslams official merge RUN_DIR --out official_result.json`
  - include leaderboard-ready public fields, validation status, aggregate token/cost usage, proof counts, and audit links/placeholders.

Acceptance criteria:

- Re-running the same plan produces the same `plan_hash`.
- Shards are disjoint and cover the full case set.
- Resume skips completed cases only when the invariant tuple matches.
- Interrupted runs do not repeat completed paid provider cases.
- Progress output is machine-readable JSONL, not human-only text.

### Wave 6 - Runner/container and Arena stateless contracts

**Purpose:** Make the Core runner easy for Platform containers to call without embedding Platform assumptions.

Actions:

- Publish `RunnerJobRequest` and `RunnerJobResult` schemas:
  - snake_case input fields.
  - artifact output target fields, but generic, not R2-specific.
  - expected artifact key/URI response shape.
  - rule: completed runner result without artifact location is invalid.
  - explicit distinction between runner completion and scoring eligibility.
- Add failure categories:
  - `provider_timeout`
  - `runner_timeout`
  - `artifact_validation_failed`
  - `illegal_action`
  - `no_action`
  - `state_hash_invalid`
  - `gateway_auth_failed`
  - `runner_signature_missing`
- Add retry recommendation block:
  - `rerun_after_repair`
  - `record_non_scoring_result`
  - `retry_with_reviewed_policy`
  - `do_not_retry`
- Add runner health payload schema:
  - `core_commit`
  - `core_version`
  - `registry_hash`
  - `game_count`
  - `renderer_vocabulary_hash`
  - `action_schema_hash`
- Add stateless Arena APIs:
  - `initial_state`
  - `legal_actions`
  - `step`
  - `public_state`
  - `state_hash`
  - `serialize_state`
  - `deserialize_state`
- Add Arena browser start/resume contract shape:
  - idempotency key fields: user, game, model, client intent, optional session key.
  - response fields: `created`, `existing`, `session_id`, `current_turn`, `state_hash`, `legal_action_count`, `replay_readiness`.
  - no actual browser session store in Core.

Acceptance criteria:

- Platform can call a Core runner/container using one documented JSON schema.
- Core can prove all 50 games can initialize, serialize, deserialize, hash, and expose legal actions over JSON transport without provider calls.
- Runner completion and official scoring eligibility are separate fields in all reports.

### Wave 7 - Publication bundle and proof-index exports

**Purpose:** Give Platform deterministic publication inputs without making Core own storage/database execution.

Actions:

- Add publication bundle exporter:
  - `eslams publish export --kind official-proof --plan PLAN.json --artifacts DIR --out BUNDLE_DIR`
  - `eslams publish export --kind battlefield-sample --artifacts DIR --out BUNDLE_DIR`
  - `eslams publish export --kind uploaded-replay --artifact ARTIFACT --out BUNDLE_DIR`
- Bundle contents:
  - public manifest JSONL
  - public replay manifest/events
  - proof index JSONL
  - leaderboard rows JSONL
  - provider/model rows JSONL
  - aggregate usage JSON
  - object manifest with hashes and sizes
  - checkpoint manifest
  - signature/readback manifest
- Full proof export fields:
  - plan hash
  - suite fingerprint
  - object manifest hash
  - statement/projection hash
  - completed object count
  - completed projection chunk count
  - timestamps derived from immutable plan/report evidence or recorded explicitly in the plan.
- Staging semantics:
  - insert/replace first.
  - stale-delete last.
  - never reduce existing public sample proof coverage during all-case staging.
  - activation allowed only when proof counts match published game counts or row is explicitly `sample_verified`.
- Do not implement direct D1/R2 writes in Core. Optional adapters can live in Platform or a separate deployment tool.

Acceptance criteria:

- Publication export is deterministic across invocations.
- Bundle can be validated without secrets.
- Full-proof checkpoint cannot skip chunks if projection logic changes.
- Public proof rows are clearly marked as evidence rows and cannot accidentally become leaderboard predicates unless explicitly configured.

### Wave 8 - Fixtures, smoke tests, and CI matrix

**Purpose:** Prevent regressions and make Platform integration cheap.

Fixtures to add:

- `fixtures/artifacts/local_tic_tac_toe.eslams`
- `fixtures/artifacts/uploaded_replay_minimal.eslams`
- `fixtures/artifacts/official_signed.eslams`
- `fixtures/artifacts/official_unsigned.eslams`
- `fixtures/replay/public_tic_tac_toe.jsonl`
- `fixtures/provider/mock_success.json`
- `fixtures/provider/mock_timeout.json`
- `fixtures/provider/mock_parse_error.json`
- `fixtures/provider/mock_missing_usage.json`
- `fixtures/publication/official_plan.json`
- `fixtures/publication/battlefield_sample_bundle/`

Tests to add:

- artifact compatibility tests.
- artifact profile validation tests.
- public replay safety scanner tests.
- public reasoning binding tests.
- all-50 arena start/step/serialize smoke.
- all-50 replay renderability/completeness classification.
- provider runtime mock tests.
- provider receipt redaction tests.
- plan hash determinism tests.
- shard partition/resume tests.
- official result merge tests.
- publication bundle determinism tests.
- signed and unsigned official artifact tests.

Acceptance criteria:

- `pytest`, `ruff`, and `mypy` pass.
- No provider API keys are required for CI.
- No Cloudflare account is required for CI.
- No MP4 generation is required for CI.

## Detailed change list by file area

### CLI

Update `src/eslams/cli.py`:

- Add `schemas export`.
- Add `artifact public-export`.
- Add `replay validate-public`.
- Add `providers preflight`.
- Add `plan official|battlefield|public-match`.
- Add `official merge`.
- Add `publish export`.
- Add `arena smoke --all`.
- Add `catalogue games|models|availability`.
- Add `validate --profile --summary-json`.

### Runner

Update `src/eslams/runner.py`:

- Add suite/case context fields to `RunConfig`.
- Add actor metadata to trace and replay events.
- Add requested and effective timeout metadata.
- Add scoring safety reason enum.
- Add provider runtime config and receipt normalization.
- Add public replay completeness counters.
- Keep single-match `eslams run` behavior working.

### Events

Update `src/eslams/events.py`:

- Extend `ReplayEvent` with actor, seat, state hash before/after, safety, state-hash validity, and reasoning reference fields.
- Extend `ScoreSummary` with official scoring safety fields and aggregate usage/cost fields.
- Add public result summary models.

### Artifacts

Update `src/eslams/artifacts.py`:

- Add manifest v1.1 additive fields.
- Add validation profiles.
- Add no-secret validation summary.
- Add archive-aware extraction helpers.
- Add official result, public manifest, and public replay sidecars.
- Add public safety scan hooks.
- Add signed/unsigned fixture validation.

### Providers

Update `src/eslams/agents.py` and `src/eslams/providers/*`:

- Add provider runtime config.
- Add retry/timeout/rate/concurrency controls.
- Add preflight logic.
- Add generic base-url/gateway mode.
- Normalize receipts.
- Remove debug/raw text from public receipts.
- Add failed-attempt receipts.
- Add usage/cost aggregation.

### Registry and catalogue

Update `src/eslams/providers/capabilities.py`, `src/eslams/providers/registry.py`, provider data files, and a new catalogue module:

- Add `official_eval`, `battlefield`, `arena` capability flags.
- Add model public slug/display/source fields.
- Add game catalogue metadata.
- Add availability exports and absence reasons.
- Keep backward compatibility for `game_agent_supported`.

### Replay

Update `src/eslams/replay.py` and add `src/eslams/public_replay.py`:

- Keep local HTML replay renderer.
- Add renderer hint vocabulary and completeness classification.
- Add public replay exporter.
- Add public replay safety scanner.
- Add public reasoning binding.
- Do not generate MP4.

### Publication

Add `src/eslams/publication/*`:

- Official publication bundle exporter.
- Battlefield sample publication envelope.
- Uploaded replay projection bundle.
- Full-proof object manifest and checkpoint manifest.
- Deterministic bundle validation.
- No D1/R2 execution code.

## Minimum viable release order

### Release 1 - Contract and artifact sanity

Ship:

- Contract module and schema export.
- Artifact validation profiles.
- `eslams.artifact.validation.v1` output.
- Public manifest sidecar.
- Archive-aware summary and usage extraction.
- Signed/unsigned official fixtures.

This immediately reduces Platform glue around upload, signing, validation, and scoring eligibility.

### Release 2 - Replay correctness and safety

Ship:

- Public replay manifest/event v1.
- Actor metadata.
- Timeline completeness fields.
- Participant metadata.
- Public reasoning references.
- Public replay safety scanner.
- Minimal uploaded replay fixture.
- No MP4 generation, metadata only.

This fixes replay pages, uploaded artifacts, Battlefield samples, and public detail pages.

### Release 3 - Provider runtime and model eligibility

Ship:

- Provider runtime config.
- Provider preflight.
- Normalized provider receipt v1.
- Usage/cost aggregation.
- Failed-attempt receipts.
- Official/Battlefield/Arena eligibility split.
- Generic gateway base URL support, no Cloudflare dependency.

This reduces failed paid runs and makes costs auditable.

### Release 4 - Eval planning and publication bundles

Ship:

- Official/Battlefield/public-match plan envelopes.
- Shards, resume, progress JSONL.
- Official result merge.
- Publication bundle export and checkpoint manifest.
- Full-proof deterministic object/projection manifests, no direct D1/R2 writes.

This makes official evals and proof publication reproducible without Platform-side monkey patching.

### Release 5 - All-50 catalogue and Arena smoke

Ship:

- 50-game catalogue metadata.
- Render hint vocabulary.
- All-50 stateless Arena start/step/serialize smoke.
- All-50 replay renderability classification.
- Browser start/resume contract schema.

This protects all-game Arena rollout and runner/web catalogue consistency.

## Rejected recommendations, explicit notes

1. **Do not generate MP4 in Core.** Core should provide replay event streams, replay manifests, broadcast metadata, destination metadata fields, and renderability/completeness flags. Actual video rendering belongs to Platform or renderer workers.
2. **Do not make Cloudflare a Core dependency.** Core should support generic gateway/base-url provider routing and redacted gateway metadata. Platform owns Cloudflare AI Gateway, binding auth, Worker route health, R2, D1, and Durable Objects.
3. **Do not add direct R2/D1/Wrangler commands to Core.** Core should output deterministic publication bundles and checkpoint manifests. Platform owns execution.
4. **Do not make Platform database schema the canonical Core schema.** Core owns semantic contracts. Platform-specific D1 compact fields are projections.
5. **Do not use public proof rows as leaderboard predicates by default.** Mark proof rows with stable source and eligibility fields.
6. **Do not expose raw provider/action payloads in public exports.** Split private debug data from public replay/event data by construction.
7. **Do not solve Next.js build races, profile DB 404 behavior, or platform-specific public web copy in Core.** Keep Core-generated public strings clean, but leave web implementation to Platform.

## Definition of done

The change set is done when:

- `eslams run`, `eslams validate`, and `eslams replay` remain backward compatible.
- Existing `.eslams` artifacts still validate.
- New artifacts include no-secret public summaries and validation summaries.
- Provider receipts are normalized, redacted, and emitted for successes and failures.
- Public replay exports include actor metadata, participants, state-hash status, replay completeness, and safety validation.
- Public replay packages can be validated without full private runner bundles.
- Official result exports contain case counts, scoring eligibility, usage totals, cost provenance, proof counts, and signature status.
- Plan-only commands produce deterministic JSON and plan hashes.
- Sharded/resumable evals do not repeat completed cases when checkpoints match.
- All 50 arenas pass start/step/serialize smoke without provider calls.
- No Cloudflare, D1, R2, Wrangler, Stream, YouTube, Next.js, or MP4 generation dependency is introduced into Core.

## First pull request scope

The first PR should be small and foundational:

1. Add contracts package and schema version constants.
2. Add artifact validation summary contract.
3. Add validation profiles, including `public_replay_package`.
4. Add archive-aware extraction helpers.
5. Add public replay safety scanner skeleton.
6. Add signed and unsigned artifact fixtures.
7. Add tests proving current artifacts still validate.

Do not start with provider runtime, eval planning, or publication backfill. Those depend on the contract foundation.

## Second pull request scope

1. Add replay event actor fields and public replay manifest.
2. Add timeline completeness counters.
3. Add participant metadata.
4. Add public reasoning reference export.
5. Add `artifact public-export` and `replay validate-public` CLI commands.
6. Add minimal uploaded replay fixture.
7. Add safety scanner enforcement.

## Third pull request scope

1. Add provider runtime config.
2. Add provider preflight command.
3. Normalize provider receipts.
4. Emit failed-attempt receipts.
5. Add usage/cost aggregation and unavailable reasons.
6. Add generic gateway/base-url support, not Cloudflare-specific code.

## Fourth pull request scope

1. Add model capability split for `official_eval`, `battlefield`, and `arena`.
2. Add game and model catalogue exports.
3. Add plan-only commands.
4. Add sharding/resume/progress.
5. Add official result merge.

## Fifth pull request scope

1. Add publication bundle exports.
2. Add full-proof manifest/checkpoint exports.
3. Add all-50 Arena smoke.
4. Add runner job and stateless Arena transport contracts.
