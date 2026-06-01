# eSlams Artifacts

Every serious run produces a `.eslams` proof package. During local development it is a directory; for transport it can be zipped with the `.eslams` extension.

Required structure:

```text
run.eslams/
  manifest.json
  signatures/runner.sig
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

`manifest.json` contains file hashes and an artifact id derived from the manifest file table. Public artifacts never include hidden official eval seeds or private judge-only data in public traces.
