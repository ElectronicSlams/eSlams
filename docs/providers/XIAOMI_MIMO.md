# Xiaomi MiMo direct adapter

This is unreleased 0.7.1 adapter work on Core 0.7.0. No package version,
public contract, arena behavior or registry snapshot changes are included.

Use `xiaomi:<exact-model-id>`, `mimo:<exact-model-id>`, or
`xiaomi-mimo:<exact-model-id>`. Case and underscores in the provider alias are
normalized. Model spelling, case, separators and revision suffixes pass through
unchanged. Bare aliases select `mimo-v2.6-flash`; supply a model explicitly for
reproducible configuration. Catalogue membership is advisory by default.

```bash
# Export an account key privately; Core does not load .env files.
export MIMO_API_KEY=...
eslams providers preflight --provider xiaomi --model mimo-v2.6-flash --arena tic-tac-toe
eslams run --arena tic-tac-toe --seat-agent player_1=xiaomi:mimo-v2.6-flash
```

The first command is offline. `run` invokes inference and can incur charges.
No live inference or real credentials were used in developing this adapter.
Account model discovery and an inference preflight are separate explicit choices:

```bash
eslams providers models --provider mimo --live
eslams providers preflight --provider mimo --model mimo-v2.6-flash --arena tic-tac-toe --live
```

## Official API evidence

Researched on 2026-11-04 using Xiaomi's official documentation. The former
`platform.xiaomimimo.com` documentation redirects to `mimo.mi.com`. Search-indexed
official content was readable; some direct page fetches returned empty rendered
pages, and the cloud shell's direct documentation fetch was denied by its proxy.
These findings verify the documented contract, not live account availability.

| Concern | Official source | Adapter behavior |
| --- | --- | --- |
| Endpoint, authentication and request/response fields | [Chat Completions](https://mimo.mi.com/docs/en-US/api/chat/openai-api) | POST `https://api.xiaomimimo.com/v1/chat/completions`; `api-key: <MIMO_API_KEY>` and JSON. Xiaomi also documents bearer authentication; this adapter uses `api-key`. |
| Models discovery | [List Models](https://mimo.mi.com/docs/en-US/api/model/list-models) | GET `https://api.xiaomimimo.com/v1/models`, same key header, parse `data[].id`. Discovery does not substitute another model. |
| Regional accounts | [Account and Authentication](https://mimo.mi.com/docs/en-US/faq) | The FAQ says account regions have separate base URLs, keys and accounting. This adapter defaults only to the published endpoint above. It does not infer a region, invent another hostname, change keys or reroute a region denial. |
| Error and throttling behavior | [Error Codes](https://mimo.mi.com/docs/en-US/quick-start/error-codes), [Models / rate limits](https://mimo.mi.com/docs/en-US/quick-start/model) | 401 authentication; 403 region/access/risk restriction; 429 request frequency or Token Plan quota; 5xx availability failure. Docs recommend backoff; Core defaults to zero retries and only permits optional replay of a definitive rejection without work observations. |
| Reasoning and tool history | [Deep Thinking](https://mimo.mi.com/docs/en-US/usage-guide/passing-back-reasoning_content), [Chat Completions](https://mimo.mi.com/docs/en-US/api/chat/openai-api) | Native `thinking.type` enabled/disabled; auto omits the field. Reasoning stays private and is never used as action text. Tool conversations require reasoning continuity; this text-action adapter does not initiate tool calls. |

The published API currently lists `mimo-v2.6-flash`, `mimo-v2.6-pro` and
`mimo-v2.6-pro-ultraspeed`. The adapter does not enforce this list: the account's
endpoint decides availability for the exact requested ID. Current thinking models
override custom sampling settings; a custom temperature therefore requires
explicit `reasoning="disabled"`. Unsupported effort or thinking-token-budget
controls fail before submission, with a diagnostic receipt.

No automatic region or endpoint fallback exists. The existing explicit generic
gateway setting can route traffic through an operator-selected gateway; its mode
must be recorded accurately by that operator. It is not a provider/region discovery
mechanism. For a region-specific account, verify its issued base URL and key
outside this adapter before use; unverified alternative direct endpoints are out
of scope for this change.

## Request policy and parsing

The adapter sends one system message and Core's complete public ActRequest
prompt, including all supplied history by default. Core's explicit history-window
compatibility option still applies when selected. It retains no private chat state
between actions, requests no tools and sends no broker routing fields. No
game-specific reasoning decisions are made.

`ProviderRuntimeConfig(reasoning="auto")` preserves the provider's native thinking
default. `enabled` and `disabled` map directly to `thinking.type`. An explicit
operator output limit maps to `max_completion_tokens`, which includes thinking
and visible tokens. Without that choice, the parameter is omitted. Provider
defaults and model context/output ceilings still apply. No framework elapsed or
read timeout is introduced; the shared 10-second connection safety limit,
cancellation/deadline handling and bounded 1 MiB response transport remain.

A successful non-streaming envelope must have `object="chat.completion"`, one
choice, index zero, an assistant message, nonempty string `content` and
`finish_reason="stop"`. `reasoning_content` is ignored. `content_filter` and
defensive refusal-field handling yield `provider_refused`; `length` and
`repetition_truncation` yield `provider_output_truncated`; tool calls are rejected.
Unknown/missing finish fields, empty content, SDK-only fields, streaming chunks,
ambiguous choices and malformed/duplicate JSON fail closed. Legal-looking partial
text never becomes an action after these failures.

HTTP failures preserve status, safe request IDs and Retry-After evidence without
copying error prose. Error-body identity and accounting observations are
quarantined by the existing receipt machinery, including HTTP-200 error envelopes.
Timeouts, ambiguous transports, 5xx, malformed bodies, refusals and truncations are
never automatically replayed. Optional safe retries require an unambiguous 429
error classifier with no response/work/usage/cost observations; the default
`max_retries=0` and `action_repair_attempts=0` each produce one physical request.
Every physical request uses the shared attempt ledger.

## Identity, accounting and privacy

Only a response `model` attests `locked_model_id`; absent or unsafe identity stays
null. Requested model IDs never stand in for missing provider evidence.

Usage reads documented `prompt_tokens`, `completion_tokens`, `total_tokens`,
`prompt_tokens_details.cached_tokens` and
`completion_tokens_details.reasoning_tokens`. Completion details are subsets of
completion tokens, so reasoning is included in output and is not added twice.
Absent counters remain null, including an absent total; no count is inferred from
text length. Invalid types, negative counts and inconsistent totals/subsets remain
diagnosable. Missing usage produces an incomplete receipt rather than invented
zeroes or a scoring claim.

No direct-API monetary rate card is attested by these response fields. Catalogue
prices can be historical or broker sourced and do not establish this account's
region, plan or currency. This adapter therefore emits `cost_unavailable`; it does
not interpret undocumented cost fields or fabricate USD accounting. This limits
cost-complete publication eligibility even when a legal action succeeds. A live
preflight's `ok` is readiness evidence, not cost or Official eligibility.

Credentials, headers, prompts, private reasoning, refusal prose and arbitrary raw
provider payloads are excluded from public receipts. The existing Runner owns
the public/private artifact projections.

## Offline fixture provenance and checks

`tests/fixtures/provider/xiaomi_chat_completions_success.json` uses the documented
raw Chat Completions envelope and native usage-detail fields from the official
Chat Completions reference above. IDs/time, response text and numeric examples
are sanitized synthetic values; the message is replaced with a legal test action
and private-reasoning sentinel. It is not a captured production response or an
SDK convenience object. Fault fixtures mutate that envelope deterministically.

`tests/test_xiaomi_mimo.py` exercises aliases through CLI configuration,
preflight/discovery and dispatch, exact model transmission, full history,
reasoning and output controls, identity, accounting and privacy; HTTP 400/401/
403/404/429/5xx, malformed bodies, timeouts, refusals, repetition truncation and
safe/unsafe retry paths. The entire test suite requires no paid provider access.
