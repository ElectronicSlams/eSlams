# Poolside native adapter (0.7.1 work)

Research checked 2026-11-04 against official Poolside sources. Package version
remains 0.7.0 pending release review. No credentials or live inference were used.

## Verified hosted contract

The [API overview](https://docs.poolside.ai/api/overview) documents
`https://inference.poolside.ai/v1`, `POST /v1/chat/completions` and
`GET /v1/models`. Obtain a key through Poolside Platform and export
`POOLSIDE_API_KEY`; the adapter sends `Authorization: Bearer <key>`.
Hosted inference, self-managed inference and OpenRouter are distinct access
methods. This adapter targets hosted inference directly. It never substitutes a
broker, another model, another region or a self-managed deployment.

Use an explicit, exact model ID, for example `poolside/laguna-s-2.1`, as shown in
the overview. The [supported models page](https://docs.poolside.ai/get-started/supported-models)
cautions that IDs and availability vary by access method; family names alone
do not prove hosted availability. This change does not rewrite the frozen model
catalogue or turn discovery into an availability guarantee. Configuration
preflight is advisory; `--strict-catalogue` retains existing catalogue policy.

```bash
# Offline: no credential or provider request is needed.
eslams providers preflight --provider poolside \
  --model poolside/laguna-s-2.1 --arena tic-tac-toe

# These commands require a key and explicit permission to contact the service.
eslams providers models --provider poolside --live
eslams providers preflight --provider poolside \
  --model poolside/laguna-s-2.1 --arena tic-tac-toe --live
eslams run --arena tic-tac-toe \
  --agent poolside:poolside/laguna-s-2.1 --opponent first-legal --output-dir runs/poolside
```

`poolside-ai` and `poolsideai` are Core provider aliases; case and underscore
normalization work through CLI, preflight, discovery and direct dispatch. They
do not rewrite the model. Missing/blank models are rejected, with no default
model selected. Discovery uses the documented OpenAI-compatible `data[].id`
shape; the detailed Models reference is restricted, so additional pagination
semantics are unverified.

## Requests, thinking and responses

The [official API examples](https://docs.poolside.ai/api/openai-api-examples)
show `model`, `messages`, `choices[].message.content`, optional
`reasoning_content`, and `finish_reason`. The adapter requests non-streaming
responses and accepts one assistant answer with `finish_reason: stop`.
The shared eSlams prompt includes all supplied public history by default;
there is no adapter-specific history window or game-specific thinking choice.
An operator's existing explicit history-window setting remains supported.

Automatic reasoning mode leaves Poolside's native default untouched. Explicit
`--reasoning enabled/disabled` maps only to
`chat_template_kwargs.enable_thinking: true/false`. Effort and token-budget
controls are unsupported and fail before submission, including offline and live
preflight. The adapter omits temperature and output-token controls unless the
operator supplies them. Explicit output tokens map to `max_tokens` and
temperature maps to `temperature` without consulting broker capabilities.
Poolside documents its own generation defaults and constraints; omission does
not make the service unlimited. Core adds no generation or total-time cap.
Existing connection and response-byte safety checks still apply.

Only answer `content` is parsed as an action. Private `reasoning_content` is
never parsed, copied into receipts, or retained between calls. Each `/act`
request is a stateless conversation built from the complete supplied game
history. Poolside recommends preserving assistant reasoning when replaying
assistant turns in agentic tool conversations; this adapter does not implement
such a conversation or discard an existing assistant transcript.

## Accounting, identity, errors and privacy

The examples report `usage.prompt_tokens`, `completion_tokens`, and
`total_tokens`. Those are the only normalized counters here. Absent totals are
not synthesized; absent cache/reasoning counters and whether reasoning is
included in completion usage remain unknown. No native price or cost schema
was verified. Broker price cards and arbitrary `usage.cost` extensions do not
establish native costs; receipts report cost unavailable. Receipt identity is
only the observed response `model`, which can be absent or differ from the
requested ID. An endpoint URL or model request does not attest a resolved model.

HTTP status handling uses Core's existing sanitized classifications (400 request
rejection, 401 authentication, 403 permission, 404/5xx unavailable, 429 rate
limited). Refusal, truncation, tool-call and malformed/incomplete envelopes fail
closed before legal-looking answer text can become an action. These are
defensive compatibility checks, not claims that Poolside's public docs specify
every fault shape. Error-body accounting remains quarantined as unverified.
Timeout/transport failures retain one attempt. Default retries and action
repairs are zero. Poolside automatic transport retries are disabled even when
an operator sets a retry budget: public documentation does not establish
idempotency or a definitive no-work rejection. Retry-After, when present, is
diagnostic and never authorizes a replay.

Receipts exclude prompts, answer/refusal prose, reasoning, request headers and
raw provider bodies. Known credentials echoed in IDs/receipt fields are
removed, including success, HTTP error, malformed-body and partial-body paths.
The provider key is also redacted from parsed answer text, including keys
represented with JSON character escapes inside the answer. There are no
secondary Poolside credentials in this adapter. Credential-echo model discovery
fails closed. This is a Core artifact privacy boundary, not a provider-side
retention promise.

Poolside's [privacy policy](https://poolside.ai/legal/privacy) describes variable
processing jurisdictions, retention and model-training uses with opt-out.
The hosted documentation does not establish a selectable regional endpoint or
zero-retention guarantee. Self-managed deployment data-control claims do not
establish hosted privacy. No region parameter or residency attestation is
invented.

## Evidence limits and fixture provenance

The linked [chat reference](https://docs.poolside.ai/inference-api/chat/create-chat-completion)
and [Models reference](https://docs.poolside.ai/inference-api/models/list-models)
redirected to an access-code login during research. No access-control bypass was
attempted. Hosted error schemas, numeric rate limits, retry/idempotency
guarantees, extended usage and billing remain unverified. No live account
visibility, endpoint availability or response was tested.

`tests/fixtures/provider/poolside_chat_completions_success.json` follows the
overview's raw response example (including 447/88/535 counters), with synthetic
ID and answer/reasoning text for deterministic action/privacy checks. All fault,
refusal, truncation and usage mutations are synthetic injections into the
OpenAI-compatible envelope. They are not recorded Poolside responses.
