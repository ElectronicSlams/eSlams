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

Core 0.6 also records `integrity_status`, stable `invalid_reason_codes`,
provider/logical action counts, `usage_complete`, `cost_complete`,
`attempt_ledger_complete`, `model_identity_verified`, aggregate usage/cost, and
the deterministic `match_fingerprint`. The execution `run_id` is unique; it is
not the configuration fingerprint. Existing artifact paths are refused unless
overwrite is explicit.

`runs/latest.eslams` points at the latest archive when a run produced one.
`runs/latest.eslams.d` points at the latest expanded copy.

Public artifacts never include hidden official eval seeds or private judge-only
data in public traces.

## Profiles and Public Exports

Core validates artifacts with explicit profiles:

- `runner-bundle`: the full local runner artifact.
- `official-bundle`: a runner bundle with official result and runner signature
  requirements.
- `official-case`: a signed official bundle plus fail-closed per-case execution
  integrity checks.
- `battlefield-bundle`: a runner bundle with public match projection
  requirements.
- `public-replay-package`: a no-secret replay package containing only
  `manifest.json`, public replay files, display frames, replay manifest, and
  optional public reasoning.

Use `--summary-json` to produce the stable
`eslams.artifact.validation.v1` validation contract:

```bash
eslams validate runs/latest.eslams --profile runner-bundle --summary-json
eslams validate runs/latest.eslams --profile official-case --summary-json
```

`official-case` rejects fallback or agent-error counts, non-`provider_ok`
status for the evaluated seat, mismatched provider/logical action counts,
missing or duplicate physical attempts, incomplete usage or cost, unverified
model identity, and any non-valid Core integrity state. It reconciles every
provider action across public trace, replay, and receipt rows. A successful
provider action must reference exactly one completed, applied, scoring-valid
receipt with the same logical action ID and seat, and no applied-success receipt
may be orphaned.

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

## Provider Receipts and Action Provenance

Core 0.6 writes `eslams.provider.receipt.v2` rows. A runner-enriched row has a
deterministic `event_id`, unique run/case/logical-action identity,
`case_attempt_index`, positive gap-free `attempt_index`, `attempt_kind`, seat,
terminal status, provider/model identity source, endpoint/parser versions,
request IDs, normalized usage/cost, and `action_applied` /
`case_valid_for_scoring` flags.

`case_valid_for_scoring` is the gameplay verdict for that action and does not
claim complete billing evidence. The manifest, validation summary, public
result, and official result set `per_case_scoring_eligible` and
`proof_row_publication_eligible` only when gameplay, usage, cost, attempt-ledger,
and model-identity integrity are all complete. Thus a clean action with missing
cost can remain game-score-valid while every publication claim stays false.

Action repair is a separate physical attempt (`action_repair`), not a rewrite
of the primary receipt. Whole-case retries use `case_retry` in orchestration and
a new positive `case_attempt_index`. Official execution prohibits hidden
adapter retries so the attempt ledger is complete.

Each applied trace/replay action records one provenance value:
`provider_action`, `local_action`, or `fallback_action`. Provider actions carry
the successful attempt event ID. Fallback actions are permanently unscoreable,
including when the artifact has a valid signature.

Provider raw request/response bodies and credentials are not public receipt
fields. Failed HTTP 200 wire parsing preserves sanitized request ID, status,
usage, and cost evidence when those fields were safely available.

## Usage and Cost Completeness

Canonical totals remain `null` unless every physical attempt has coherent,
non-negative provider usage. Reasoning inclusion is explicit so reasoning is
never double-counted: inclusive reasoning is already inside output tokens;
separate reasoning is added to the canonical total and priced once. Provider
totals are preserved and checked against the canonical derivation.

Cost is complete only when every attempt has a finite non-negative cost and a
complete, provider/model-matching `eslams.price-card-reference.v1`. Missing or
malformed data remains unavailable; Core never converts unknown cost to zero.

## Runner Signatures

When `RUNNER_ARTIFACT_SIGNING_PRIVATE_KEY` is set, Core writes
`signatures/runner_signature.json`. The v2 signature uses Ed25519 over a
canonical JSON payload containing the artifact id, artifact version, run id, and
SHA-256 hash of `manifest.json`.

The private key is never written to the artifact. Set
`RUNNER_ARTIFACT_SIGNING_KEY_ID` to include a non-secret key identifier;
otherwise Core records `runner-artifact-env-key`.

`eslams validate` verifies the signature when
`RUNNER_ARTIFACT_VERIFY_PUBLIC_KEY` is available. If only the private signing
key is available locally, validation derives the public key for developer
convenience. Unsigned local artifacts remain portable and report `unsigned`.
Legacy v1 HMAC artifacts are still readable as `legacy_hmac`, but official
bundle validation rejects them as untrusted.

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
