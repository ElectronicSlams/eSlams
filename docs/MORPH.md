# Morph direct text inference

This adapter targets the 0.7.1 workstream; the package version remains 0.7.0.
Contract research was checked against official Morph documentation on 2026-11-10.
No credentials, paid inference, or live account access were used for verification.

## Suitability and sources

Morph now serves general open-weight chat models as well as specialized products.
The [general inference guide](https://docs.morphllm.com/general-inference) documents
ordinary text prompts through Chat Completions. The
[endpoint guide](https://docs.morphllm.com/endpoints) distinguishes general chat
models from Apply, WarpGrep and Compact. This establishes a suitable text-action
contract; it does not establish game quality or Official evaluation eligibility.

The existing frozen catalogue's Morph Apply entries were incorrectly marked as
game-capable. They are now excluded. `auto`, Fast Apply, WarpGrep, Compact, Reflex
and router identities are rejected by the text-action adapter. These products
merge code, search repositories, compress context, classify decisions, or select
another model. The adapter never executes tools or switches to one of them.

| Concern | Verified contract and implementation |
| --- | --- |
| Endpoint | `POST https://api.morphllm.com/v1/chat/completions`; raw HTTP through Core's existing bounded transport. |
| Authentication | `Authorization: Bearer <MORPH_API_KEY>` and JSON content type. Only the selected credential is sent; surrounding pasted whitespace is trimmed. Other configured credentials are read locally for redaction only. |
| Model | Explicit nonblank provider-native ID, preserved exactly. No alias expansion, default model, automatic routing or provider fallback. Unknown exact IDs may be submitted with native defaults; explicit reasoning controls require model-specific evidence. |
| Region | General inference uses shared pools behind the global endpoint. [Cache placement](https://docs.morphllm.com/sdk/components/caching) is best effort and may move regions. No region selector, stable physical backend or regional residency guarantee is established; the adapter makes no such claim. |
| Request | `model`, `messages` containing Core's common system instructions and the complete supplied observation/history prompt, `stream: false`. No tools, search, router, compaction, service-tier override or response-format control is added. |
| Limits | No Core output-token maximum, total timeout or read timeout by default. Only explicit operator/request output limits produce `max_tokens`; explicit operator deadlines use the shared transport. Existing connection and transport resource protections still apply. History-window truncation is rejected for Morph. |
| Response | A `chat.completion` object with one choice at integer index 0, assistant `message.content` string and `finish_reason: stop`. Refusal, truncation, tool calls, missing or malformed finish fields and ambiguous choice arrays fail before an action can be applied. |
| Identity | Only the response `model` can attest `locked_model_id`; absent, malformed or sensitive identity stays null. Requested identity is never substituted. `id` and safe request headers supply diagnostic IDs only. An explicit Core gateway override retains its gateway mode, without inventing model or region identity. |
| Usage | `usage.prompt_tokens`, `completion_tokens`, `total_tokens`; cached input from `prompt_tokens_details.cached_tokens`. Optional standard Chat Completions `completion_tokens_details.reasoning_tokens` is retained when returned; Morph does not promise its presence. Missing counters stay unknown and malformed counters retain validation errors. Shared derived totals are explicitly labeled `derived`. |
| Reasoning accounting | Morph documents reasoning as billed output. Normalized output includes reasoning; it is never added a second time. Absence of a reasoning counter is not evidence of zero reasoning. |
| Cost | No price estimate or measured charge is invented. No prices are copied from broker feeds or baked into this adapter. Native cost extensions are not treated as an attested bill. Account-specific rates and live billing remain unverified. |
| Errors | HTTP 400 request rejection, 401 authentication, 403 permission, 404 unavailable, 429 rate limit, 5xx unavailable; transport failures, malformed JSON and incomplete bodies retain safe receipts. HTTP-200 error bodies also fail. Provider error prose and private bodies are excluded. |
| Retry | Zero default retries and action repairs. Even if the caller enables retries, Morph failures are not automatically replayed without provider-specific proof that generation did not occur. `Retry-After` is retained as bounded receipt evidence; it is not permission to replay. |
| Credential containment | Selected and secondary configured credential substrings, URL/JSON encodings and recognized credential patterns are rejected in actions and cleared from receipt strings and IDs. Credential-named environment values (API keys, tokens, access/private keys, passwords, secrets and credentials) are used for local redaction only. An invocation-scoped snapshot survives environment rotation until receipts are published, then is released. Decoded action JSON, including ignored fields, is checked before action repair or returning. Success, error, malformed-body and interrupted-body paths use the same boundary. Discovery rejects an entire model list if any returned ID contains credential evidence, so partial results or redacted IDs cannot masquerade as a valid list. |

The [Open Source Models guide](https://docs.morphllm.com/sdk/components/fast-models)
and [official machine-readable index](https://docs.morphllm.com/llms.txt) establish
the general models and reasoning controls. The
[Apply reference](https://docs.morphllm.com/api-reference/endpoint/apply) supplies
Morph's shared Chat Completions response schema and error examples; its specialized
Apply request format is not used for general inference. The success fixture retains
that documented response envelope and token counters with a synthetic legal action.
The documented sample omits `model`, so the base fixture also omits it. Tests that
add response identity or reasoning detail fields are synthetic fault/compatibility
cases, not captured live traffic.

## Reasoning configuration

With `reasoning="auto"` and no effort, the adapter omits the control and leaves the
native model default intact. It never picks reasoning from the arena. Explicit
efforts are sent unchanged using `reasoning_effort`:

| Models | Accepted explicit string efforts |
| --- | --- |
| `morph-kimik31` | `none`, `low`, `medium`, `high`, `xhigh`, `max` |
| `morph-glm53-744b`, `morph-glm52-744b`, `morph-glm53flash` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` (per the official index) |
| `morph-dsv41flash`, `morph-dsv41flash-1017`, `morph-dsv41flash-abliterated` | `none`, `low`, `high`, `xhigh`, `max`; accepted aliases `minimal` → `low`, `medium` → `high` |

The November 10 model table now names Kimi K3.1 Pro as `morph-kimik31`.
Older `morph-kimik3`, `morph-kimik3-fast` and `morph-dsv4flash` IDs are no longer
advertised here as verified capabilities. They are not rewritten to a newer ID
or declared retired without evidence; explicit requests can still use unknown
native defaults. `morph-glm52-744b` remains in the official index, although absent
from the shorter Fast Models table. Availability remains account-unverified.

Morph documents rolling `kimi-latest` and `deepseek-flash-latest` aliases. Core
submits them literally without resolving or pinning them, and permits native
defaults only because their future reasoning controls are not pinned. A different
response `model` is recorded as returned; an absent one stays unknown. Use a
specific provider ID and an identity policy when a stable model is required.

Morph maps DeepSeek V4.1 `minimal` to `low` and `medium` to `high`; Core preserves
the caller's wire value. Morph also supports integer efforts on DeepSeek V4.1,
but Core's existing `reasoning_effort` contract is a string, so this adapter rejects
numeric strings instead of inventing integer or token-budget semantics.
`reasoning="disabled"` sends `none` only for a model with verified support.
`reasoning="enabled"` requires an explicit supported non-`none` effort; it cannot
promise enabled reasoning from a model's unknown default. Anthropic token budgets,
Gemini thinking budgets and OpenRouter route-order controls are rejected.

The uncensored model requires separate provider approval; documentation of its
wire contract does not grant account access. Catalogue records describe capability
evidence with account availability unknown and no pricing or Official eligibility.

## Usage

Configure only the desired credential in your own environment. Core does not
load `.env` files automatically. Offline preflight does not make network requests:

```bash
eslams providers preflight --provider morph --model morph-kimik31
eslams providers models --provider morph
eslams run --arena tic-tac-toe --agent morph:morph-kimik31 --out ./morph-run
```

The run command makes billable inference requests when credentials are configured.
`eslams providers models --provider morph --live` explicitly requests authenticated
[`GET /v1/models`](https://docs.morphllm.com/api-reference/endpoint/models).
`eslams providers preflight --provider morph --model morph-kimik31 --live` also
requests inference and may incur charges. Neither runs automatically. Model lists
may contain specialized products; appearing in discovery does not establish text
game support. No live command was run as part of this implementation.

Offline tests cover CLI/dispatch/preflight, exact payloads, reasoning controls,
full history, raw response parsing, identity, usage, costs, HTTP errors, timeouts,
malformed envelopes, actual interrupted/oversized transport reads and credential
echoes. These tests establish implementation behavior, not live availability,
regional placement, throughput, billing completeness or game quality.
