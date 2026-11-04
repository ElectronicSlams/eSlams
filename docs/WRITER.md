# Writer direct API adapter

For the planned 0.7.1 release; package version remains 0.7.0 in this change.
Verified against Writer's primary documentation on 2026-11-04. No credential
or paid inference was used to validate this adapter.

## Use

Export `WRITER_API_KEY` in your shell; Core does not load `.env` automatically.
Use `--agent writer:palmyra-x6` (or another exact account model ID). `writer-ai`
and `writerai` are Core aliases for the same direct Writer adapter. An explicit
nonblank model ID is required: bare `writer`, `writer:`, and whitespace-only
model IDs fail before transport. Model IDs, including slashes and colons, are
sent unchanged; no automatic migration or provider/model fallback occurs.

```bash
eslams providers preflight --provider writer --model palmyra-x6 --arena connect-four
```

This configuration check is offline and does not prove account access. Only
with separate permission to use credentials and incur inference charges, add
`--live` to discover account models and perform one inference. The model list
is advisory unless the caller requests strict catalogue policy.

## Verified contract

| Concern | Primary evidence and implementation |
| --- | --- |
| Endpoint/authentication | [Chat reference](https://dev.writer.com/api-reference/completion-api/chat-completion): `POST https://api.writer.com/v1/chat`, JSON, `Authorization: Bearer <key>`. [API keys](https://dev.writer.com/api-reference/api-keys) documents Models permissions and legacy-key retirement on December 1, 2026. |
| Models | [List models](https://dev.writer.com/api-reference/completion-api/list-models): `GET https://api.writer.com/v1/models`, bearer auth, `models[].id`; no pagination contract is documented for this endpoint. [Model overview](https://dev.writer.com/home/models-overview) lists X6 via API, while older examples still list X4/X5. It announces X4/X5 deprecation December 14, 2026. Account availability remains unverified without live discovery/inference. |
| Request | [Chat guide](https://dev.writer.com/home/chat-completion): `model`, `messages[]` with `system` and `user` roles; non-streaming `stream:false`. Core's public ActRequest prompt includes the complete supplied history by default. Optional `max_tokens` and `temperature` are sent only when the operator supplies them. No default output cap or elapsed/read timeout is introduced. Existing transport connect limits and bounded response bytes remain in effect. |
| Response | A `chat.completion` object with one `choices[0].message`, assistant role, string `content`, and a recognized `finish_reason`. Identity comes only from response `model`; absent model/response IDs stay unknown. |
| Completion | [Writer's OpenAPI-generated choice schema](https://github.com/writer/writer-python/blob/6e66089d6532945349c9cbf81a9d9966bfb834b8/src/writerai/types/chat_completion_choice.py) specifies `stop`, `length`, `content_filter`, `tool_calls`. Only complete text is eligible for action parsing. Refusal, filtering, truncation, tool calls and unknown/missing finish reasons cannot produce actions, even when content contains legal JSON. Usage receipts survive these failures; private refusal text does not. |
| Reasoning | The direct Chat request reference and [generated request schema](https://github.com/writer/writer-python/blob/6e66089d6532945349c9cbf81a9d9966bfb834b8/src/writerai/types/chat_chat_params.py) expose no effort/budget/enable/disable control. Core preserves native defaults; explicit reasoning controls fail in offline/live preflight before discovery or inference, and before submission when invoked directly. No game-dependent policy or reasoning prompt is added. |
| Usage | Top-level `usage.prompt_tokens`, `completion_tokens`, `total_tokens`; cached tokens under `prompt_token_details.cached_tokens`. The REST example uses `completion_token_details.reasoning_tokens`, while the [generated usage schema](https://github.com/writer/writer-python/blob/6e66089d6532945349c9cbf81a9d9966bfb834b8/src/writerai/types/chat_completion_usage.py) uses `completion_tokens_details`. Both are recognized without summing them; conflicting details are marked invalid. Neither source explicitly establishes reasoning inclusion, so it stays unknown. Provider totals are retained without adding reasoning a second time. |
| Errors | [Error reference](https://dev.writer.com/api-reference/error-codes): `tpe`, `errors[]` (`description`, `key`, `extras`), `extras`. Shared transport classifies HTTP status and sanitizes telemetry. Descriptions and raw responses never enter receipts. Unexpected error envelopes in HTTP 200 fail closed and do not attest model identity. |
| Retry | [Rate limits](https://dev.writer.com/api-reference/rate-limits) documents 429 and recommends slowing down/backoff. Core defaults to zero retries. Writer's documented error envelope does not prove no generation occurred; automatic replay remains disabled even with optional retries configured. `Retry-After` is recorded by shared transport. Timeouts and ambiguous transport failures are never replayed. |
| Cost/privacy | Writer Chat does not document response-level monetary cost. No native cost or rate card is invented; missing usage stays unknown. Reuse Core's sanitized receipts, cancellation, safe transport and operator-supplied gateway support. Tool payloads, reasoning, credentials, prompts, and raw private response/error text are excluded from public receipts. |

## Deterministic checks

`tests/fixtures/provider/writer_chat_success.json` follows the REST reference's
success envelope, with synthetic action text and no private data.
`tests/test_writer_adapter.py` tests aliases through CLI, registry, offline and
mock-live preflight, discovery, and dispatch; exact wire requests, full history,
operator controls, usage variants, missing identity/accounting, malformed JSON,
errors (400/401/403/404/429/500/503), refusal, truncation, timeout, transport
failure, no replay, and receipt privacy. Additional tests exercise raw success,
refusal, truncation, 429, 5xx, and oversized bodies through the real bounded
transport with a local mock, and verify failed generations never apply an
action or become scoring-valid in validated artifacts. All network traffic is
intercepted locally. Fixture success is evidence of parsing, not live service
availability or Official eligibility.

## Echoed-credential privacy

Writer snapshots the configured primary credential (including a custom key
environment) and other credential-named environment values for redaction only;
the snapshot is never emitted or sent to Writer. IDs containing known credentials
are discarded, leaving identity evidence unknown. Errors, malformed bodies and
partial-response receipts are scrubbed before publication. Discovery rejects
credential-containing model IDs and does not return a partial model list.
Action text containing a configured credential, including a JSON-escaped echo,
is rejected before action parsing or publication; its sanitized usage receipt
is retained. These protections do not request inference retries or action repair.
