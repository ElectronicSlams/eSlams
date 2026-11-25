# Azure Foundry direct inference adapter (proposed for 0.7.1)

This adapter uses `azure:<deployment>` and Azure's GA v1 Chat Completions REST
API. The package remains 0.7.0 pending release review. Research checked against
Microsoft documentation on 2026-11-04; no credentials or paid inference were used.

## Endpoint and deployment identity

Set `AZURE_AI_ENDPOINT` to the resource endpoint copied from Azure, for example
`https://YOUR-RESOURCE.services.ai.azure.com` or
`https://YOUR-RESOURCE.openai.azure.com/openai/v1/`. Core accepts the resource root
or v1 base and sends `POST /openai/v1/chat/completions`. The GA v1 contract needs
no dated `api-version` query. A project URL ending in `/api/projects/...` is a
different service endpoint. Public Azure HTTPS resource hosts only are supported;
sovereign cloud hosts, arbitrary gateways, legacy deployment URLs and
`*.models.ai.azure.com` endpoints are rejected. Redirects are not followed.

The supplied deployment string is required and sent unchanged in `model`.
There is no default model, deployment discovery, region substitution, fallback,
or attempt to resolve it through the OpenAI catalogue. The legacy aliases
`azure` and `azure-ai` previously resolved catalogue lookups to `microsoft`;
they now select this Azure adapter. `azure-foundry`, `azure-ai-foundry` and
`microsoft-azure` also select it (case and underscores are normalized).
`microsoft` remains a model-publisher catalogue identity, with no implied Azure
deployment. Microsoft-published weights are not evidence of Azure hosting.

Azure v1 also serves compatible models from other publishers. This adapter is
limited to deployments supporting this Chat Completions contract. It does not
support every Foundry catalogue model, partner-native Messages APIs, Responses,
managed compute, or preview instant-access model routing. Microsoft recommends
Responses for Azure OpenAI models; Chat Completions is the shared v1 route
selected here. The older Azure AI Model Inference REST route uses dated API
versions (currently documented as `2025-04-01`); it is a different contract.
Microsoft's migration guide marks the `azure-ai-inference` SDK retired on
2026-08-26. Core uses HTTPX and does not add that SDK.

Sources: [v1 API and deployment names](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle),
[older Model Inference REST API](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/modelinference/),
[SDK migration](https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic).

## Authentication and setup

The default `AZURE_AI_AUTH_MODE=api-key` reads `AZURE_AI_API_KEY` and sends only
`api-key`. Optional `AZURE_AI_AUTH_MODE=entra` reads `AZURE_AI_AUTH_TOKEN` and
sends only `Authorization: Bearer ...`. Supply an already acquired token for the
Azure inference audience; current v1 docs use `https://ai.azure.com/.default`
and the Cognitive Services OpenAI User role. Core neither acquires nor refreshes
tokens, and never uses `OPENAI_API_KEY`. Expired tokens produce an auth failure.
A Python caller can explicitly supply another credential environment name through
`ModelProviderAgent.api_key_env`; the selected authentication mode still applies.

```bash
# Export credentials separately; never commit them or paste them into artifacts.
export AZURE_AI_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com

# Offline configuration check: no provider request, credentials optional.
eslams providers preflight --provider azure --model YOUR-DEPLOYMENT --arena tic-tac-toe

# These commands invoke inference and incur Azure charges; run only when authorized.
eslams providers preflight --provider azure --model YOUR-DEPLOYMENT --arena tic-tac-toe --live
eslams run --arena tic-tac-toe --agent azure:YOUR-DEPLOYMENT --opponent first-legal
```

Configuration preflight validates the endpoint, auth mode and explicit deployment.
It does not attest deployment existence, model availability, permissions or region.
Live preflight makes an explicitly requested inference. Azure deployment listing
is not implemented: account visibility remains unknown, and `providers models
--provider azure --live` returns discovery unavailable. `/models` catalogue IDs
must not be substituted for an account's deployment names. Strict catalogue
preflight rejects unregistered deployments; ordinary preflight is advisory.

Source: [v1 authentication and RBAC](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle).

## Request, completion and reasoning

The request contains the shared system instruction and complete supplied public
history in the user prompt, with `stream: false` and `store: false`. By default,
Core omits output limits, temperature, reasoning effort and total/read time limits;
its existing connection timeout and bounded response-size safety remain.
An explicit legacy history window or operator time/output policy is honored.
Azure's own context/output ceilings and native defaults still apply.

An explicit output limit becomes `max_completion_tokens`, including reasoning
where the model uses it. Explicit `reasoning_effort` and temperature are forwarded
unchanged; unsupported controls are rejected by Azure without removal or replay.
Explicit `reasoning_budget_tokens` and `gemini_thinking_budget` are unsupported
and rejected in configuration/live preflight and before transport, including
explicit zero/automatic sentinel values. No model-name heuristics, game-specific
reasoning mode or hidden reasoning budget is selected. `reasoning=disabled` omits optional reasoning controls; it cannot
promise that a model with native reasoning will stop reasoning. Use an explicit,
model-supported effort when needed.

Only one choice with `finish_reason: stop`, assistant role and nonempty string
`message.content` supplies action text. A refusal or content filter is refused;
`length` is truncated even if its partial text resembles a legal action. Tool
calls, pending/unknown finish states, missing choices and malformed JSON fail
closed. Private reasoning fields are ignored. Semantic failures retain observed
usage and identity in their sanitized attempt receipt.

Sources: [reasoning parameters and raw chat response](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning),
[Azure v1 OpenAPI](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/ai/data-plane/OpenAI.v1/azure-v1-v1-generated.json).

## Errors and retries

HTTP 400 maps to request rejected, except documented `content_filter` rejection
which maps to refused. 401 maps to auth failed, 403 to permission failed, 404
and 5xx to unavailable, 429 to rate limited. Malformed responses have a schema
failure; timeouts and transport failures preserve the shared attempt semantics.
Error prose, request headers and raw bodies are never copied into receipts.

Retries and action repairs default to zero. Opt-in shared safe retries require
an unambiguous 429 rejection body with recognized rate-limit classifiers and no
observed generation, usage or cost. Azure's numeric-string `429` or unknown error
classifiers are conservatively not replayed. Ambiguous timeouts, 5xx, malformed
bodies and accepted generations are never automatically replayed. `retry-after-ms`
is used when valid, otherwise the shared `Retry-After` parser applies. Every
physical attempt has its own receipt and index; no retry changes deployment or
endpoint. This is stricter than generic Azure backoff guidance.

Sources: [HTTP errors](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/troubleshoot-errors),
[quota and throttling](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota).

## Usage, region and privacy

The requested deployment stays in `model`; only response `model` can set
`locked_model_id` with `model_identity_source: provider_response`. An absent
identity remains null. A returned base-model ID does not attest a fixed model
version behind an upgradeable deployment. Core does not invent endpoint,
subscription or region attestations. Verify the deployment's model/version,
region and SKU in your Azure resource before use. Model/region availability and
quota depend on the subscription and deployment type.

`prompt_tokens`, `completion_tokens`, `total_tokens`, cached tokens and
`completion_tokens_details.reasoning_tokens` are normalized from Azure's wire
usage. Reasoning is included in completion tokens and is not added twice.
Missing/malformed usage remains unavailable or marked invalid. Error-body
observations remain quarantined diagnostics. No Azure price card is bundled;
cost remains unavailable unless separately configured with verified pricing.
Direct OpenAI prices must not be applied to Azure deployments.

Source: [raw response usage](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning).

Azure-hosted models sold by Azure run in Microsoft's environment and do not call
the publisher's service, including the direct OpenAI API. Microsoft says prompts
and completions are not available to other customers or model publishers and
are not used for foundation-model training without permission. Content filtering
and abuse monitoring still apply; selected material may be stored for human
review. `store: false` disables optional stored completions, not all service
retention or abuse monitoring. This adapter makes no zero-retention claim.
Public receipts and artifacts exclude credentials, headers, prompts, raw private
responses and reasoning text. Provider-supplied model and request/response/gateway
IDs containing the active credential or recognizable secondary credential patterns
are discarded before success or failure receipts are published. This includes
HTTP errors, malformed bodies and partial-body header observations. A discarded
model identity remains unknown with no identity source; sanitization does not
turn an ambiguous failure into a safely retryable rejection.

Global deployment processing may cross geographies; Data Zone processing stays
within the selected zone; Standard/Regional processing stays within the Azure
geography and may cross regions there. A resource hostname does not prove the
processing region. At-rest data and inference processing have different location
rules. Verify deployment and privacy terms for the chosen model and SKU.

Sources: [Azure data privacy](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy),
[deployment types](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types),
[models sold and hosted by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure).

## Fixture provenance

`tests/fixtures/provider/azure_chat_completions_success.json` is a redacted,
normalized copy of the documented Chat Completions response in Microsoft's
[reasoning guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning).
It preserves the documented envelope, token counts and model ID, replaces the
response ID/text with deterministic fixture values, and trims unrelated filter
categories. Fault fixtures mutate this envelope or documented Azure error
objects. These are offline protocol tests, not evidence of account access,
regional availability, live billing, model behavior or a completed Azure call.
