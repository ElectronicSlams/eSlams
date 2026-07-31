# Provider Guide

eSlams Core 0.6 has native, secret-free artifact support for OpenAI,
Anthropic, Google Gemini, OpenRouter, and Amazon Bedrock. The adapters call raw
HTTP APIs; their parsers are pinned to documented REST envelopes rather than SDK
convenience properties.

## Provider Matrix

| CLI agent | Credential environment variable | Endpoint contract | Response text path | Model identity evidence |
| --- | --- | --- | --- | --- |
| `openai:<model>` | `OPENAI_API_KEY` | Responses | typed `output[].content[]` `output_text` parts | response `model` |
| `anthropic:<model>` | `ANTHROPIC_API_KEY` | Messages | `content[]` text blocks | response `model` |
| `gemini:<model>` | `GEMINI_API_KEY` | `generateContent` | `candidates[].content.parts[]` text | `modelVersion` |
| `openrouter:<vendor/model>` | `OPENROUTER_API_KEY` | Chat Completions | `choices[0].message.content` | response `model` |
| `bedrock:<model-id>` | `AWS_BEARER_TOKEN_BEDROCK` | Converse | `output.message.content[]` text | explicitly pinned endpoint model |

An absent provider model identity remains `null`. Core never copies the
requested model into `locked_model_id` as if it came from the response. Bedrock
is the deliberate exception: the literal model ID is part of the signed
Converse endpoint and is recorded with `model_identity_source:
pinned_endpoint`.

## Setup and Preflight

Set only the credential needed by the selected provider:

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export OPENROUTER_API_KEY=...
export AWS_BEARER_TOKEN_BEDROCK=...
```

Registry-only preflight is offline and checks local metadata, Arena creation,
and legal-action availability:

```bash
eslams providers preflight \
  --provider openai \
  --model gpt-5-mini \
  --arena tic-tac-toe
```

Its `preflight_mode` is `registry_only`. It does not prove account visibility
or live invocation.

Live preflight adds account model discovery where the provider exposes a Models
API, one bounded inference, legal-action parsing, and normalized usage
extraction:

```bash
eslams providers preflight \
  --provider openai \
  --model gpt-5-mini \
  --arena tic-tac-toe \
  --live

eslams providers models --provider openai --live
```

Review every live check. A missing Models API is reported separately and does
not fabricate account visibility.

## Running Each Adapter

```bash
eslams run --arena tic-tac-toe \
  --agent openai:gpt-5-mini --opponent first-legal

eslams run --arena tic-tac-toe \
  --agent anthropic:claude-sonnet-4-20250514 --opponent first-legal

eslams run --arena tic-tac-toe \
  --agent gemini:gemini-2.5-flash --opponent first-legal

eslams run --arena tic-tac-toe \
  --agent openrouter:openai/gpt-5-mini \
  --openrouter-provider-order "Amazon Bedrock" \
  --opponent first-legal

eslams run --arena tic-tac-toe \
  --agent bedrock:amazon.nova-micro-v1:0 \
  --bedrock-region us-east-1 \
  --opponent first-legal
```

OpenRouter sends `allow_fallbacks: false` whenever a provider order is present.
Official plans should pin a route and verify the returned model. Bedrock model
IDs retain a literal colon such as `:0`; the CLI splits `provider:model` on the
first colon and the adapter does not percent-encode the version separator.

## Reasoning Controls

Use `--reasoning disabled`, `enabled`, or `auto`.

- OpenAI sends only reasoning effort declared by the capability registry.
- Anthropic manual thinking requires at least 1,024 budget tokens and a budget
  below `max_tokens`; it uses the required temperature behavior. Claude 4.7+
  and Claude 5 use adaptive thinking and omit manual budget/temperature fields.
- Gemini sends `thinkingConfig` only when the registry says the model accepts
  it and a budget is configured.
- OpenRouter and Bedrock do not receive invented reasoning controls. Their
  provider/model-native behavior is preserved unless a supported contract is
  explicitly added to the registry and adapter.

`auto` enables optional reasoning only for configured Arena families and known
capabilities. The exact effective control is visible in registry metadata; do
not infer it from a model name in official infrastructure.

## Failure and Retry Semantics

Stable provider failures include transport, request rejection, response-schema
mismatch, auth, permission, rate limit, timeout, and unavailability. Action
parsing, legality, and Arena-apply failures have separate classes. Every class
makes the case unscoreable under the fail-closed defaults.

`interactive` runs may opt into deterministic fallback, but every fallback is
recorded as `fallback_action` and permanently invalid for scoring. The
`official_eval` profile rejects fallback policies and nonzero adapter
`max_retries`; whole-case retries belong to the official orchestrator and must
increment `case_attempt_index`.

An action repair is a second physical request with
`attempt_kind: action_repair`. It never overwrites the primary attempt receipt.

## Usage and Cost

Receipts normalize input, cached input, cache read/write, output, reasoning, and
total tokens. `reasoning_included_in_output` is explicit. Inclusive reasoning
is not added or billed twice; separate reasoning is added and priced once.
Provider-reported totals are preserved and validated against the canonical
derivation. Negative, non-finite, missing, or incoherent usage makes the run's
usage incomplete.

OpenRouter's native `usage.cost` is retained with a deterministic provider-cost
contract reference. Registry pricing can estimate other providers, but an
officially complete cost also requires a reviewed, hashed
`eslams.price-card-reference.v1` matching the provider and model:

```json
{
  "schemaVersion": "eslams.price-card-reference.v1",
  "rateCardId": "openai-reviewed-2026-07-31",
  "rateCardHash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "provider": "openai",
  "model": "gpt-5-mini",
  "currency": "USD",
  "sourceUri": "https://example.invalid/reviewed-rate-card.json",
  "effectiveAt": null,
  "retrievedAt": null,
  "complete": true
}
```

Pass the JSON file with `--rate-card-reference`. `--rate-card-id` alone is a
diagnostic label and cannot make cost complete.

## Secrets and Diagnostics

Artifacts and public events never store credential values, authorization
headers, prompts, hidden observations, or raw private provider responses.
Provider error output is bounded and redacted. Full sanitized diagnostics are
written to the exact artifact path printed by the CLI.

After a run:

```bash
eslams validate runs/latest.eslams --profile runner-bundle
eslams replay runs/latest.eslams
```

For an official case, use `--profile official-case`. A signature is necessary
but not sufficient: fallback, agent errors, route mismatch, incomplete
usage/cost, or a broken trace/replay/receipt join still fails validation.
