# IBM watsonx.ai direct chat adapter

This prospective 0.7.1 adapter runs in the unchanged 0.7.0 package. `watsonx`
identifies IBM Cloud hosting; `ibm` and `ibm-granite` remain model-author catalogue
namespaces. Neither author name silently selects this transport. Supported host
aliases are `watsonx-ai`, `ibm-watsonx`, `ibm-watsonx-ai` and underscore spellings.
Supply the exact IBM model ID, including its namespace. Missing, blank or
whitespace-padded IDs fail in CLI resolution, agent construction and preflight.
No model default, substitution, gateway routing or fallback is selected.

## Configuration

Configure only settings you intend to use; Core does not load `.env` files:

```bash
export WATSONX_REGION=eu-de
export WATSONX_PROJECT_ID='<your-project-id>'
# Set WATSONX_API_KEY through your local secret mechanism.
eslams providers preflight --provider watsonx --model ibm/granite-4-h-small
```

This command checks configuration without authentication or inference. The
model name is an example, not a guarantee of current region/account access.
Explicit `--live` authenticates and makes one potentially billable inference;
that requires the operator's permission. A game run uses
`--agent watsonx:<exact-model-id>` with the same environment settings.

`WATSONX_API_KEY` is an IBM Cloud API key, not an IAM token. The adapter exchanges
it using form-encoded `grant_type=urn:ibm:params:oauth:grant-type:apikey` at
`https://iam.cloud.ibm.com/identity/token`; only the resulting bearer token goes
to inference. Tokens are not persisted or refreshed; authentication failure
never triggers an inference replay. See IBM's [IAM token API](https://cloud.ibm.com/apidocs/iam-identity-token-api).

Set exactly one of `WATSONX_PROJECT_ID` or `WATSONX_SPACE_ID`. Required
`WATSONX_REGION` choices are `us-south`, `eu-de`, `eu-gb`, `jp-tok`, `au-syd`
and `ca-tor`; each selects `https://<region>.ml.cloud.ibm.com`. This adapter
supports the IBM Cloud IAM surface, not AWS Mumbai, private/on-prem endpoints
or the watsonx model gateway. Requests use `/ml/v1/text/chat` and a pinned
`version=2025-10-25`, also used in IBM's [Granite 4 example](https://www.ibm.com/granite/docs/models/granite4-0).
Override with an explicit ISO date in `WATSONX_API_VERSION` only when the
operator has verified compatibility. IBM requires version dates and cautions
against choosing the current date automatically. See the [service API](https://cloud.ibm.com/apidocs/watsonx-ai).

## Wire behavior and accounting

The request carries `model_id`, one context ID and system/user messages. The
user message includes the complete supplied public history by default through
Core's existing prompt builder. Explicit operator output limits become
`max_completion_tokens`; omitted limits leave IBM's defaults in effect.
Temperature is sent only when explicitly supplied. No `time_limit`, hidden
output ceiling, arena-based reasoning control or automatic history window is
added. IBM's [chat parameter reference](https://ibm.github.io/watsonx-ai-node-sdk/interfaces/1_7_x.WatsonXAI.TextChatParams.html)
describes these controls and the project/space requirement.

Reasoning `auto` leaves native defaults untouched. An explicit enabled/disabled
choice sends `chat_template_kwargs.thinking`; explicit effort sends
`reasoning_effort` (`low`, `medium`, `high`). Model support varies; IBM rejection
is retained. Unsupported token-budget controls (including explicit zero or dynamic budgets)
fail in both configuration/live preflight before discovery and before authentication.
`include_reasoning=false` would suppress returned reasoning, not disable
thinking, and is not used as a substitute. References: IBM's [parameter schema](https://ibm.github.io/watsonx-ai-python-sdk/v1.9.0/fm_schema.html)
and [SDK changelog](https://ibm.github.io/watsonx-ai-python-sdk/changelog.html).

Only `choices[0].message.content` is parsed. `reasoning_content` is never parsed
as an action or copied into receipts. Known API-key and IAM-token echoes are
removed from request/response/model identifiers and recursively redacted from
other receipt strings, including nested extensions and malformed/partial-response
receipts. Transport diagnostics are filtered even when no response headers were
observed. Generated action text containing either credential is rejected before
action parsing, publication or action repair. The [response schema](https://ibm.github.io/watsonx-ai-node-sdk/interfaces/1_7_x.WatsonXAI.TextChatResponse.html)
attests identity with `model_id`; an OpenAI-shaped `model` field does not.
Missing identity stays null. A different reported model fails while retaining
its evidence. The exact requested model remains unchanged in every receipt.

The documented [usage schema](https://ibm.github.io/watsonx-ai-node-sdk/interfaces/1_7_x.WatsonXAI.TextChatUsage.html)
reports `prompt_tokens`, `completion_tokens`, and `total_tokens`. Preserve
reported counters; never invent missing totals, cached/reasoning counts,
reasoning inclusion, or USD cost. Reasoning inclusion remains unknown, so
artifact `usage_complete` is false even when all three numeric counts exist.
Preflight's numeric `usage_extraction` check does not establish complete billing
or official eligibility. No host-specific price card is fabricated from an
author catalogue row.

Only `stop` is accepted as complete. IBM's [finish reasons](https://ibm.github.io/watsonx-ai-node-sdk/enums/1_6_x.WatsonXAI.TextChatResultChoiceStream.Constants.FinishReason.html)
include length, tool calls, time limit, cancellation, error and pending/null.
These cannot turn partial legal-looking output into an action. Synthetic
refusal/content-filter cases also fail closed. HTTP 400/401/403/404/429/5xx,
timeouts, transport errors and malformed JSON retain sanitized outcomes.
Retry-After is observed, but IBM error lists do not establish the shared
transport's narrowly verified safe replay shape. Even explicit optional retries
therefore do not replay these ambiguous rejections; defaults remain zero.

## Scope and test provenance

`WATSONX_DEPLOYMENT_ID` is explicitly rejected. IBM's [deployment chat contract](https://ibm.github.io/watsonx-ai-node-sdk/classes/1_7_x.WatsonXAI-1.html#deploymentsTextChat)
uses the deployment's base model and prompt-template parameters; treating a
deployment ID as a model would fabricate identity and could change messages.
This adapter supports direct base-model chat only. IBM has a foundation-model
specification API; account discovery is not implemented here and remains
advisory/unverified. Strict catalogue mode cannot attest new host/model rows.

`tests/fixtures/provider/watsonx_text_chat_success.json` is a redacted synthetic
instance of the documented REST response envelope and message/usage fields,
not an SDK convenience property or captured paid call. Fault tests mutate
this envelope, preserving private reasoning/error sentinels. Tests exercise
aliases through CLI, configuration/live preflight and dispatch, IAM encoding,
region/context/version, controls, missing/invalid evidence, refusal, truncation,
429, malformed bodies, transport, receipts and artifact privacy. Mocked live
preflight never contacts IBM. Both requests reuse Core's bounded transport,
existing cancellation/deadline policy and response-size safety bound.
