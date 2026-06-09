# Changelog

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
