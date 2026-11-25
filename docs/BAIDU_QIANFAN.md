# Baidu Qianfan direct adapter

Implementation target: Core 0.7.1, based on 0.7.0 without a package version bump.
Official documentation checked 2026-11-04. Tests are deterministic and keyless;
they establish parser behavior, not live model/account availability.

## Configuration and region

Use `baidu:<exact-model-api-name>`, `qianfan:<exact-model-api-name>` or
`baidu-qianfan:<exact-model-api-name>`. All three resolve to provider `baidu`.
There is no default model, model-name rewrite or fallback. Additional colons in
a service API name are preserved. Missing, non-string and blank names are rejected
at agent construction and preflight, including through all CLI aliases.

Set `QIANFAN_API_KEY` in the process environment. Core does not load `.env` files.
Use a Qianfan ModelBuilder API key with the correct application resource scope;
legacy OAuth access-token/secret-key exchange is not used. Authentication is
`Authorization: Bearer <API Key>` with JSON request bodies. The documented
optional `appid` header is not exposed in this first adapter; use a key whose
resource scope permits the selected service without an explicit application
header. See [authentication](https://cloud.baidu.com/doc/qianfan-api/s/ym9chdsy5)
and [common headers](https://cloud.baidu.com/doc/qianfan-api/s/3m9b5lqft).

Direct calls use the domestic service at
`https://qianfan.baidubce.com/v2/chat/completions`. This is an account/endpoint
selection, not an attestation of a physical datacenter or data residency.
The separate [international API](https://intl.cloud.baidu.com/en/doc/qianfan/s/3m7of64lb-intl-en)
uses `https://api.baiduqianfan.ai/v1/chat/completions`; this adapter does not
select it, copy credentials there, or fail over between regions. Coding Plan,
Token Plan and legacy V1 model-specific endpoints are outside this adapter.
An explicitly configured existing Core gateway remains an operator-selected
transport override; it does not establish physical-provider identity.

Offline configuration check (no network or spend):

```bash
eslams providers preflight --provider qianfan --model YOUR_MODEL_API_NAME --arena tic-tac-toe
```

Only after deliberate account/spend authorization, a caller can use the normal
`providers models --provider baidu --live`, preflight `--live`, or
`run --agent baidu:YOUR_MODEL_API_NAME` commands. This change ran none of those
commands against Baidu.

## Wire and identity

The [domestic text API](https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb)
defines a POST containing `model`, `messages` and optional `stream`. Core sends
`stream: false` and includes the complete agent-visible request history in its
existing prompt. No previous private reasoning is added to history.

Only final `choices[0].message.content` text is parsed. Success requires one
assistant choice with `finish_reason: stop`. Length termination is truncation;
content filtering or a nonzero safety flag is refusal; tool calls are rejected.
These cases retain receipts and usage but cannot supply an action. Unknown or
missing completion fields fail closed. A response `model`, including an SFT
service's `model:version` form, is retained separately from the requested name.
Absent model identity remains null.

No output ceiling or model elapsed/read timeout is injected by default. Explicit
operator output limits map to `max_tokens`; provider-native constraints still
apply. Existing Core connection, response-size and cancellation safeguards remain.

## Reasoning

[Deep-thinking documentation](https://cloud.baidu.com/doc/qianfan-docs/s/Wm95lyynv)
provides distinct controls. Core's `auto` omits controls; `disabled` suppresses
Core injection, preserving the established 0.7.0 meaning. It does not assert
that intrinsic provider reasoning is disabled.

Explicit `enabled` maps to `thinking.type: enabled` or `enable_thinking: true`
only for the exact documented names frozen in `providers/baidu.py`. Unknown
names/controls fail before submission. `reasoning_effort` accepts `high`/`max`
for `deepseek-v4-pro`/`deepseek-v4-flash`; Core does not silently remap other
efforts. `reasoning_budget_tokens` maps to `thinking_budget` for `ernie-5.1`,
`ernie-5.0-thinking-preview` and `deepseek-v3.2-think`, with minimum 100 and no
Core-selected default. Provider maxima are enforced by Baidu. No arena changes
these settings.

Offline and live preflight validate the same reasoning controls as inference.
Unsupported explicit budgets fail before discovery or transport; supported
budgets are sent unchanged rather than replaced with an inferred default.

The guide states output usage includes reasoning. Accordingly,
`reasoning_included_in_output` is true. Documented reasoning detail is retained
without adding it twice; private `reasoning_content` never becomes action text,
receipt content or public explanation.

## Accounting, errors and retry

Only documented token fields are projected. Input, output, total, cached input
and reasoning counts remain null when absent; a missing total is not synthesized.
Contradictory or invalid counts retain existing usage-validation diagnostics.
No price or native cost is invented. Missing cost is `cost_unavailable`; any
existing explicitly supplied price-card mechanism retains its own provenance.

[The error reference](https://cloud.baidu.com/doc/qianfan-api/s/Om9b4yj3w)
uses `error: {code, type, message}` and optional `id`. HTTP status maps through
Core's transport classification: 400 request rejected, 401 authentication,
403 permission, 404 unavailable, 429 rate limited, and 5xx unavailable.
An error inside HTTP 200 also fails. Error prose stays private; observed usage
is quarantined and cannot attest model identity or trusted cost.

Default retries and action repairs are zero. Ambiguous timeouts, partial bodies,
5xx and Qianfan rate-limit envelopes are not automatically replayed, even with
an optional retry allowance: documented string error codes and an `id` do not
satisfy Core's narrow proof of a safe pre-generation rejection. `Retry-After`
is parsed if supplied; no undocumented retry/reset header is required or invented.
Each submitted attempt uses existing receipt custody and cancellation handling.

Before receipt publication, provider echoes of the selected API key and configured
Qianfan secondary/legacy credentials are removed across success, HTTP errors,
malformed bodies and partial-reader failures. Tainted request, gateway, response
and resolved-model identifiers become null; a removed model identifier also clears
its identity source. Credential-bearing final text is rejected before action
parsing, and discovery cannot publish credential-bearing model IDs. Normalized
usage and observed status survive this redaction. Secondary/legacy credentials
are redaction inputs only; they never become authentication fallbacks.

## Discovery and fixture provenance

[GET models](https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y) documents
`https://qianfan.baidubce.com/v2/models` with bearer authentication and a
`data[]` list of exact `id` values. The native adapter participates in existing
explicit live discovery/preflight. Catalogue warnings remain advisory unless
strict policy is selected. A discovery result does not pin a backend build.

`tests/fixtures/provider/baidu_qianfan_chat_completions_success.json` follows
the domestic text API's first non-streaming response example, retaining its
envelope, model, ID and usage. Only assistant text is replaced by synthetic
`{"action": 1}`. The ID is a published documentation example, not a live run.
Reasoning accounting tests follow the deep-thinking guide's
2 input / 544 output / 446 reasoning / 546 total example. Faults and privacy
markers in `tests/test_baidu_qianfan.py` are synthetic injections. Tests exercise
aliases, CLI, preflight, dispatch, actual bounded HTTP reading and Runner artifact
validation without contacting a provider.
