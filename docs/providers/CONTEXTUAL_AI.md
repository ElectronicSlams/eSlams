# Contextual AI Generate adapter

Research checked 2026-11-04 for the proposed 0.7.1 adapter; the package version
remains 0.7.0. No live inference or account credentials were used.

```bash
# Export your own key only when deliberately making a paid request.
export CONTEXTUAL_API_KEY=...
eslams providers preflight --provider contextual-ai --model v2 --arena tic-tac-toe
eslams run --arena tic-tac-toe --agent contextual-ai:v2 --opponent first-legal
```

Preflight without `--live` is offline. The run command and `--live` preflight
invoke the provider and may incur charges. Account availability, game performance
and suitability for a competition's identity/accounting requirements are unverified.

## Official contract and evidence

| Area | Verified contract and adapter behavior |
| --- | --- |
| Endpoint | `POST https://api.contextual.ai/v1/generate`, JSON; not `/chat/completions` or `/agents/{id}/query`. |
| Auth | `Authorization: Bearer <token>`; `CONTEXTUAL_API_KEY` follows the official Python client. |
| Region | Public documentation and the client specify the single host above, with no Generate region parameter. No geographic processing or residency guarantee is inferred. An explicitly configured Core gateway remains caller-owned. |
| Model | Required literal version; current reference names `v1` and `v2`. No default, alias substitution, model fallback or silently rewritten ID. Unknown explicit IDs may be submitted; availability is unverified. |
| Request | `model`, `messages` with `user`/`assistant` roles and final user message, required `knowledge`; optional `system_prompt`, `avoid_commentary`, `temperature`, `top_p`, `max_new_tokens`. |
| Text without retrieval | The provider-owned LangChain implementation defaults omitted knowledge to `[""]` and calls Generate directly. Core follows that shape, supplies no documents, and invokes no search, retrieval, agent workflow or tool. This is provider integration evidence, not a live success claim. |
| History | Shared game-neutral `/act` prompt contains the entire supplied public history. Explicit history truncation is rejected for this adapter. The prompt is one user message, with shared instructions in `system_prompt`. |
| Output | Raw success is `{"response":"<string>"}`. The fixture substitutes deterministic action JSON for that string. Only that envelope is accepted; unknown extensions fail closed rather than inventing semantics for error, finish or accounting fields. |
| Reasoning | No documented reasoning enable/disable, effort or budget controls. Only Core's `auto` is accepted; no extra reasoning prompt is injected. This makes no claim that internal reasoning is disabled. |
| Limits | Provider documents 32,000 total request tokens and `max_new_tokens` default 1024, range 1–2048. Core omits the output field by default; explicit operator limits in the documented range are forwarded unchanged. Provider defaults and constraints still apply. No framework total/read deadline is added; existing connection/resource safeguards remain. |
| Errors | Generate reference documents 422 `detail[]` entries (`loc`, `msg`, `type`). The official SDK also maps 400/401/403/404/409/422/429/5xx and transport/timeout exceptions. Core reuses its status taxonomy and safe transport, without publishing raw error messages or promoting undocumented body telemetry. |
| Retry | Core defaults to zero retries and zero action repairs. No automatic transport replay is allowed by this adapter, even with a nonzero retry maximum: the published contract supplies no definitive no-work rejection or idempotency guarantee. SDK defaults retry some failures twice; those defaults are not used. |
| Identity | Response has no resolved model/build field. `locked_model_id` and `model_identity_source` remain null; the requested body field does not attest the served model. |
| Usage/cost | Response has no token, cached-token, reasoning-token, reasoning-inclusion or cost fields. Usage stays empty, reasoning inclusion unknown, cost unavailable. Published token prices cannot establish per-request accounting. No billing API calls are made. |
| Completion | No published finish, refusal or truncation indicator is present in the success envelope. Core cannot attest that an otherwise valid `response` string was not truncated upstream. Unsupported envelopes and unparseable actions fail; no undocumented completion contract is assumed. |
| Discovery | No public Models API is established. Live model discovery returns unknown without network traffic; configuration-only readiness and mocked inference do not prove account visibility. |
| Privacy | Credential echoes in returned action text are rejected. Credential-bearing request IDs are removed on success, HTTP errors, malformed JSON and partial-body transport failures. Unknown response/error fields are not copied into receipts or action metadata. |

Primary sources:

- [Generate REST reference](https://docs.contextual.ai/api-reference/generate/generate)
- [Generate quickstart](https://docs.contextual.ai/quickstarts/generate) and
  [how-to](https://docs.contextual.ai/how-to-guides/generate)
- [Provider-owned text-only knowledge default](https://github.com/ContextualAI/langchain-contextual/blob/c82d03610ed96289187fc15673729da84d4ce95e/langchain-contextual/langchain_contextual/chat_models.py#L122)
  and [chat integration tests](https://github.com/ContextualAI/langchain-contextual/blob/c82d03610ed96289187fc15673729da84d4ce95e/langchain-contextual/tests/integration_tests/test_chat_models.py)
- Official Python client at `0ddf9547dd15cb595143424b15cb1328339c32cf`:
  [request types](https://github.com/ContextualAI/contextual-client-python/blob/0ddf9547dd15cb595143424b15cb1328339c32cf/src/contextual/types/generate_create_params.py),
  [response type](https://github.com/ContextualAI/contextual-client-python/blob/0ddf9547dd15cb595143424b15cb1328339c32cf/src/contextual/types/generate_create_response.py),
  [auth/default host/error mapping](https://github.com/ContextualAI/contextual-client-python/blob/0ddf9547dd15cb595143424b15cb1328339c32cf/src/contextual/_client.py),
  [retry documentation](https://github.com/ContextualAI/contextual-client-python/blob/0ddf9547dd15cb595143424b15cb1328339c32cf/README.md#retries).

The official documentation index advertises an OpenAPI JSON download, but that
download was inaccessible in this cloud run (proxy 403 and web-reader error).
The published REST page and pinned generated client types provide the contract
above. The agent platform's `should_check_retrieval_need` only conditionally skips
retrieval; it is not used as a replacement for direct inference.

## Fixture provenance and verification scope

`tests/fixtures/provider/contextual_generate_success.json` copies the documented
single-string REST envelope, replacing only the placeholder string with a
synthetic legal action. It is not a captured paid response. Fault injections
exercise HTTP errors, malformed/duplicate/extended JSON, missing accounting,
credential echoes, unknown identity, safe transport and partial bodies. CLI
dispatch and offline/mock-live preflight are tested without provider traffic.

Competitions requiring resolved identity, complete billing/usage or verified
completion need additional authoritative provider evidence. This adapter does
not establish those properties, and does not add speculative catalogue records.
