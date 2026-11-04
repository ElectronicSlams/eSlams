# Qwen / Alibaba Cloud DashScope adapter

Research checked 2026-11-04 for the proposed 0.7.1 adapter. Alibaba Cloud Model
Studio supplies the direct API. Qwen is also a model-author namespace on brokers;
that namespace alone is not evidence of a direct API, account access or backend
identity. This adapter uses native DashScope REST without an SDK dependency.

## Configure and select

```bash
# Export your own pay-as-you-go Model Studio key through your secret manager.
# DASHSCOPE_API_KEY must match the region and workspace.
export DASHSCOPE_REGION=ap-southeast-1
# Optional for Singapore, Beijing and Hong Kong; required in the other regions below.
export DASHSCOPE_WORKSPACE_ID=your-workspace-id

# Offline: no credentials, model discovery or inference required.
eslams providers preflight --provider dashscope --model qwen-plus --arena tic-tac-toe

# Inference is billable; run only when you choose to call your account.
eslams run --arena tic-tac-toe --agent qwen:qwen-plus
```

`qwen` is canonical. `alibaba`, `alibaba-cn` and `dashscope` resolve to it in the
registry, CLI, preflight and execution receipts. Provider aliases are case
insensitive and accept surrounding whitespace and underscores. An alias does
not select a region: even `alibaba-cn` uses the configured region. A bare
`qwen`/`dashscope` agent defaults to `qwen-plus`; an explicit model is sent
unchanged, including case and snapshot suffix. Catalogue membership is advisory
unless `--strict-catalogue` is selected. Account visibility stays unverified:
this adapter does not implement a Models API. A live preflight must be explicitly
requested with `--live` and needs a key.

The adapter posts only to `/api/v1/services/aigc/text-generation/generation`.
`DASHSCOPE_REGION` defaults to `ap-southeast-1`. The following table describes
endpoint selection, not model availability in every region:

| Region | Host without a workspace ID |
| --- | --- |
| `ap-southeast-1` (Singapore) | `dashscope-intl.aliyuncs.com` |
| `cn-beijing` | `dashscope.aliyuncs.com` |
| `cn-hongkong` | `cn-hongkong.dashscope.aliyuncs.com` |
| `us-east-1` (Virginia) | Workspace required |
| `eu-central-1` (Frankfurt) | Workspace required |
| `ap-northeast-1` (Tokyo) | Workspace required |

With `DASHSCOPE_WORKSPACE_ID`, the host is
`{WorkspaceId}.{region}.maas.aliyuncs.com`. Workspace IDs must be lowercase DNS
labels. Unrecognized regions and invalid/empty workspace settings fail before
submission and in configuration preflight. These are Core environment settings,
not additional public runtime-contract fields. Explicit gateway configuration
uses Core's existing gateway path mapping; it does not change provider identity
or attest a model. Regional keys, model lists and permissions are separate.
Token/Coding Plan subscription endpoints and their dedicated keys are outside
this adapter's scope. See [authentication](https://www.alibabacloud.com/help/en/model-studio/get-api-key).

## Request and completion policy

The implementation requests `parameters.result_format: message`, sends bearer
authentication, and places system/user messages under `input.messages`. Core's
user prompt carries all supplied public history unless the operator explicitly
sets `history_window_turns`. It does not maintain private assistant or reasoning
history between actions.

The documented text endpoint includes models such as `qwen-plus`. Use the exact
native model ID authorized in the selected region; broker IDs and the frozen
registry do not establish availability. Unknown explicit IDs reach this same
endpoint for an authoritative response. There is no alternate model, provider,
region, protocol or endpoint retry. In particular, this implementation does not
switch to the multimodal-generation route for Qwen-VL, Omni or newer multimodal
families. Image/audio/video, streaming-only models, files, async jobs, search,
code execution, tools and preserved private reasoning are unsupported.

Defaults omit output limits, sampling and reasoning controls. Explicit
`max_output_tokens` maps to native `max_tokens`, which for Qwen caps answer
tokens, excluding thinking. This does not impose a total reasoning ceiling.
Explicit temperature is forwarded. Explicit runtime `reasoning` maps
enabled/disabled to `enable_thinking`; auto omits it. `reasoning_budget_tokens`
maps to `thinking_budget`, and `reasoning_effort` is forwarded unchanged. Neither
is inferred from an arena or catalogue recommendation. Effort and budget cannot
be combined; Gemini controls are rejected before submission. Support and valid
ranges depend on the requested model, and provider rejection remains a failed
attempt. Synchronous inference cannot serve streaming-only thinking modes; the
adapter never disables thinking automatically to make one work. See
[thinking modes](https://www.alibabacloud.com/help/en/model-studio/deep-thinking).

No `response_format` schema, tool definition or tool choice is sent. Model-specific
JSON/schema support is not assumed. The public legal-action schema stays inside
the prompt and Core validates the returned action. DashScope has a separate
[function-calling protocol](https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling);
this game adapter does not execute it. Tool requests, refusals and unfinished
generations cannot become legal actions merely because their text parses.

Only one completed assistant choice with string content and `finish_reason:
stop` is accepted. Length termination is truncation; tool calls are rejected;
filter/refusal signals are failures. Missing/unknown completion fields, multiple
choices, malformed JSON, duplicate fields, text-format envelopes and SDK/OpenAI
response shapes are rejected. Private reasoning/error/refusal prose is excluded
from receipts.

## Identity, accounting and retry limits

The native envelope's `request_id` is correlation evidence, not model identity.
The route takes a model in the request body and does not attest it through a
pinned model URL. `locked_model_id` and `model_identity_source` therefore remain
null, even if an undocumented extension echoes `model`.

Input/output/total token counts and optional reasoning/cache counts pass through
Core's integer and total-consistency validation. Output includes reasoning;
reasoning is not added twice. Cache reads/creation are input subsets. Missing
cache counters remain unknown; the documented native fields live under
`usage.prompt_tokens_details` (see [context cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)). Missing
usage stays missing; partial usage is incomplete, and invalid counts are not
coerced to zero. Non-2xx observations stay quarantined. Native usage does not
provide a USD charge. Catalogue prices are deliberately excluded from this
adapter's receipts: they cannot represent this region, input tier, thinking mode,
cache categories and current account promotions. Cost remains unavailable, and
this adapter alone cannot establish official cost/identity eligibility.

[Pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) is
pay-as-you-go by default, with separate input/output rates. Some models price
all tokens at a tier selected by input length. Cache and batch discounts have
separate rules; thinking output is billable. Region, deployment scope and
promotions matter. The adapter performs synchronous inference without batch or
explicit-cache creation controls and does not turn a free quota into a zero-cost
claim.

Transport, resource bounds, deadlines, cancellation, admission and receipt
custody reuse Core. The total/read timeout defaults remain unbounded; the existing
connect timeout is retained. Default retries and action repairs are zero.
Native flat error envelopes are not added to Core's narrow safe-replay allowlist:
even configured `max_retries` does not replay them. HTTP 429, 5xx, connection
failure, timeout, partial bodies, HTTP-200 body errors, parse failures and
incomplete output cannot trigger implicit replays. Only explicitly configured
action repair can submit a fresh action attempt after a completed but
unparseable action, retaining each attempt and its usage.

HTTP status drives normal error classification. Documented moderation codes
classify refusals; known flat codes also classify HTTP-200 failures defensively.
Unknown body codes fail closed without copying their text. Request IDs and
Retry-After are sanitized through existing Core helpers. Follow the official
[error guide](https://www.alibabacloud.com/help/en/model-studio/error-code) to fix
region/key/permission/parameter problems and resolve uncertain execution before
resubmitting; [rate limits](https://www.alibabacloud.com/help/en/model-studio/rate-limit)
depend on model and account.

## Offline evidence and integration

`qwen_dashscope_success.json` preserves the raw HTTP message response example in
the [native API reference](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope)
(updated 2026-10-27), with action text and consistent token counts substituted.
`qwen_dashscope_error.json` is a synthetic documented flat error envelope with a
rate-limit code and sample request ID. Neither comes from a paid call or an SDK
convenience object. Failure variants are deterministic fault injection, including
defensive 200-error and filter extensions; these are not claims that undocumented
success capabilities exist. No live account/model/region verification was done.

Run `python -m pytest tests/test_qwen_dashscope.py` for provider coverage, then the
full repository checks in `CONTRIBUTING.md`. The provider suite covers aliases,
CLI/preflight/dispatch, requests, history, regions, explicit controls, identity,
accounting, privacy, errors, truncation and transport interruption. Exact cloud
validation results belong in the draft PR description for its final commit.

Parallel adapter integration may conflict at imports/dispatch/endpoint-parser
maps and error/usage hooks in `agents.py`, the CLI defaults map, credential map
and configuration checks in `provider_preflight.py`, provider documentation,
`.env.example` and the changelog. Keep the Qwen module, tests and fixtures separate;
do not overwrite another adapter's insertion. Revalidate after resolving those
conflicts on the actual integration commit. No registry regeneration, public
schema change or package-version bump is part of this adapter.
