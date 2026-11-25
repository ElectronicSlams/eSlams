# SenseTime / SenseNova direct adapter

Research checked **2026-11-04** for the planned 0.7.1 adapter work; package version
remains 0.7.0. This is the current **Token Plan** API contract. It is not the
older SenseCore JWT service and does not use OpenRouter.

## Official evidence

- [SenseNova 6.8 API guide, pinned commit
  11de698940848156cbd25858d44be43ac0a1704f](https://github.com/OpenSenseNova/SenseNova6.8/blob/11de698940848156cbd25858d44be43ac0a1704f/API.md):
  sections 1, 3–6, 9–10 cover credentials, model ID, request/response, reasoning,
  conversation history, SDK compatibility and errors.
- [SenseNova 6.7 API guide, pinned commit
  71a30cf8ef19437f3381c39263265d5028c14291](https://github.com/OpenSenseNova/SenseNova6.7/blob/71a30cf8ef19437f3381c39263265d5028c14291/API.md):
  corroborating earlier Token Plan contract and exact `sensenova-6.7-flash-lite` ID.
- [Official Token Plan](https://platform.sensenova.cn/token-plan) and
  [console](https://platform.sensenova.cn/console): registration and identity
  verification precede API key creation. Account access and quotas are conditional.
- [Older SenseCore API](https://console.sensecore.cn/micro/help/docs/model-as-a-service/nova/vision/ChatCompletions/)
  documents `/v1/llm/chat-completions`, `max_new_tokens`, a `data` envelope and
  different reasoning fields. Those fields are deliberately not mixed into Token Plan.

| Concern | Verified contract / boundary |
| --- | --- |
| Endpoint | `POST https://token.sensenova.cn/v1/chat/completions` |
| Authentication | `Authorization: Bearer <API key>`; `SENSENOVA_API_KEY` locally |
| Region | The official guide supplies this `.cn` endpoint, with no region parameter or alternate regional host. This establishes the configured host, not a data residency guarantee. No global endpoint is inferred. |
| Model | Guide names `sensenova-6.8-flash-lite` as a preview; exact account availability may change. An operator must supply a nonblank model ID. |
| Response | `choices[0].message.content`; `id`, `request_id`, `model` are separate evidence fields |
| Reasoning | `message.reasoning` is separate from the answer; the guide advises omitting it from conversation replay. No verified hosted reasoning switch/effort/budget is specified. |
| Tokens | `prompt_tokens`, `completion_tokens`, `total_tokens`, and optional cached-input detail. Output includes reasoning; a separate reasoning count is not guaranteed. |
| Errors | Guide lists 400, 401, 403, 404, 429 and 5xx with an `error` object; its example uses a string application code `"5"`, which is not an HTTP status. |

## Use

```bash
# Export SENSENOVA_API_KEY securely only when intentionally making a live call.
eslams providers preflight --provider sensenova \
  --model sensenova-6.8-flash-lite --arena tic-tac-toe
eslams run --arena tic-tac-toe --agent sensetime:sensenova-6.8-flash-lite
```

The preflight command above is offline; the run command makes inference calls.
Explicit `--live` preflight also makes inference calls and may incur charges.
`sensetime`, `sensenova`, `sense-nova` and `sense-time` select the same native
adapter. Receipts use canonical provider `sensetime`; model IDs retain their
exact spelling. There is no default model substitution and no fallback.

The adapter sends the ordinary Core system instruction plus the agent-visible
request, including its entire public history by default. An explicit operator
history window still uses Core's existing policy. It does not adopt the guide's
suggestion to truncate history automatically. Sampling and output limits are
omitted unless explicitly chosen. `max_output_tokens` maps to `max_tokens` and
Core's existing optional elapsed/read deadlines apply. The shared connection
timeout and response byte safety boundary are retained.

Only `reasoning="auto"` with no effort or budget controls is accepted. An
explicit unsupported control, including disabling reasoning, fails in both
configuration preflight and transport without submission. No game label selects
reasoning or sampling parameters. Returned reasoning is never action text,
history, public explanation, or receipt material.

## Integrity, retry and accounting

One assistant text message with `finish_reason="stop"` is required. Legal-looking
partial text with `length` is rejected as `provider_output_truncated`; a filtered
or refusal response is `provider_refused`. Unknown or malformed finish fields,
legacy envelopes and tool-only results fail closed. HTTP-200 error envelopes
are inspected before action parsing. Refusal extensions are defensive handling
of the compatible protocol; the guide does not enumerate every refusal shape.

The shared transport maps HTTP 401 to authentication failure, 403 to permission
failure, 429 to rate limiting, 404/5xx to unavailable, and other 4xx to rejection.
Errors never publish provider prose. Each attempted call retains a receipt.
Default retries and action repairs are zero. Although the guide recommends
backoff for rate limiting, Core retries only an explicitly enabled, definitive
429 rejection without evidence of accepted work. Ambiguous timeouts, transport
failures, 5xx, refusal and truncation are never replayed automatically.

Absent returned model identity stays null. A different returned model ID fails
closed; it never silently becomes the requested model. Missing token counts,
cache counts and reasoning counts remain unknown. Existing Core usage
validation and derived-total provenance apply. No pricing, currency conversion,
or zero-cost assumption is inferred from a free-plan advertisement. This
adapter has no verified rate card; cost remains unavailable. Credential echoes
are removed from receipt identifiers on success and failure, including legacy
secondary SenseNova/SenseTime secret environment values.
The same primary and secondary credentials are checked in final action text,
decoded JSON fields, keys and prose, including Unicode escapes. An echo rejects
the response before action parsing, explanation publication or action repair;
the sanitized failure receipt retains observed usage and response evidence.

No Models API is established by these pinned guides. Core reports discovery
unavailable and leaves account visibility unverified, rather than inventing a
catalogue. The frozen model registry is not rewritten; ordinary configuration
preflight allows exact unknown IDs and strict catalogue mode retains its
existing admission rules.

## Availability and local evidence

Official guides and the Token Plan page were retrievable on 2026-11-04. A
credential-free HEAD request to the inference route from Codex cloud failed at
the egress proxy (`CONNECT` HTTP 403); a web read of `/v1/models` was also
inaccessible. Neither proves a provider outage or successful service. No
provider credential was read, no account login performed, and no paid or free inference
was attempted. Account entitlement, live response shape, quotas, regional
access and billing remain unverified.

`tests/test_sensenova_provider.py` uses synthetic raw-wire fixtures based on the
official response envelope, never claimed live captures. It covers aliases
through CLI, registry, preflight and dispatch; exact model identity; full history;
omitted defaults; explicit limits; reasoning rejection; malformed JSON; refusal;
truncation; HTTP/body errors; conservative retry; missing/invalid usage; and
primary/secondary credential echoes in every receipt path.
Discovery tests also prove that its unsupported route neither reads credentials
nor makes a network request. Action-text and live-preflight tests cover raw and
escaped credential echoes without publishing the affected answer.
