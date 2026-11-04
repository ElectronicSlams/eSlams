# Sarvam direct inference (proposed 0.7.1)

Use `sarvam:sarvam-105b` or `sarvam-ai:sarvam-105b-conversations` with
`SARVAM_API_KEY`. `sarvam_ai` is also accepted. The prefix selects the direct
provider; the model string after the first colon is sent unchanged, including
unknown or deprecated IDs. The default model for a bare Sarvam prefix is
`sarvam-105b`. No model substitution, broker routing or provider fallback occurs.
Package version remains 0.7.0 pending release review.

```sh
eslams providers preflight --provider sarvam --model sarvam-105b --arena tic-tac-toe
eslams models list --provider sarvam-ai --json
```

These commands are offline. Gameplay and `preflight --live` submit billable
inference; do so only with deliberate authorization and a configured key.
The adapter uses V1. Sarvam's `/v2/models` describes the V2 fleet, so it is not
used to claim account visibility for V1; preflight leaves that check unknown.

## Primary-source review

Reviewed 2026-11-04. Documentation availability does not prove account access.

- [V1 reference](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1):
  `POST https://api.sarvam.ai/v1/chat/completions`, `model`, `messages`, optional
  `temperature`, `max_tokens`, and `reasoning_effort`; assistant content in
  `choices[0].message.content`, identity in `model`, ID in `id`.
- [Authentication](https://docs.sarvam.ai/api-reference/authentication):
  the adapter sends `api-subscription-key`; chat also accepts Bearer auth.
- [Models](https://docs.sarvam.ai/api/token-factory/models/sarvam-105b):
  V1 serves `sarvam-105b` and `sarvam-105b-conversations`, with 128K and 32K
  context respectively. Sarvam-M and 30B are deprecated. Old registry rows are
  marked unavailable; advisory routing still forwards an exact explicit ID.
  See the [30B deprecation](https://docs.sarvam.ai/api/getting-started/models/sarvam-30b)
  and [M deprecation](https://docs.sarvam.ai/api/getting-started/models/sarvam-m).
- [Thinking controls](https://docs.sarvam.ai/api/token-factory/how-to/adjust-the-models-thinking-level):
  omission keeps native reasoning; JSON null disables it. The guide lists
  low/medium/high, while the V1 reference enum lists low/high/max and describes
  medium as its default. Explicit effort values are forwarded unchanged for
  endpoint validation. `enabled` preserves the native enabled default;
  `disabled` sends null. Foreign token-budget controls fail before submission.
- [Response/finish contract](https://docs.sarvam.ai/api/token-factory/chat-completions):
  `reasoning_content` is private reasoning, never action text. `length` is
  truncation; `content_filter` is refusal. Tool/function calls, unknown/missing
  finish reasons, multiple choices and malformed assistant envelopes fail closed.
  Only one completed assistant text choice is accepted. Text refusals without a
  structured marker cannot be reliably identified and fail action parsing.
- [Errors](https://docs.sarvam.ai/api/getting-started/errors-troubleshooting):
  errors have an `error` object with `code` and `message`, sometimes `request_id`.
  Invalid-key 403 is authentication failure; other 403s remain permission errors.
  402 is exhausted credit; 400/413/422 reject requests; 404/5xx are unavailable;
  429 includes rate, capacity and seat-budget errors. HTTP-200 error envelopes
  also fail. Raw error prose is never persisted.
- [Billing and limits](https://docs.sarvam.ai/api/getting-started/pricing):
  prompt/completion/total counters are provider usage; reasoning is included in
  completion tokens. Cache and reasoning detail counters remain unknown when
  absent. Prices are INR and are not silently represented as USD or as zero.
  This adapter supplies no price card and invents neither missing identity nor
  missing totals. Cost remains unavailable without independently verified rates.

## Execution and privacy

Core's existing bounded HTTP transport, cancellation, optional operator limits,
rate controls and attempt receipts are reused. Full supplied public history is
preserved by default; the existing explicit history-window option remains an
operator choice. No game selects reasoning policy. Omitted output/time limits
stay omitted; Sarvam's documented default `max_tokens` is 2048, and plan/context
constraints still apply. Core does not promise unlimited provider output.

Retries and action repair default to zero. With explicit optional retries, only
an exact documented 429 rate/capacity rejection without telemetry or unknown
extensions is eligible, honoring `Retry-After` and Core's backoff. Seat-budget
429, ambiguous 5xx/timeouts, accepted generations, refusal and truncation are
never replayed automatically, even though Sarvam's generic examples retry 5xx.

Receipts contain sanitized identity, status, finish markers and usage, never
keys, request headers, prompts, private reasoning, refusal prose or raw response
bodies. The raw-wire fixture under `tests/fixtures/provider/` follows the V1
reference envelope with redacted identifiers and deterministic action text;
fault variants are synthetic. No live inference was used for validation.
