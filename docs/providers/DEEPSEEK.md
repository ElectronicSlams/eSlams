# Native DeepSeek adapter

Verified against official documentation on 2026-11-04, for the proposed 0.7.1
adapter. No live inference, credential use, or paid calls were performed.

## Identity, endpoint and account

DeepSeek operates a direct API; an OpenRouter DeepSeek model is a separate route.
Core uses `deepseek` as the provider namespace and accepts `deep-seek` (including
underscore/case normalization) as a Core spelling alias. These names resolve to
the same adapter through registry lookup, preflight, CLI construction and dispatch.
Export `DEEPSEEK_API_KEY`; Core sends it only in the Bearer authorization header.
An explicit nonblank model ID is required, including in the CLI; `deepseek` and
`deepseek:` without a model are rejected rather than replaced by a default.
The [official quick start](https://api-docs.deepseek.com/) identifies
`https://api.deepseek.com` as the OpenAI-format base URL. The adapter uses
`POST /chat/completions`; account discovery uses `GET /models`.

```bash
export DEEPSEEK_API_KEY='your-key'
eslams providers preflight --provider deepseek --model deepseek-flash
eslams providers models --provider deep-seek
eslams run --arena tic-tac-toe --agent deepseek:deepseek-flash --output-dir ./deepseek-run
```

The first two commands above use local configuration/catalogue checks. Adding
`--live` to provider preflight queries discovery and performs billable inference;
adding it to provider models performs authenticated discovery. Use those options
only when intended. The `run` command also makes billable inference calls.
Core does not automatically read `.env.example`.

The [current model list](https://api-docs.deepseek.com/api/list-models/)
contains `deepseek-flash` and `deepseek-v4-pro`. It describes model and protocol
metadata; the frozen catalogue is advisory, and account availability is unverified
until an authorized live check. Unknown requested models still reach the endpoint
unchanged unless strict catalogue preflight was explicitly selected.

The [pricing/model page](https://api-docs.deepseek.com/quick_start/pricing/)
currently associates these names with Flash-1017 and Pro-0813 versions. It says
legacy Flash names are accepted but served by the replacement Flash model. Core
never rewrites a requested model name, infers an exact version from acceptance,
or substitutes another model/provider after failure. Receipts retain the requested
name and separately record only the sanitized response `model`; a missing returned
identity stays null. A returned alias alone does not attest a particular weight
snapshot. Older broker/imported catalogue rows are not direct API guarantees.

## Messages, controls and deliberately limited surface

The [Chat Completions REST reference](https://api-docs.deepseek.com/api/create-chat-completion/)
defines string system messages, user/assistant/tool messages, and non-streaming
`chat.completion` envelopes. Core sends system instructions and the full public
ActRequest prompt, including all supplied history by default. It accepts one
assistant string answer with `finish_reason: stop`, then applies Core's existing
JSON/action/legal-action validation. Reasoning text is neither action content nor
receipt content. Missing/unknown finish reasons and malformed choices fail closed.

The [thinking guide](https://api-docs.deepseek.com/guides/thinking_mode/)
documents native thinking defaults and explicit controls. Core's `auto` omits
thinking controls, explicit enabled/disabled sends `thinking.type`, and an explicit
`reasoning_effort` passes through unchanged. Explicit token budgets
(`reasoning_budget_tokens` or `gemini_thinking_budget`, including zero or -1)
are unsupported and fail configuration preflight and the execution guard before
any discovery/inference transport. It never derives these choices from
the game or catalogue default. Temperature is forwarded only when thinking is
explicitly disabled, because it has no effect in thinking mode. Output limits
are omitted unless the caller selects one, then sent as `max_tokens` unchanged.
Provider context/output limits remain provider-owned; no framework output or
inference-time ceiling is introduced.

[JSON output](https://api-docs.deepseek.com/guides/json_mode/) is a JSON-object
mode, with prompt requirements and possible blank output; it is not a general
JSON-schema response format. Core uses its ordinary action prompt and parser,
without claiming endpoint schema enforcement.
[Tool calls](https://api-docs.deepseek.com/guides/tool_calls/) support functions;
strict schema validation requires the beta route. Tool choices also have
thinking-mode restrictions. This adapter sends no tools and rejects unsolicited
tool calls. It does not implement tool execution/continuation, beta prefix/FIM,
streaming, vision, Files, Search/Fetch, Responses, or Anthropic-format requests.
Those provider features do not imply equivalent Core support.

## Failure, retry and accounting

[Official error codes](https://api-docs.deepseek.com/quick_start/error_codes/)
cover invalid format/parameters (400/422), authentication (401), insufficient
balance (402), rate limits (429), and server failures (500/503). Core retains its
existing outcome vocabulary: 402 is `provider_request_rejected`; server failures
are `provider_unavailable`. HTTP 200 error envelopes are also failures. Refusal,
length truncation, aborted/resource interruption and tool-call finishes reject
even legal-looking partial actions, while preserving observed usage. Error prose,
raw completions and credentials do not enter sanitized attempt receipts.

The [rate/keepalive guide](https://api-docs.deepseek.com/quick_start/rate_limit/)
describes account concurrency and whitespace keepalives. Core reuses its bounded
transport, cancellation and explicit deadline controls; ordinary JSON whitespace
is accepted. Retries default to zero. An opted-in retry can replay only a complete,
definitive 429 rejection accepted by Core's existing safe-retry predicate, with no
observed accepted work. Ambiguous 5xx, partial bodies and timeouts never replay,
even if the provider recommends retrying operationally. There is no fallback.

Usage comes from the documented REST `usage` fields: prompt includes cache hits
plus misses, and completion includes reasoning. Cache hits map to the input-cache
subset; reasoning is not added a second time. Missing fields remain unknown;
malformed counts, conflicting cache fields and inconsistent totals are flagged.
No tokenizer estimate replaces provider usage. Missing usage cannot become an
official accounting-valid result.

Pricing is intentionally unavailable in receipts. Current prices vary by cache
category, peak/off-peak schedule (including Chinese public holidays), model and
currency. The [Chinese pricing page](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
quotes CNY and the English page quotes USD, using the same API hostname and
corresponding UTC/Beijing schedule. Neither establishes an operator-selectable
regional endpoint or an account's billing currency. Core clears old imported
DeepSeek rates through narrow overrides, without regenerating the registry or
inventing a regional route, exchange rate, fixed cost, or zero charge. A complete
account-applicable rate-card integration remains future work; these receipts alone
do not establish official cost eligibility.

## Offline evidence and integration

`tests/fixtures/provider/deepseek/*.json` are synthetic, keyless fixtures authored
from the linked raw REST schema and error semantics. They are not captured live
responses. The fake action, IDs, key and reasoning text deliberately test parsing
and privacy; they attest no service availability or exact model version.
`tests/test_deepseek_adapter.py` exercises success, full history, native defaults,
explicit controls, aliases across entrypoints, unknown models/identity/usage,
malformed/duplicate JSON, blank answers, refusal, truncation/interruption, HTTP and
in-body failures, safe retry custody, credential redaction, discovery and artifacts.

Integration conflict points with parallel adapter work are the small insertions
in `agents.py` (dispatch/parser/usage maps), `cli.py` (defaults),
`provider_preflight.py` (credential/discovery maps), `providers/registry.py`
(alias), `providers/data/overrides.json`, `.env.example`, `CHANGELOG.md`, and
`docs/DOCS_INDEX.md`. Provider execution, fixtures and tests are separate files.
Reconcile those insertions and rerun checks on the combined commit; this branch's
checks cannot attest another integration commit. No version bump, generated
registry update, workflow change, merge, deployment or release is included.

### Cloud validation (Python 3.12.14)

- All 68 provider-specific tests pass. Repository-wide Ruff and strict mypy pass.
- Both TypeScript packages type-check with TypeScript 5.5.4. Arena version
  fingerprints, initial-state budgets, deterministic portable bytes, schema export
  byte comparison, benchmark smoke, wheel/sdist build and Twine metadata pass.
- Full pytest is blocked by two failures reproduced independently on untouched
  main `270a863d10d57a0953f21924f1a0dd50159e6cf1`:
  `test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
  expects `TimeoutError` while partial-response custody raises `ProviderCallError`;
  `test_cli_fallback_failing_seat_board_win_is_only_a_board_result` expects a
  player-one board win but receives null.
- Python/Core-lite runtime parity is also blocked on untouched main: TypeScript
  emits Core `0.6.2` / prompt v2 while Python emits `0.7.0` / prompt v3. Type-check
  success does not establish runtime parity. These release checks remain intact.
- Only this Linux/Python environment was executed; no native Windows/macOS or
  Python 3.10/3.11 validation is claimed. Hosted Actions and live API calls were
  not initiated. The commit carries `[skip ci]` for preserving the remote branch.


### Review hardening

The adapter rejects missing/blank model IDs at construction and CLI parsing;
preflight returns a rejected configuration, and execution rechecks the model and
unsupported token budgets before transport. Nonblank model names are preserved
exactly. This changes the initial draft's provider-only CLI default behavior.

Credential redaction compares provider-derived strings against the active primary
key and nonempty environment values whose names identify keys, tokens, secrets,
passwords or credentials. These values are private comparison material; secondary
credentials are never sent to DeepSeek. Literal and URL-encoded echoes in receipt
values are removed, and credential-bearing dictionary keys are discarded. An
identity removed by redaction becomes unknown. This applies to success, HTTP
errors, in-body errors, malformed JSON and interrupted-body header evidence.
Action text containing credentials, including JSON-escaped values, is rejected
before it can enter public explanations or raw-action metadata. Discovery also
rejects credential echoes masquerading as model IDs.

Redaction happens after retry admission is determined from original evidence:
removing an echoed accepted-work ID cannot make an ambiguous failure retryable.
The credential-hardening update at `3066bb0` has 110 deterministic DeepSeek cases,
retaining full-history,
native-default, explicit-limit and existing safe-retry coverage. Validation of the
updated head is reported in PR #251; the initial 68-case results above refer to
commit `844b7c7559c2b86763b37c89c44d2b69ceaaf039`.


### Nested action JSON safety

Credential scanning and receipt redaction use iterative traversal. Before action
text reaches shared action parsing, the adapter checks decoded JSON for at most
64 nested containers (including the root object). This is a structural safety
limit for action JSON; it does not cap generated tokens, inference time or supplied
history. Parser recursion/depth exhaustion and structural-limit violations become
`provider_response_schema_mismatch` with the already verified HTTP response,
request/response identity and usage retained in the sanitized attempt receipt.
They do not permit action repair, retry or action application.

The current provider suite has 120 cases. Regressions include exactly 2,000 and
20,000 nested arrays in an otherwise valid HTTP 200 completion, a 64/65-container
boundary, ordinary shallow controls, an iterative 20,000-array credential scan,
and persisted artifact usage after rejection. Final-head validation is reported
in draft PR #251; previously documented baseline failures remain disclosed.
