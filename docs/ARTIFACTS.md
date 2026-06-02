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
  "provider_status_by_player": { "player_1": "not_provider", "player_2": "not_provider" }
}
```

`runs/latest.eslams` points at the latest archive when a run produced one.
`runs/latest.eslams.d` points at the latest expanded copy.

Public artifacts never include hidden official eval seeds or private judge-only
data in public traces.

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
