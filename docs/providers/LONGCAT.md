# Meituan LongCat native adapter

Prepared for the 0.7.1 adapter series on Core 0.7.0; no package version change.
Official documentation checked **2026-11-04**. No account, credentials, model
discovery request or paid inference was used for verification.

## Official contract and evidence

| Topic | Official source | Verified contract / limitation |
| --- | --- | --- |
| Endpoint, authentication, errors | [API overview](https://longcat.chat/platform/docs/api-docs) | HTTPS `POST /openai/v1/chat/completions` on `api.longcat.chat`; `Authorization: Bearer <key>`. HTTP 400 invalid request, 401 authentication, 402 quota, 403 permission, 429 rate limit, 500/502 service failures. |
| Request and response | [Chat Completions](https://longcat.chat/platform/docs/api/chat) | Exact `model`, text `system`/`user`/`assistant` messages, optional `max_tokens`, `stream:false`; response `model`, `id`, `choices[].message.content`, `reasoning_content`, `finish_reason`, and `usage`. Current documented model: `LongCat-2.5`. |
| Reasoning and limits | [Model parameters](https://longcat.chat/platform/docs/api/model-params) | `thinking:{type:enabled/disabled}` and `thinking_budget`; `length` denotes truncation. Context 1,048,576; output maximum 262,144. Temperature fixed by thinking state (1.0 enabled, 0.7 disabled); other values are overridden server-side. These are provider constraints, not Core defaults. |
| Discovery and identity | [Models](https://longcat.chat/platform/docs/api/models) | Bearer-authenticated `GET /openai/v1/models`; `data[].id`. The list establishes advertised IDs, not proof that a particular inference used one. |
| Rate limiting | [Quick start](https://longcat.chat/platform/docs/) | HTTP 429 example has `error.code:rate_limit_exceeded`, `type:rate_limit_error`, numeric `retry_after` seconds. The provider recommends backoff. Core retains zero retries by default. |
| Accounts and billing | [FAQ](https://longcat.chat/platform/docs/FAQ.html) | Mainland and international registration differ. FAQ says failed HTTP responses are uncharged; Core still records unknown cost rather than claiming a measured zero. The FAQ includes an inconsistent `/openai/native/chat/completions` spelling; the dedicated API reference and quick start agree on `/openai/v1/chat/completions`, which this adapter uses. |
| Region and privacy | [API Platform privacy policy](https://longcat.chat/platform/private/policy) | The platform identifies Beijing Kuxun Interactive Technology Co., Ltd. and affiliates; processing/transfers may involve Frankfurt, Hong Kong and mainland China. No selectable inference region or per-request residency guarantee was established by these API docs. The adapter has no region selector. |

The provider exposes OpenAI-compatible wire formats. The route remains Meituan's
native service; it does not use OpenAI, OpenRouter, an SDK, or a substitute model.
Anthropic and Responses endpoints exist but are outside this adapter's scope.
Images, tools, streaming and structured-output controls are also outside scope.

## Configuration and use

Canonical provider: `meituan`. Aliases: `longcat`, `meituan-longcat` (case
insensitive, underscore spelling accepted). Aliases normalize the provider only;
the model string is preserved byte for byte, including case, slashes and colons.
There is **no default model**: select one explicitly. Missing, empty and
whitespace-only IDs fail before registry lookup in direct construction and
preflight, as well as in the CLI. Nonblank IDs remain unchanged.

Configure `LONGCAT_API_KEY` in the process environment only when deliberately
making a live call. Core does not automatically read `.env` files.

Offline configuration check (no credentials or inference required):

```bash
eslams providers preflight --provider longcat --model LongCat-2.5 --arena tic-tac-toe
```

The following commands contact the provider and may consume quota; they were
not run during development:

```bash
eslams providers models --provider meituan --live
eslams providers preflight --provider longcat --model LongCat-2.5 --arena tic-tac-toe --live
eslams run --arena tic-tac-toe --agent longcat:LongCat-2.5 --opponent first-legal
```

Discovery is advisory unless `--strict-catalogue` is requested. New or unlisted
model IDs are forwarded unchanged. The documented model has a local capability
record; API availability remains account-dependent until observed live.

## Execution policy

The adapter sends the ordinary shared system instructions and full public
`ActRequest` prompt, including every supplied history record by default. It
does not reconstruct private conversations, insert game-specific reasoning,
change model IDs, reroute, or fall back to another provider. An explicitly
configured shared `history_window_turns` remains an operator choice.

Default `ProviderRuntimeConfig(reasoning="auto")` omits `thinking` and
`thinking_budget`. `enabled` and `disabled` map directly to `thinking.type`,
independent of arena or catalogue knowledge. Explicit `reasoning_budget_tokens`
maps unchanged to `thinking_budget`; explicit temperature is forwarded and may
be overridden by the provider as documented. Unsupported `reasoning_effort` and
`gemini_thinking_budget` fail before submission with `provider_request_rejected`;
offline and live preflight also reject these explicit controls before discovery.
This includes zero and automatic Gemini budgets, not just positive values.
Native `reasoning_budget_tokens` remains supported and is forwarded unchanged.
Conflicting disabled reasoning and budgets are rejected by the existing runtime
contract. Example Python configuration:

```python
from eslams.agents import ModelProviderAgent
from eslams.contracts.provider import ProviderRuntimeConfig

agent = ModelProviderAgent(
    provider="longcat",
    model="LongCat-2.5",
    api_key_env="LONGCAT_API_KEY",
    runtime_config=ProviderRuntimeConfig(reasoning="enabled"),
)
```

No default `max_tokens`, total inference deadline or read timeout is introduced.
An explicit `max_output_tokens` or request execution policy maps to `max_tokens`;
explicit runtime/deadline limits use shared cancellation. The shared 10-second
connect/write limits and 1 MiB response-body safety bound still apply. These
are transport safeguards; large provider responses can exceed the body bound.
Generic gateways retain shared explicit endpoint remapping; they do not select
an alternate model or provider automatically.

## Receipts, parsing and accounting

Receipts use provider `meituan`, endpoint kind `longcat_chat_completions`, and
parser version `longcat-chat-completions-raw-v1`. Only a safe returned `model`
populates `locked_model_id` with source `provider_response`; absence stays null.
Requested and returned identities remain separate, including mismatches.

Only a single complete assistant string choice with `finish_reason:stop` is
eligible for action parsing. `length` is `provider_output_truncated`; defensive
OpenAI-compatible `content_filter`/`message.refusal` handling is `provider_refused`.
Those refusal fields are compatibility defenses, not independently verified
LongCat-specific refusal examples. Unknown/malformed finish fields and unsupported
envelopes fail closed. HTTP 200 body errors are classified before action parsing.
Private reasoning, arbitrary error/refusal prose, headers and raw bodies are
never copied into receipts. Accepted public action text follows Core's existing
action metadata behavior.

LongCat inference takes a request-scoped snapshot of the selected credential,
the ordinary `LONGCAT_API_KEY`, and configured LongCat secondary key/token/secret
environment values. Exact or embedded matches in provider-controlled identifiers
are omitted, leaving model identity unknown when necessary. This applies to
success, HTTP error, malformed JSON, and partial/invalid transport responses.
Credential-bearing completion metadata and action content, including JSON-escaped
explanations after decoding, are rejected rather than copied into public
explanations or raw action metadata. Models discovery rejects matching IDs.
Credentials are not retained on the agent or in global mutable redaction state;
the scope resets after each invocation. Redacting a generation ID never removes
the original work observation or authorizes a retry.

Usage records retain only documented non-negative integer `prompt_tokens`,
`completion_tokens`, `total_tokens` and
`completion_tokens_details.reasoning_tokens`. Invalid values are marked; missing
fields stay null and missing totals are not synthesized. Cache accounting is
unknown. The official example reports 15 completion tokens and 78 reasoning
tokens without specifying their relationship. Consequently
`reasoning_included_in_output` remains null and artifact usage completeness is
false, even when all three headline counts are present. Preflight also reports
incomplete usage. This prevents scoring eligibility claims based on unresolved
accounting; a legal action alone does not establish Official eligibility.

No native cost field is documented for this response. The adapter deliberately
does not apply broker/catalogue prices to native traffic. Native cost and price
coverage remain unavailable, including with partial usage or error bodies.
No counts, cost, identity or fixed backend guarantee is inferred from an HTTP
status, a model request, or an empty body.

Default transport and action-repair retry counts are zero. Explicit transport
retries apply only to a definitive 429 rejection with recognized classifiers,
no work/accounting observations and no unknown extensions. The documented
numeric `retry_after` is accepted as a delay hint; a valid HTTP `Retry-After`
takes precedence. Receipts retain each attempt and delay. Unknown, conflicting,
malformed or work-bearing errors never become safely retryable. Timeouts,
transport failures, 5xx, refusal and truncation are not automatically replayed.
The general receipt quarantine retains usable error-body observations without
promoting them to trusted billing. No raw error message is exposed.

## Offline verification

`tests/test_longcat_provider.py` uses `httpx.MockTransport` and serialized raw
HTTP bodies through the shared bounded reader. Its fixture is synthetic and
uses the documented envelope/counts with public legal-action content. Coverage
includes aliases through CLI/preflight/dispatch, full history, unknown models,
reasoning, limits, success, errors, refusal, truncation, malformed/duplicate JSON,
missing identity/usage, safe and unsafe 429 retries, and privacy. These tests
establish deterministic client behavior, not live service/account availability.
