# Legacy board evidence inspector (design, not admission)

Status: experimental implementation for review, offline only. No runner, deployment, CLI continuation, route
selection, paid request, or scoring behavior changes are authorized by this design.

## Evidence established by private inspection

Four Core 0.6.2 archives contain ten successful board actions: two tic-tac-toe
prefixes of three actions each, one connect-four prefix of three, and one othello
prefix of one. Each action's response contains a provider_receipt equal to its
ledger row, and the response action equals the trace action. Non-null gateway
request IDs and run/episode/logical-action/turn/player identities agree. Each
response has one attempt_receipts entry equal to the provider receipt except for
the absent derived usage_complete and cost_complete fields.

All successful_attempt_event_id values are null, and receipts retain
action_applied=false. Those facts must remain unchanged. Archived association
is demonstrable; independently authenticated provider execution is not.

The final error is at the next turn with policy invalid-match and error_kind
agent_crash. Its response_metadata.error contains a 502 Bad Gateway diagnostic.
There is no final failed request receipt. This is archived HTTP error evidence,
not proof of the provider's underlying failure, billing outcome, retryability,
or completeness of the physical request ledger.

The temporal source-build attribution is operator inference. Historical route
identity, source image attestation, and Platform case identity remain unverified.
No alias table, present-day route, or matching resolved model name repairs this.

## Experimental API and output boundary

An independent experimental developer tool at
`scripts/inspect_legacy_board_evidence.py`, not imported by runtime admission:

    inspect_legacy_board_evidence(source: Path, expected_sha256: str) -> report

A versioned report includes only fixed codes, booleans, action counts, supported
arena slug/version, archive SHA-256, replay-final state hash, and terminal status.
It never returns raw receipts, prompts, explanations, IDs, model names, routes,
URLs, board positions, history, execution pins, or continuation descriptors.
`executable`, `scoring_eligible`, and `official_admission` are always false.
`assurance.route`, `assurance.signed_build`, `assurance.platform_case`, and
`assurance.provider_authenticity` remain unverified.
`final_attempt.provider_execution`, `final_attempt.physical_call_count`, and
`final_attempt.spend` remain unknown.
Malformed or contradictory input fails closed with fixed, non-reflective codes.
A successful report means internal evidence consistency only.

## Existing Core APIs to reuse

- eslams.zip_extract.extract_archive and ArchiveLimits: bounded, portable ZIP
  handling; refuse traversal, aliases, duplicate members, links, encryption.
- eslams.arenas.tic_tac_toe.TicTacToeArena, connect_four.ConnectFourArena,
  othello.OthelloArena: initial_state, is_legal, apply_action.
- ArenaState.to_dict and state_hash: compare complete recorded states as well as
  hashes, not just copied archive hashes. Extract seed from recorded state
  metadata and explicitly label it as archived input, not trusted execution pin.
- eslams.contracts.provider.provider_attempt_event_id: recompute attempt identity
  where the exact legacy identity contract is supported, never invent IDs.

Do not call prepare_board_continuation, _inspect_archive, _check_receipts, or
VerifiedChessContinuation as compatibility shortcuts: their contracts represent
modern admission evidence. Do not relax ArtifactValidator or provider validators.
The inspector separately verifies manifest member digests and lengths without
misrepresenting that as modern artifact validation or external signature trust.

## Strict archive-internal association

Snapshot the source once, hashing while bounded-copying to a private temporary
file. Check the supplied digest before parsing. Never rewrite the source.
Require exact supported legacy package/arena versions, explicit required member
hashes, unique JSON keys, finite values, strict scalar types, bounded lines and
row counts. Preserve original bytes; canonical equality is only a comparison.

For every contiguous trace row, require a unique event and logical action ID;
matching archive run and episode identities; active player matching the rules;
empty failure/fallback markers; legal action; exact before/after reconstructed
state and hashes; response.action equal to action; and matching request identity,
state hash, arena and legal actions. Public and auditor trace shared fields must
agree. Require local_action and unchanged legacy false application flags for this
narrow profile, without promoting them to provider_action.

Require a nonempty, unique successful receipt event/gateway identity;
request_id is null in the historical receipts and is never a join key. Require
status completed, outcome ok, wire/action parse ok, HTTP 200; exactly one ledger
row matched by response.metadata.provider_receipt; gateway identity matching
response metadata; logical/run/episode/turn/player matching the trace; exactly one
attempt_receipts entry matching all supplied fields and missing only the two
known derived completeness flags. Require primary attempt 1, unique gap-free
case attempt identity, and reject any orphan, duplicate, failed, missing,
contradictory, or multiply matched receipt. Never join by row order, model alias,
seat alone, timestamps, null IDs, or action equality alone.

Require exactly one archived terminal error at the next turn and next player;
report only recognized error_kind/policy and a narrow 502 diagnostic classifier.
Do not echo its free text. An unrecognized diagnostic is rejected.

## Contract tests and adversarial matrix

Implemented focused tests cover all arenas, contradictory associations, malformed
input, byte preservation, privacy, archive limits, aliases, duplicate ZIP entries,
symlinks and path traversal. The following matrix is the review checklist, not a
claim that every mutation already has a separate test.

Use synthetic fixtures only, with conspicuous non-production IDs. Cover all
three arenas, normal prefixes, and byte-for-byte input preservation. Assert no
runtime import/admission route and no descriptor fields in output. Verify output
and errors never contain canary prompts, secrets, URLs, IDs or receipt payloads.

Reject tampered digest/member hash/length, missing/duplicate/aliased ZIP members,
traversal, symlinks, oversized ZIP/member/line/row count, malformed JSON, duplicate
keys, non-finite numbers, bool-as-int indexes, empty or duplicated IDs, unmatched
or orphan receipts, swapped receipts, changed action, missing nested receipt,
null identity false matches, wrong turn/player/episode/run, bad parse/status,
extra failed attempts, contradictory request state, illegal moves, changed state
hash/full state, terminal prefixes, unexpected markers, unsupported versions,
multiple or wrong-turn final errors. Modern fixture validation must remain
unchanged and the installed continuation runtime must continue refusing these
legacy archives.

## Actionable missing evidence and separate product proposal

Authenticated per-run source image identity; trustworthy Platform case linkage;
contemporaneous requested model and exact gateway route identity; authoritative
final physical-attempt outcome/cost evidence; and an explicitly reviewed legacy
scoring policy are missing. A successful inspector cannot manufacture any of
these. A future recovered-position, unscored completion mode could use a newly
identified run and clear provenance, only after owner discussion. It is neither
implemented nor enabled here.

## Limits and verification scope

The implementation accepts at most 8 MiB compressed, 64 ZIP members, 8 MiB per
member, 32 MiB total decompressed, 1 MiB per JSON/JSONL line, 128 JSONL rows and
64 successful board actions. These are intentionally narrower than general Core
artifact limits. Unknown profiles fail closed. Free-text archived error messages
are classified only as containing the HTTP 502 diagnostic with the matching
HTTPX documentation suffix; this is not independently verified HTTP evidence.

The inspector does not establish which Platform run owns the archive. A separate
operator custody record may identify the artifact-owning successor. The report
cannot attribute the recovered position or any outcome to a different original
uncertain run. Caller-supplied archive SHA-256 binds bytes, not that attribution.

The source archive and embedded raw receipt bytes are never rewritten, repaired,
normalized on disk or returned. JSON parsing exists solely for comparison. Output
contains a digest of the original archive and the reconstructed state hash, not
raw state or raw receipt bytes. Temporary copies are private and cleaned up.

## Experimental report contract

The closed JSON Schema is `legacy-board-evidence-v1.schema.json` beside this
document. TypedDict/Literal declarations in the standalone script mirror it.
Every returned report is validated against this schema at runtime. It is not
part of Core's exported admission contracts or installed runner interfaces.
`verified.listed_member_digests` means all listed member lengths/digests agree
with these bytes, including the legacy `unhashed_files` timing entry. All actual
file members except the manifest must be covered; the only permitted unhashed
entry is `timings/timings.json`, which is nevertheless byte-checked here. This
is self-consistency, not a cryptographic signature or trusted build attestation.

The exact supported final reason is the next player followed by
`:agent_crash:agent_crash,no_action`. Additional response metadata, including a
failed receipt or attempt list, is rejected rather than ignored.

## Running from a development checkout

First install `.[dev]` following CONTRIBUTING.md. Then run
`PYTHONPATH=src python scripts/inspect_legacy_board_evidence.py --archive
<local-archive> --sha256 <expected-original-file-sha256>`. The digest is the bare
64-character lowercase SHA-256 of the original archive bytes. Do not publish the
archive or copy private content into a fixture. Success prints only the closed
report; failure prints a fixed error code and exits nonzero. This command never
contacts a gateway, provider or Platform service.

Focused regressions are in `tests/test_legacy_board_evidence_inspector.py`. The
implementation was checked against the four local originals without modifying
them. All private-source checks are aggregate-only and do not add private
fixtures or original identifiers to the repository.

The no-secret example `legacy-board-evidence-v1.example.json` is generated from a
synthetic test fixture, not any historical private archive. The report is a
source-development tool format, not a new canonical Core API: it is included in
source distributions with its script, schema, tests and documentation, and is
not exported through the installed wheel, Core CLI, canonical schema bundle, or
TypeScript SDK. Use a development installation with the `[dev]` dependencies
(including jsonschema). There is no supported cross-language admission consumer.
Any future promotion to a Core API must coordinate the canonical contract
registry, generated TypeScript, schema export and compatibility gates separately.
