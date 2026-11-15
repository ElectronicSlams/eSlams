# Unscored recovered board positions

This opt-in mode recovers an archive-internal legal board prefix from a narrowly
supported interrupted Core 0.6.2 archive. It is separate from verified chess
continuation. Supported historical arenas are tic-tac-toe 1.0.0, connect-four
1.0.0 and othello 1.0.1. It does not support hidden-information games, a supplied
board position, partial archive fragments or an unchecked ruleset migration.

The permanent execution label is:

> Recovered position; historical model routing unverified

Legal replay and archive-internal receipt association do not prove historical
routing, signed-build custody, Platform case custody or provider authenticity.
All four remain `unverified`. Recovery never makes the source or child eligible
for scoring, proof-row publication, competitive winners, leaderboard aggregation
or official admission. A terminal board outcome is display-only.

## Public contracts

`eslams.contracts.board_recovery` defines TypedDict wire contracts and closed
JSON Schemas for these versioned objects:

| Version | Meaning |
| --- | --- |
| `legacy-board-evidence/v1` | Original snake_case evidence-inspector report; non-executable |
| `board-recovery/v1` | Source identity, byte-derived history, accepted prefix and prospective execution pins |
| `board-recovery-engine/v1` | Actual local or installed target engine identity |
| `board-recovery-preparation/v1` | Descriptor and target engine with independent digests; no execution/publication permission |
| `board-recovery-lineage/v1` | Private source archive, copied receipt ledger, child identity, evidence and accounting |
| `board-recovery-public-result/v1` | Display-only result with explicit historical uncertainty and no private source identities |
| `board-recovery-validation/v1` | Successful child-internal replay validation marker, not external custody verification |

New recovery objects use camelCase. The unchanged nested evidence report and its
four assurance labels retain snake_case. All fields are required, including
nullable time budgets. Unknown properties are rejected. Participant lists are
ordered `player_1`, `player_2`; no seat duplication or substitution is allowed.
SHA-256 fields contain raw lowercase 64-character hexadecimal digests, except
for the legacy report's `prefix.final_state_sha256`, which retains `sha256:`.

The source descriptor separates:

- `source`: Platform-provided source bindings and exact archive/payload hashes.
- `history`: Core 0.6.2, historical arena/version, seed, turn and time budgets,
  requested-budget presence/value, and requested model identities. Historical
  requests are not routing evidence.
- `prefix`: accepted ply count, normalized legal prefix hash and checkpoint hash.
- `prospective`: new wrapper/runner/scoring policy, current rules hash, turn/time
  budgets and newly pinned providers/routes. These claims apply only to new calls.

`preserve-source` retains the historical cutoff. `native-arena-horizon` allows
max(source cutoff, the arena's native horizon) without rewriting history. The
recorded source budgets are unchanged. `history.timeBudgetMs` is the effective
historical budget; `requestedTimeBudgetMs` and `requestedTimeBudgetRecorded`
separately preserve the requested value and whether the source recorded one.
A missing requested value is represented as null with the presence flag false;
it is not inferred from the effective budget.

Future deadline policy is explicit and independent of turn limits.
`preserve-source-effective` uses the historical effective time budget;
`native-default` sets prospective `timeBudgetMs` to null and does not inherit a
historical 30/60-second framework timeout. Newly requested model IDs/version IDs
must match the recorded requested identities; this mode does not substitute models.

Local engine identity requires `coreRef` and `runnerImageDigest` equal to
`local-development` and cannot claim installed evidence. Installed identity
requires immutable 40-hex Core/Platform refs, `coreSourceSha256`,
`wrapperSourceSha256` and `runnerBuildSha256`; it cannot include a caller-supplied
image digest. Both variants bind `recoveryContractVersion` to the lineage version.

## Preparation is read-only

```python
from pathlib import Path

from eslams.board_recovery import prepare_recovered_position

prepared = prepare_recovered_position(
    source_archive=Path("source.eslams"),
    source=source_identity_from_authoritative_platform,
    history=historical_constraints_from_authoritative_platform,
    prospective=prospective_execution_pins,
    target_engine_identity=expected_installed_engine_identity,
)
assert prepared["newProviderCalls"] == 0
assert prepared["executionEligible"] is False
assert prepared["publicationEligible"] is False
```

The variables above must come from the trusted caller, not archive self-claims.
`history.requestedParticipants` is required; other historical fields may be
omitted and are derived from the archive. Supplied fields are constraints, never
authority, and unknown constraint keys are rejected. Present legacy receipt locked
model versions must match requested versions without inferring missing identities.
`source.coreRunId` may be omitted in preparation input and is then derived from
source bytes; it is always required in the emitted descriptor. Preparation
verifies source bytes and historical constraints, reconstructs accepted actions
without paid calls and returns review material. It does not create child IDs,
start a run, publish a result, or authorize a subsequent run/publication.

Execution uses `RecoveredPosition` with the prepared descriptor/target engine,
the same archive path, a fresh child Platform run ID and a fresh child match ID.
Pass it as `RunConfig.recovered_position`. The runner verifies the source and
actual target runtime again. Child Core/Platform/match IDs must be distinct and
must not reuse source IDs. This feature does not relax normal caller
permissions or provider-budget authorization.

## Accounting, output and publication

The private lineage binds the full source archive at `recovery/source.eslams`
and its byte-preserved receipt ledger at
`recovery/source_provider_receipts.jsonl`. The missing final legacy attempt
remains unknown: no synthetic receipt, zero-cost assumption or guessed physical
call count is permitted. Historical spend and historical final physical call
count are the literal `unknown`; aggregate scope is `incremental_only`.

Reconstructed actions are labeled `reconstructed_action` and reference no newly
paid successful attempt. New calls keep separate receipts and are counted once.
A complete future ledger does not retroactively complete the historical ledger.

`recovery/public_result.json` uses the dedicated public-result contract. It
contains the required unverified label, the requested historical model IDs,
separately identified prospective model/provider IDs, reconstructed/incremental
turn counts and, only when terminal, `boardOutcome` with `winnerSeat` and `draw`.
`competitiveWinner` is always null. It contains no archive/source IDs, route keys,
route hashes, receipt bodies or private lineage. Public board replay is allowed
for these public-information arenas; this is not a hidden-state disclosure API.

`publicationRequiresAuthoritativeSourceReread` is always true. Publication must
reread the authoritative source and current source-to-run bindings immediately
before use and verify lineage, preparation/descriptor/engine digests and target
policy. A local schema pass, an uploaded file or previously prepared wrapper is
not publication authority. Source drift must fail closed.

## Validation and generated types

A successful full artifact validation may include an optional `recovered_position`
object using `board-recovery-validation/v1`. Its `status: verified` applies only to
`validatorScope: child_internal_source_replay`. It is emitted only when the full
strict reader and deterministic replay succeed. It does not verify external
custody or replace the mandatory authoritative source reread before publication.
The object is absent for ordinary artifacts and unsuccessful validation. It does
not authenticate a target build merely because its self-reported identity and
hashes agree. Publication must compare the complete target identity with the
independently frozen admission pins. Reading an older artifact does not require
its target build to equal the currently running validator's build.


The `validate_board_recovery_descriptor`, `validate_board_recovery_engine`,
`validate_board_recovery_preparation`, `validate_board_recovery_lineage`,
`validate_board_recovery_public_result`, `validate_board_recovery_validation`
and `validate_legacy_board_evidence`
functions return detached typed copies or raise the fixed error
`invalid board recovery contract`. They do not echo input values and do not
require the development-only jsonschema package. Runtime integers are exact
integers; booleans, numeric strings and integral floats are not coerced.
Structural validation does not verify digests, legal replay, source authority,
provider identity, endpoint configuration or installed build authenticity.

Export with `eslams schemas export --out <empty-directory>`. The bundle remains
flat: slash-version contracts use filenames such as `board-recovery.v1.schema.json`.
The schema-bundle manifest preserves the original wire schema version separately
from the filename. Existing dot-version filenames and bundle layout are unchanged.

Generate or check TypeScript from the canonical schema definitions:

```sh
PYTHONPATH=src python scripts/generate_board_recovery_types.py
PYTHONPATH=src python scripts/generate_board_recovery_types.py --check
```

The generated module is exported by `@eslams/core-contracts`. No generated schema
or build ID is hand-edited. These are new opt-in contracts; existing historical
artifacts and chess-continuation contracts are not rewritten or reclassified.
