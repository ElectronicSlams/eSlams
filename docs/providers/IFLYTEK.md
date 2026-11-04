# iFlytek Spark direct HTTP adapter

Research checked 2026-11-04 against the official Chinese-site documentation:

- [Spark HTTP](https://www.xfyun.cn/doc/spark/HTTP调用文档.html), sections 2–4.
- [Spark X2 HTTP](https://www.xfyun.cn/doc/spark/X1http.html), updated 2026-02-09,
  sections 1–4. The URL still contains `X1`; the current page describes X2.
- [WebSocket authentication](https://www.xfyun.cn/doc/spark/general_url_authentication.html).

## Routing and identity

| Exact requested model | Direct POST endpoint |
| --- | --- |
| `spark-x` | `https://spark-api-open.xf-yun.com/x2/chat/completions` (X2) |
| `lite`, `generalv3`, `pro-128k`, `generalv3.5`, `max-32k`, `4.0Ultra` | `https://spark-api-open.xf-yun.com/v1/chat/completions` |

The adapter accepts canonical provider `iflytek` and aliases `spark`,
`iflytek-spark`, `xfyun`, including uppercase spellings. Model spelling and case
are preserved. Unverified model/endpoint pairs fail before transport. There is
no model fallback or cross-provider routing.

These are the official Chinese-site endpoints. The HTTP documents expose no
region selector or processing-location attestation. This adapter cannot promise
regional residency, international-account eligibility, or account availability.
No region is inferred from a hostname. No Models API is documented; discovery
returns unavailable, and preflight leaves account visibility unverified.

The X1.5 endpoint `/v2/chat/completions` also uses `spark-x`. It is deliberately
outside this adapter's routing table; the same wire name must not silently select
another service. The historical `x1` identifier is not accepted. The v1 page
announces that Max is being upgraded to Ultra and Ultra to X1.5 fast thinking;
the old names are mutable service IDs, not immutable backend attestations.
Receipts preserve the requested name, retain `sid` as the response ID, and leave
resolved identity null unless an actual response `model` is supplied. Error-body
identity remains unverified even when HTTP status is 200.

## Credentials and requests

Export `IFLYTEK_API_PASSWORD` with the HTTP APIPassword for the selected service.
The request uses JSON and `Authorization: Bearer <APIPassword>` over verified
HTTPS. Core never loads `.env` automatically. Do not reuse a bare WebSocket API
key. X2's official example also permits an `APIKey:APISecret` credential string;
Core passes an explicitly supplied valid HTTP credential unchanged, but never
assembles, discovers, or reads additional credential variables.

The separate WebSocket protocol uses AppID/APIKey/APISecret and an RFC1123 date,
HMAC-SHA256 over host/date/GET request-line, then Base64 authorization in the
handshake URL. That signature does not apply to this HTTP adapter.

Requests use `stream: false`; generic action instructions and the complete
serialized agent-visible request/history are in one user message. This avoids
assuming system-role support on every model. Built-in web search is explicitly
disabled on supported routes; Lite has no search control. No tools are executed.
No JSON-mode instruction, domain-specific reasoning rule, or new history window
is added. An operator's existing history window remains an explicit runtime
choice.

No default `max_tokens`, sampling override, total timeout, read timeout, or
thinking budget is added. Explicit output limits and valid temperatures pass
through. Provider constraints/defaults still apply. Existing Core connection,
response-byte, concurrency, cancellation and deadline protections are reused.

For X2, `reasoning=auto` omits `thinking`, preserving its documented native
default of enabled. Explicit enabled/disabled maps to `thinking.type` unchanged.
Core's `auto` means preserve provider policy, not force Spark's distinct
`thinking.type=auto`. v1 rejects explicitly enabled reasoning. Effort and budget
controls unsupported by Spark are rejected before transport.

## Responses, errors and accounting

The parser consumes raw `code`, `sid`, `choices[0].message.content`, and `usage`.
Only assistant answer text can become an action; `reasoning_content` never enters
receipts or public explanations. The documented v1 success envelope lacks a
finish reason, so no stop reason is invented. X2's `status: complete` is accepted.
Supplied incomplete/unknown states, truncation, filtering, tool calls and
business errors reject even legal-looking answer text. SSE is not parsed by the
non-streaming adapter.

HTTP 400/401/403/404/429/5xx receive the existing normalized outcomes. X2's
business codes are classified independently of HTTP status: 10013/10014/10019
are refusal/filtering, 10007/11201/11202/11203 are rate/concurrency/quota limits,
11200 is permission/entitlement failure, and 10907 is rejected input context.
Unknown nonzero codes fail closed. Messages and raw private bodies are never
copied into public errors. Error-body accounting is quarantined by the shared
receipt policy. Retry-After is retained as diagnostic data.

Default retries and action repairs are zero. Spark's documents do not establish
safe replay or idempotency, so this adapter does not automatically retry even
with an optional retry maximum. A 429 can also mean exhausted quota.

Only reported integer prompt/completion/total counters are retained. Missing
totals are not reconstructed; malformed or inconsistent counters are marked.
The docs do not establish separate reasoning/cache accounting or reasoning
inclusion, so those fields remain null. Unexpected search expansion is marked
unsupported. No price, USD conversion, billed cost, or complete official
accounting is invented. A successful action is not proof of complete billing.

## Offline use and verification

```bash
eslams providers preflight --provider spark --model spark-x --arena connect-four
eslams run --help
python -m pytest tests/test_iflytek_provider.py
```

Configuration preflight and deterministic tests make no paid inference calls.
An explicitly requested `--live` preflight would submit inference and may incur
charges; none was run for this implementation.

The two `tests/fixtures/provider/iflytek_*_success.json` fixtures preserve the
official non-streaming envelopes/counters with synthetic answer, reasoning and
session IDs. Fault injection covers HTTP/business failures, refusal, truncation,
malformed JSON, timeout, usage gaps, privacy, exact routing and all aliases
through CLI/preflight/dispatch. No SDK convenience properties are fixtures.
