# Databricks native chat adapter

This adapter targets the documented Databricks Model Serving chat invocation
API. It is intended for the 0.7.1 adapter work; the package version remains 0.7.0.

## Configuration and identity

Set `DATABRICKS_HOST` to your explicit HTTPS workspace origin (AWS, Azure, or GCP)
and provide a caller-managed bearer token in `DATABRICKS_TOKEN`. No SDK profile,
cloud credential discovery, token minting, or refresh occurs. A workspace PAT or
an already obtained, appropriately scoped OAuth access token can be supplied.
The caller must have permission to query the endpoint. Configuration preflight
validates the host/name without contacting Databricks; it does not attest account
access. Token values are never stored in receipts.

```bash
# Set DATABRICKS_HOST and DATABRICKS_TOKEN in your environment first.
eslams providers preflight --provider databricks \
  --model my-exact-deployment --arena tic-tac-toe
eslams run --arena tic-tac-toe \
  --agent databricks:my-exact-deployment --opponent first-legal
```

The run command performs paid inference. A preflight with `--live` also invokes
inference; run those only after authorizing the cost and configuring credentials.
The implementation and its tests were verified without live inference.

`databricks`, `databricks-mosaicml`, and `databricks_mosaicml` select the canonical
provider `databricks-mosaicml` in CLI, preflight, and direct agent dispatch. A
serving endpoint name is mandatory. The adapter sends
`POST {DATABRICKS_HOST}/serving-endpoints/{exact-name}/invocations` with
`Authorization: Bearer ...` and JSON. There is no implicit deployment or region.
Names containing a catalogue prefix such as `databricks/databricks-gpt-oss-120b`
are rejected; choose the actual workspace deployment explicitly. The adapter
never strips prefixes, substitutes a model, probes alternate hosts, or falls
back to another provider.

The receipt's `model` is the requested deployment name. `locked_model_id` comes
only from response `model`, with `model_identity_source: provider_response`.
A safe `served-model-name` response header is retained as `served_model_name` on
the native adapter receipt; it identifies a served entity, not a model version.
Neither the requested deployment nor that header fills in a missing model ID.
Deployment routing can split traffic across models on the server. Operators
must configure and verify their deployment; this client cannot disable such
server-side routing. Core's existing official identity/accounting validation
still applies, and receipt observations do not attest immutable model weights.

Regional availability, capacity, and cross-region data processing depend on the
workspace, model, and account policy. No region is inferred or selected by Core.
Route-optimized URLs, Unity Gateway/model-service paths, custom MLflow prediction
schemas, embeddings, Responses, tools, and streaming are outside this adapter's
scope. Use the corresponding official contract when configuring those products.
There is no Models API discovery implementation here: live account visibility
remains `null`, and explicit live inference is decisive for action readiness.

## Wire behavior and reasoning

The request contains system instructions and the full agent-visible public
history in the user prompt, using Core's existing prompt construction. An
explicit operator history window is respected. `stream: false` selects the
bounded JSON transport. No output token or elapsed thinking ceiling is added;
provider defaults remain in effect. An explicit output limit becomes
`max_tokens`, and an explicit temperature is forwarded unchanged. Core retains
its existing response-byte bound and connection admission controls.

With default `reasoning: auto`, no reasoning parameter is sent. An explicit
`reasoning_effort` is forwarded unchanged for endpoint validation. `disabled`
sends `reasoning_effort: none`; models that do not support that choice reject it
without a retry that drops the control. `enabled` requires an explicit effort.
Anthropic/Gemini token-budget settings are rejected locally by this adapter.
There is no model-name heuristic, arena-specific reasoning, or default effort.

One assistant choice with `finish_reason: stop` is required. The API reference
also documents `finishReason`; the parser accepts either spelling and rejects
conflicting values. Null, absent, or unknown termination fails closed.
Text strings and typed `text` blocks are parsed; typed `reasoning` blocks are
excluded from action extraction. Tool output, reasoning-only output, malformed
JSON, and ambiguous/multiple choices cannot become actions. Refusal/filtering
and length/token truncation retain distinct outcomes even if the partial text
looks like a legal action. An omitted model ID does not prevent ordinary action
parsing, but remains unavailable for identity validation.

## Errors, retries, accounting, and privacy

The existing transport classifies 400 as request rejection, 401 as auth failure,
403 as permission failure, 404/5xx as unavailability, and 429 as rate limiting.
`Retry-After` is retained. Embedded error envelopes, malformed bodies, connection
errors, and timeouts also retain physical-attempt receipts. Default retries and
action repairs are zero. Explicit retry settings use Core's conservative policy:
only a proven, non-billable rate rejection can be retried; work observations or
an uncertain result prevent retry. There is no action/provider fallback here.

`prompt_tokens`, `completion_tokens`, and `total_tokens` map to input, output,
and total counts. Top-level `reasoning_tokens`, `cache_read_input_tokens`, and
`cache_creation_input_tokens` are retained. Missing counts stay unavailable;
this adapter does not derive a missing total or replace absent counts with zero.
Malformed counts and inconsistent totals remain validation errors. The docs do
not give a universal reasoning-inclusion guarantee across hosted/external
models; inclusion stays unknown and nonzero reasoning flags that ambiguity.
Reasoning is never silently added to the reported total or billed twice.
Catalogue token pricing cannot prove the billing of a workspace deployment, so
this adapter supplies no inferred cost. A rate-card label alone cannot make cost
complete. HTTP error-body accounting observations remain quarantined by the
existing receipt machinery.

Only selected identity, usage, and completion metadata enter receipts. Raw
response/error prose, reasoning text, prompts, and authorization headers are not
persisted. Tests use `httpx.MockTransport` through Core's real bounded transport,
with raw JSON bytes; they do not call a Databricks service.

## Official sources checked 2026-11-04

- [Serving endpoint query API](https://docs.databricks.com/api/model-serving-query/v1/query): invocation path, chat fields, response model and served-model-name.
- [Foundation model API reference](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/api-reference): chat format, typed content, usage and reasoning fields.
- [Query a chat model](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-chat-models): workspace chat deployment examples; distinguishes newer gateway routes.
- [Query reasoning models](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-reason-models): model-dependent effort controls and reasoning/text content blocks.
- [PAT authentication](https://docs.databricks.com/aws/en/dev-tools/auth/pat) and [OAuth service principals](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m): workspace host, caller tokens, and permissions.
- [Regional availability](https://docs.databricks.com/aws/en/resources/feature-region-support): model/workspace region restrictions and cross-region processing.
- [Limits and quotas](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/limits): distinction between 429 rate limits and 503 capacity errors.
- [Route-optimized endpoints](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-route-optimization): separate endpoint URL and OAuth requirements, excluded here.
