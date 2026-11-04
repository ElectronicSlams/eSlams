# Native xAI provider

Research date: 2026-11-04. This adapter targets the direct Grok API documented
at `docs.x.ai`, whose current branding is SpaceX Super Intelligence (SpaceXSI).
It is independent of OpenRouter, Bedrock, Vertex AI, Microsoft Foundry, and
other distributors. A model author's name in a gateway catalogue does not
establish a direct API route. The native namespace is `xai`; `x-ai` is an alias
(case, surrounding whitespace and underscore spelling are normalized for xAI).
Model strings are passed unchanged, including aliases and unknown names.

## Configure and use

Export `XAI_API_KEY` from the xAI console into the process environment; Core does
not load `.env` automatically. Authentication is `Authorization: Bearer <key>`.
No new SDK or dependency is required. [Official quickstart](https://docs.x.ai/overview).

```bash
# Configuration only; no paid request or model discovery:
eslams providers preflight --provider x-ai --model grok-4.7 --arena tic-tac-toe
eslams providers models --provider xai
# Inference example: deliberately costs money when credentials are configured.
eslams run --arena tic-tac-toe --agent xai:grok-4.7
```

An explicit nonblank model ID is required in the agent, CLI and preflight. Bare
`xai`/`x-ai`, an empty suffix, null and whitespace-only IDs are rejected before
discovery or transport. An explicitly supplied model is never replaced. Catalogue records for `grok-4.7`
and `grok-4.6` document text Responses support; availability remains
account-dependent. Existing generated catalogue entries are historical, advisory
metadata, not proof of current access. No registry snapshot was regenerated.
The [models reference](https://docs.x.ai/developers/rest-api-reference/inference/models)
documents authenticated `GET https://api.x.ai/v1/models`: the adapter's explicit
live discovery reads its `data[].id`. Live preflight additionally makes an
inference call. Neither was called with credentials during development.

## Endpoint choice and message behavior

The adapter uses `POST https://api.x.ai/v1/responses`. The current
[Responses reference](https://docs.x.ai/developers/rest-api-reference/inference/responses)
recommends this interface for new integrations. We parse REST `output[]` items,
assistant messages and `output_text` content parts. Top-level SDK convenience
`output_text`, Chat Completions `choices`, unknown output types, unfinished
message items, tool calls and non-completed envelopes cannot supply an action.
Response model identity comes only from the response `model` field; missing
identity stays null. Request identity is retained separately.

[Chat Completions](https://docs.x.ai/developers/model-capabilities/legacy/chat-completions)
is still documented as legacy. It uses `messages`/`choices` rather than
`input`/`output`, and cannot return encrypted reasoning items. It is not a
fallback transport. Neither it nor the provider SDK is used by this adapter.

Each action sends a system instruction and a user message containing Core's
public observation, legal actions, action schema, memory policy and supplied
public history. History remains complete unless the operator explicitly chooses
Core's existing history window. `store: false` disables stored Responses
continuation; `truncation: disabled` avoids automatic context truncation.
[Text generation and storage](https://docs.x.ai/developers/model-capabilities/text/generate-text).

The adapter keeps no private conversational state or previous response IDs.
Reasoning summaries and encrypted content are ignored and never copied to
receipts. Core's full public game history is preserved, but encrypted model
reasoning is **not** carried to later actions. This limits the potential benefit
of xAI's recommended reasoning continuity; it also prevents retaining hidden
model state outside Core's existing history contract.

## Controls, schemas and tools

No framework output cap, total/read time cap, per-game reasoning selection,
model fallback or provider fallback is introduced. Explicit Core output limits
become `max_output_tokens`. Explicit effort becomes `reasoning.effort`;
otherwise xAI owns its default. `grok-4.7`/`grok-4.6` document low, medium, high
and xhigh; `grok-4.5` lacks xhigh. Reasoning cannot be disabled on these models;
Core's `reasoning="disabled"` does not promise to disable native reasoning.
Other names and explicit values remain subject to authoritative endpoint
rejection. Token-based thinking budgets are rejected by configuration-only and live
preflight before discovery, and by execution before submission.
The [reasoning guide](https://docs.x.ai/developers/model-capabilities/text/reasoning)
also documents encrypted reasoning and explains that 4.7 returns it by default.

Explicit temperature is forwarded. The Responses reference documents server-side
sampling caps, so an echoed temperature is not proof of the effective sampler.
There is no presence/frequency penalty, stop override, service-tier override,
search, code execution, MCP, file attachment, streaming or asynchronous polling.
The normal Core connect timeout remains a transport constraint.

xAI documents [structured outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs)
and strict function schemas with a supported JSON Schema subset. Core accepts
arbitrary arena action schemas and validates legal actions locally. This adapter
uses Core's existing JSON prompt and action parser rather than claiming every
arena schema is supported by xAI's schema subset. No schema or tool definition is
sent. The [function-calling guide](https://docs.x.ai/developers/tools/function-calling)
describes a separate execution loop, which this game adapter does not implement.

## Usage, cost and uncertainty

Current Responses usage uses `input_tokens`, `output_tokens`, `total_tokens`,
`input_tokens_details.cached_tokens` and
`output_tokens_details.reasoning_tokens`. Cached input is a subset of input.
Missing or invalid counters are never converted to zero. Core's validators
retain malformed/inconsistent usage diagnostics.
[Usage and pricing](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing).

The current usage examples contain zero reasoning tokens. An older example in
the Responses REST reference instead uses `prompt_tokens: 32`,
`completion_tokens: 9`, reasoning 110 and total 151: reasoning is excluded from
that completion counter. We support that legacy envelope with exclusion marked
false. We deliberately leave inclusion unknown for current input/output-shaped
usage. Nonzero reasoning therefore carries `reasoning_inclusion_unknown`. Current-shape
usage cannot establish complete accounting/Official eligibility because Core
requires a known inclusion flag even when reasoning is zero. Live preflight
therefore reports `readiness.usage_complete: false` for current-shaped usage
while a legal action can still satisfy advisory readiness. Provider totals are
retained without guessing inclusion or silently double-counting reasoning.

`usage.cost_in_usd_ticks` is the documented billed request cost after discounts,
including token and server-side tool charges. Only a nonnegative integer is
accepted; one USD is 10,000,000,000 ticks. Core's existing USD float receipt field
holds the converted amount and a native-cost provenance reference. A reported
zero is accepted; an absent/invalid cost is unavailable, not zero. No static
catalogue price estimate is substituted. [Cost tracking](https://docs.x.ai/developers/cost-tracking).

[Pricing](https://docs.x.ai/developers/pricing) varies with model, long-context
thresholds, caching, tier and region. Grok 4.7 Fast is not a public API model.
The adapter uses the global endpoint only. The documented US endpoint
`https://us.api.x.ai/v1` currently serves 4.7/4.6 with a 10% token premium and has
specific processing/storage guarantees and exclusions. There is no region flag
or automatic region switch in this adapter. Existing Core gateway URL rewriting
is preserved; an operator using it owns routing and residency, and discovery
still uses the global endpoint. [Regional endpoints](https://docs.x.ai/developers/advanced-api-usage/regions).

## Errors, retry and receipts

Core's existing bounded transport, cancellation, strict JSON decoding, concurrency
and explicit deadline controls apply. HTTP 400/422 are request rejection, 401 is
authentication failure, 403 permission failure, 404 unavailable, 429 rate limiting
and 5xx unavailable under Core's error taxonomy. xAI's
[error guide](https://docs.x.ai/developers/debugging) documents causes; its native
string error body is never published. HTTP-200 error envelopes are rejected too.
Refusals, truncation, cancellation and pending/incomplete results retain usage
and sanitized finish metadata without applying legal-looking partial actions.

Default retries and action repairs remain zero. Explicit safe retries use Core's
existing conservative rule: only a verifiable 429 rejection without response ID,
usage or cost/work observations may be replayed. Ambiguous timeout, transport,
5xx, malformed output and accepted work are never retried automatically.
Non-2xx error-body observations remain quarantined, not trusted billing/model evidence.
Credentials, headers, prompts, refusal prose, reasoning and raw private responses
are absent from public receipts. Every physical attempt keeps Core's existing
invocation-scoped receipt and action ID behavior.

Credential-aware redaction snapshots the selected primary credential and configured
secondary credential environment values for each xAI invocation and discovery.
Identifiers containing a known credential remain unknown rather than attesting a
redacted ID. Explanations and action-text metadata are scrubbed after JSON decoding,
including escaped strings; a credential inside the selected action is rejected.
Malformed/partial response headers and private exception chains receive the same
protection. Context-local scopes reset on every exit and do not change unrelated
provider behavior. Raw work observations are classified before redaction, so
removing a credential-bearing ID never makes an ambiguous attempt retryable.

## Fixture provenance and verification

`tests/fixtures/provider/xai_responses_success.json` is a synthetic, redacted
fixture of the documented raw Responses envelope; it is not a captured live
response. Message structure follows the Responses reference's raw `response.body`
example. Usage follows the current usage guide; the native tick field follows
the cost guide. The harmless action text, IDs, model and encrypted placeholder
are substitutions. Failure mutations are deterministic fault injection.

`tests/test_xai_provider.py` intercepts every inference/discovery call. It covers
alias paths, payload/history, explicit controls, credential checks, missing
identity/usage/cost, current and legacy accounting, refusal/truncation/pending,
malformed JSON and output, HTTP and transport failures, safe retry and ambiguous
work, and an artifact round trip with no truncated action applied.
`tests/test_xai_integrity_audit.py` adds model/control rejection, primary/secondary
credential echoes across success/errors/discovery/partial responses, escaped action
text, concurrent redaction scopes and full artifact privacy regressions.

Integration hotspots for parallel adapters: `agents.py` dispatch, endpoint/parser
maps, native-cost provenance and usage routing; `provider_preflight.py` maps;
`cli.py` provider defaults; planning credential names; registry aliases and additive overrides;
`.env.example`, changelog and docs index. Preserve each provider's insertion and
rerun checks after combining branches. No version, public schema, arena behavior
or generated registry snapshot changes are included.
