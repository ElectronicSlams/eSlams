# Red Hat AI Inference on IBM Cloud

This prospective 0.7.1 adapter runs in the unchanged 0.7.0 package. IBM Granite
is a model family, not a hosting endpoint. `ibm` and `ibm-granite` remain author
catalogue namespaces. The native `ibm-rhai` host (aliases `rhai`,
`redhat-ai-inference`, and underscore spellings) identifies **Red Hat AI Inference
on IBM Cloud**. It is separate from the watsonx adapter proposed in
[draft #260](https://github.com/ElectronicSlams/eSlams/pull/260).

IBM's [service overview](https://cloud.ibm.com/docs/inference?topic=inference-about)
describes managed, OpenAI-compatible inference. Its
[getting-started guide](https://cloud.ibm.com/docs/inference?topic=inference-getting-started)
demonstrates Granite with `granite-4-0-h-small`. That literal is an example,
not a default or a promise of current account access. Supply the exact host
model ID. Missing, blank or whitespace-padded IDs fail CLI resolution, agent
construction and preflight. No author-to-host alias, model substitution,
route fallback or automatic tool/search request is added.

## Configuration and endpoint

Core does not load `.env` files. Configure only the variables you intend to use:

```bash
export IBM_RHAI_REGION=us-east
export IBM_RHAI_PROJECT_ID='<your-project-id>'
# Set IBM_RHAI_API_KEY through your secret mechanism.
eslams providers preflight --provider ibm-rhai --model granite-4-0-h-small
eslams run --arena tic-tac-toe --agent ibm-rhai:granite-4-0-h-small --opponent first-legal
```

Configuration preflight is offline; running a game or explicitly adding `--live`
submits potentially billable inference. No credentials or inference were used
to develop this adapter. IBM requires a paid account and a project with Writer
service access for chat. It recommends a service ID API key; user API keys are
also documented. See [authentication](https://cloud.ibm.com/docs/inference?topic=inference-inf-auth).

The adapter sends `Authorization: Bearer <IBM_RHAI_API_KEY>` directly, as in the
getting-started example. There is no IAM exchange, token refresh or auth replay.
IAM bearer authentication is a separate documented option and is not configured
here. This differs from watsonx's API-key-to-IAM-token contract.

This adapter has one authentication credential: the active API key. It does not
create, fetch or send a secondary IAM token, refresh token or gateway secret.
Credential-echo tests cover both original and rotated active keys through
dispatch and preflight. Model discovery is an offline, unimplemented path and
does not authenticate. The project ID selects a resource; it is not a second
authentication credential.

Explicit `IBM_RHAI_REGION=us-east` selects:

```text
POST https://us-east.rhai.ibm.com/v1/projects/<project_id>/inference/chat/completions
```

The [API reference](https://cloud.ibm.com/docs/apis/inference), getting-started
guide and [chat guide](https://cloud.ibm.com/docs/inference?topic=inference-inf-chat-completions)
agree on that concrete path. The IBM-owned docs source at
[`5aa0dd31543049b08162dc32e014345492f022fe`](https://github.com/ibm-cloud-docs/inference/blob/5aa0dd31543049b08162dc32e014345492f022fe/inf-chat-completions.md)
has `lastupdated: 2026-10-30` and the same curl/SDK base URL. The guide's general
API label says `/v1/chat/completions`, and an
[IBM community example](https://community.ibm.com/community/user/blogs/lucas-palm/2026/07/13/red-hat-ai-inference-on-ibm-cloud-new-models)
instead appends `/inference/v1/chat/completions`. This discrepancy remains
unverified against a live account. The adapter pins the concrete API-reference
and guide path, without probing or trying alternate endpoints. Live endpoint
acceptance is a remaining operator check, not a fixture claim.

Only the documented public us-east host is implemented. Other regions,
private/VPC/on-prem endpoints, custom gateways and watsonx endpoints are outside
this adapter. The project path component must contain letters, digits or
hyphens; invalid values are rejected without echoing them. IBM documents a
Models API, but account discovery is not implemented; preflight says so and
does not invent visibility. Strict catalogue mode cannot attest new host rows.

## Wire behavior and limitations

The request carries `model` unchanged and developer/user `messages`. The user
message includes the full supplied public history through Core's prompt builder
unless the operator explicitly requests a history window. Explicit output
limits use `max_completion_tokens`; temperature is sent only when supplied.
Omitted controls leave native defaults in effect. No output ceiling, elapsed
thinking limit or arena-specific reasoning choice is added. Shared transport
still enforces its existing response-size, cancellation and explicit deadline
safety policies.

IBM delegates chat parameters and response fields to the
[OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
Only the non-streaming `chat.completion` envelope with one assistant text choice
and `finish_reason=stop` is accepted. Refusal, tool/function calls, truncation,
pending/null/unknown finish reasons, semantic errors, wrong roles and malformed
bodies fail before action parsing or repair. Private `reasoning_content` and
other response extensions are never action or receipt sources.

Granite's self-hosted model controls and watsonx's thinking parameters do not
establish this host's support. `reasoning=auto` preserves native defaults;
explicit enabled/disabled, effort and token-budget settings (including zero
and dynamic budgets) are rejected in configuration/live preflight before
discovery and in dispatch before transport. The adapter does not translate
or silently ignore an unsupported reasoning request.

Only response `model` attests identity; missing identity stays null. A different
or malformed identity fails while retaining sanitized evidence. A response model
alias is not treated as equivalent without a verified host mapping. No requested
model, author name or project ID is fabricated as resolved identity.

Usage preserves `prompt_tokens`, `completion_tokens` and reported `total_tokens`.
Missing/invalid totals stay unknown, with no derived substitute. IBM's hosted
docs do not attest reasoning inclusion or cache details; those fields stay
unknown even if an unverified compatible extension is present. No native USD
cost or host price card is invented from an author catalogue row. Complete
official accounting is therefore not established by numeric preflight success.
IBM's [billing FAQ](https://cloud.ibm.com/docs/inference?topic=inference-faq-b)
describes per-model input/output token charging and notes successful and
user-canceled operations are billable. It does not prove safe replay.

HTTP status errors retain shared classifications and Retry-After observations.
Default retries remain zero. Even explicitly configured optional retries do not
replay this host's errors: no verified safe rejection envelope has been
established. A timeout or partial response never proves remote work stopped.

Known credentials are removed from identifiers and recursively redacted in
receipt values and keys across successful, error, malformed and partial paths.
Transport prose is replaced with a fixed diagnostic, including when headers
were never observed. Credential-bearing action text is rejected before parsing
or action repair. Receipts exclude authorization headers, prompts, raw response
bodies, refusal prose and private reasoning.

## Fixture provenance and verification

`tests/fixtures/provider/ibm_rhai_chat_completions_success.json` is a redacted,
synthetic instance of the raw REST response example in the OpenAI reference
that IBM explicitly links as its chat contract. Model, IDs, content and token
counts are replaced with deterministic fixture values. It is not an IBM paid
capture or an SDK convenience property. Provider-specific tests cover endpoint,
auth, controls, full history, CLI/preflight/dispatch, identity/accounting gaps,
credential echoes, status errors, malformed/partial bodies, cancellation,
semantic failure and conservative retries. All provider calls are mocked;
the listener test file remains excluded from cloud suite execution.
