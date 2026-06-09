# eSlams Artifacts

Every serious run produces a `.eslams` proof package. `.eslams` is the
portable zip-compatible archive. The expanded inspection directory uses the
`.eslams.d` suffix.

Required structure:

```text
run.eslams.d/
  manifest.json
  traces/public_trace.jsonl
  traces/agent_visible_trace.jsonl
  traces/private_judge_trace.jsonl
  traces/auditor_trace.jsonl
  replay/replay_events.jsonl
  replay/display_frames.jsonl
  replay/replay_manifest.json
  scores/score.json
  scores/metrics.json
  logs/runner.log
  logs/agent_io.jsonl
  logs/errors.jsonl
  receipts/provider_receipts.jsonl
  environment/lockfile.json
  environment/container_digest.txt
  environment/package_versions.json
  public/public_manifest.json
  public/public_result_summary.json
  public_reasoning/reasoning.jsonl
  validation/validation_summary.json
  scores/official_result.json
  broadcast/broadcast_manifest.json
  broadcast/vod_metadata.json
```

`manifest.json` contains file hashes and an artifact id derived from the
manifest file table. It also records the deterministic replay contract for new
Core artifacts and the scoring-validity posture:

```json
{
  "deterministic_replay": {
    "version": "eslams-deterministic-replay-v1",
    "status": "recorded",
    "source": "traces/auditor_trace.jsonl"
  },
  "match_valid_for_scoring": true,
  "invalid_reason": null,
  "agent_error_count_by_player": { "player_1": 0, "player_2": 0 },
  "illegal_action_count_by_player": { "player_1": 0, "player_2": 0 },
  "fallback_action_count_by_player": { "player_1": 0, "player_2": 0 },
  "per_case_run_valid": true,
  "per_case_scoring_eligible": true,
  "proof_row_publication_eligible": true,
  "aggregate_leaderboard_eligible": false,
  "aggregate_ineligibility_reason": "single_case_not_full_suite",
  "provider_status_by_player": { "player_1": "local_agent", "player_2": "local_agent" }
}
```

`runs/latest.eslams` points at the latest archive when a run produced one.
`runs/latest.eslams.d` points at the latest expanded copy.

Public artifacts never include hidden official eval seeds or private judge-only
data in public traces.

## Profiles and Public Exports

Core validates artifacts with explicit profiles:

- `runner-bundle`: the full local runner artifact.
- `official-bundle`: a runner bundle with official result and runner signature
  requirements.
- `battlefield-bundle`: a runner bundle with public match projection
  requirements.
- `public-replay-package`: a no-secret replay package containing only
  `manifest.json`, public replay files, display frames, replay manifest, and
  optional public reasoning.

Use `--summary-json` to produce the stable
`eslams.artifact.validation.v1` validation contract:

```bash
eslams validate runs/latest.eslams --profile runner-bundle --summary-json
```

Public replay packages can be exported and validated without private traces,
provider prompts, raw model responses, request headers, API keys, or debug
payloads:

```bash
eslams artifact public-export runs/latest.eslams --out public_replay_package
eslams replay validate-public public_replay_package
```

The public replay package manifest records optional files. In particular,
`public_reasoning/reasoning.jsonl` is listed as present or absent with SHA-256,
size, and absent reason fields. `replay/display_frames.jsonl` is a public-safe
projection of replay events for UI rendering; rows include renderer family,
visibility, actor, action label, display cells/summary, and source replay event
id only.

Broadcast video remains metadata-only in Core. `broadcast/vod_metadata.json`
can describe external media status, destination ids, hashes, and failure
reasons, but Core does not generate MP4 files or upload video.

## Deterministic Replay Audit

The auditor trace stores the full canonical arena state before and after each
action. `eslams validate` reconstructs those states, resolves the recorded JSON
action against the registered arena's legal actions, applies the action through
the arena, and verifies:

- the before/after state hash chain;
- the registered arena transition result;
- the public replay snapshot for each state.

This catches semantic tampering even when the manifest file table is refreshed
after editing trace or replay files. Older artifacts without state snapshots are
reported as `deterministic_replay.status = "not_recorded"` rather than being
mistaken for fully audited replay packages.

## Runner Signatures

When `RUNNER_SIGNING_KEY` is set, Core writes `signatures/runner_signature.json`.
The signature uses HMAC-SHA256 over a canonical JSON payload containing the
artifact id, artifact version, run id, and SHA-256 hash of `manifest.json`.

The signing key is never written to the artifact. `RUNNER_SIGNING_KEY_ID` may be
set to include a non-secret key identifier; otherwise Core records
`runner-env-key`.

`eslams validate` verifies the signature when `RUNNER_SIGNING_KEY` is available.
Without the key, validation still checks artifact hashes and reports the
signature as unverified. Unsigned local artifacts remain portable and report
`unsigned`.

## Publication Bundles

Publication bundles are deterministic storage/database inputs for Platform:

```bash
eslams publish export --kind uploaded-replay --artifact runs/latest.eslams --out bundle
eslams publish validate bundle --json
```

Bundles include public manifests, public replay files, proof index rows,
leaderboard rows, provider/model rows, aggregate usage, an object manifest,
checkpoint manifest, and signature/readback manifest. Core validates object
hashes, projection hashes, public replay packages, aggregate usage shape, and
proof-row policy without requiring secrets or storage credentials. Proof rows
are evidence-only by default and do not imply aggregate leaderboard eligibility.
