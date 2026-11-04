# Apodex direct Core adapter

Candidate for 0.7.1; researched 2026-11-04 on Core 0.7.0. No paid requests or
account credentials were used. Examples below are instructions for an operator,
not live validation evidence.

## Operator contract

[Core Models](https://platform.apodex.ai/docs/models) documents
`POST https://api.apodex.ai/v1/chat/completions`, text messages, and exactly
`apodex-1.1` / `apodex-1.1-mini`. The adapter selects `stream: false`, sends the
requested ID unchanged, and parses assistant text from `choices[0].message.content`.
Reasoning is native and included in the output budget; its private
`reasoning_content` never becomes action text or a receipt.

Apodex's Core models have no server-side tool loop. Deep Research/Solve/Discover
IDs select a different, tool-running service on the same path, so this adapter
rejects them. Non-streaming has genuine operator constraints: 32,768 maximum
tokens and approximately 600 seconds at the gateway. Streaming is not implemented.
Core imposes no default generation deadline or output maximum; explicit maxima
are passed unchanged and may be rejected by the endpoint.

The response `model` attests identity; absence stays null, and a different model
fails closed. Usage maps prompt/completion/total and cached prompt tokens. Missing
breakdowns stay unknown. A derived total is labeled as derived; no cost is invented.

[Authentication](https://platform.apodex.ai/docs/authentication) specifies an
account API key in `Authorization: Bearer …`. Supply it through `APODEX_API_KEY`.
The published endpoint has no documented regional selector or residency guarantee;
the adapter makes no geographic claim and offers no region override.

## Errors and retries

[Core error documentation](https://platform.apodex.ai/docs/models) describes real
HTTP 400/401/402/429 errors; gateway 504 can carry HTML. The adapter reuses the
bounded transport and classifies HTTP errors, malformed JSON and partial responses
without exposing raw bodies. Truncation, refusals, unexpected tool calls and unknown
finish reasons fail before action acceptance. Safe telemetry remains in receipts.

[Rate limits](https://platform.apodex.ai/docs/rate-limits) are account-wide
concurrency/TPM limits. HTTP 429 carries `Retry-After` in seconds and rate-limit
headers. A complete documented rate rejection precedes generation. Core defaults
to zero retries. Only caller-enabled retry of a complete, unambiguous rate rejection
is eligible; observed work or an incomplete response vetoes replay. Timeout,
transport failure and HTTP 5xx never automatically retry. Caller cancellation and
explicit deadlines still apply.

## Routing and self-hosting

This adapter contacts Apodex's operator domain. It rejects gateway overrides and
OpenRouter routing settings. Third-party router credentials, endpoints and billing
are separate contracts; an Apodex author namespace does not establish a direct API.

The [official model card](https://huggingface.co/apodex/Apodex-1.1-mini)
also supplies downloadable weights and SGLang/vLLM deployment examples. Those
self-hosted servers use deployment-specific endpoints, controls and identity
evidence. The weight ID `apodex/Apodex-1.1-mini` is not the hosted API ID
`apodex-1.1-mini` and is rejected here.

## Use and validation

Choose the full ID; `apodex` and `apodex:` do not choose a default model:

```bash
eslams providers preflight --provider apodex --model apodex-1.1-mini
eslams run --help
# After configuring your own credential and authorizing paid inference:
eslams run --arena connect-four --agent apodex:apodex-1.1-mini --opponent first-legal
```

Offline preflight only checks configuration. The frozen catalogue has no Apodex
entry, so strict catalogue mode rejects it; account visibility remains unverified
until an operator explicitly requests live discovery/preflight. Live discovery uses
`GET /v1/models` and bearer auth. It does not run automatically during agent calls.

`reasoning=auto` and `enabled` retain native reasoning. Disabling reasoning or
supplying effort/budget/Gemini controls is rejected before submission. Default
history includes everything supplied to the request. An explicit history window,
output limit or deadline remains an operator choice.

`tests/fixtures/provider/apodex_chat_completions_success.json` follows the official
non-streaming example envelope; only content/reasoning text is replaced for game
and privacy assertions. Faults are synthetic, not recorded service outcomes.
`tests/test_apodex_provider.py` covers raw HTTP bytes via MockTransport, CLI,
mocked live preflight/discovery, native defaults, errors, retry, identity, usage,
reasoning privacy and exact credential echoes, including JSON-escaped action text.
No credentials, headers, prompt bodies or private reasoning enter public receipts.
