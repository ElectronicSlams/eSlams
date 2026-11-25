# Chess continuation

Continuation is a new, explicitly linked execution, not a repair of the source
run and not a claim that the game ran uninterrupted. The first supported arena
is standard chess. No arbitrary FEN, caller-supplied checkpoint, replacement
move, or prefix agent is accepted. Official evaluation rejects continuation.

## Python integration

The integration surface in `eslams.continuation` is:

```python
from eslams.continuation import (
    ChessContinuation,
    chess_continuation_child_execution,
    local_chess_continuation_engine_identity,
    prepare_chess_continuation,
)
from eslams.runner import RunConfig, Runner

descriptor = prepare_chess_continuation(
    source_archive, source_identity, execution_spec
)
target_engine_identity = local_chess_continuation_engine_identity(
    wrapper_version=execution_spec["wrapperVersion"],
)
child_execution = chess_continuation_child_execution(
    descriptor, turn_limit_policy="native-arena-horizon",
)
child_platform_run_id = "platform_child_run"
child_platform_match_id = "platform_child_match"
continuation = ChessContinuation(
    source_archive=source_archive,
    descriptor=descriptor,
    target_engine_identity=target_engine_identity,
    child_platform_run_id=child_platform_run_id,
    match_id=child_platform_match_id,
    child_execution=child_execution,
)
# Supply new agents configured from trusted model/route pins, and the same
# arena, seed and model parameters as the source descriptor. The separately
# approved child policy resolves the execution cutoff; source pins stay frozen.
result = Runner().run(RunConfig(
    arena_id="chess",
    agents=agents,
    seed=execution_spec["seed"],
    max_turns=child_execution["maxTurns"],
    wrapper_version=execution_spec["wrapperVersion"],
    scoring_policy_version=execution_spec["scoringPolicyVersion"],
    time_budget_ms=source_requested_time_budget_ms,
    run_id="continued_example",
    case_id=child_platform_run_id,
    run_job_id=child_platform_run_id,
    output_dir=output_dir,
    continuation=continuation,
))
```

`source_archive` is a local complete archive stored as a regular, non-symlink
file. Preparation and execution validate
that archive before calling agents. The source is read-only. Preparation derives
`coreRunId`, accepted ply count, prefix digest and checkpoint digest from verified
archive contents; callers cannot choose a shorter prefix. The child replays every
accepted move from the initial state, preserving chess repetition and full model
history, including `reveal_turn` semantics, and starts inference at the first
unexecuted ply. A source with 88 accepted actions starts new calls at turn 88.

The caller obtains source identity and execution pins from trusted Platform
records, not by trusting arbitrary archive metadata. The required
`source_identity` fields are `matchId`, `runId`, `artifactId`, `artifactKey`, and
`artifactSha256`. The builder checks the internal artifact identity and derives
`coreRunId` independently. The source archive's `run_metadata.case_id` must
equal `descriptor.source.runId`. Match/run/archive identities must not be confused.

`ChessContinuation` requires the new `child_platform_run_id` and `match_id`.
The child Platform run ID must differ from the source Platform run ID, and the
child Platform match ID must differ from the source Platform match ID. Both
identities refer to a new, explicitly linked execution. The wrapper sets both `RunConfig.case_id` and
`RunConfig.run_job_id` to `child_platform_run_id`. The child Core run ID
(`RunConfig.run_id`) must also differ from source identities. Child identities
must not reuse ancestor identities.

Set `time_budget_ms` to the verified source metadata's
`requested_time_budget_ms`; it must also equal the source's
`effective_time_budget_ms` (including `None`). A source with different requested
and effective budgets is not accepted. Continuation forbids `overwrite=True`
and requires a new output destination; it never replaces a source archive.

## Explicit child execution budget (Core 0.8.1)

The source descriptor is still `chess-continuation/v1`, including its actual
historical `execution.maxTurns`. It is never relabeled or changed to increase a
child's allowance. New executions use `chess-continuation-lineage/v2` and record
`childExecution` plus its canonical `childExecutionSha256` independently:

```json
{
  "schemaVersion": "chess-continuation-child-execution/v1",
  "turnLimitPolicy": "native-arena-horizon",
  "maxTurns": 240
}
```

The public `chess_continuation_child_execution` helper accepts only two policies:

- `preserve-source` (default): retain the source execution cutoff exactly.
- `native-arena-horizon`: derive the existing standard chess arena's horizon,
  currently 240 plies. The source arena version and public rules digest must
  match the runtime and the source cutoff must not exceed that horizon. No
  caller-selected turn count, new game rule, output cap or time budget is accepted.

The object has exactly these three fields. `ChessContinuation.child_execution`
accepts the resolved object, defensively validates/copies it and defaults to an
explicit `preserve-source` object when omitted. The runner requires
`RunConfig.max_turns` to match the resolved child budget. Artifact validation
binds the same budget to manifest `run_metadata.max_turns`, the lineage digest
and the executed trace length. Platform must separately include the object and
digest in the reviewed, admitted and published child claim. A digest binds the
chosen policy but is not authorization by itself.

For example, an 88-ply source with a 160-ply caller cutoff can explicitly resume
with 240 while retaining 160 in its immutable source descriptor. Chess already
terminates at its own 240-ply draw horizon, so this removes an execution cutoff,
not a chess rule. A child without the new policy still truncates at 160 if the
board is nonterminal, remains invalid and cannot be treated as a completed game
or a newly supported continuation source.

Readers continue to validate historical v1 lineage using its source cutoff.
Only v2 targets can execute the new policy; v1 lineage cannot carry child budget
fields. Repeated continuation freezes the immediate source's actual child
budget, including 240, while the ancestor descriptor retains its original 160.

## Frozen descriptor

The descriptor has schema version `chess-continuation/v1`:

- `source`: `matchId`, `runId`, `artifactId`, `artifactKey`, `coreRunId`,
  `artifactSha256`.
- `execution`: `coreVersion`, `coreRef`, `coreSourceSha256`, `arenaSlug`,
  `arenaVersion`, `variantSlug`, `runnerVersion`, `wrapperVersion`,
  `scoringPolicyVersion`, `rulesSha256`, `seed`, `maxTurns`,
  `sourcePayloadSha256`, and `players`.
- Each player: `seat`, `modelId`, `modelVersionId`, `providerModelId`,
  `routeKey`, and `routeSha256`. The seats are `player_1` and `player_2`.
- `executionSpecSha256`: digest of the frozen execution object.
- `prefix`: `acceptedPlyCount`, `prefixSha256`, `checkpointStateSha256`.

Continuation digests use lowercase hexadecimal SHA-256, without a `sha256:`
prefix. Canonical JSON recursively sorts object keys and uses compact UTF-8 JSON
with unescaped Unicode. These descriptor digests are distinct from existing Core
hash wire strings, which retain their existing `sha256:` convention.

The normalized prefix contains `turnId`, `player`, `action`, `stateHashBefore`,
`stateHashAfter`, `markers`, `actionProvenance`, `logicalActionId`, and
`sourceEventId`. The `stateHashBefore` and `stateHashAfter` values retain
Core's `sha256:` prefix; only the descriptor digest fields use raw hex.
Its provenance describes the source evidence, not an invented
provider attribution. Child trace/replay projections use new child IDs and
`reconstructed_action` provenance. They are deterministic reconstruction, not
new provider executions. Full source event IDs, logical IDs and original
provenance appear only in the auditor/private continuation evidence, not in
public trace projections.

`sourcePayloadSha256` hashes the exact persisted `runjobs.payloadjson` bytes.
`rulesSha256` hashes the canonical frozen Platform rules/version contract. These
pins come from trusted API custody; the Core archive alone cannot independently
reconstruct either value.

A descriptor freezes the immediate source execution, separately from the target
engine. For a repeated continuation, copy the immediate source lineage's
`targetEngine` fields into the new descriptor's `coreVersion`, `coreRef`,
`coreSourceSha256`, `runnerVersion`, and `wrapperVersion`. Do not retain the
original ancestor's engine pins for a child produced by a newer engine. Preserve
the game, rules, seed, scoring and player pins across the chain. The immediate
source `maxTurns` must equal its verified child execution budget (or the source
descriptor cutoff for historical v1 lineage), not an older ancestor's cutoff.
The new `sourcePayloadSha256` binds the immediate source job payload.

Source execution pins never become target-engine pins. The separate target
identity has schema version `chess-continuation-engine/v1`, with `coreVersion`,
`coreRef`, `coreSourceSha256`, `runnerVersion`, `wrapperVersion`,
`continuationContractVersion: "chess-continuation-lineage/v2"` for new execution.
Historical v1 identities remain readable only as historical artifact evidence.
Installed identities add build-evidence fields documented below; local identities
add `runnerImageDigest: "local-development"`.
`targetEngineSha256` binds that identity. For a local source checkout, obtain
the target identity using
`local_chess_continuation_engine_identity(wrapper_version=...)`. It hashes the
actual Python source bytes and deliberately sets `coreRef` and
`runnerImageDigest` to `local-development`. Verification checks that the supplied
identity matches the running local source. Recompute the identity after editing
code. A source release identity cannot describe uncommitted continuation code.

This local helper does not attest a production image or dependency environment.
The installed resolver below verifies build evidence, while image provisioning
and release custody remain Platform responsibilities. Local success is not a
production deployment claim.

For the reviewed legacy 0.7.0 source, `execution.coreSourceSha256` identifies
the immutable published source-distribution archive. In an installed target,
`targetEngine.coreSourceSha256` instead hashes the complete installed Python
file manifest. These digests have distinct meanings and must not be compared or
substituted. A repeated continuation inherits its immediate source's verified
target identity, including that runtime-manifest meaning. Platform must preserve
the provenance kind and independently bind package, runtime-build and image
identities in its release evidence.

## Ledger and lineage boundaries

The child artifact contains:

- `continuation/lineage.json`: frozen descriptor, source and child identities,
  explicit child execution policy and digest,
  verified prefix/checkpoint, historical ledger digest/count and explicit
  accounting scopes.
- `continuation/source_prefix.json`: normalized source prefix evidence, used to
  verify the descriptor digest and reconstruct its checkpoint.
- `continuation/source_provider_receipts.jsonl`: historical ledger bytes,
  preserved separately, including failed requests and unknown cost. The lineage
  records ordered per-source segments with source Core run/artifact IDs, byte
  counts, receipt counts and hashes. Each segment retains its exact source bytes.
- `receipts/provider_receipts.jsonl`: only calls made by this child execution.

A source receipt with `action_applied: false` remains false. Historical Platform
HTTP-agent receipts may have this flag even when a corresponding move exists;
reconstruction does not turn them into proof that the provider applied that
move. The Platform bridge uses `model` for `providerModelId` and
`locked_model_id` for the catalogue `modelVersionId`. If `requested_model` is
present, it must equal `providerModelId` too. These are distinct identity
namespaces: do not compare a catalogue version ID to a provider model ID or
reinterpret old stored receipts. Core `HttpAgent` retains a closed, sanitized optional allowlist of
`requested_model`, `model_version_id`, `route_key`, and `route_sha256`. When
present, these fields must agree with the trusted pins in both historical and
new receipts. Their absence in historical receipts is not filled in or inferred
as new evidence.
Successful source receipts require the pinned provider model and catalogue
version. Unknown model/catalogue identity is allowed only for failed, non-applied
interruption receipts at the source checkpoint, with no contradictory known
pins. A failed receipt with an unknown provider model may still retain a
non-null locked catalogue version when that version matches the trusted pin.
Preserve those receipts unchanged; unknown identity is never synthesized.
Configure new HTTP agents explicitly with their trusted provider/model pins
rather than detecting historical agents heuristically.

Applied incremental receipts and new actions must reconcile one-to-one. Orphan
applied receipts and receipts beyond the final turn/checkpoint are rejected.

Normal child usage/cost totals are incremental, not lifetime game totals. The
historical ledger is audit evidence and must not be charged a second time. A
repeat interruption produces another linked execution while retaining earlier
history; it must not erase failed attempts or unknown-cost evidence. Ancestor
segments are retained in order, then the immediate source's incremental ledger
is appended as its own byte-preserving segment. Nested parent lineage supports
internal consistency checks, not independent verification of ancestor archives.

The raw source archive SHA-256 is verified only when the complete source archive
is available. Child-artifact validation checks lineage, prefix and historical
ledger internal consistency. It does **not** independently verify the raw archive
hash from the included subset. Before publication, Platform must reopen the
authoritative source archive and compare it to the descriptor and lineage.
Private lineage and historical receipts are not automatically public exports.

## Eligibility and failure behavior

Preparation rejects wrong games/variants, terminal sources, invalid or fallback
prefixes, tampering, duplicate evidence and incompatible execution pins. A source
must represent a failed interruption, not an arbitrary saved position. All source
validation completes before new inference. Failure to verify is not a request to
restart from scratch or rerun already accepted moves.

A continued game obtains an outcome only through valid terminal chess actions.
New provider failures remain failures with their own receipts. Continuation does
not grant official-evaluation, benchmark, aggregate leaderboard or other
non-game eligibility. Consumers must show that the game was continued and retain
its source link; successful completion does not make the original failed source
successful or pristine.

## Provenance compatibility

`eslams.action-provenance.v1` adds the enum member `reconstructed_action` alongside
`provider_action`, `local_action` and `fallback_action`. Existing values remain
valid. Strict older readers must be upgraded before consuming continued runs.
The Python enum, exported JSON Schema and TypeScript union agree. For example,
this sanitized provenance record describes a reconstructed historical action:

```json
{
  "schemaVersion": "eslams.action-provenance.v1",
  "eventId": "continued_example:action:000000",
  "runId": "continued_example",
  "episodeId": "episode_001",
  "turnId": 0,
  "seatId": "player_1",
  "provenance": "reconstructed_action",
  "logicalActionId": "continued_example:episode_001:player_1:000000",
  "successfulAttemptEventId": null,
  "metadata": {}
}
```

This record does not assert that a new provider request occurred.

## Installed runner build identity

Released execution uses `installed_chess_continuation_engine_identity()` from
`eslams.continuation_build`. It accepts no caller path or environment override.
It reads `/opt/eslams-continuation/build.json`, verifies that evidence and every
ancestor are root-owned, regular (directories for ancestors), non-symlink and
not group/other writable, and rejects root execution. It checks every installed
Core Python source byte and every wrapper Python source byte under `/app/app`
against the complete manifests. Missing, additional or changed Python files fail
closed. All source tree entries and their ancestors must likewise be protected.
Core's packaged commit and Core/core-runner versions must match the evidence.
The separate `runnerVersion` is the trusted Platform wrapper runner identifier;
`wrapperVersion` is the Core action protocol version, not that runner identifier.

The build evidence schema is `eslams.chess-continuation-build/v1`, with exactly
`schemaVersion`, `coreVersion`, `coreRef`, `runnerVersion`, `wrapperVersion`,
`platformRef`, `coreRunnerVersion`, `coreFiles` and `wrapperFiles`. Both refs are full lowercase
40-character Git commits. Each file map uses normalized relative `.py` paths
and raw lowercase SHA-256 values. After verifying release inputs, image build
tooling calls `build_chess_continuation_evidence` with the imported Core package
root, wrapper source root and trusted release pins, writes canonical JSON to the
fixed evidence path as root, and runs the image as a non-root user.

An installed target identity uses `runnerBuildSha256` (canonical evidence hash),
`wrapperSourceSha256` (canonical wrapper file-map hash) and `platformRef` instead
of `runnerImageDigest`. The existing `coreSourceSha256` hashes the Core file map.
The final OCI image digest cannot be embedded inside the same image; Platform's
external deployment records must bind that image digest to this build identity.
Neither a caller-asserted image pin nor a mutable environment variable is trusted
as installed evidence. This attestation is an image-filesystem trust boundary,
not an independently signed external release attestation.

`chess_continuation_engine_identity(wrapper_version=...)` selects installed
evidence whenever present. A packaged installation without evidence fails
closed; only an unpackaged Git source checkout can use the separate local
identity. Verification resolves the actual runtime identity again and compares
the complete target identity before callbacks. Supplying a local target in an
installed runner cannot bypass installed verification.
