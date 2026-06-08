# Changelog

## Unreleased

### Added

- Added a versioned `eslams.contracts` package with deterministic schema export
  for artifact manifests, validation summaries, replay events/manifests,
  provider receipts, eval plans, progress events, resume checkpoints, official
  results, publication bundles, runner jobs, and catalogue rows.
- Added artifact validation profiles for runner bundles, official bundles,
  Battlefield bundles, and public replay packages, with no-secret JSON summaries.
- Added public replay exports with actor metadata, participant metadata, state
  hash status, replay completeness counters, public reasoning rows, and recursive
  public-output safety scanning.
- Added provider runtime controls for timeout, connect/read timeout, retries,
  retry backoff, synchronous concurrency limits, rate limits, generic gateway
  base URLs, and normalized redacted provider receipts for success and failure.
- Added model and game catalogue exports with official eval, Battlefield, and
  Arena eligibility, explicit absence reasons, and all-50 renderer vocabulary
  metadata.
- Added deterministic official, Battlefield, and public-match planning helpers
  with shard partitioning, resume checkpoint checks, and JSONL progress events.
- Added runner/container contracts, runner health output, and stateless Arena
  transport helpers for all registered games.
- Added publication bundle export and validation for uploaded replay,
  Battlefield sample, and official proof workflows without storage/database
  dependencies.
- Added deterministic fixtures for artifacts, provider receipt scenarios, public
  replay JSONL, official plans, and a Battlefield sample publication bundle.

### Changed

- Extended runner artifacts additively with public sidecars, validation summaries,
  official result sidecars, metadata-only broadcast manifests, provider usage
  aggregation, and scoring safety fields.
- Kept `.eslams` artifacts zip-compatible and backward-compatible while adding
  Platform-facing public contracts.
- Updated docs for Platform contracts, artifact profiles, public replay packages,
  provider runtime behavior, catalogue commands, and publication bundles.

### Validation

- `python3 -m pytest -q`
- `python3 -m ruff check .`
- `python3 -m mypy src`
- Deterministic schema export comparison
- Publication bundle validation
- Legacy `run` -> `validate` -> `replay` CLI smoke
