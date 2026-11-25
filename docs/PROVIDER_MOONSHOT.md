# Moonshot / Kimi native adapter

This adapter targets Core 0.7.1 while leaving the package at 0.7.0. Research was
verified against official documentation on 2026-11-04. No paid inference or
account discovery was performed. Tests substitute raw REST responses locally.

## Direct API and regions

The [global API overview](https://platform.kimi.ai/docs/api/overview) specifies
`POST https://api.moonshot.ai/v1/chat/completions` and
`GET https://api.moonshot.ai/v1/models`, authenticated with
`Authorization: Bearer $MOONSHOT_API_KEY`. JSON requests use `Content-Type:
application/json`. The adapter sends one non-streaming completion with the
requested model and Core's system instructions plus the full agent-visible
request history in its prompt. Each action is an independent API conversation;
the adapter does not keep a hidden assistant conversation or discard assistant
reasoning from an existing API conversation. Operator-selected history windows
retain Core's explicit opt-in semantics.

The [China API overview](https://platform.kimi.com/docs/api/overview) specifies
the same paths on `https://api.moonshot.cn`. The explicit `moonshotai-cn` alias
selects China for both discovery and inference. `moonshot-ai`, `moonshot`,
`moonshotai`, and `kimi` select global. Case and underscore normalization match
the registry. Receipts use canonical provider `moonshot-ai`; the endpoint kind
identifies the protocol, not a data-residency attestation.

The [authentication guidance](https://platform.kimi.ai/docs/api/errors) says
regional keys are independent. Never retry a failed global key against China
or vice versa. There is no region failover, provider fallback, model substitution,
or inferred backend identity. Core's existing explicit gateway configuration is
still available; it does not establish direct-provider identity.

## Models and reasoning

The [current model list](https://platform.kimi.ai/docs/models) lists
`kimi-k3.1-pro`, `kimi-k3.1-pro-highspeed`, and `kimi-k3`. The CLI default is
`kimi-k3.1-pro`. K2.6 and K2.7 Code variants are restricted to users registered
before November 1 and expected to be deprecated in late December 2026. K2.5,
K2 Thinking, `moonshot-v1-*`, and earlier preview models are deprecated.

The release-pinned registry is intentionally unchanged. New model names are
accepted as explicit operator selections in advisory mode, even when unknown to
that snapshot. Strict catalogue mode can reject them. Neither a registry row nor
configuration preflight proves account availability; live discovery/inference
requires separate authorization and credentials.

The [parameter reference](https://platform.kimi.ai/docs/api/models-overview)
defines these controls:

| Model family | Adapter reasoning controls |
| --- | --- |
| K3 / K3.1 Pro, including highspeed | Native reasoning always enabled; optional `reasoning_effort` is `low`, `high`, or `max`; omit to preserve the provider default. |
| K2.7 Code / highspeed | Native reasoning always enabled; omit `thinking`. |
| K2.6 | `auto` omits controls; `disabled` sends `thinking.type=disabled`; `enabled` sends `thinking.type=enabled, keep=all`. |

Disabling reasoning on always-thinking families, unsupported efforts, and token
thinking budgets fail before submission. For unknown models, auto mode forwards
the exact model and leaves provider defaults alone; explicit reasoning controls
require a verified family. There is no arena-based reasoning selection.
Temperature is omitted by default. An explicit operator temperature is forwarded
unchanged, so the provider can reject incompatible values without silent coercion.
Output `max_tokens` and elapsed/read time limits are omitted unless the operator
chooses them. Provider context, output, and service constraints still apply.

The [thinking guide](https://platform.kimi.ai/docs/guide/use-thinking-models)
requires retaining complete assistant messages including `reasoning_content`
when continuing a native API conversation. This adapter instead starts a fresh
conversation per Core action and supplies the full public game history; it does
not expose or persist private chain-of-thought in Core artifacts.

## Responses, usage, and privacy

The [Chat Completions REST reference](https://platform.kimi.ai/docs/api/chat)
defines `object=chat.completion`, `choices[].message`, `finish_reason`, model,
and usage. Only a single completed assistant string with `finish_reason=stop`
can produce an action. Length termination, filtered output, tool calls, invalid
JSON, and incomplete or malformed envelopes never yield a scoring-valid action.
Only final `message.content` is parsed; reasoning is never treated as an action.

Usage maps prompt/completion/total tokens, `completion_tokens_details.reasoning_tokens`,
and `prompt_tokens_details.cached_tokens/cache_write_tokens` into Core receipts.
Reasoning is already included in completion tokens; cache reads and writes are
subsets of prompt tokens. Counts are not added twice. Missing usage, missing
reasoning counts, and missing response model identity remain unknown. Unexpected
usage extensions and response cost fields are not treated as trusted evidence.
No new rate card or price is fabricated; existing Core pricing rules apply only
when sourced configuration exists.

Keys, headers, prompts, arbitrary provider prose, and raw reasoning never enter
sanitized receipts. A response `model` is recorded as provider-reported evidence;
it is not independently verified with the signature-verification API.
Provider-side retention is separate: the official
[ZDR policy](https://platform.kimi.ai/docs/guide/zero-data-retention) describes
an enterprise option that must be arranged server-side. The adapter cannot
enable or attest ZDR with a request flag.

## Errors and retries

The [official error reference](https://platform.kimi.ai/docs/api/errors) documents
400 safety/request errors, 401 authentication, 403 permissions, 404 missing or
inaccessible models, 429 rate/quota/overload, and server/connection failures.
HTTP 400 `content_filter` and response filtering produce `provider_refused`.
Other statuses retain Core's typed classifications and sanitized attempt receipts.

Core retries zero times by default. Explicit `max_retries` allows only an
unambiguous, fully observed 429 rejection whose classifiers agree and whose body
contains no generation, usage, or cost evidence. Documented
`rate_limit_reached_error` and `engine_overloaded_error` support that conservative
path with `Retry-After` and existing backoff. Quota errors, malformed/ambiguous
429s, timeouts, transport errors, and 5xx responses are not automatically replayed.
Every physical retry retains the same endpoint, model, and payload and receives
its own gap-free attempt receipt.

## Offline checks and fixture provenance

```bash
eslams providers preflight --provider kimi --model kimi-k3.1-pro --arena tic-tac-toe
eslams providers models --provider moonshotai-cn
python -m pytest tests/test_moonshot_adapter.py
```

These commands make no network inference calls. `--live` on preflight performs
discovery and inference and must be deliberately authorized. `providers models
--live` performs authenticated discovery only.

`tests/fixtures/provider/moonshot_chat_completions_success.json` follows the
official REST reference's non-streaming example (the 373 input / 112 output /
485 total, 90 reasoning, 256 cache-write example). Identity and private prose
are redacted; the answer is replaced with a legal-action JSON object. Fault
tests mutate that real envelope synthetically. Tests cover aliases and regions,
history, controls, success, refusal, truncation, HTTP faults, malformed bodies,
missing identity/usage, 429 custody/retries, timeout, privacy, and runner exclusion.
