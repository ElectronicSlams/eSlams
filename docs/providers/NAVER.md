# NAVER Cloud HyperCLOVA X / CLOVA Studio

Evidence checked on 2026-11-04 against official NAVER documentation. This adapter
targets the native non-streaming Chat Completions v3 API, not an OpenAI-compatible
shim, a router, a tuning task or a third-party hosted model.

## Access and setup

[CLOVA Studio prerequisites](https://guide.ncloud-docs.com/docs/en/clovastudio-spec)
list **Korea**, on Classic and VPC. This is the supported service region, not
evidence that overseas callers are universally permitted or that another regional
hostname exists. Account subscription, network access and model entitlement were
not tested. No inference calls, real credentials or billable probes were used.

The [API overview](https://api.ncloud-docs.com/docs/en/ai-naver-clovastudio-summary)
documents `https://clovastudio.stream.ntruss.com`, `Authorization: Bearer <API key>`,
and JSON responses by default. `Accept: application/json` selects the ordinary
bounded response path. Streaming is not requested. Legacy API Gateway credentials
and the deprecated `clovastudio.apigw.ntruss.com` host are not used.

Issue a CLOVA Studio API key through your authorized NAVER account. Supply it as
`CLOVASTUDIO_API_KEY`; Core never loads `.env` automatically. A configuration-only
preflight needs no key and sends no requests:

```bash
eslams providers preflight --provider naver --model HCX-007 --arena tic-tac-toe
```

After separately authorizing paid provider access, an operator can export the key
and run `eslams run --arena tic-tac-toe --agent naver:HCX-007`. `--live` preflight
also performs inference and can incur charges. No Models API is assumed; discovery
returns unavailable and account visibility remains unknown. The frozen catalogue
is advisory by default and is not updated by this adapter.

## Model, payload and reasoning

[Thinking](https://api.ncloud-docs.com/docs/en/clovastudio-chatcompletionsv3-thinking)
defines `POST /v3/chat-completions/{modelName}` for HCX-007.
[Text and image](https://api.ncloud-docs.com/docs/en/clovastudio-chatcompletionsv3)
documents the same route for HCX-005 and HCX-DASH-002. The adapter sends text only:
one system message and the public ActRequest prompt, including all supplied history
unless the caller explicitly selects a history window. The exact model ID is URL
encoded as one path component and retained unchanged in metadata. Blank/missing
IDs and outer whitespace are rejected. There is no default model or fallback.

HCX-007 supports `thinking.effort`: `none`, `low`, `medium`, `high`. Core `auto`
omits the control unless an effort is explicit; `disabled` sends `none`; `enabled`
uses explicit effort or the documented `low` default. `enabled` plus `none` is
rejected. Token-budget controls, unknown efforts and reasoning controls for other
model IDs are rejected before inference. Arena/game identity never chooses effort.
Future exact model IDs may be submitted with native defaults; explicit reasoning
controls require documented support. No tools, function calls, searches or RAG are
configured or executed.

An explicit operator output limit becomes `maxCompletionTokens` for HCX-007 or
`maxTokens` otherwise. No limit is sent by default. NAVER still applies its native
limits/defaults, including effort-dependent HCX-007 output defaults. Explicit
temperature is forwarded. Core's existing connect timeout, cancellation,
concurrency controls and bounded JSON reader are reused; there is no added total
or read timeout. Existing JSON size/depth checks are safety limits, not token or
thinking budgets.

## Responses, identity and accounting

The parser requires `status.code == "20000"`, `result.finishReason == "stop"`,
and a nonempty string at `result.message.content` with assistant role. `length`
is truncated output, `tool_calls` is unsupported, and missing/unknown finish
markers fail closed, even if the content looks like a legal action. Reasoning
at `result.message.thinkingContent` never becomes an action or public receipt.

The v3 envelope does not attest a response model or generation ID. Successful
direct endpoint calls record the literal path model as `locked_model_id` with
`model_identity_source: pinned_endpoint`. This attests the requested endpoint
identity, not a backend revision. Gateway calls leave locked identity and region
unknown. Errors and interrupted bodies do not assert locked identity. Optional
`X-NCP-CLOVASTUDIO-REQUEST-ID` response headers are retained if observed; a request
ID or response ID is never invented.

`result.usage.promptTokens`, `completionTokens`, `totalTokens` and
`completionTokensDetails.thinkingTokens` map to normalized input, output, total
and reasoning counts. Thinking is included in completion tokens and never added
twice. Missing values stay unknown; the shared normalizer can derive a total from
complete component counts and labels it as derived. Invalid counts remain flagged.
Absent usage stays absent. No token counts are estimated from text, no absent
reasoning/cache counts are filled with zero, and no prices or USD cost are invented.
No price card is bundled. Cost/Official eligibility is not established by preflight.

## Errors, retries and privacy

[Troubleshooting](https://api.ncloud-docs.com/docs/en/clovastudio-troubleshoot)
documents native five-digit status codes: validation/model errors, authentication,
permission, rate limiting, timeouts and server failures. Native failures are
classified before action parsing, including in HTTP-200 envelopes. HTTP failures
reuse the existing transport classification. Error status messages and raw bodies
are never copied into receipts. Observed usage accompanying a native error is
retained with quarantined provenance; it is not verified billing or identity.

Default retries and action repairs are zero. NAVER errors are not established as
safe to replay, so the adapter does not grant automatic retry permission even when
an operator supplies `max_retries`. Timeout, disconnect, malformed and partial
responses remain ambiguous and are not retried. Bounded header observations survive
interrupted reads without inferring usage, completion or remote cancellation.

Credential values echoed in provider-controlled identifiers are discarded across
success and failure paths, including partial reads. Credentials in action content
or its JSON-decoded envelope cause rejection before parsing; this includes escaped
JSON strings. The private thinking field is ignored. This is covered by synthetic
credential tests, not a claim to detect arbitrary transformations of a secret.

## Fixture provenance and validation

`tests/fixtures/provider/naver_chat_completions_v3_success.json` follows the official
Thinking success envelope and its documented usage counts; content and reasoning
are synthetic replacements, not a captured live response. Fault fixtures exercise
the same native envelope and deliberately malformed variants.
`tests/test_naver_provider.py` covers exact endpoint/auth/payload, history,
reasoning, identity, usage/cost, offline and mocked live preflight, CLI artifact
validation, native/HTTP errors, malformed JSON, credential echoes, timeout and
actual bounded-reader partial/disconnect/oversize cases through HTTPX MockTransport.
