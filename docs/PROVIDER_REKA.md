# Reka direct adapter (planned 0.7.1)

The `reka-ai` route calls Reka directly. `reka`, `reka_ai` and case-insensitive
spellings are aliases for that provider identity. Model IDs are passed byte for
byte, including any slash, case or revision suffix supplied by the operator.
Every route requires an explicit model ID. Bare aliases, an empty suffix after
the colon, and whitespace-only model IDs are rejected by CLI construction and
preflight before network access. There is no default model, alternate model,
broker route or provider fallback.
The package version remains 0.7.0 until a separately reviewed release.

## Setup

Export `REKA_API_KEY` only when deliberately making a live call. Core trims
surrounding whitespace and rejects internal whitespace or non-ASCII keys before
network access. Configuration preflight is keyless and makes no API calls:

```bash
eslams providers preflight --provider reka --model reka-flash-3 --arena tic-tac-toe
```

These commands explicitly contact the account; live preflight also performs
billable inference:

```bash
eslams providers models --provider reka-ai --live
eslams providers preflight --provider reka-ai --model reka-flash-3 --arena tic-tac-toe --live
eslams run --game tic-tac-toe --agent reka-ai:reka-flash-3 --opponent first-legal
```

No live call or real provider credential was used to develop this adapter.
The frozen catalogue is unchanged. A direct Reka model can therefore be unknown
in the catalogue while configuration preflight is ready; `--strict-catalogue`
continues to reject unknown records. Successful offline fixtures do not attest
account availability, official eligibility or prices.

## Verified contract

Official documentation was checked on 2026-11-04:

| Concern | Official contract and implementation |
| --- | --- |
| Endpoint/auth | [Chat Completions](https://docs.reka.ai/chat/api-reference/create-chat-completion): `POST https://api.reka.ai/v1/chat/completions`, `Authorization: Bearer REKA_API_KEY`, JSON body. This is the current API, not the legacy v0 `/chat` protocol. |
| Request | [Chat guide](https://docs.reka.ai/chat/overview): `model`, `messages` with system/user/assistant/tool roles; optional `max_tokens`, `temperature`. Core sends its standard system instruction and the entire public ActRequest history in the user prompt. Only an explicit history-window choice reduces history. |
| Models | [Models](https://docs.reka.ai/chat/models) and [List Models](https://docs.reka.ai/chat/api-reference/list-models): authenticated `GET https://api.reka.ai/v1/models`, `data[].id` is authoritative for that account. The documentation lists `reka-flash-3`, `reka-edge-2603`, `deepseek4-flash`, `gemma4-26b`, `glm5.3`, `glm5.3-flash`, `qwen3.8-27b`; the developer reference also mentions `deepseek-v4-pro`. These lists can differ and change. Core does not infer a prefix, remove namespaces or replace retired names such as `reka-core`. |
| Response | One `choices[0].message` with role `assistant`, nonempty string `content`, and `finish_reason: stop` is accepted. `id`, response `model`, and `X-Request-ID` become sanitized receipt evidence. Missing identity remains null. The checkpoint field `metadata.weight_version` is documented but is not an authenticated build attestation and is not copied into receipts. |
| Reasoning | [Developer reference](https://developer.reka.ai/reference): `reasoning_effort` accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; it maps to model-specific tiers and has no effect on Reka Flash 3 or Edge 2603. Core forwards an explicit effort unchanged and lets the endpoint validate it. Omitted effort leaves provider defaults intact. No game selects reasoning policy. `reasoning_content` and the alternate `reasoning` trace are never action text or public receipt content. |
| Accounting | The developer reference specifies `usage.prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens` (also `completion_tokens_details.reasoning_tokens`). Reasoning is already included in completion tokens and is counted once. Standard `prompt_tokens_details.cached_tokens` is normalized when returned; absent cache/reasoning counts stay unknown. A total derived from reported input/output is labeled as derived. Invalid numeric counts, inconsistent totals or contradictory reasoning mirrors make usage explicitly unavailable. |
| Pricing | [Pricing](https://docs.reka.ai/pricing): current per-token rates are strings in `GET /v1/models` and can change. Discovery does not install a reviewed price card. No rate, dollar cost, cache discount or native cost is invented from a token count; cost remains unavailable without pricing evidence. |
| Errors | [Errors](https://docs.reka.ai/errors): OpenAI-shaped `error` envelope; 400 invalid request, 401 auth, 404 unknown model, 429 rate/capacity, 5xx server error. Core retains status/request ID, maps 403 to permission failure, and excludes raw error prose and credentials from receipts. |
| Retry | Reka recommends backoff for 429/5xx. Core's stricter existing policy defaults to zero retries and zero action repairs. Explicit retry permission applies only to a fully observed, unambiguous 429 rejection without work evidence. Null/conflicting classifiers, observed usage/response ID, timeouts, transport interruptions and 5xx are not automatically replayed. Each permitted retry has a separate receipt. |

The adapter omits `max_tokens`, reasoning controls and temperature unless chosen
explicitly. It adds no read or total thinking deadline. Existing shared connect,
write, cancellation and response-byte protections still apply. Reka documents a
per-model default output budget when `max_tokens` is omitted; provider ceilings
remain provider-owned.

The adapter rejects explicit `reasoning_budget_tokens` and
`gemini_thinking_budget` values, including zero and automatic-budget sentinels.
Configuration and live preflight reject those unsupported controls before model
discovery or inference; direct calls reject them before transport. An explicit
`reasoning_effort` remains an endpoint-validated choice.

Receipt redaction compares provider strings against the active credential and
known credentials configured in the process environment, including credentials
for other providers. Matching request, gateway, response and resolved-model IDs
become null; an erased model identity also loses its identity-source claim.
This applies to success, HTTP errors, malformed JSON and partial-body header
observations before receipt publication. Removing an echoed ID does not remove
the observation of work or make a rejection eligible for retry. Credential
material in action text is rejected before parsing or action repair. Credential
values are kept only in invocation-local memory for comparison. Credential-like
model IDs in discovery also fail closed before reaching CLI or preflight output.

Refusal/content-filter fields and truncation (`finish_reason: length`) are
classified before action parsing, retaining reported usage. Tool calls, unknown
finish values and malformed responses fail closed even if they contain a legal
looking action. Refusal fault cases use synthetic OpenAI-compatible envelopes;
the current Reka pages do not promise a distinct refusal payload.

## Offline verification

`tests/fixtures/provider/reka_chat_completions_success.json` preserves the
published Chat Completions envelope, with synthetic redacted IDs, action text,
reasoning and usage values. It combines the documented reasoning fields for
deterministic accounting checks. It is not a recorded live inference result.
`tests/test_reka_adapter.py` exercises aliases through CLI/configuration/live
preflight and dispatch, exact wire fields, full history, operator controls,
missing identity/accounting, reasoning privacy, refusal, truncation, malformed
bodies, HTTP 400/401/403/404/429/5xx, timeouts, transport errors and safe opt-in
retries. Regressions also cover missing model IDs, unsupported reasoning budgets
and primary/secondary credential echoes across success and failure paths.
HTTP error tests exercise the real bounded transport with an in-memory
HTTPX transport. All tests are keyless and do not contact Reka.
