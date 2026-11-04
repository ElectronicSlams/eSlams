# Upstage native adapter (planned for 0.7.1)

Uses the direct Upstage API with `UPSTAGE_API_KEY`. No SDK dependency or broker
route is involved. Supply the exact desired model:

```sh
export UPSTAGE_API_KEY=...  # export locally; never commit a real key
eslams providers preflight --provider upstage --model solar-pro4 --arena tic-tac-toe
eslams run --arena tic-tac-toe --agent upstage:solar-pro4
```

Configuration preflight is offline. `--live` submits billable inference and
requires the operator's separate authorization. No live inference was used to
validate this adapter. Bare `upstage` selects `solar-pro4`; explicit aliases and
snapshots are forwarded unchanged. There is no model substitution or fallback.

## Verified protocol

Primary sources checked **2026-11-04**:

- [Chat reference](https://console.upstage.ai/api/chat): JSON POST to
  `https://api.upstage.ai/v1/chat/completions`, Bearer authentication, `model`,
  `messages`, optional `max_tokens` and `temperature`. Requests use non-streaming
  mode. Parse final text from `choices[0].message.content`, independently of
  visible reasoning. The fixture under `tests/fixtures/provider/` follows this
  page's response example: only answer/reasoning text is replaced for a legal
  test action and privacy sentinel; identifiers and numeric usage are from the
  example. This is a documented-shape fixture, not a captured paid response.
- [Model catalogue](https://console.upstage.ai/docs/models) and
  [history](https://console.upstage.ai/docs/models/history): current chat IDs
  include `solar-pro4`, `solar-pro4-260806`, `solar-mini4`,
  `solar-mini4-260922`, `syn-pro`, `syn-pro-251021`. Earlier Pro 2/3 versions
  have been deprecated. Core's existing frozen catalogue may lag these docs;
  advisory configuration preflight permits explicit unlisted IDs. Strict
  catalogue mode can reject them. This adapter does not rewrite the global
  discovery snapshot or claim account availability.
- [Conversation quickstart](https://console.upstage.ai/docs/capabilities/generate/chat):
  each call is stateless. Core sends the entire supplied public history inside
  its normal action prompt by default. The existing explicit operator history
  window remains available. Nothing is inferred from game identity.

Some rate-limit examples still show the legacy `/v1/solar` path. The current
Chat reference above determines the endpoint used by this adapter.

## Reasoning and accounting

The [reasoning guide](https://console.upstage.ai/docs/capabilities/generate/reasoning)
confirms that current Solar Pro/Mini 4 omit reasoning by default. Explicit
`none`/`minimal` disable it; `low`, `medium`, `high`, `xhigh`, `max` enable it.
Use `--reasoning-effort high`, for example. Core's `auto` leaves native defaults
alone; `disabled` sends `none`. `enabled` requires an explicit enabling effort.
Numeric budgets and unknown effort values fail before submission. Model-specific
support is ultimately decided by Upstage; no catalogue-based effort substitution
occurs. No default output or total/read timeout cap is added. Explicit operator
limits use the shared transport; its connection timeout and response byte safety
limit remain in force.

The final answer is parsed separately from `message.reasoning`; visible reasoning
never enters action text or receipts. Reasoning tokens are already included in
`completion_tokens`. The shared normalizer records reported prompt, completion,
cache, reasoning and total counts and validates their types/relationships.
Missing identity stays null; only response `model` attests a resolved model.
Missing usage stays unknown. No native monetary cost is documented for this
response. Without an applicable verified price reference, cost stays unavailable;
a legal action alone does not establish official accounting eligibility.

## Failures and retries

The [error guide](https://console.upstage.ai/docs/resources/error-codes) specifies
an `error` envelope with `message`, `type`, `param`, `code`. Classification uses
HTTP status; private provider prose is excluded. 400 is request rejection,
401 authentication, 403 permission, 404/5xx unavailable, 429 rate limited.
The guide distinguishes `too_many_requests` from `usage_limit_exceeded`; the
latter cannot be fixed by retrying. Timeouts and incomplete bodies carry unknown
work/accounting and are never automatically replayed.

The [rate-limit guide](https://console.upstage.ai/docs/guides/rate-limits) specifies
`X-Upstage-RateLimit-Retry-After-{Requests,Tokens,Pages}` as Unix timestamps.
The adapter records the longest valid category cooldown, combined conservatively
with standard HTTP Retry-After. Default retries and action repairs are zero.
Core's existing strict consensus gate applies even with optional retries: a
429 with `code: too_many_requests` and `type: invalid_request_error` does not
establish unanimous replay admission, so it is retained without replay. Quota,
malformed, ambiguous, generation-bearing and usage-bearing errors are likewise
not replayed.

Malformed envelopes, refusals and truncation retain any observed usage. A
legal-looking partial answer is rejected on `length`, filtering or tool calls.
Unknown/missing finish reasons, multiple choices and non-assistant messages fail
closed. Refusal fields are defensive compatibility checks, not claims that
Upstage guarantees a particular refusal envelope. No action fallback is added.

No documented account Models API was found in the current reference. Live
model discovery therefore reports unavailable; preflight leaves account
visibility unverified rather than fabricating a model list.

## Keyless verification

`python -m pytest tests/test_upstage_provider.py` covers CLI construction/run,
preflight, exact model aliases, request controls/history, usage/identity/privacy,
raw success and errors, refusal/truncation, 429 cooldowns and retry admission,
malformed JSON, transport interruption and invocation-scoped receipt custody.
