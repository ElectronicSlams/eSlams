# Native Cohere adapter (proposed for 0.7.1)

QA correction checked 2026-11-10: final text containing known credentials is
rejected before action parsing, repair or retry. Raw text and decoded JSON
keys/values are checked; clean answer bytes remain unchanged. Receipt sanitation
does not authorize replacing a completed model action with redacted JSON.
The thinking-ID allowlist below records models verified against official model
pages; it is not a complete Cohere catalogue or a prediction about future IDs.

Research checked 2026-11-04. This implements Cohere Platform's native API,
not a model-author inference guess or an OpenRouter backend. Source version is
Core 0.7.0; the package version and generated catalogue remain unchanged.

## Configuration and identity

Export `COHERE_API_KEY` explicitly; Core does not load `.env`. Authentication is
`Authorization: Bearer <key>`. Inference uses
`POST https://api.cohere.com/v2/chat`, with `stream: false`. The official
[API reference](https://docs.cohere.com/v2/reference/chat) specifies the native
message and response shapes. The official Python SDK's
[production environment](https://github.com/cohere-ai/cohere-python/blob/f2decac2515eab6b21c7e980f63d399df229b670/src/cohere/environment.py)
confirms the host; this adapter adds no SDK dependency.

The canonical Core namespace is `cohere`. The local convenience alias
`cohere-ai` (including case/underscore normalization) resolves to the same
namespace in registry lookup, CLI construction, configuration/live preflight,
discovery, dispatch, and receipts. This alias is a Core convention, not an API
model alias. An explicitly supplied model string is forwarded verbatim.
Missing, blank, and non-string model IDs fail before transport, including bare
`cohere` and `cohere:` CLI agents. There is no default model or provider fallback.

```bash
eslams providers preflight --provider cohere-ai --model command-a-03-2025 --arena tic-tac-toe
eslams providers models --provider cohere --live
# --live preflight also submits one real, potentially billable inference:
eslams providers preflight --provider cohere --model command-a-03-2025 --arena tic-tac-toe --live
eslams run --arena tic-tac-toe --agent cohere:command-a-03-2025 --opponent first-legal
```

Configuration-only preflight submits no requests. The implementation was tested
with keyless fixtures only; no account availability or paid behavior is claimed.

## Models, endpoints, and regions

The official [model catalogue](https://docs.cohere.com/docs/models) currently
lists native Chat models including `command-a-plus-05-2026`,
`command-a-03-2025`, `command-r7b-12-2024`, and
`command-a-reasoning-08-2025`. These are examples, not an adapter allowlist or
account-access guarantee. Text chat is the supported scope. Embed, Rerank,
Parse, audio, image inputs, and specialized translation quality are outside
this adapter. A registry row is advisory by default; strict catalogue policy
remains opt-in and uses the existing snapshot without regeneration.

Explicit live discovery uses
[`GET /v1/models`](https://docs.cohere.com/reference/list-models), filtered by
`endpoint=chat`, with `page_size=1000`. It reads `models[].name` and follows
`next_page_token` using `page_token`. Malformed pages, repeated/invalid cursors,
HTTP failures, or exceeding Core's existing 20-page discovery convention fail
without presenting a partial list as complete. Discovery is advisory unless
strict catalogue policy is requested; it is not proof that inference will work.

This adapter uses the shared Cohere Platform endpoint and makes no residency
claim. [Deployment options](https://docs.cohere.com/docs/the-cohere-platform)
distinguish Platform, dedicated Model Vault, cloud AI services, and private
deployments. Model Vault has region-specific dedicated infrastructure; Azure,
Bedrock, SageMaker, and Oracle have distinct authentication/model names and
availability. They are not inferred from a Cohere model name or silently routed
through this adapter. Existing explicit Core gateway configuration forwards
`/v2/chat`; operators must supply a compatible gateway. Discovery targets the
public Cohere Platform host, as for other Core public discovery clients.

## Messages, schemas, tools, and thinking

The request contains a system message with Core's action instructions and a user
message containing the existing serialized public observation, legal actions,
action schema, and history. Full supplied history is retained by default;
an explicit Core history window remains an operator choice.

The adapter requests ordinary text containing JSON and uses Core's existing
legal-action parser. It does not enable `response_format`, tools, documents,
citations, or streaming. Cohere's [structured output guide](https://docs.cohere.com/docs/structured-outputs)
documents model-specific JSON/schema support and restrictions when combined
with tools/documents. Core does not claim universal schema enforcement.
Cohere's [tool protocol](https://docs.cohere.com/docs/tool-use-overview) requires
assistant tool calls and matching tool messages; Core never executes those
tools. Unsolicited tool calls are rejected even if accompanied by legal-looking
text. Only typed final text blocks supply an action.

[Thinking](https://docs.cohere.com/docs/reasoning) is left at the provider's
native default in `auto` mode. Explicit enabled/disabled choices map to
`thinking.type`; a positive explicit reasoning budget maps to
`thinking.token_budget` with type enabled. Explicit thinking controls require
the exact documented `command-a-reasoning-08-2025` or
[`command-a-plus-05-2026`](https://docs.cohere.com/docs/command-a-plus) ID.
Unknown aliases/models may still use native defaults, but explicit controls
require independent verification first. Zero budgets and unsupported effort
or Gemini-specific controls fail both preflight modes and before submission.
Thinking blocks are ignored
for action parsing and excluded from receipts and response metadata. No arena
selects a reasoning mode. Account availability remains an endpoint decision.

`max_tokens` is omitted by default, preserving the provider's model-specific
output ceiling. Only a positive operator output limit sends that parameter.
Temperature is forwarded only when supplied. Core imposes no new generation
deadline; the existing connection timeout, explicit deadline, cancellation, and
bounded response transport remain in force.

## Completion, failures, and retry

The raw uppercase finish enum is verified against the official SDK's
[API-generated type](https://github.com/cohere-ai/cohere-python/blob/f2decac2515eab6b21c7e980f63d399df229b670/src/cohere/types/chat_finish_reason.py).
`COMPLETE` and `STOP_SEQUENCE` permit final-text parsing. `MAX_TOKENS` becomes
`provider_output_truncated`; `TOOL_CALL` is rejected; `ERROR` is unavailable;
`TIMEOUT` is timeout. Missing/unknown/malformed completion fields or content
blocks fail closed. Valid-looking partial actions are never accepted.

The shared transport handles invalid JSON, duplicate fields, nonfinite values,
bounded bodies, and transport failures. HTTP 200 error envelopes cannot supply
an action. Cohere's documented ordinary refusal is not accompanied by a
dedicated refusal discriminator in Chat v2: refusal prose fails action parsing
without an invented refusal classifier or copying private prose to receipts.

The official [errors reference](https://docs.cohere.com/reference/errors) and
Chat endpoint document authentication, access, validation, rate limit, token,
cancellation, and service errors. Core classifications are retained for 400,
401, 403, 404, 422, 429, and 5xx; Cohere's 498 invalid-token and 499 cancellation
map to authentication failure and cancellation respectively.

Retries and action repair default to zero. Existing transport, cancellation,
rate/concurrency controls, and attempt receipts are reused. Cohere native
errors contain a `message` string: neither that prose nor an undocumented
gateway error proves no work was accepted. This adapter therefore permits no
automatic transport retry, including when `max_retries` is nonzero. Timeouts,
5xx, truncation, tools, and incomplete output are never replayed. Existing
explicit action repair remains a separate physical attempt after invalid final
action text; it is not fallback and remains prohibited by official-run policy.
Headers such as request ID and Retry-After are sanitized by shared machinery;
credential values and private error bodies are not published. Scrubbing covers
the active custom credential, `COHERE_API_KEY`, and the SDK's `CO_API_KEY`,
including identifiers, malformed/partial-response receipts, and final action
text before parsing or metadata capture. JSON-escaped and URL-encoded echoes
are covered. `CO_API_KEY` is a redaction source only; Core does not silently
select it for authentication. Discovery rejects credential-bearing model names
or cursors without returning partial results or inventing replacement IDs.

## Usage, pricing, and integrity limits

The documented [raw response](https://github.com/cohere-ai/cohere-python/blob/f2decac2515eab6b21c7e980f63d399df229b670/src/cohere/v2/types/v2chat_response.py)
contains a reply `id`, not an attested served model ID. `locked_model_id` and
`model_identity_source` remain null, even if an unverified `model` extension is
present. The requested model is preserved separately. A successful action is
not an official identity attestation; existing integrity gates remain unchanged.

[Cohere billing semantics](https://docs.cohere.com/docs/how-does-cohere-pricing-work)
distinguish processed `usage.tokens` from `usage.billed_units`. Canonical input
and output counts come only from `tokens`; their total is derived only when
both are present. Billed input/output counts are retained separately in the
normalized usage diagnostics. Billed-only observations never fabricate
processed usage. Missing values stay null, zero stays zero, and malformed
counts get validation errors. This adapter does not infer a reasoning-token
breakdown, reasoning inclusion, or cache billing policy.

Monetary cost remains `cost_unavailable`; catalogue rates are not applied to
processed tokens or treated as account charges. [Pricing](https://cohere.com/pricing)
separates input/output token rates, free limited trial usage, paid production
usage, and dedicated infrastructure pricing. Account terms and served identity
are not verified here. The [rate-limit documentation](https://docs.cohere.com/docs/rate-limits)
also distinguishes trial/production keys and model-dependent limits; no fixed
requests-per-minute value is invented in the adapter.

## Fixture provenance and review

`cohere_chat_success.json` preserves the documented v2 REST envelope; reply
content and counts are synthetic game-action data. `cohere_chat_thinking.json`
uses the documented typed thinking/text union. `cohere_models.json` preserves
the documented native list/pagination envelope. `cohere_rate_limit.json` uses
the documented native error shape. Tests mutate these fixtures for failures;
none are captures of paid or credentialed requests.

`tests/test_cohere_provider.py` verifies canonical/alias CLI and live preflight,
exact requested IDs, full history, default/explicit controls, thinking privacy,
all finish outcomes, malformed/truncated bodies, HTTP 200 errors, native HTTP
failures, timeouts, redaction, usage/identity gaps, pagination, and runner
receipt/artifact validation. Run with the declared dev dependencies:

```bash
python -m pytest tests/test_cohere_provider.py
python -m ruff check .
python -m mypy src
```

Shared integration points are insertion-sized changes in `agents.py`,
`provider_preflight.py`, CLI defaults/construction, registry aliases,
`.env.example`, and documentation links. Other adapter branches may conflict
at those map/import insertions; combine entries without changing namespaces,
dispatch, or zero-retry policy. Revalidate the actual integrated commit.
