# Internal Core backlog candidate

This is an internal review candidate, not a public release or a claim that every historical incident is fixed. Its source base is PR226 head `6df70125b2ef9406c0ad609b16d5ef7182c23fa1`. The separately reviewed C4 checkpoint `9e6a7418bac57db07abef484e5f9eb87e830d37b` stays frozen for selected research admission. This broader candidate includes its unbounded execution and invocation-scoped receipt fixes.

## Model execution and compatibility

`RunConfig.time_budget_ms`, native output capacity and preflight time/output choices default to `None`. This removes the framework's model-thinking/output deadline; it does not promise infinite provider capacity. Native optional fields are omitted instead of replaced with a sentinel integer. Provider-required output fields need an explicit caller choice or a verified provider capacity with provenance. Connect/write failure detection, legal actions, turn rules, input limits, cancellation and operator financial policy remain independent.

Act-v2 requires an explicit null or positive budget and matching closed `metadata.model_execution_policy`. Legacy finite Act-v1 remains readable. Runner-job request-v2 has the same policy and explicit null requirement. Its JSON schema is published in schema bundle-v6 alongside job-v1. Budget/duration equality additionally requires the runtime validator; JSON Schema validation alone is insufficient. Rebuild downstream generated clients against this bundle before rollout. General metadata remains open; policy objects reject hidden caps and contradictions before callbacks.

The native defaults do not choose catalogue reasoning effort or truncate supplied history. Explicit supported operator reasoning/history settings remain available. Provider preflight no longer injects 30-second or small-output test limits. Model compatibility/provider-required fields remain validated. Registry lifecycle/readiness data has not been converted into an unconditional promise of live model availability.

## Failure and accounting boundary

Only complete, valid actions advance games. Provider-reported output/context exhaustion, refusal, pending, cancellation and generic interruption follow the versioned completion corpus. A local body timeout/reset or byte guard is not provider-reported token exhaustion. For incomplete bodies the transport/resource classification takes precedence; observed HTTP status and bounded safe request/Gateway IDs remain diagnostic evidence. No partial-body usage, response ID or cost is inferred, including after HTTP429/503. This does not authenticate billing.

Optional `max_retries` no longer replays timeouts, transport failures or HTTP5xx. A complete rate-rejection response may use caller-enabled retry/backoff; observed generation/usage in a parsed error envelope prevents that retry. Defaults still make one attempt. Explicit action repair remains an operator opt-in and is separately recorded. This is not a durable inference ledger or permission to restart ambiguous work.

The new header observation is private transport evidence, not a new public receipt field. Existing `receipt.outcome`, `status_code`, safe IDs, unknown usage/cost and action-applied status suffice. The 27 completion vectors remain unchanged. A cancellation can return while a quarantined callback is draining: an embedding transport must retain its own invocation-scoped custody and persist unknown holds. No upstream termination, refund or complete late-header custody guarantee is made.

## Host policy and session concurrency

`RunnerSessionStore(max_sessions=None, idle_ttl_seconds=None)` has no implicit eviction. A host can choose finite limits; active leases are not evicted. Session mutation, signed state and returned snapshot share a per-session lock. Independent sessions progress separately. Sync HTTP session work runs in FastAPI's thread pool rather than blocking the async event loop. This is in-memory state, not durable checkpoint/resume or exactly-once execution.

Signed-request nonce claims are atomic. Existing default replay protection was already bounded/expiring; the change adds a thread-safe backend and optional `ESLAMS_RUNNER_NONCE_DB` SQLite storage for shared local processes. SQLite is not a distributed lock or inference ledger. Backend/capacity failures fail closed. Multiple hosts need an external shared authority.

Agent and runner request admission limits bytes before JSON parsing/callbacks. `max_request_bytes` is an explicit host setting (default1MiB); malformed/mismatched Content-Length is rejected. These guards remain resource policy, not thinking deadlines. Outbound response guarding remains1MiB and is a documented remaining configurable-host-policy follow-up.

## Cursor migration

Legal-action lists were already fully pageable:225 Gomoku and288 Pentago actions are not truncated by the200 page ceiling. New `ep2` opaque cursors bind HMAC-protected offsets to state, actor, query and ordered descriptors. Forgery, stale state or malformed cursor fails rather than silently restarting page0. Page schema stays v1 because it already declares an opaque string. Legacy numeric cursor acceptance requires explicit `allow_legacy_cursor=True` or CLI `--allow-legacy-cursor`; emitted cursors always use ep2. Coordinate the consumer migration before dropping compatibility at a deployment boundary.

## Output recovery and CLI

Persistent output guard files use OS locks released on process death. Do not delete them: replacing a locked inode can create a second writer domain. Legacy empty/unknown guards fail closed and require operator confirmation that the old writer stopped. This protects artifact writing only, never inference replay. POSIX crash tests are included; native Windows/shared-filesystem acceptance remains open. Orphan staging directories are not automatically declared authoritative or removed.

Missing-file and overwrite failures now have actionable CLI messages. Plain `eslams run` remains the documented local ConnectFour demo. Existing concise-error behavior is retained. README links resolve outside the repository (including package renderers); no claim of a new PyPI publication is made.

## Remaining release gates

Independent review of this broader checkpoint, supported Python/Windows matrix, real deployed transport and cancellation/late-custody acceptance, cross-host durability, final Platform policy propagation and private independent-language parity are open. Session CAS/idempotency and transactional booking/outbox remain separate design work. The numerical replay profile is a separately versioned proposal, not activated in these game equations. No historical goldens are replaced. No model-paid validation or production change is part of this candidate.
