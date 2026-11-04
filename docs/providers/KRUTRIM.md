# Krutrim direct inference adapter research

Researched 2026-11-04 for the 0.7.1 adapter work, against Core base
`270a863d10d57a0953f21924f1a0dd50159e6cf1` (package remains 0.7.0).

## Official evidence and service boundary

Krutrim operates a direct text inference service. Its current
[inference guide](https://docs.cloud.olakrutrim.com/basics/ai-studio/ai-jobs/inferencing)
shows the OpenAI Python client pointed at `https://cloud.olakrutrim.com/v1`.
The operator's [raw HTTP example](https://github.com/ola-krutrim/ai-cloud/blob/fa812ede7db271476083240edcfbba9d464a6f09/samples/API/README.md)
spells out the chat endpoint, Bearer authentication, system/user messages and
generation parameters. That sample dates to 2024; it is corroborated by the
operator's SDK at **`6c01ffa0dffd151b08dd7fdd65d3f7e931ed6e2a`**, dated
2026-10-07, linked from the current
[AI Studio SDK guide](https://docs.cloud.olakrutrim.com/sdk-guide/ai-studio-sdk).

This adapter calls the operator's service. The author of a model hosted by that
service may be another organization. A third-party router serving Krutrim weights
would be a different provider route and is not implemented here. The official
[Krutrim-2 weights and model card](https://huggingface.co/krutrim-ai-labs/Krutrim-2-instruct)
describe downloadable model execution; their repository ID does not establish a
hosted API model ID. Kruti consumer/agent functionality and
[Cloud MCP](https://docs.cloud.olakrutrim.com/mcp/hosted-mcp) are separate interfaces.
Dedicated/BYOM deployments described in the
[deployment guide](https://docs.cloud.olakrutrim.com/basics/ai-studio/ai-jobs/deployment)
also have separate provisioning and account requirements; this adapter does not
provision resources or guess a deployment endpoint.

## Contract and deliberate unknowns

| Concern | Verified contract / adapter behavior |
| --- | --- |
| Endpoint | `POST https://cloud.olakrutrim.com/v1/chat/completions`; fixed direct HTTPS destination, no gateway override or router controls. |
| Authentication | `Authorization: Bearer <key>`, JSON body. Core reads `KRUTRIM_CLOUD_API_KEY`, the SDK-documented environment name. No automatic credential creation or refresh. |
| Key scope | The current [API-key guide](https://docs.cloud.olakrutrim.com/basics/key-management-system/model-api-keys) describes general API keys; permissions and service access remain account-dependent. |
| Region | The text inference request in the SDK and direct example has no region parameter. Neither the hostname nor unrelated infrastructure region names attest inference residency. Region, residency and backend placement remain unverified. |
| Model | Caller must supply a nonblank, exact, case-sensitive operator model ID. No default model, normalization, substitution, catalogue prerequisite or fallback. The guide's `krutrim-1` and SDK's `Krutrim-spectre-v2` are examples, not proof of current account availability. |
| Request | Explicit model, system instruction and user text containing the full supplied public history; `stream: false`. Optional caller temperature and `max_tokens`; no implicit output or thinking cap, tools, search, reasoning prompt or model discovery. |
| Response | One `choices[]` item, index 0, assistant `message.content` string and `finish_reason: stop`. Tool/function calls, missing/unknown finish state, wrong roles, multiple choices, malformed JSON and nontext content are rejected. |
| Identity | Only a safe response `model` attests resolved identity, with source `provider_response`. Missing/invalid/credential-bearing identity remains null. A requested model never attests itself. No physical-backend/version-lock claim. |
| Reasoning | No reasoning control is documented in the inspected SDK or inference guide. Only `reasoning=auto` is accepted. Explicit enabled/disabled modes, effort or budgets fail locally. This is no assertion that the model cannot reason. |
| Usage | The generated SDK response schema has no usage field. Missing counters stay unknown. Optional OpenAI-compatible `usage.prompt_tokens`, `completion_tokens`, `total_tokens` are recorded only if actually supplied as nonnegative integers; totals are never derived. Reasoning/cache counts, inclusion semantics, rates and costs remain unknown. No billable completeness claim. |
| Errors | Shared conservative HTTP classification: 400/other 4xx rejection, 401 auth, 403 permission, 429 rate limit, 404/5xx unavailable. These are local classifications, not a verified Krutrim error-body specification. Error prose is not exported. Error-body telemetry remains quarantined by shared receipt provenance. |
| Retry | Default zero retries/repairs. No Krutrim error envelope inspected establishes that a rejected request did no work; adapter errors therefore never authorize automatic HTTP replay, even with a nonzero retry maximum. Timeouts/partial bodies never prove cancellation. |
| Transport/privacy | Shared bounded nonstreaming transport, byte limits and caller-selected deadlines; no default read/thinking deadline. Exact credential echoes are removed from receipt values and keys, including IDs and malformed/partial failures. Generated action/explanation echoes are rejected, including JSON escapes. |

The privacy filter captures the selected credential environment plus other
Krutrim-named API-key, token, secret, password and credential environment values
for each action. These secondary values are used only for redaction, never as
authentication fallbacks. The snapshot remains available if a key changes while
the response is in flight. It covers receipt keys/values, response/request IDs,
resolved identity, sanitized exceptions and complete decoded action payloads,
including unused JSON fields and escaped strings. Raw exception chains are
suppressed because they can carry private transport headers or malformed bodies.

The operator SDK sources used to pin the wire contract:

- [Client base URL, credential environment and Bearer header](https://github.com/ola-krutrim/krutrim-cloud-python/blob/6c01ffa0dffd151b08dd7fdd65d3f7e931ed6e2a/src/krutrim_cloud/_client.py)
- [Chat resource and accepted parameters](https://github.com/ola-krutrim/krutrim-cloud-python/blob/6c01ffa0dffd151b08dd7fdd65d3f7e931ed6e2a/src/krutrim_cloud/resources/chat/completions.py)
- [Generated response envelope](https://github.com/ola-krutrim/krutrim-cloud-python/blob/6c01ffa0dffd151b08dd7fdd65d3f7e931ed6e2a/src/krutrim_cloud/types/chat/completion_create_response.py)

The documentation index links Model Catalog API and KrutrimConnect pages, but
their content could not be retrieved through the available web reader; direct
cloud retrieval returned a proxy 403. No model-list endpoint, error schema,
region promise, reasoning setting, current model inventory or pricing contract
was inferred from those unavailable pages. No authenticated endpoint or paid
inference was probed. API availability for an actual account remains unverified.

## Use and keyless verification

Configure the key privately in your execution environment. Never paste it in a
command example, prompt, artifact or shared configuration. Copy the exact model
ID from your account's model card/starter code. Configuration-only preflight:

```bash
eslams providers preflight --provider krutrim --model '<exact-model-id>' --arena tic-tac-toe
```

Select an agent using `--agent-1 'krutrim:<exact-model-id>'`. A run or an explicit
`--live` preflight submits inference and may incur charges. Live account access
has not been tested here. The adapter exposes no verified Models API, so live
preflight keeps account visibility unknown. Strict catalogue mode remains an
operator opt-in and can reject IDs absent from the frozen local catalogue.

`tests/fixtures/provider/krutrim_chat_completions_success.json` is a synthetic,
redacted instance of the official generated REST envelope above. It is not a
captured paid response or an SDK convenience property. Its response identity,
timestamps and action text are test data; usage is absent as in the generated
schema. Fault-injection tests add optional counters, errors, secret echoes and
partial/malformed responses without representing them as observed live results.

Tests cover CLI dispatch, offline and mocked live preflight, full history,
explicit output/timeout controls, exact identity, missing/partial/malformed usage,
400/401/403/404/429/5xx, timeout/transport/bounded-body failures, partial response
headers, semantic truncation/refusal/tool calls and credential echoes. A keyless
runner test validates generated artifacts and receipt custody. All HTTP calls
are deterministic in-process stubs; no listener or real-transport acceptance is
claimed. The inherited denied elapsed-deadline listener file is excluded under
the existing release offline policy, without executing it or opening its listener.
