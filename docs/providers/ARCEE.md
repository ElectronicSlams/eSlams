# Arcee Platform adapter (0.7.1 candidate)

Research checked 2026-11-04 against official documentation. This adds a native
direct adapter without changing the package version from 0.7.0.

## Product, authentication and models

Use Arcee Platform, rather than Arcee Conductor, Orchestra, OpenRouter, or a
self-hosted vLLM server. Configure `ARCEE_API_KEY` in your environment. Core
sends it only as `Authorization: Bearer ...` with JSON content type. Arcee's
reference describes keys prefixed `rcai-`; Core validates credential safety
without imposing an undocumented fixed length or rejecting future key formats.
See [first API call](https://docs.arcee.ai/api-reference/your-first-api-call)
and [chat reference](https://docs.arcee.ai/api-reference/chat-completion).

Both [quickstart](https://docs.arcee.ai/get-started/quick-start) examples and
the first-call page use `https://api.arcee.ai/api/v1/chat/completions`.
The chat reference's generated schema instead says `/v1/chat/completions`.
The adapter follows the concrete quickstart URL; it never probes or falls back
to the alternate path after a failure. This discrepancy has not been resolved
by live inference.

Always specify an exact model ID. No default model is selected. The current
[pricing page](https://docs.arcee.ai/get-started/pricing) includes
`zai-org/glm-5.3-flash`; model availability is account-dependent and changes.
[Model discovery](https://docs.arcee.ai/api-reference/models) uses
`GET https://api.arcee.ai/api/v1/models`, with model IDs in `data[].id`.
Core preserves model strings, including case, slashes, colons and revisions.
Aliases `arcee`, `arcee-ai`, `arcee_ai` and uppercase spellings select the
canonical provider `arcee-ai` throughout CLI, preflight and dispatch.

```bash
eslams providers preflight --provider arcee-ai --model zai-org/glm-5.3-flash --arena tic-tac-toe
eslams run --help
```

For gameplay select `--agent arcee-ai:<exact-model-id>` on the run command.
Offline preflight checks configuration only. `providers models --live` performs
authenticated discovery; `providers preflight --live` additionally submits
inference and may incur charges. Neither was called against Arcee in this work.

## Request and completion policy

The request uses `model`, system/user `messages`, and `stream: false`. The user
message contains the full supplied public/agent-visible history by default.
Existing explicit history-window, timeout, temperature and output policies
remain operator choices. `max_tokens` is omitted unless explicitly chosen.
No arena chooses a reasoning policy. Shared safe HTTP transport keeps its
connect safeguard and has no default elapsed/read/output cap.

Accept only one `choices[]` entry with assistant text at `message.content` and
`finish_reason: stop`. Refusal/filter, length, tools, malformed/unknown finish
fields and HTTP-200 error envelopes fail with receipts; parseable partial
actions are never accepted. SDK convenience fields and reasoning-only output
are not action text. Core never substitutes a different model, provider or
endpoint. Arcee does not document a backend-pinning/fallback control here:
direct service selection is not proof of a fixed physical backend.

## Reasoning and accounting limits

The quickstart reads `message.reasoning_content`; the first-call page reads
`message.reasoning`. Both are treated as private response fields. The direct
request schema documents no reasoning effort/budget/enable switch. The adapter
uses native defaults, rejects explicit reasoning switches/budgets and routing
preferences before submission, and never copies self-hosted or OpenRouter
controls into this API.

Only response `model` attests resolved identity; absence remains null. Usage
normalizes standard `prompt_tokens`, `completion_tokens`, `total_tokens` and
optional detail counts through existing receipt validation. Reasoning inclusion
remains unknown unless explicitly reported; missing counts remain missing.
Catalogue/OpenRouter prices and undocumented `cost` fields cannot establish
direct billing. Cost stays unavailable without authoritative accounting.
The [usage API](https://docs.arcee.ai/api-reference/usage) reports organizational
daily/aggregate statistics, so Core does not use it to invent per-call charges.

## Errors, retries and evidence

The chat reference lists 400, 401, 402, 403, 404, 422, 429, 500 and 503 with
`detail` errors. Existing shared transport maps these into sanitized outcomes;
raw error prose, headers, keys, prompts and reasoning never enter receipts.
`Retry-After` is retained where supplied. Default retries and action repair are
zero. Even opted-in retries require shared proof of rejection before work;
a plain Arcee `detail` 429 is insufficient proof, and timeout/ambiguous work
is never automatically replayed. No retry timing guarantee is documented here.

`tests/fixtures/provider/arcee_chat_completions_success.json` instantiates the
documented OpenAI-compatible REST envelope with synthetic redacted identifiers,
counts and text. It is not a captured inference. Deterministic tests cover
success, errors, refusal, truncation, 429, malformed bodies, timeout, missing
identity/usage, unsupported controls, aliases, discovery and privacy. Live
availability, endpoint discrepancy, model reasoning behavior and actual charges
remain unverified. No paid request or provider credential was used.
