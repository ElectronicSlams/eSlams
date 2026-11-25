# Direct Ant Ling (Ant Group / Bailing / InclusionAI)

Research checked on 2026-11-04 against Core base
`270a863d10d57a0953f21924f1a0dd50159e6cf1` (Python Core 0.7.0).
This is an adapter candidate for 0.7.1; package and contract versions are unchanged.

## Provider identity and access routes

[InclusionAI's official GitHub organization](https://github.com/inclusionAI)
identifies itself as Ant Group's open-source organization. The
[official Ling cookbook](https://github.com/inclusionAI/ling-cookbook)
links `ant-ling.com` as its official website. The
[Ant Ling introduction](https://developer.ant-ling.com/en/docs/)
links that organization and explicitly distinguishes direct API access from
third-party OpenRouter and ZenMux access. The
[original Ling technical report](https://arxiv.org/abs/2503.05139)
connects the Ling and Chinese Bailing names.

The native provider is `ant-group`; the registry's existing `bailing` alias
also works in CLI dispatch. Direct IDs retain exact case, for example
`Ling-3.1-flash`. `inclusionai/ling-3.1-flash` is an
[OpenRouter identity](https://openrouter.ai/inclusionai), not a direct ID.
The `inclusionai` organization namespace remains separate and receives no
implicit dispatch or credential alias. At this Core base, `ant-group` contained
only `Ling-1T` and `Ring-1T`; `inclusionai` had no model rows. These catalogue
facts do not establish which provider serves a routed request.

The official [Ring-1T model card](https://huggingface.co/inclusionAI/Ring-1T)
demonstrates a ZenMux URL/key and separately gives local SGLang/vLLM deployment
instructions. Neither is evidence for a second InclusionAI-operated inference
service. Self-hosted OpenAI-compatible servers must not be represented as this
native direct provider. Older Tbox/Yuque references were investigated; the
Yuque API page could not be retrieved. No legacy endpoint is inferred from it.

## Verified direct contract

The [official OpenAI-compatible reference](https://developer.ant-ling.com/en/docs/api-reference/chat/openai/)
documents POST `https://api.ant-ling.com/v1/chat/completions`, JSON content type,
and HTTP bearer authentication. Conversation messages carry roles and content.
Non-streaming responses use `choices[].message.content`, a completion reason,
response ID/model, and token usage. The documented usage example includes
prompt, completion, total, and cached prompt token counters.

For Ling 3.0/3.1, reasoning is controlled by `thinking.type` with `enabled` or
`disabled`; omission retains the provider's default. Temperature accepts 0–1.
Search is opt-in through `enable_search`. The adapter explicitly disables it
and supplies no tools. The reference does not establish reasoning-token counts
or whether they are included in completion usage; the receipt leaves these
unknown. It does not establish a response cost or a Models discovery endpoint.

[Quickstart](https://developer.ant-ling.com/en/docs/getting-started/quickstart/)
also demonstrates optional `max_tokens`. This adapter sends it only for an
explicit operator limit. No output ceiling or total/read timeout is selected by
the adapter. The existing bounded transport retains its response-size and
connection safety checks.

## Current models and lifecycle

The [official lifecycle page](https://developer.ant-ling.com/en/docs/models/deprecation/)
lists `Ling-3.1-flash`, `Ling-3.0-flash`, `Ling-3.0-flash-VL`, and `Ling-3.0-tiny`
as current models. This adapter uses text input/output only. `Ling-1T` and
`Ring-1T` retired on 2026-06-15; `Ling-2.5-1T` and `Ring-2.5-1T` retired on
2026-09-30. `Ling-2.6-1T`, `Ring-2.6-1T`, and `Ling-2.6-flash` have a scheduled
retirement of 2026-11-15 00:00 UTC+8. Local provider-specific catalogue metadata
records these distinctions. It never substitutes a suggested replacement.

Unknown exact model IDs may be submitted with native reasoning defaults under
Core's advisory catalogue policy. Explicit reasoning control is accepted only
for the four documented Ling 3.x IDs. Unsupported effort, budget, gateway,
and routed-provider controls fail before submission. Strict catalogue preflight
remains available when an operator wants catalogue enforcement.

## Account, region, errors, retry, and accounting limits

[Prerequisites](https://developer.ant-ling.com/en/docs/getting-started/prerequisites/)
identifies the console at `chat.ant-ling.com` and its Create Token operation.
The [FAQ](https://developer.ant-ling.com/en/docs/faq/) describes Alipay binding.
No account, token, balance, or paid inference was used for this work. The
examined official documentation does not specify a selectable region, complete
country availability list, or data-residency guarantee. None is claimed by Core.
Account access and actual deployed model identity remain unverified offline.

[Rate limits](https://developer.ant-ling.com/en/docs/api-reference/api-guide/queries-per-second/)
documents 2 requests/second and a provider-enforced 90-second synchronous
timeout, recommending streaming for longer generation. This initial adapter
uses non-streaming JSON through the existing safe transport. The upstream
90-second constraint is a material limitation, not a framework timeout setting.
Streaming support is deferred; an upstream timeout never becomes a legal action.

[Error codes](https://developer.ant-ling.com/en/docs/api-reference/api-guide/error-code/)
documents 400, 401, 402, 404, 413, 428, 429, 500, 503, and 504. The adapter maps
428 to refusal and 504 to timeout, while retaining shared authentication,
permission, rate-limit, unavailable, and request-rejection outcomes. The docs
do not specify a normative error JSON envelope or guaranteed safe replay signal.
Fault-injection error bodies in tests are explicitly synthetic. Default retries
remain zero; even an opt-in retry budget does not replay ambiguous Ant Ling
failures. A Retry-After observation is diagnostic, not replay authorization.

Missing model identity stays null. A conflicting returned identity is retained
as evidence but rejected for action dispatch. Missing usage/counters and prices
stay unknown; missing total tokens are not synthesized. Error-body observations
remain quarantined. Arbitrary model prose, reasoning, private responses, and
headers never become public receipts. Known credential echoes are removed from
receipt values, including request IDs and malformed/partial response paths;
credential-bearing action content is rejected before parsing.

The active bearer and configured `ANT_LING_API_KEY`, `BAILING_API_KEY`, and
`OPENAI_API_KEY` values are all covered by credential-echo checks, including
JSON-escaped and percent-encoded action text. Additional configured values are
used only for redaction; they never supply fallback authentication. The native
API uses one selected bearer and has no secondary authentication header.
Preflight applies the same validation after provider alias normalization, so
`ant_group` and surrounding whitespace cannot bypass model or reasoning checks.

[Billing migration](https://developer.ant-ling.com/en/docs/getting-started/changelog/billing-upgrade/)
describes a switch to the Ling wallet by 2026-10-31 and monthly vouchers instead
of the older daily token quota. The FAQ still describes the old daily quota.
This inconsistency is not converted into a free-usage promise or an inferred USD
price. Official eligibility and cost completeness are not established by a
successful fixture or a legal action.

## Usage and deterministic validation

Export `ANT_LING_API_KEY` only when intentionally making direct calls. Core does
not automatically load `.env`. Configuration preflight is offline:

```bash
eslams providers preflight --provider ant-group --model Ling-3.1-flash --arena tic-tac-toe
```

An explicitly requested `--live` preflight or run can consume paid tokens:

```bash
eslams run --arena tic-tac-toe --agent ant-group:Ling-3.1-flash --opponent first-legal
eslams run --arena tic-tac-toe --agent bailing:Ling-3.1-flash --reasoning disabled --opponent first-legal
```

The default preserves the complete supplied public history, native reasoning
policy, exact requested model, and one physical attempt. No tool execution,
automatic search, model replacement, or provider fallback is added.

The success fixture at
`tests/fixtures/provider/ant_ling_chat_completions_success.json` follows the
reference's non-streaming example; only content is replaced with a legal test
action. All IDs and counts are public example values, not live inference data.
`tests/test_ant_ling_adapter.py` checks dispatch/CLI/preflight, payload policy,
accounting, failures, credential echoes, and real bounded transport with a
mock HTTPX stream that fails after response headers. Run without credentials:

```bash
python -m pytest tests/test_ant_ling_adapter.py
```
