# StepFun direct API adapter

Prepared for 0.7.1; package version remains 0.7.0. Official documentation
reviewed on 2026-11-04. No real key, account discovery or paid inference was
used to validate this adapter.

## Endpoint, account and region

`stepfun:<exact-model-id>` sends non-streaming JSON to
`POST https://api.stepfun.ai/v1/chat/completions` with
`Authorization: Bearer <STEPFUN_API_KEY>` and `Content-Type: application/json`.
An explicit nonblank model ID is required; bare `stepfun` and `stepfun:` fail
before transport rather than selecting a model.
Account discovery uses `GET https://api.stepfun.ai/v1/models`, whose documented
envelope is `{"object":"list","data":[{"id":"step-3.7-flash",...}]}`.
Sources: [quickstart](https://platform.stepfun.ai/docs/en/quickstart/overview),
[Chat Completions](https://platform.stepfun.ai/docs/en/api-reference/chat/chat-completion-create),
[Models API](https://platform.stepfun.ai/docs/en/api-reference/models/list).

This adapter selects the international `.ai` Open Platform endpoint. The
[Chinese API reference](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create)
instead documents `api.stepfun.com`. Endpoint selection does not attest a
physical serving region or data residency. Core makes no such claim and does
not switch domains on errors. A Chinese account/endpoint needs a separately
reviewed configuration; `stepfun-cn` is deliberately not an alias.

[Step Plan](https://platform.stepfun.ai/docs/en/step-plan/integrations/reasoning-api)
is a distinct subscription path, `/step_plan/v1/chat/completions`. It is outside
this adapter's default contract. `stepfun-plan`, `step-plan`, `stepfun-ai` and
third-party router model namespaces are not aliases for the direct endpoint.
The existing explicit generic gateway override still applies, carries gateway
metadata and is an operator configuration, not proof of direct custody.

## Models and controls

| Exact model ID | Documented input | Reasoning effort metadata |
| --- | --- | --- |
| `step-5-preview` | text, image, video | `low`, `medium`, `high` |
| `step-3.7-flash` | text, image, video | `low`, `medium`, `high` |
| `step-3.5-flash` | text | native default; no model-specific effort list asserted |
| `step-3.5-flash-2603` | text | `low`, `high` |

Sources: [Step 5](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview),
[Step 3.7](https://platform.stepfun.ai/docs/en/guides/models/step-3.7-flash),
[Step 3.5 variants](https://platform.stepfun.ai/docs/en/guides/models/step-3.5-flash).
The adapter currently sends text only. The capability registry describes model
capabilities, not a claim that Core implements image/video requests.

Model IDs retain case, punctuation, slashes and colons. Variants are distinct:
Core never maps `step-3.5-flash-2603` to `step-3.5-flash`, prepends a vendor,
replaces a retired model or changes provider. Unknown exact IDs may be sent;
the endpoint is authoritative. Registry entries remain account-dependent.
[Retirement notices](https://platform.stepfun.ai/docs/en/guides/model-migration)
are advisory by default and enforced by `--strict-catalogue`; retired entries
are preserved for historical lookup without a replacement alias.

The request contains the shared system instructions and the complete supplied
agent-visible ActRequest history in the user prompt. It uses no conversation
summarization, private-reasoning replay or game-specific effort selection.
`--reasoning-effort` is forwarded exactly when explicitly supplied, including
for an unknown model; unsupported choices receive normal endpoint rejection
receipts. Default/`auto`/`enabled` add no reasoning fields. `disabled` omits
optional controls; it does not promise to disable native model reasoning.
`reasoning_format` is omitted, retaining the documented `general` default;
neither `reasoning` nor the alternate `reasoning_content` response field is
used as action text or included in receipts.

Explicit `reasoning_budget_tokens` and `gemini_thinking_budget` are unsupported
and rejected during configuration/preflight and again before transport; they
are never silently dropped. `reasoning_effort` remains the supported explicit
control and is forwarded exactly.

`max_tokens` is omitted unless the operator explicitly supplies an output
maximum. The API documents an unlimited default subject to model constraints;
Core adds no ceiling. Total/read/action deadlines also remain unset by
default, with the existing connection timeout retained. Explicit operator
limits use the shared transport. Native context/output constraints still
apply, and `length` output is rejected even when the action JSON parses.

## Results, failures and custody

The parser requires a `chat.completion` object with one index-zero assistant
choice, nonempty string `message.content`, and `finish_reason=stop`. It rejects
stream chunks, content arrays, missing/unknown finish fields and tool output.
Model and response ID come only from observed response fields; absent values
remain null. A returned model different from the request is preserved exactly
for downstream identity policy, never rewritten to match the request.

[Error codes](https://platform.stepfun.ai/docs/en/api-reference/error-codes) and
[exception guidance](https://platform.stepfun.ai/docs/en/guides/developer/exception)
document request/auth/balance/path/rate/safety/server errors. Core maps 400/402
to request rejection, 401 to authentication failure, 403 to permission failure,
404/5xx to unavailability, 429 to rate limitation, and StepFun's 451 to refusal.
Response `content_filter` is refused, `length` is truncated and `tool_calls`
is incomplete. Embedded error bodies are inspected before action parsing.
Raw error/refusal prose is excluded from receipts.

Each physical attempt snapshots the primary credential and configured
credential-named environment values for literal echo filtering. Credential-bearing receipt
strings (including header IDs, response IDs and returned model IDs) become
null on success, HTTP errors, malformed bodies and partial responses. Redaction
does not erase evidence that remote work may have occurred or authorize a
retry. Action text containing a credential is rejected before public action
metadata or explanation parsing.

Default retries and action repair are zero. Even when explicitly enabled,
the shared retry policy admits only a definitive 429 rejection with no work
observations; conflicting classifiers, generation IDs, usage, cost, malformed
bodies, timeouts and ambiguous 5xx cannot authorize replay. `Retry-After` is
honored only inside the operator's available deadline. Every physical attempt
keeps a separate gap-free receipt. Non-2xx accounting observations remain
quarantined, with unknown model identity and canonical cost.

## Usage and cost

The documented `usage` fields map as follows:

| Wire field | Receipt field |
| --- | --- |
| `prompt_tokens` | `input_tokens` |
| `completion_tokens` | `output_tokens` |
| `total_tokens` | provider total, validated against input + output |
| `cached_tokens` | `cached_input_tokens`, `cache_read_input_tokens` (subset of input) |

[Prompt cache documentation](https://platform.stepfun.ai/docs/en/guides/developer/prompt-cache)
places `cached_tokens` directly on `usage`; cached input is not free or added
again to the input count. Missing counters remain unknown; numeric integrity
errors remain visible to accounting validation. The Chat Completions reference
does not specify a separate reasoning-token counter. The generic projection
leaves `reasoning_tokens` unknown and never estimates it from reasoning text
or trusts undocumented extensions.

[Pricing documentation](https://platform.stepfun.ai/docs/en/guides/pricing/details)
explicitly says Step 5 output includes reasoning and final answer. This does
not provide a per-response reasoning split or attest inclusion for every
model. When the response attests `model=step-5-preview`, the receipt records
`reasoning_included_in_output=true`; other or absent model identities keep
that field unknown. No separate reasoning count is added to output. Rates
and account limits are documented there, but this change installs no reviewed
price card. Cost stays unavailable; an undocumented `usage.cost` extension
cannot make it complete. Provider-specific reviewed pricing can be added in
a separate change. An adapter success does not establish scoring eligibility,
account availability, exact backend-build identity or complete cost accounting.

## Keyless verification and fixture provenance

`tests/fixtures/provider/stepfun_chat_completions_success.json` follows the
non-streaming example and response field definitions in the official Chat
Completions reference, with synthetic/redacted ID, model, reasoning and action
text. The optional cached counter follows the official cache example. It is a
documented-wire fixture, not a captured live response. Fault-injection payloads
retain this envelope; error messages and keys are synthetic test sentinels.

```bash
python -m pytest tests/test_stepfun_adapter.py -ra
eslams providers preflight --provider stepfun --model step-3.7-flash --arena tic-tac-toe
eslams providers models --provider stepfun
```

For separately authorized live use, set `STEPFUN_API_KEY` and run
`eslams run --agent stepfun:step-3.7-flash --opponent first-legal`.
Preflight with `--live` also makes an inference call and may incur charges.
No live commands were run during this implementation.

## Socket deadline regression investigation

The existing slow-header socket test could reach its 250 ms deadline while
HTTPX initialized its client/trust store, before the server accepted a request.
Its subsequent server-disconnect assertion then had no observed request to
attach to. A controlled delayed-client regression reproduces that condition,
verifies the caller still times out, and verifies cleanup when setup resumes.
The socket-closure test now prepares its trust context before timing the call
and explicitly requires a server-observed request. Real HTTPX/TCP cancellation
and the original elapsed limits are retained. Production transport and timeout
semantics are unchanged.
