# Baichuan direct adapter (planned 0.7.1)

The package version remains 0.7.0. Use `baichuan-ai:<exact-model>`; `baichuan`
and `baichuan_ai` are aliases for the same direct provider identity. Model IDs
remain case-sensitive and unchanged. A bare provider name is rejected.

```bash
# Offline: no credentials or inference required.
eslams providers preflight --provider baichuan --model Baichuan4-Turbo

# After explicitly authorizing provider charges and configuring BAICHUAN_API_KEY:
eslams run --arena tic-tac-toe --agent baichuan-ai:Baichuan4-Turbo --opponent first-legal
eslams providers preflight --provider baichuan-ai --model Baichuan4-Turbo --live
```

## Official evidence checked 2026-11-04

| Topic | Official source and finding |
| --- | --- |
| Wire/auth | [General API](https://platform.baichuan-ai.com/docs-v2/api): POST `https://api.baichuan-ai.com/v1/chat/completions`, JSON, Bearer key; `model`, `messages`, `stream`; synchronous `choices[].message.content`, `finish_reason`, `model`, `id`, and token usage. Lists Baichuan4-Turbo/Air, Baichuan4 and Baichuan3-Turbo/128k. `length` denotes truncation; `max_tokens` is optional, with a documented provider default of 2048. |
| Reasoning | [Medical API](https://platform.baichuan-ai.com/docs-v2/medical): M2/M3 expose `thinking.budget_tokens`; `reasoning_content` is separate from answer text. No verified effort mapping or disable switch. |
| Independent first-party implementation | [Official MCP client](https://github.com/baichuan-inc/baichuan-mcp-servers/blob/main/packages/baixiaoying-mcp-server/src/api/client.ts) confirms endpoint, Bearer auth, synchronous requests and `X-BC-Request-Id`. [Types](https://github.com/baichuan-inc/baichuan-mcp-servers/blob/main/packages/baixiaoying-mcp-server/src/api/types.ts) identify `content_filter` and `refuse_answer` refusals and three token counters. |
| Account | [Quick start](https://platform.baichuan-ai.com/docs-v2/guide): registration, real-name verification, recharge, API key. Public docs and the linked official MCP project are present; this does not prove account inference availability. |
| Region | [Privacy policy, section 5](https://platform.baichuan-ai.com/article/privacy-agreement): information collected in China is stored in China. No verified selectable regional API route; adapter uses the documented host. This is not an independent residency guarantee. |

The documentation reader retrieved only a navigation shell for several pages;
indexed official documentation supplied the general and medical contract details.
The cloud egress proxy rejected direct documentation fetches and an unauthenticated
HEAD to the API host with CONNECT HTTP 403. This is a cloud-network result, not
evidence of a Baichuan outage, invalid account or regional restriction. No inference,
real credentials, account creation, balance check or paid discovery was attempted.

[Error codes](https://platform.baichuan-ai.com/docs-v2/errCode) and
[rate limits](https://platform.baichuan-ai.com/docs-v2/rate-limit) were linked but
their tables could not be retrieved. Exact current account limits and proprietary
error-code mappings remain unverified; the adapter classifies observed HTTP status,
keeps unknown body errors generic, and never guesses numeric Baichuan codes.
No documented Models API was verified. Offline catalogue entries remain advisory;
live discovery reports unavailable, while explicitly requested live preflight may
perform one inference. The packaged catalogue has no Baichuan model rows, so strict
catalogue mode rejects these unregistered models.

## Adapter policy

Requests use Core's shared bounded, non-streaming transport with the standard JSON
action instructions and public request history. Full history and native output
defaults apply unless an operator explicitly supplies limits. There is no default
thinking deadline, output maximum, automatic action repair or provider retry.
Core's existing response-byte and connection protections still apply. No tools,
search enhancement, retrieval, provider fallback, model substitution or arena-based
reasoning settings are added.

`temperature` and `max_output_tokens` are forwarded as explicit native choices
(`max_tokens` on the wire), without clamping to a guessed model limit. `reasoning=auto`
omits reasoning controls. `reasoning_budget_tokens` maps only to the documented
M2/M3 `thinking.budget_tokens`; no budget is invented. Exact acceptance/ranges are
left to the endpoint. Unsupported explicit effort, disable, enable-without-budget,
and Plus-model budget controls fail before submission. Native reasoning, search or
grounding defaults may vary by model; the adapter makes no claim to disable them.

Only a synchronous assistant message with one index-zero choice and `stop` is
accepted. Refusals and truncation reject even legal-looking partial actions.
Unexpected finish codes, tool calls, malformed JSON/envelopes and a different
returned model fail closed. A missing returned model stays unknown. Receipts retain
stable SHA-256 fingerprints of opaque request/gateway/generation identifiers,
status and documented token observations; reasoning, grounding, unknown extensions
and raw provider error prose are excluded. Fingerprints preserve correlation without
publishing an unrelated credential echoed as an opaque identifier. Actual API-key
echoes are removed from receipt fields; an answer containing that key, including
JSON-escaped forms, is rejected before action parsing or artifact recording.
Bearer values, recognizable key formats and credential-labeled fields/prose are
also rejected in answer text, including escaped values. Ordinary public explanation
text is preserved. Arbitrary unrelated opaque values in unlabeled prose cannot be
identified as secrets without their value or a credential marker; the adapter does
not read unused environment secrets to guess those values.
Sanitized transport errors suppress raw exception chains, including timeouts.
Unexpected returned model strings are omitted from mismatch receipts. This adapter
transmits one Bearer key and has no secondary-credential setting.

Missing counters remain null, including total tokens; the adapter never derives
missing accounting. Invalid or inconsistent counters are quarantined with static
validation evidence and omitted from canonical usage, keeping artifact generation
valid and accounting incomplete. Preflight distinguishes counter extraction from
complete usage and does not claim completeness while reasoning inclusion is unknown.
Cache/reasoning counters, reasoning inclusion and cost remain
unknown. Even a complete three-counter response cannot establish complete usage
for Official scoring without verified reasoning inclusion. No price card, USD
conversion, service-availability claim or Official eligibility is invented.

HTTP 400/401/403/404/429/5xx use Core's existing classifications. Error-body work
observations are quarantined and never attest model identity or complete cost.
Numeric cost extensions cannot establish currency and are never labeled USD.
Optional retries retain the shared narrow policy: only definitive 429 rejection
without observed generation/usage/cost may replay. Unknown error shapes, timeouts,
transport failures, 5xx, refusals and truncation do not automatically replay.

## Deterministic cloud verification

`tests/fixtures/provider/baichuan_chat_completions_success.json` preserves the
documented synchronous envelope with replacement identifiers, action text and
token counts. Fault injections are synthetic, not captured live responses.
`tests/test_baichuan_adapter.py` covers aliases, CLI/preflight/dispatch, full history,
explicit controls, raw-wire success/errors/refusal/truncation/429, malformed JSON,
unknown identity/accounting, safe transport and receipt/public artifact privacy.
These checks verify implementation behavior; live account service and the
unretrieved official error/rate-limit tables remain release-verification gaps.
