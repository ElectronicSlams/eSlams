# Huawei MaaS / Pangu direct text inference

Research checked on 2026-11-04 against Huawei's official documentation. This
adapter targets the next 0.7.1 work; package and protocol versions stay unchanged.

## Service and model identity

Huawei provides a direct hosted text API. The [Chinese OpenAI-compatible API
reference](https://support.huaweicloud.com/model-call-maas/model-call-021.html)
lists `openpangu-2.0-pro` and `openpangu-2.0-flash` and restricts this service to
Southwest Guiyang 1. The [Pangu quickstart](https://support.huaweicloud.com/bestpractice-maas/bestpractice_maas_0021_02.html)
documents subscribing to the built-in service and making API calls. These are
Huawei-hosted openPangu models, not merely downloadable weights.

The provider key is `huawei`, denoting the inference host. The operator must supply
an exact nonblank model ID; there is no default, rewrite, substitute or fallback.
An unlisted explicit ID can be submitted under native defaults without claiming
catalogue verification. Explicit thinking controls are supported only for the
two documented Pangu IDs. Hosting other authors' models on MaaS does not make
their model authors Huawei. Conversely, routing a Huawei model through a broker
does not make that broker the Huawei direct API.

[ModelArts Studio deployment inference](https://support.huaweicloud.com/intl/en-us/api-pangulm/pangulm_05_0079.html)
has deployment/project-specific routes and authentication. It is a separate
contract. This adapter does not manage deployments, run weights locally, or
redirect requests to user-deployed services. The [international MaaS reference](https://support.huaweicloud.com/intl/en-us/model-call-maas/model-call-021.html)
uses a Singapore endpoint and different example models; it does not establish
Singapore availability for these Pangu IDs. No regional endpoint is synthesized.

## Setup and wire contract

Set `HUAWEI_MAAS_API_KEY` to the API key for the Guiyang service. Huawei requires
account verification, access authorization, and service activation; creating a
key alone does not establish access. Do not put the value in a command, artifact,
receipt, or checked-in file. Core does not load `.env.example` automatically.

Configuration-only preflight performs no network I/O:

```bash
eslams providers preflight --provider huawei --model openpangu-2.0-flash --arena tic-tac-toe
```

After explicit authorization for paid inference, use `--live` on that preflight
or select `--agent huawei:openpangu-2.0-flash` for a run. Neither was called against
Huawei during development. Fixture success establishes parser behavior, not
live availability, speed, pricing, or Official eligibility.

Inference uses POST `https://api.modelarts-maas.com/openai/v1/chat/completions`,
JSON content type, and `Authorization: Bearer <API key>`. Requests contain the
exact `model`, `stream: false`, system instructions, and the complete supplied
public history in Core's normal prompt. No tools, search, broker routing,
prefix continuation, or automatic fallback are requested. History-window and
gateway overrides are rejected for this direct adapter.

Core adds no default output, total-time, or read-time cap. The shared transport
retains its connection timeout and response byte safety boundary. An explicit
operator output limit maps to `max_completion_tokens` (answer plus reasoning);
an explicit temperature passes through. Omitted settings retain Huawei defaults
and service constraints, which are not a promise of unlimited provider output.

`--reasoning auto` omits thinking controls. `enabled` / `disabled` send
`chat_template_kwargs.thinking: true` / `false` for the documented Pangu models.
Huawei's [thinking guide](https://support.huaweicloud.com/model-call-maas/model-call-005.html)
documents their native thinking default and on/off capability. Effort strings,
reasoning token budgets, and Gemini budgets are rejected; they have no verified
Pangu mapping. No arena-specific reasoning policy is applied.

The [Models API](https://support.huaweicloud.com/model-call-maas/model-call-029.html)
is GET `https://api.modelarts-maas.com/v2/models`, using the same regional bearer
key and a `data[].id` list. Existing explicitly requested live preflight uses it
as advisory discovery before inference. Offline preflight does not call it.
Returned IDs remain exact; catalogue listing does not prove model access.

## Response, accounting, failures and custody

The parser requires a non-streaming `chat.completion` object, a single index-zero
assistant choice, nonblank `message.content`, and `finish_reason: stop`.
`reasoning_content` is never an action source and never enters public fields.
Tool calls, errors, refusals, malformed envelopes, model mismatch, and even
legal-looking truncated output fail before action parsing. Missing response
`model` remains unknown; a present differing model is rejected. A matching model
attests a service model ID, not an immutable weight revision.

Only documented usage fields are normalized: `prompt_tokens`,
`completion_tokens`, `total_tokens`, prompt detail `cached_tokens`, and completion
detail `reasoning_tokens`. Reasoning is included in completion/output tokens.
Missing counters are null, including a missing total; no token estimate or price
is invented. Inconsistent counts retain validation errors. Cost stays unavailable
without verified pricing. Error-body usage is quarantined by Core's existing
transport receipts, not treated as verified model identity or pricing.

Huawei publishes a [model-call error table](https://support.huaweicloud.com/model-call-maas/model-call-035.html),
including invalid requests, authentication and allowlist failures, inactive or
blocked services, nonexistent models, rate limits, and server failures. Core
uses its shared HTTP error classes: 400/413 request rejection, 401 authentication,
403 permission, 404/5xx unavailable, and 429 rate limiting. Error prose is never
copied into action or receipt fields. Local transport timeouts remain distinct.

Default retries and action repairs are zero. Automatic transport retries remain
disabled for Huawei even if a retry count is configured: these documents do not
establish safe replay or idempotency for ambiguous/billable work. No timeout,
partial body, or 5xx causes an automatic repeat. An explicitly configured action
repair remains the shared Core policy for parse failures after completed output.

Exact active-key echoes are removed from identifiers and all returned receipts
on success, HTTP errors, malformed JSON, and partial-body transport errors.
Credential-bearing answer content is rejected before it can enter action,
explanation, or raw-action metadata. Removed model identity has no identity-source
claim. This is in addition to shared structural receipt redaction.

`tests/fixtures/provider/huawei_maas_success.json` preserves the documented
OpenAI-compatible envelope. Its Pangu model ID, action text and telemetry are
synthetic fixture values; it is not a live Huawei capture. Tests include both
documented IDs, CLI/preflight/dispatch, native and explicit controls, full history,
identity and missing usage, HTTP failures, malformed and partial bodies, unsafe
completions, credential echoes, and zero replay.
