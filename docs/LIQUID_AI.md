# Liquid AI direct text adapter (0.7.1 candidate)

Verified 2026-11-04 against Core base `270a863d10d57a0953f21924f1a0dd50159e6cf1`.
The package version remains 0.7.0. No paid inference or account access was used.

## Service and identity

[Liquid's API page](https://www.liquid.ai/api) establishes an operator-hosted
generative text service. [Pricing](https://www.liquid.ai/pricing) separately
identifies Liquid Console, OpenRouter and Vercel billing paths. Local weights,
LEAP, llama.cpp, vLLM, Ollama, Modal and Baseten deployments do not establish
the contract for Liquid's hosted endpoint.

The existing registry alias `liquid` resolves to canonical `liquid-ai`.
Its 90-organization catalog contains Liquid's organization but no direct Liquid
model rows. Its four Liquid-related model rows are under `kilo`, `nano-gpt`,
`pioneer` and `togetherai`. Their IDs and capabilities are not transferred to
Liquid. In particular, `liquid/lfm-2-24b-a2b`, `LiquidAI/LFM2-24B-A2B` and
`lfm2.5-24b-a2b` are not interchangeable IDs.

The official [API model list](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/models.mdx)
documents `lfm3-1.7b` and `lfm2.5-24b-a2b` among generation models. Access
depends on the account; the adapter also accepts an explicit unlisted ID.
Returned model identity is recorded as supplied, never inferred from the
request. A different returned ID rejects the action; an absent ID remains null.
Neither an ID nor this adapter attests immutable weights, quantization or a
physical serving backend.

## Authoritative contract

The web documentation index omitted the API section during this check. Liquid's
linked official documentation repository includes it, pinned here for review:

- [Reference and bearer authentication](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/reference/overview.mdx).
- [Raw request/response OpenAPI document](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/openapi.json).
- [Text generation, history and usage](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/guides/text-generation.mdx).
- [Errors](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/reference/error-codes.mdx)
  and [rate limits](https://github.com/Liquid4All/docs/blob/09ef69be5c92a4d375ee65f3558debc83b8922d1/api/reference/rate-limits.mdx).

The adapter posts to `https://api.liquid.ai/openai/v1/chat/completions`, with
`Authorization: Bearer $LIQUID_API_KEY`. The reference specifies one host;
regional endpoint selection and physical processing location are unverified.
No region or residency claim is made. Gateway rewriting is rejected.

The request contains the exact caller model, system instructions and the full
Act request history in the user prompt, with `stream: false`. Optional operator
temperature and output limit map to `temperature` and `max_tokens`. Neither is
added by default. No tools, search, fallback, sampling preset or total/read
deadline is added. Shared transport retains its connect/write safety limits,
bounded response reader, cancellation and any explicit operator deadline.

Only a complete assistant text choice ending in `stop` is accepted. Refusal,
truncation, tool requests, model mismatch and malformed envelopes fail closed.
Hosted reasoning controls and reasoning-token inclusion are not established by
the reference. Only native-default (`reasoning="auto"`) is accepted; explicit
reasoning switches, effort and budgets fail before submission. Local model
chat-template settings are not assumed to work on the hosted API.

Observed prompt, completion and total counts are normalized; absent counts stay
unknown. Unreported reasoning and cache counts are never zero-filled. Finite
nonnegative `usage.cost` is preserved as reported USD cost, with Liquid source
provenance. No price card or accounting-completeness claim is invented. Static
pricing is not inferred from marketing prices.

HTTP errors retain Core's classifications and sanitized attempt receipts.
Liquid documents 400/401/402/403/404/413/422/429/499/502/503/504 and an OpenAI-style
error envelope. Core deliberately applies a stricter replay rule than Liquid's
general retry advice: zero default retries; an explicit retry requires a
definitive rate rejection without work evidence and honors `Retry-After`.
Timeout, interrupted body, ambiguous errors and observed work are not replayed.
Credential echoes are removed from receipt values and rejected in action text,
including URL-encoded and JSON-escaped values. This covers the credential selected
by `api_key_env` and the standard `LIQUID_API_KEY` when both are configured.
No raw provider error prose is published. Provider-name normalization is applied
before validation, so `liquid_ai` cannot bypass preflight's model/reasoning checks.

## Use and validation

```bash
eslams providers preflight --provider liquid-ai --model lfm3-1.7b --arena tic-tac-toe
eslams run --arena tic-tac-toe --agent liquid-ai:lfm3-1.7b --opponent first-legal
```

The first command is configuration-only. The second needs an operator-provided
`LIQUID_API_KEY` and may incur charges. Neither was run against Liquid here.
`liquid:<exact-model>` is an alias; missing or blank model IDs are rejected.
Models discovery is not implemented; live preflight reports discovery as
unverified and only invokes inference when explicitly requested.

`tests/fixtures/provider/liquid_chat_success.json` derives from the pinned
OpenAPI 200 example: `$MODEL_ID` becomes `lfm3-1.7b`, and greeting content becomes
`{"action":0}`. All other fields are preserved. Fault cases are synthetic
mutations of that envelope, not claims of captured production traffic.
`tests/test_liquid_provider.py` covers CLI/preflight/dispatch, full history,
identity, usage, costs, safe retry, HTTP errors, malformed JSON and actual
bounded-reader partial failures with credential-echoing headers.
