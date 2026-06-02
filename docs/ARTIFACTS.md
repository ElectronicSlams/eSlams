# eSlams Artifacts

Every serious run produces a `.eslams` proof package. During local development it is a directory; for transport it can be zipped with the `.eslams` extension.

Required structure:

```text
run.eslams/
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
Core artifacts:

```json
{
  "deterministic_replay": {
    "version": "eslams-deterministic-replay-v1",
    "status": "recorded",
    "source": "traces/auditor_trace.jsonl"
  }
}
```

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
