# BytePlus ModelArk direct inference (proposed 0.7.1)

Researched 2026-11-04 against official documentation. Package version stays 0.7.0
until the coordinated release. No live inference or account access was used.

## Service selection and setup

Use `byteplus:<exact-model-id>` or `byteplus:<account-endpoint-id>`. Aliases are
`byteplus-modelark`, `byteplus-ark`, and `modelark` (case/underscore normalization
is accepted). No default model is selected. `bytedance`, `volcengine`, and `ark`
do not select this adapter. The author catalog's ByteDance entries do not prove
that those model names are callable through BytePlus.

The [BytePlus authentication guide](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/base-url-and-authentication)
specifies the direct data-plane base `https://ark.ap-southeast.bytepluses.com/api/v3`
and bearer API keys. The documentation/console region is `ap-southeast-1`; the host
spelling is `ap-southeast`, without `-1`. Core reads only `BYTEPLUS_API_KEY`, a
provider-specific name for the BytePlus key called `ARK_API_KEY` in official examples.
It never borrows `ARK_API_KEY`, Volcengine credentials, or Access Key signatures.
Access Key signing and endpoint management are outside this adapter.

[Volcengine Ark](https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=zh)
documents `ark.cn-beijing.volces.com/api/v3`. That is a distinct service.
BytePlus Coding Plan also has a separate base URL. Neither is a fallback route.
An explicit Core gateway retains the existing generic gateway semantics and
appends `api/v3/chat/completions`; it is an operator routing choice.

```bash
# Configure BYTEPLUS_API_KEY through your environment/secret manager.
# This command is offline and does not spend inference credits:
eslams providers preflight --provider byteplus \
  --model dola-seed-2-1-turbo-260628 --arena tic-tac-toe

# Inference example: run only after explicitly authorizing provider spend.
eslams run --arena tic-tac-toe \
  --agent byteplus:dola-seed-2-1-turbo-260628 --opponent first-legal
```

Account activation and entitlement still apply. Endpoint IDs begin `ep-`; see
[GetEndpoint](https://docs.byteplus.com/en/docs/ModelArk/1262431). A deployment
ID is sent unchanged, but does not identify immutable weights. Only a concrete
response `model` supplies `locked_model_id`. Missing/unsafe identity remains
null. Core does not resolve deployments via the management API. Operators must
pin deployment configuration and disable server-side fallback themselves.

## Wire behavior and accounting

The [Chat reference](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/chat-api)
defines POST `/chat/completions`, system/user `messages`, assistant text in
`choices[0].message.content`, completion identity, finish reasons, and usage.
Core requests non-streaming text and accepts only a single completed choice.
Refusal/filter, truncation, tools, unknown finish reasons, body errors, reported
fallback, or a different concrete model cannot supply a legal action. A server's
unreported configuration change cannot be ruled out by an offline adapter test.

The full supplied public ActRequest history enters the existing prompt by
default. No conversation ID, private reasoning, or provider tool loop is retained.
Missing usage stays unknown. `prompt_tokens`, `completion_tokens`, `total_tokens`,
cached input, and reasoning details are normalized; reasoning is included in
completion output and is not counted twice. No rates, measured cost, or account
availability are invented. The existing explicit price-card rules still apply.

[Deep reasoning](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/deep-thinking)
documents model-dependent thinking switches, effort, and combined output limits.
Core's `reasoning=auto` omits the switch; explicit enabled/disabled sends
`thinking.type`. Explicit effort is forwarded unchanged. Unsupported token-budget
controls fail before submission. No game selects reasoning. An explicit operator
output limit sends `max_completion_tokens` to cover answer plus reasoning; otherwise
both output-limit fields are omitted. Endpoint defaults and context limits remain.
No framework total/read deadline is added by this adapter. Existing operator
deadlines, connection limits, cancellation and bounded body custody still apply.

## Errors, retries and verification limits

The [official error table](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/error-codes)
documents authentication, permission, endpoint/model access, moderation, quota,
burst, capacity, and internal failures. HTTP status determines the shared outcome;
documented text-moderation 400 codes become refusal. Provider error prose stays
private. HTTP-200 error envelopes cannot become successful actions. Receipts
retain request IDs and quarantined usage observations where available.

Default retries and action repairs are zero. This adapter disables automatic
transport retries even if `max_retries` is configured: quota/burst errors alone
do not establish safe replay. Ambiguous timeouts and 5xx are never replayed.
Explicit action repair remains governed by Core's existing operator policy.

`tests/fixtures/provider/byteplus_chat_success.json` follows the Chat reference's
non-streaming response example. IDs/text are replaced, the action is deterministic,
and cache/reasoning counts are synthetic fault-test values using documented keys.
Reasoning/encrypted fields follow Deep reasoning. Error bodies are synthetic
documented `error` envelopes; malformed and fallback cases are fault injection.
Tests assert endpoint/auth/payload, aliases through CLI/preflight/dispatch,
history, explicit controls, identity, usage, missing accounting, refusal,
truncation, HTTP errors, timeout, no replay and private-data exclusion.

Model discovery is not implemented in this adapter. Offline preflight can verify
configuration; live preflight would perform paid inference and was not run.
No account access, regional availability, deployment pin, or production success
is claimed by fixture tests.
