# Python 0.7.0 reliability release candidate

This is a local `0.7.0rc1` candidate, not a publication or a Platform deployment. It includes PR #226 at `6df70125b2ef9406c0ad609b16d5ef7182c23fa1`. Existing research pins and their prompts remain unchanged. Individual provider adapters beyond the existing five families are deferred to 0.7.1.

## Selected source

Start at `ea786e392dfa13f143e9f8d4f2907183f22c0f53` (itself based on PR #226). Carry the non-2xx receipt/retry fixes from `16a10fe`, `e68c813`, and `817055a`; carry the safe-retry fixture correction from `d109bff`. Carry prompt-v3 logic/tests from `8349500` while preserving non-numeric CLI arena dispatch. Set fresh package identity instead of carrying intermediate dev versions. No portable numeric profile, changed game equations, version-2 game activation, optimization experiments or course benchmark corpus is selected. The default legacy game algorithms are unchanged.

## Model execution

Core thinking deadlines, provider total/read deadlines and optional output-token fields default to null/omitted. There is no small framework token budget, automatic reasoning upshift or per-game reasoning switch. Explicit caller deadlines/output budgets, cancellation and provider/resource requirements remain independent. Omission retains genuine provider defaults; it does not prove unlimited upstream capacity.

OpenAI's explicit reasoning effort and Gemini's explicit thinking budget no longer depend on stale model-name capability gates. Native default means omitted reasoning controls. Historical `reasoning="disabled"` means suppress Core control injection, not a guarantee that a provider turns its intrinsic reasoning off. Contradictory explicit controls with disabled injection fail before submission. Other provider-specific control mappings retain their documented adapter contracts; this release does not provide arbitrary parameter passthrough.

Anthropic Messages still requires a real output maximum. Without a caller maximum, the adapter uses a verified model capacity; absent either, it reports a configuration error. Manual thinking has genuine endpoint-specific budgeting requirements. Core must not send invented `unlimited` parameters or a huge sentinel integer. Connect/write failure detection remains 10 seconds by default and is configurable; this is not a model-thinking/read deadline.

## Strict routing

OpenRouter provider fallback remains forbidden. `allow_fallbacks: false` is now sent even when no provider order is supplied. Caller model identifiers and supplied route order are preserved, returned model identifiers remain verbatim, and no model fallback list or automatic alternate paid request is introduced. One local HTTP submission is not proof of one physical upstream attempt. An absent route order does not attest a pinned backend; strict experiments/official consumers must require their actual provider/endpoint identity policy. Privacy, identity and official-eligibility checks are not bypassed by generic Core admission.

The user explicitly deferred the stronger OpenRouter backend enforcement/evidence change to 0.7.1 with individual provider adapters. 0.7.0 preserves the current no-fallback wire/configuration behaviour and does not claim a stable backend across calls. This deferral narrows the release claim; it is not proof that backend verification already exists.

## Preflight contract

Default preflight checks configuration without making catalogue membership a universal admission rule. `ok` means supported local adapter/configuration and, only for explicitly requested live preflight, a legal action observed. `model_availability=unverified` and `readiness.inference=not_attempted` are explicit for offline checks. No credentials are inferred from readiness. Live inference still requires actual credentials.

Catalogue lifecycle/game metadata and Models-list visibility remain diagnostics. Failed discovery or an absent listing does not prevent the explicitly requested model invocation in advisory mode. `strict_catalogue=True` / `--strict-catalogue` retains conservative catalogue/list policy. A model-specific actual inference error remains a failure; Models API success never proves inference success. Optional usage completeness remains separate from legal-action readiness, and cost/build identity/official eligibility are not attested by preflight. `checks` retains individual results, `warnings` explains uncertainty, and `discovery_error` retains the bounded diagnostic separately from inference `error`. Live mode is explicitly opt-in and can incur provider charges.

Compatibility: offline `preflight_mode` becomes `configuration_only`; old consumers relying on `registry_only` or interpreting `ok` as model eligibility must migrate or request strict mode. Act-v2/job-v2 require explicit null plus matching closed execution policy; finite legacy requests remain readable. Generated schema clients must follow the bundled contract. Provider prompts retain all supplied history by default. Prompt package v3 does likewise; explicit v2 retains exact historical projection/hash semantics. Callers must supply actor-authorized history. Larger prompts can hit genuine provider context limits; they are not silently truncated.

## Reliability and issue crosswalk

- #225 / PR #226: invalid fallback/truncated runs do not publish a scored winner through public summary/CLI/viewer; best_score describes the evaluated seat. Existing top-level diagnostic score semantics are preserved, pending the decisions below.
- #224: OS-owned output locks permit recovery after process death without promoting partial artifacts or stealing another live writer's inode.
- #223, #227, #228, #113: actionable output/file CLI diagnostics, documented bare-run demo and package links. #57 concise normal-error handling is preserved, not a new fix.
- Receipt custody: invocation isolation; no stale duplicate accounting; bounded error observations and content redaction; partial/unknown work is not measured zero.
- Retry: default zero retries/repair; explicit retry only for definitive safe rejection without work evidence, all supplied classifiers agreeing. Long Retry-After is no longer rejected by an arbitrary five-second rule. Explicit deadline/cancellation still applies. No cross-host paid-work recovery is claimed.
- Session/input/security: configurable host session TTL/capacity, bounded pre-parse admission, nonce authority, signed cursor scope and async endpoint work isolation. SQLite nonce authority is same-filesystem coordination, not a distributed inference ledger.
- Legal-action transport pages already expose all actions (including 225 Gomoku / 288 Pentago); cursor binding is a security improvement, not a repair of a nonexistent transport truncation.

## Preserved decisions and release gates

For 0.7.0 the user explicitly chose to keep PR #226's existing raw diagnostic fields. Invalid public scored fields stay null. Top-level score.json board fields remain diagnostic as before; error-forfeit is excluded, distinct from a genuine game-rule resignation; fallback CLI exit behaviour stays compatible unless --require-scoring-valid is used. No nullable top-level score schema or new outcome rule is introduced. This closes the raw-field product decision; consumers must still respect validity rather than score an invalid board result. No guessed competitive game loss is created for transport interruption.

Fresh composed-candidate static, regression, package and independent review evidence is required; older 1769-test totals include excluded numeric work and are not this release's count. Previously denied elapsed-deadline listener fixtures remain excluded and must not be retried here. Real transport/late-callback custody, supported-runtime/OS acceptance, actual consumer/image migration and final publication approval remain explicit gates. Arena/Battlefield deployment, external worker enrollment/outbox/durable game authority and Rust parity are separate work; local Python package success does not close them. No paid model run is required by these local checks.
