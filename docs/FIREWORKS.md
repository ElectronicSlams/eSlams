# Fireworks direct inference adapter

This is a 0.7.1 adapter candidate on the Core 0.7.0 baseline; package and contract
versions are unchanged. It calls Fireworks directly with raw HTTP, using Core's
bounded transport, cancellation, attempt receipts and safe retry admission.

## Configuration

Export `FIREWORKS_API_KEY` only when you intend to make a live call. Core does not
load `.env` files. Examples use an explicit placeholder; choose a model resource
from your Fireworks account before running inference:

```bash
# Offline configuration check: no inference or account discovery.
eslams providers preflight --provider fireworks \
  --model 'accounts/fireworks/models/<MODEL_ID>' --arena tic-tac-toe

# Paid inference when deliberately invoked with a configured key.
eslams run --arena tic-tac-toe \
  --agent 'fireworks:accounts/fireworks/models/<MODEL_ID>' --opponent first-legal
```

`fireworks`, `fireworks-ai` and `fireworks_ai` resolve to the canonical receipt
provider `fireworks`. The CLI requires a model; it chooses no default. The exact
model string, including account, case, slash and colon separators, reaches the
wire unchanged. It is never translated to an OpenRouter name or another model.
No fallback provider or model is attempted.

The request is `POST https://api.fireworks.ai/inference/v1/chat/completions`,
with `Authorization: Bearer <FIREWORKS_API_KEY>` and JSON content. Core sends its
system instructions and the full supplied agent-visible history in its user
prompt, with `stream: false`. An explicitly configured Core history window still
applies. It requests `context_length_exceeded_behavior: error`; it never sets
`prompt_truncate_len` or silently trims supplied history to fit.

Core omits `max_tokens`, temperature and reasoning effort unless the operator
selects them. Total/read thinking deadlines are unset by default; existing
connection/write transport safeguards and the 1 MiB response bound still apply.
Provider-native context/output constraints can still stop generation.

## Reasoning and completed answers

`ProviderRuntimeConfig(reasoning="auto")` leaves native reasoning unchanged.
`reasoning="disabled"` sends `reasoning_effort: "none"`; `reasoning="enabled"`
sends `true`. An explicit `reasoning_effort` string passes through unchanged;
an explicit positive `reasoning_budget_tokens` maps to the integer form of
`reasoning_effort`. Effort and budget cannot be combined. Foreign Gemini controls
and zero token budgets are rejected before transport. Unsupported model-specific
choices are left for Fireworks to reject authoritatively. No arena selects an
effort, output maximum or thinking budget.

Only a single completed assistant text choice is accepted. Core reads
`choices[0].message.content`; it excludes `reasoning_content`. For the documented
inline form, it removes one leading completed `<think>...</think>` block before
action parsing or diagnostic metadata. Incomplete/remaining thinking delimiters,
reasoning-only output, unexpected finish codes and tool output fail closed.
`length` is `provider_output_truncated`; `content_filter` is `provider_refused`.
The optional compatible `message.refusal` field is also rejected defensively.
Parseable partial/refused actions never reach the arena or action repair.

## Identity, usage and failures

The response `model` is the only resolved identity evidence. Missing identity
stays null; a different returned identity remains different in the receipt.
Neither the requested model nor the endpoint hostname attests a backend build.

Usage reads `prompt_tokens`, `completion_tokens`, `total_tokens`, cached prompt
details, and reasoning details from the documented completion/output detail
fields. Reasoning is included in generated output tokens and is never counted or
priced twice. Missing counters remain unknown. Core labels derived totals and
retains validation errors for malformed or conflicting counters. These facts do
not establish measured cost. No undocumented `usage.cost`, fixed price or reviewed
rate card is invented; ordinary registry estimates and explicit reviewed rate-card
requirements remain in force.

HTTP 400/402/408/412/413 map to Core's request-rejection class; 401 to authentication,
403 to permission, 404 and 5xx to unavailability, and 429 to rate limiting.
These are existing Core classifications: HTTP 408/504 do not prove local timeout
or stopped remote work. HTTP-200 error envelopes are classified before parsing.
Receipts retain safe request IDs, status, attempt identity and available numeric
usage, while excluding headers, prompts, raw errors, refusals and private traces.
Non-2xx usage observations retain Core's quarantined provenance.

Default retries and action repairs are zero. An operator can opt into a retry
only when Core proves a complete rate rejection with no work/accounting evidence;
each physical attempt gets a separate receipt. Ambiguous 429s, timeouts, transport
failures and 5xx responses never authorize replay or fallback.

## Discovery boundary and verification

This adapter does not implement Models discovery. Fireworks' documented management
List Models endpoint is account-scoped and paginated, distinct from inference.
Core does not guess the operator's account or treat the frozen registry as live
availability. `providers models --live` reports discovery unavailable; an explicitly
requested live preflight can still invoke the exact model and leaves account
visibility unverified. Offline readiness proves configuration only. Strict
catalogue policy may reject unregistered Fireworks resources; there is no bundled
live availability or price claim.

`tests/fixtures/provider/fireworks_chat_completions_success.json` transcribes the
official REST envelope with synthetic identity, text, counters and private-trace
markers. It is not a captured live generation or an SDK convenience property.
Fault tests mutate that envelope for malformed output, errors, refusal, truncation,
429 ambiguity and privacy. Tests cover CLI aliases, mocked live preflight, real
shared transport with an in-memory HTTP transport, receipts and artifact validation.
No credential access or paid inference was needed for these tests.

Official sources reviewed 2026-11-04:

| Source | Contract checked |
| --- | --- |
| [Chat Completions REST](https://docs.fireworks.ai/api-reference/post-chatcompletions) | Endpoint, bearer auth, messages, context policy, reasoning controls, response envelope and usage detail fields. |
| [Text models](https://docs.fireworks.ai/guides/querying-text-models) | Model resource names, direct serverless/dedicated invocation, multi-turn input. |
| [Reasoning](https://docs.fireworks.ai/guides/reasoning) | Separate `reasoning_content`, inline thinking and explicit reasoning controls. |
| [API object reference](https://docs.fireworks.ai/tools-sdks/python-client/api-reference) | `stop`/`length` finish semantics and prompt/completion totals; SDK timeout defaults are not adopted. |
| [Glossary](https://docs.fireworks.ai/getting-started/glossary) | Thinking tokens are generated tokens. |
| [Inference error codes](https://docs.fireworks.ai/guides/inference-error-codes) | Authentication, billing, context/request, model visibility, rate/capacity and service failures. Provider retry advice does not override Core's stricter replay policy. |
| [List Models](https://docs.fireworks.ai/api-reference/list-models) | Account-scoped management discovery and pagination, intentionally unimplemented here. |
