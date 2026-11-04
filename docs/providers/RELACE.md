# Relace Open Models adapter

This adapter targets Relace's direct Open Models service, using an explicit
`relace:<model-id>` agent. It does not invoke Apply, Compact, Search, a hosted
agent harness, tools, or web search. No model default, alternate model, or
alternate provider is selected. A different attested response model fails the
request; missing identity remains unknown.

```bash
export RELACE_API_KEY=...
eslams providers preflight --provider relace \
  --model deepseek-ai/DeepSeek-V4-Flash-0731 --arena tic-tac-toe
eslams run --arena tic-tac-toe \
  --agent relace:deepseek-ai/DeepSeek-V4-Flash-0731 --opponent first-legal
```

The first command is offline. The second calls paid inference when a real key
is configured. Explicit `providers models --provider relace --live` performs
account discovery; explicit live preflight also performs inference. Tests use
fictional keys and mocked HTTP only.

## Verified official contract

Checked 2026-11-04:

- [Open Models guide](https://docs.relace.ai/docs/open-models/quickstart):
  Relace hosts open-weight models in addition to its specialist code models.
  It documents direct SDK calls and a non-code prose example. This establishes
  a general text interface; text-game performance has not been measured.
- [Chat Completions reference](https://docs.relace.ai/api-reference/open-models/chat-completions):
  `POST https://models.relace.ai/v1/chat/completions`, JSON body, Bearer
  authentication with the Relace key. Required fields are `model` and
  OpenAI-format `messages`. The adapter sends system instructions and the full
  supplied history in the public game request, with `stream: false`. It reads
  `choices[0].message.content`, requires one complete `stop` choice, and rejects
  refusals, truncation, tool requests, and malformed completions. Response
  `model` alone supplies model identity; requested ID is never substituted.
  The documented usage fields are `prompt_tokens`, `completion_tokens`, and
  `total_tokens`, with automatic cache hits in
  `usage.prompt_tokens_details.cached_tokens`. Reasoning counts against output
  limits. Missing token categories stay unknown; arbitrary cost extensions
  are not accepted as billing evidence.
- [List Models reference](https://docs.relace.ai/api-reference/open-models/list-models):
  authenticated `GET https://models.relace.ai/v1/models` returns account-visible
  IDs, supported parameters and current per-token rates. Static catalogue
  membership is advisory. This change does not fetch prices automatically or
  install a rate card; costs without verified pricing remain unavailable.
- [Error reference](https://docs.relace.ai/api-reference/errors):
  chat errors use an OpenAI error object, with upstream error bodies sometimes
  passed through. Status is authoritative. Relace documents transient 429,
  502, 503 and 504, one retry for 500, and honoring `Retry-After`. Core keeps
  its stricter physical-attempt policy: zero retries by default; optional
  retry only after a definitive, complete rate-limit rejection without work
  evidence. Ambiguous transport failures, timeouts and server errors are
  never automatically replayed. Errors preserve sanitized observed receipts.

## Limits and evidence gaps

Only native reasoning defaults (`reasoning=auto`, no effort/budget) are accepted.
The reviewed Chat Completions schema does not establish a concrete reasoning
control mapping. The catalog's boolean reasoning capability is insufficient to
invent that mapping. Explicit enable/disable/effort/budget settings fail before
HTTP. No game-specific reasoning policy is introduced.

Full supplied history is mandatory. `history_window_turns` and gateway/other
provider routing overrides are rejected. Omitted output and thinking limits
remain omitted; explicit operator output, deadline and temperature choices use
Core's existing transport. Provider-imposed limits still apply.

The reviewed sources establish one public hostname, not regional routing or
physical data residency. There is no fabricated region or backend-provider
attestation. Relace remains the selected API provider; the response model is
recorded separately. The API does not establish a fixed physical backend.

Credential echoes are removed from receipt identifiers on success, HTTP error,
malformed JSON and interrupted bodies. Credential-bearing action text is
rejected, including decoded JSON and common URL/Unicode escape forms. Raw
provider bodies and headers are never copied into action metadata or receipts.

## Fixture provenance

`tests/fixtures/provider/relace_chat_completions_success.json` is a synthetic,
secret-free fixture adapted from the documented Chat Completions envelope,
content access in the Open Models guide, and documented cache accounting. Its
IDs and counts are illustrative, not a live response or availability claim.
`tests/test_relace_native.py` covers raw envelopes, CLI/preflight/dispatch,
accounting/identity gaps, controls, and credential boundaries. It also exercises
an interrupted HTTP body through the real bounded transport with MockTransport.
