# Public-board continuation (source-checkout preview)

Core can reconstruct and continue a verified interrupted public `tic-tac-toe`,
`connect-four`, or `othello` game. Only the `standard` variant and the current
exact arena versions are accepted. This is a separate contract family from
[chess continuation](CHESS_CONTINUATION.md), whose public APIs and wire versions
are unchanged. There is no generic arena allowlist switch and no state import.

**This feature is source-checkout-only. It is not a production runner release,
legacy archive migration, or evidence that an old match is admissible.** The
installed/packaged runtime refuses board continuation, including when chess
build evidence is present. A local identity cannot substitute for an immutable
production build attestation. No package, runner or arena version is bumped by
this preview; release/version decisions and Platform integration are separate.

## API

```python
from eslams.continuation import (
    BoardContinuation,
    board_continuation_child_execution,
    board_continuation_engine_identity,
    prepare_board_continuation,
)
from eslams.runner import RunConfig, Runner

descriptor = prepare_board_continuation(
    source_archive, authoritative_source_identity, authoritative_execution_spec
)
child_execution = board_continuation_child_execution(
    descriptor, turn_limit_policy="native-arena-horizon"
)
continuation = BoardContinuation(
    source_archive=source_archive,
    descriptor=descriptor,
    target_engine_identity=board_continuation_engine_identity(
        wrapper_version=authoritative_execution_spec["wrapperVersion"]
    ),
    child_platform_run_id=child_platform_run_id,
    match_id=child_platform_match_id,
    child_execution=child_execution,
)
result = Runner().run(RunConfig(
    arena_id=authoritative_execution_spec["arenaSlug"],
    agents=pinned_provider_agents,
    seed=authoritative_execution_spec["seed"],
    max_turns=child_execution["maxTurns"],
    time_budget_ms=source_time_budget_ms,
    wrapper_version=authoritative_execution_spec["wrapperVersion"],
    scoring_policy_version=authoritative_execution_spec["scoringPolicyVersion"],
    run_id=new_core_run_id,
    case_id=child_platform_run_id,
    run_job_id=child_platform_run_id,
    output_dir=new_output_directory,
    archive=True,
    continuation=continuation,
))
```

The caller must supply trusted custody, exact provider routes/catalogue versions,
matching source time budget, and fresh child identities. The snippet's variables
are inputs, not generated placeholders that can be used to replace missing
source evidence. The verifier snapshots and validates the exact archive again
before any new provider request. Runner configuration must match the descriptor's
arena as well as seed, policies, models and budget.

`prepare_board_continuation` derives the descriptor. `verify_board_continuation`
rechecks source and actual local runtime bytes. `board_continuation_engine_identity`
rejects installed runtime execution; `local_board_continuation_engine_identity`
only describes local source bytes and never authorizes execution by itself.
`board_continuation_child_execution` accepts `preserve-source` (default) or
`native-arena-horizon`. The latter verifies current arena version and public-rules
digest and uses only the arena-owned maximum (9, 42, or 120). It cannot change
historical `maxTurns`, request a custom limit, reduce the source budget, or alter
model output/time policies. A source budget above the native maximum (for
example Othello `maxTurns: 128` versus native 120) must use `preserve-source`;
it can still stop naturally at the arena terminal state. Platform must not
always request native extension or silently rewrite those source pins. Othello
passes remain actual legal actions.

## Versioned contracts

The Python serializers, exported JSON Schemas, no-secret examples, and generated
TypeScript interfaces agree on these new versions:

- Descriptor: `eslams.board.continuation.v1`
- Child execution: `eslams.board.continuation.child_execution.v1`
- Lineage: `eslams.board.continuation.lineage.v1`
- Source-checkout engine: `eslams.board.continuation.engine.v1`

Field shapes and semantic checks follow the chess contracts, but a board
namespace cannot be substituted for a chess namespace or vice versa. The legacy
field `acceptedPlyCount` means accepted actions, including an Othello pass.
Regenerate only these TypeScript types and compile fixtures with
`python scripts/generate_board_continuation_types.py --write`; `--check` verifies
byte-for-byte drift from the Python schema definitions. The pytest suite checks
drift, and the standard core-contracts TypeScript check compiles positive
no-secret examples plus negative namespace/seat/engine fixtures.

Schemas check shape only. Passing a schema does not verify archive custody,
legality, execution pins, receipt identity or publication authority.

The private files retain `continuation/lineage.json`,
`continuation/source_prefix.json`, and
`continuation/source_provider_receipts.jsonl`. Historical receipt bytes are
preserved in exact, hashed segments and excluded from incremental spending and
usage totals. Public replay labels reconstructed actions and continued results;
private custody paths, source event identities and route pins are not exported
or inserted into model requests. Continued matches remain ineligible for
official evaluation, proof rows and aggregate leaderboards.

## Admission and legacy limitations

Every prefix is replayed from the exact seeded initial state through the pinned
arena implementation. Every ancestor's descriptor/engine/parent digest, namespace, unchanged execution
pins, checkpoint and receipt-ledger prefix are rechecked. The child initial
replay state is bound even when the prefix is empty. Model-visible historical
actions use fresh child logical IDs and reconstructed provenance, including for
the shared chess path; original source IDs remain in private/auditor evidence.

Each accepted action must be legal for the active player,
with matching before/after state hashes and no failure/fallback markers. Terminal
or exhausted sources, unsupported interruption reasons, missing successful
request receipts, conflicting model/route/catalogue pins and invalid archives
are rejected. New actions require attested exact provider/model pins. Failed
requests are preserved and never promoted to scoring-valid actions.

Historical replay reconstruction alone does **not** prove that a historical run
can be admitted. In particular, this preview does not reinterpret `agent_crash`
as an approved provider interruption, infer a historical Core release from an
arena version, recover absent external route custody, or rewrite old receipt
flags/model aliases. A legacy importer would need separately reviewed evidence,
explicit historical compatibility tests and unchanged publication safeguards.

## Platform prerequisites

Production integration requires all of the following, not merely an allowlist:

1. Board-specific source admission and durable custody of the original archive,
   source payload, source build/rules pins and exact model/version/route pins.
2. Explicit receipt compatibility and interruption taxonomy for any legacy
   source, with no guessed identities and no changes to original evidence.
3. Reviewed board build/engine attestation and signed target registration,
   replacing this preview's explicit installed-runtime refusal through a new
   reviewed contract. Existing chess build evidence is insufficient.
4. Board-aware dispatch/prepare requests, persisted descriptor and child budget,
   request/output/time-budget binding and exclusive continuation fencing.
5. Independent parent/source rereads at publication, child lineage validation,
   and arena/seed/version/budget checks across every continuation generation.
6. UI and result labels that distinguish continued execution, incremental costs,
   and local preview from production/official results.

No CLI auto-recovery, production enablement, deployment, paid provider request,
publication, or historical-source conversion is performed by this feature.
