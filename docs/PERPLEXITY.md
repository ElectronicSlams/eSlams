# Perplexity Agent API adapter

Verified on 2026-11-04 against official documentation. This is proposed 0.7.1
adapter work on Python Core 0.7.0, without a version bump. Verification uses
synthetic credentials and documented REST fixtures. No paid inference,
credential retrieval, merge, release, or deployment was performed.

## API selection

The [Agent API reference](https://docs.perplexity.ai/api-reference/agent-post)
documents `POST https://api.perplexity.ai/v1/agent`, JSON, bearer API-key auth,
exact `provider/model` IDs, typed output, status and usage. `/v1/responses` is a
compatibility alias; this adapter uses the canonical endpoint. The receipt
provider remains `perplexity` even when a model namespace names another company.
No model namespace is added, removed, or rewritten.

[Orchestrator routing](https://docs.perplexity.ai/docs/router/routing-and-reliability)
is in private preview. It automatically routes/retries across deployments without
routing controls and echoes requested model IDs regardless of deployment. That
does not satisfy this adapter's no-fallback requirement.
[Sonar Chat Completions support ended September 27, 2026](https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview);
remaining synchronous calls are being reformulated as Agent requests. Search,
Embeddings, and Decisions APIs do not produce the required game action envelope.

Agent requests use one `model`, shared Core system instructions, the complete
public game prompt, `tools: []`, `tool_choice: "none"`, `stream: false`, and
`store: false`. They omit fallback chains, effort bundles, presets, profiles,
skills, previous response IDs, and step limits.
[Effort bundles](https://docs.perplexity.ai/docs/agent-api/effort) can change model,
prompt, tools, budgets and fallback; they are unsuitable here.
The [tools contract](https://docs.perplexity.ai/docs/agent-api/building-agents/give-it-tools)
enables tools through the tools array. This adapter has no search/tool opt-in.
Unexpected tool output, reported tool usage, or echoed effort/preset rejects
the response. This does not undo any remote work already performed.

This guarantees deterministic request construction and fail-closed parsing,
not bit-identical hosted inference or pinned underlying weights. Live account
access, model availability, latency and repeatability remain unverified.

## Configuration

Set `PERPLEXITY_API_KEY` in the process environment. Core does not load `.env`.
This configuration-only preflight makes no network request:

```sh
eslams providers preflight --provider perplexity --model perplexity/kimi-k3 --arena tic-tac-toe
```

The agent spec is `perplexity:perplexity/kimi-k3`: provider before the colon,
exact model after it. Missing/blank models fail in Python, CLI and preflight.
There is no default model. Catalogue membership is advisory unless strict mode
is requested. Historical registry names are not the current API contract.

Every public `ActRequest.history` entry is sent on each turn; history window
settings are rejected. No server conversation chain or private reasoning state
is replayed. The [conversation-state guide](https://docs.perplexity.ai/docs/agent-api/conversation-state)
documents manual context replay. Public gameplay state and history are the
source of context for this stateless adapter.

Reasoning defaults remain native, without game-dependent selection. Explicit
`reasoning_effort` is supported only for exact `perplexity/kimi-k3`, whose
[model documentation](https://docs.perplexity.ai/docs/agent-api/models) lists
`minimal`, `low`, `medium`, `high`, `xhigh` and `max`. They are forwarded unchanged;
Perplexity maps `minimal` to low effort and `xhigh`/`max` to maximum effort.
Other exact models can use native defaults; explicit effort for unverified
models is rejected. Generic enabled/disabled reasoning, token thinking budgets,
Gemini budgets and OpenRouter routing settings are rejected instead of ignored.
The [official generated SDK](https://github.com/perplexityai/perplexity-py/blob/1a79c5d3a7b1ef8c2dce17c0f0aa7e23f9bbdced/src/perplexity/generated/api.py)
has a narrower effort enum than the Kimi model page; this REST adapter follows
the explicit model page for Kimi and does not assume SDK feature parity.

There is no default framework output or total/read timeout cap. Explicit operator
output limits, timeout policy and temperature are honored. Shared transport
retains connection/write safety limits, cancellation, deadlines and its response
byte limit. Genuine service defaults/limits still apply. The API requires an
output limit for `anthropic/*` models; the adapter rejects those requests before
networking unless the operator supplies `max_output_tokens`, without inventing
a ceiling.

## Receipts, failures and retries

Only completed raw REST `response` envelopes with the exact returned model and
completed assistant message items containing `output_text` are accepted. Missing
or mismatched identity fails; requested identity never supplies a missing resolved
model. SDK-only `output_text` shortcuts, legal-looking partial text, refusal,
truncation, pending/cancellation, embedded errors, unexpected output, malformed
JSON and duplicate keys do not produce actions.

Shared Core error classification handles HTTP 400/401/403/404/429/5xx, transport
failures and timeouts. [Official error docs](https://docs.perplexity.ai/docs/sdk/error-handling)
describe status errors and `X-Request-ID`. The native adapter uses shared bounded
HTTP transport instead of the SDK, whose [default retry count is two](https://docs.perplexity.ai/docs/sdk/configuration).
Core defaults to zero retries and zero action repairs. Explicit optional retries
only replay a verified pre-work 429 rejection. Generation IDs, usage/work
observations, ambiguous timeouts, 5xx and partial bodies prevent replay. Retried
requests preserve model and payload; no alternate provider is called.

Receipts retain supplied input/output/total counts, cache details, response/request
IDs and outcome. Missing totals remain unknown without inferred sums. Missing
reasoning counts and reasoning-inclusion semantics remain unknown; invalid counts
retain shared validation flags. A finite nonnegative `usage.cost.total_cost` with
explicit USD currency is recorded as provider-native cost; missing cost is unknown.
No rate card is fabricated. A native cost observation alone does not establish
complete accounting or official eligibility. Error-body observations remain
quarantined under shared receipt policy rather than trusted pricing or identity.

Both the selected key and canonical `PERPLEXITY_API_KEY` (when a custom credential
environment is used) are checked across retained receipt strings and keys.
Checks include mixed JSON Unicode escapes, URL escapes, and the parsed action
object before shared action parsing can expose decoded explanation text.
Contaminated fields become null or are dropped; credential-containing action
text is rejected before parsing or `raw_action_text` emission. This covers
success, errors, malformed and partial responses. Raw bodies, headers, provider
error prose and private reasoning are not copied wholesale into receipts.

`GET /v1/models` is the [public Agent catalogue](https://docs.perplexity.ai/docs/agent-api/openai-compatibility),
which does not require authentication. The existing live discovery command still
requires a configured key for the adapter, but the public GET does not send it.
The provider-specific discovery parser rejects credential-containing IDs,
malformed or duplicate-key JSON, and unexpected pagination. It returns no partial
list on failure. Its list represents catalogue visibility, not account
entitlement. Configuration preflight does not prove availability. `--live` sends
billable gameplay inference and must only be used deliberately; this contribution
did not run it against Perplexity. Perplexity preflight now uses the canonical
usage aggregator for completeness: inconsistent counts, cache counts above input,
invalid counts, and unverified reasoning inclusion remain incomplete even when a
legal action succeeds. It does not equate three present integer fields with
verified accounting.

## Cloud verification

The provider-specific tests cover dispatch, CLI/preflight, full history, reasoning,
explicit limits, unsupported controls, raw success, identity, accounting, HTTP and
semantic failures, malformed/partial responses, retries and credential echoes.
The fixture follows the official Agent response envelope with synthetic action
content and counts; it is not a captured inference response.

Initial unmodified baseline at `270a863d10d57a0953f21924f1a0dd50159e6cf1`:
1,258 passing tests and two failures:
`test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
and `test_cli_fallback_failing_seat_board_win_is_only_a_board_result`.
Baseline Ruff and Mypy passed. The full candidate run had 1,345 passing tests
and three failures: those same two plus
`test_arena_session_start_and_one_step_all_games_are_public_safe`, whose unchanged
50 ms timing assertion measured 111 ms. The timing test passed on one isolated
rerun (0.50 seconds for the test). No failure was suppressed or replaced.
Provider tests, Ruff, Mypy, schema export (45 schemas), all 50 arena fingerprints,
all 50 initial-state budgets and configuration-only CLI preflight passed.

The adapter is proposed in [draft PR #301](https://github.com/ElectronicSlams/eSlams/pull/301).
The independent hardening review added regression coverage for decoded credential
echoes, public discovery, preflight accounting, post-construction reasoning config
replacement, and reflected tool/fallback configurations. Tests use synthetic keys
and mocked HTTP only. Final review checks: 137 Perplexity tests passed, 142 tests
passed with shared discovery regressions included, and Ruff/Mypy passed. The full
review run had 1,395 passing tests and only the two baseline failures listed above;
the earlier intermittent arena timing test passed in that run. No inherited test
was modified or replaced. Updated validation results are recorded in the PR.
