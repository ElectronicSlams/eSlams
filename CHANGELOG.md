# Changelog

## v0.6.1 - 2026-07-31

### Fixed

- Embedded the immutable release source commit into wheel and source
  distributions so deterministic schema exports no longer depend on a runtime
  Git checkout.
- Unified schema-manifest and runner-health provenance behind one fail-closed
  source, including linked worktrees and clean installed environments.

### Validation

- Added a package portability regression that builds a wheel through the source
  distribution, installs it outside a Git checkout, exports schemas twice, and
  requires byte equality with the source-checkout export.

## v0.6.0 - 2026-07-31

### Breaking changes

- Changed the default agent-error and illegal-action policies from fallback to
  `invalid-match`. Any fallback action now permanently makes a run unscoreable,
  including signed artifacts.
- Added `interactive`, `smoke`, and `official_eval` execution profiles.
  `official_eval` rejects fallback policies and provider-local retries because
  the official orchestrator owns whole-case retry policy.
- Replaced deterministic execution IDs with unique
  `run_<arena>_<utc-timestamp>_<short-uuid>` IDs. The deterministic
  configuration identity is now stored separately as `match_fingerprint`.
- Refused existing artifact output paths unless `--overwrite` is explicit.
- Advanced provider receipt writers to `eslams.provider.receipt.v2`, provider
  attempts to `eslams.provider-attempt.v2`, run integrity to
  `eslams.run-integrity.v2`, usage summaries to `eslams.usage-summary.v2`, and
  schema bundle metadata to `eslams-schema-bundle-v4`. Core retains tested read
  compatibility for historical 0.5/v1 receipts.

### Added

- Added stable failure classes, action provenance, logical-action IDs,
  deterministic physical-attempt IDs, positive case-attempt indexes, explicit
  attempt kinds, parent attempt linkage, and gap-free attempt-ledger checks.
- Added the fail-closed `official-case` artifact profile. It checks signatures,
  Core scoring validity, fallback/agent-error counts, evaluated-seat provider
  status, model identity, usage/cost completeness, and exact trace/replay/
  receipt reconciliation with no orphan applied attempts.
- Added native OpenRouter Chat Completions support with provider pinning,
  fallback disabled, raw-wire parsing, request identity, normalized usage, and
  native `usage.cost` capture.
- Added native Amazon Bedrock Converse support with configurable region,
  bearer-token auth, literal model version separators, raw-wire parsing, and
  endpoint-pinned model identity.
- Added documented raw REST fixtures and fault matrices for OpenAI Responses,
  Anthropic Messages, Gemini `generateContent`, OpenRouter Chat Completions,
  and Bedrock Converse.
- Added registry-only and account-aware live provider preflight modes, live
  model listing, minimal inference/action parsing/usage checks, first-class
  OpenRouter/Bedrock registry identities, and lifecycle metadata.
- Added canonical reasoning-inclusion, cached-token, provider-total, usage
  source, and cost source semantics. Non-finite, negative, missing, or
  incoherent accounting fails closed.
- Added immutable `eslams.price-card-reference.v1` contracts. Bare rate-card
  strings no longer make cost complete.
- Added redacted CLI provider failure summaries with the exact artifact
  diagnostics path, `--reasoning`, OpenRouter/Bedrock controls,
  `--case-attempt-index`, `--rate-card-reference`, and `--overwrite`.
- Added JSON Schemas and generated TypeScript contracts for run integrity,
  action provenance, physical provider attempts, usage summaries, and price-card
  references.
- Added separate gameplay-valid and proof/publication-eligible claims. Missing
  usage, cost, attempt-ledger, or model-identity evidence now fails publication
  eligibility closed without rewriting a clean gameplay verdict.

### Fixed

- Stopped synthesizing resolved model identity from the requested model;
  unknown identity remains null unless attested by a provider response or a
  deliberately pinned endpoint.
- Preserved sanitized request ID, status, usage, and cost evidence when an HTTP
  200 response fails wire-schema parsing.
- Classified action-repair failures as `action_repair` physical attempts rather
  than primary calls.
- Classified the first provider attempt of a whole-case retry as `case_retry`
  and preserved the distinct `action_repair` lineage.
- Corrected Anthropic manual/adaptive thinking payloads and token-budget rules,
  and removed incompatible temperature/manual fields for adaptive models.
- Prevented reasoning-token double counting and double billing while retaining
  provider-reported totals and documented cross-provider derivations.
- Recursively removed credential-bearing keys and redacted bearer/query-secret
  values from caller-supplied HTTP agent endpoint metadata before persistence.
- Rejected credential-bearing provider endpoint URLs and recursively rejected
  sensitive fields or unredacted secret values in externally supplied receipts.
- Constrained explicit run IDs to portable path-safe identifiers, refused
  artifact symlink escapes, and limited `latest.eslams*` replacement to symlinks
  so real files and directories are never removed during publication.
- Made the public TypeScript contract barrel resolvable by NodeNext ESM
  consumers and added a package self-reference compile regression.

### Validation

- Added fail-closed mutation coverage across all 50 arenas, a 20-turn
  all-failure regression, signed-fallback rejection, attempt-join tamper tests,
  all-provider fault injection, accounting coherence tests, schema lifecycle
  tests, and deterministic event-ID tests.
- Release gates cover Python 3.9–3.12, pytest, Ruff, mypy, TypeScript contract
  typecheck, wheel/sdist build, `twine check`, and deterministic schema export.

## v0.5.1 - 2026-07-05

### Fixed

- Fixed result-corrupting arena bugs in card rank ordering, Backgammon bear-off
  die consumption, Chess repetition handling, forfeit terminal replay events,
  and strict model action parsing.
- Made artifact IDs reproducible for identical seeded runs by moving volatile
  timing data to an unhashed sidecar and tightening validator checks for
  terminal score/replay consistency, unlisted files, and unverified signatures.
- Hardened live Arena session transport with signed opaque session envelopes
  and env-gated debug observations.
- Corrected compact arena semantics for Blackjack, Bargaining, Prisoner's
  Dilemma, and Crazy Eights.
- Improved provider receipts, retry behavior, reasoning controls, Google/Gemini
  identity handling, usage extraction, and pricing metadata.

## v0.5.0 - 2026-06-24

### Added

- Added explicit Core 0.5 game topology, surface, result, help, render,
  animation, and usage contracts.
- Classified the 50-game catalogue into 12 solo-score benchmarks, 29
  head-to-head Arena/Battlefield games, and 9 multi-seat table games.
- Exported Core 0.5 schemas and enriched game catalogue rows with machine
  readable playability, seat, result, renderer, and help metadata.

### Changed

- Bumped Core package/version metadata to `0.5.0`, runner defaults to
  `eslams-runner:0.5.0`, and schema bundle metadata to
  `eslams-schema-bundle-v3`.

### Validation

- Added Core/Platform catalogue alignment coverage for topology, surfaces,
  and browser play availability.

## v0.4.0 - 2026-06-11

### Added

- Added Core step contract v2 with deterministic `coreStep` request/response
  semantics, canonical state/action/legal-action/observation hashes, compact
  legal-action views, replay events, terminal summaries, and per-stage timings.
- Added compact observation and prompt package generation with stable prefix
  blocks, per-turn dynamic blocks, action output JSON schemas, prompt hashes,
  and approximate token estimates.
- Added shared model-action parsing with invalid-action taxonomy, corrective
  retry prompts, `action_id` support, and streaming `action_ready` detection.
- Added persistent runner-session support with hot in-memory state,
  create/step/snapshot/ping/close APIs, and FastAPI route wiring for runner
  containers.
- Added `python -m eslams_core.bench arena-step ...` and `eslams bench
  arena-step` benchmark harnesses for Core step timings and payload sizes.
- Added observation budget reports, golden Core fixture generation, engine
  capability metadata, and speculative-precompute eligibility metadata.
- Added production-fail-closed seed derivation and runner request signing
  helpers.
- Added Platform TypeScript contract artifacts under `packages/core-contracts`
  and a gated `@eslams/core-lite` TypeScript package for tic-tac-toe and
  connect-four parity work.

### Changed

- Bumped Core package/version metadata to `0.4.0`, runner defaults to
  `eslams-runner:0.4.0`, and schema bundle metadata to
  `eslams-schema-bundle-v2`.
- Extended schema export with Core step request/response, prompt package,
  replay event, runner-session, and observability schemas.
- Enriched runner health output with warm status, loaded game count, and
  uptime while preserving existing hash fields.

### Validation

- Added v0.4.0 tests for Core step v2, prompt packages, shared model-action
  parsing, runner sessions, seed/signing security, budgets, golden fixtures,
  schema export, generated contract artifacts, and engine capability gates.

## v0.3.2 - 2026-06-10

### Security

- Replaced runner artifact HMAC signatures with Ed25519 signature v2 for
  official-publication trust. Legacy HMAC signatures remain readable as
  `legacy_hmac` history, but they no longer satisfy official bundle validation.
- Added in-process agent timeout enforcement so local agents cannot exceed
  `time_budget_ms` without a timeout marker.

### Fixed

- Preserved `max_turns=0` as an explicit zero-turn run instead of falling back
  to arena defaults.
- Fixed primary scores to track the evaluated player (`player_1`) rather than
  the highest seat score.
- Fixed multi-player forfeit scoring so remaining seats keep their scores and
  the forfeiting seat is isolated.

### Changed

- Bumped Core package/version metadata to `0.3.2` and runner defaults to
  `eslams-runner:0.3.2`.
- Added GitHub Actions CI for pytest, Ruff, and mypy.

## v0.3.1 - 2026-06-10

### Security

- Hardened `.eslams` archive validation against zip path traversal and
  concurrent validation races by validating every archive member before
  extracting into a unique temporary directory.

### Fixed

- Logged Arena transition exceptions while keeping public transport failures
  generic.
- Fixed Checkers multi-jump continuation, including forced-piece legal actions.
- Rejected missing explicit agents for arenas with more than two players.
- Preserved literal edge backticks when parsing fenced JSON model responses.
- Guarded malformed Backgammon move parsing and corrupt public replay JSONL rows.
- Made catalogue export skip and warn on missing metadata rows instead of
  crashing.
- Generated replay HTML player panels from replay data instead of hardcoding two
  player IDs.

### Changed

- Bumped Core package/version metadata to `0.3.1` and runner defaults to
  `eslams-runner:0.3.1`.

## v0.3.0 - 2026-06-09

### Added

- Added lightweight live Arena session APIs:
  `start_session`, `step_session`, and `legal_actions_page`.
- Added public JSON schemas for Arena start results, step results, legal-action
  pages, action descriptors, and live Arena events.
- Added CLI commands for live Arena transport:
  `eslams arena start`, `eslams arena step`, and
  `eslams arena legal-actions-page`.
- Added public-safe legal action descriptors for all 50 registered games,
  including stable action tokens, labels, groups, categories, prompt labels,
  and deterministic sort keys.
- Added canonical live `display_frame` projection using the same display-frame
  shape as public replay packages.
- Added public-safe live Arena events for session start, action acceptance,
  state application, model-turn requests, human-turn readiness, completion, and
  failure cases.
- Added paged/searchable legal-action descriptor output for large action sets.
- Added all-50 Arena start/step contract tests, public-safety checks, paging
  tests, failure tests, CLI tests, timing assertions, and representative golden
  fixtures.

### Changed

- Bumped Core package/version metadata to `0.3.0` and runner defaults to
  `eslams-runner:0.3.0`.
- Documented the v0.3.0 Arena transport contract, server-owned
  `session_state` boundary, browser-safe fields, and release/tag instructions.
- Narrowed public safety scanning so action descriptor `token` and
  `prompt_label` are allowed only inside action descriptor rows.

### Validation

- `python3 -m pytest -q`
- `python3 -m ruff check .`
- `python3 -m mypy src`

## v0.2.0 - 2026-06-09

### Added

- Added a versioned `eslams.contracts` package with deterministic schema export
  for artifact manifests, validation summaries, replay events/manifests,
  provider receipts, eval plans, progress events, resume checkpoints, official
  results, publication bundles, runner jobs, and catalogue rows.
- Added deterministic `schema_bundle_manifest.json` output for
  `eslams schemas export`, including Core package version, git commit when
  available, schema bundle version, schema hashes, and deterministic build id.
- Added schema coverage for catalogue renderer rows, catalogue availability
  rows, schema bundle manifests, and public display-frame rows.
- Added artifact validation profiles for runner bundles, official bundles,
  Battlefield bundles, and public replay packages, with no-secret JSON summaries.
- Added public replay exports with actor metadata, participant metadata, state
  hash status, replay completeness counters, public reasoning rows, and recursive
  public-output safety scanning.
- Added `replay/display_frames.jsonl` public-safe projections and optional-file
  manifest rows for public replay packages.
- Added `eslams runner result --artifact --artifact-uri --job-id` and
  `eslams run --runner-result-json --artifact-uri` for canonical
  `RunnerJobResult` emission.
- Added provider runtime controls for timeout, connect/read timeout, retries,
  retry backoff, synchronous concurrency limits, rate limits, generic gateway
  base URLs, and normalized redacted provider receipts for success and failure.
- Added provider-backed HTTP-agent status semantics:
  `provider_ok`, `provider_receipt_missing`, `provider_usage_unavailable`,
  `local_agent`, and `agent_error`.
- Added model and game catalogue exports with official eval, Battlefield, and
  Arena eligibility, explicit absence reasons, and all-50 renderer vocabulary
  metadata.
- Added Platform-aligned public game identity fields, category labels, variants,
  difficulty, maturity, player counts, and model provider-control capability
  metadata.
- Added deterministic official, Battlefield, and public-match planning helpers
  with shard partitioning, resume checkpoint checks, and JSONL progress events.
- Added runner/container contracts, runner health output, and stateless Arena
  transport helpers for all registered games.
- Added trusted interactive state rehydration with strict hash validation by
  default and non-strict repair diagnostics for server-owned interactive state.
- Added publication bundle export and validation for uploaded replay,
  Battlefield sample, and official proof workflows without storage/database
  dependencies.
- Added deterministic fixtures for artifacts, provider receipt scenarios, public
  replay JSONL, official plans, and a Battlefield sample publication bundle.

### Changed

- Extended runner artifacts additively with public sidecars, validation summaries,
  official result sidecars, metadata-only broadcast manifests, provider usage
  aggregation, and scoring safety fields.
- Split validity and eligibility fields across artifacts, public summaries,
  official result merges, and publication bundles so evidence rows do not imply
  ranked leaderboard eligibility.
- Kept `.eslams` artifacts zip-compatible and backward-compatible while adding
  Platform-facing public contracts.
- Updated docs for Platform contracts, artifact profiles, public replay packages,
  provider runtime behavior, catalogue commands, publication bundles, and
  release/tag instructions for `v0.2.0`.

### Validation

- `python3 -m pytest -q`
- `python3 -m ruff check .`
- `python3 -m mypy src`
- Deterministic schema export comparison
- Publication bundle validation
- Legacy `run` -> `validate` -> `replay` CLI smoke
