# Snowflake Cortex

This adapter targets the account-scoped Cortex Chat Completions API. Research
checked against official documentation on **2026-11-04**; no account, credential,
or paid inference was used. The package remains 0.7.0 pending 0.7.1 review.

## Configure and select

```bash
export SNOWFLAKE_ACCOUNT_URL=https://org-account.snowflakecomputing.com
export SNOWFLAKE_TOKEN=... # provision outside Core; never put tokens in arguments
# Optional: let Snowflake detect token type by leaving this unset.
export SNOWFLAKE_TOKEN_TYPE=PROGRAMMATIC_ACCESS_TOKEN

# Offline configuration check; does not establish access or incur inference cost.
eslams providers preflight --provider snowflake --model openai-gpt-5-mini --arena tic-tac-toe
```

Use `snowflake:<native-model-id>` in CLI agent arguments. `snowflake-cortex`,
`snowflake_cortex`, and `cortex` select the same adapter. Every selection requires
an explicit model; Core neither strips a `snowflake/` catalogue prefix nor
substitutes a default. For example, `openai-gpt-5-mini` is a native Snowflake
identifier; `snowflake/openai-gpt-5-mini` is sent literally if requested and may
be rejected. The registry remains advisory and is not refreshed by this change.

The account URL must be an HTTPS origin under `snowflakecomputing.com`, with no
userinfo, port, query, fragment, or API path. Regional locator and PrivateLink
hostnames are accepted literally. Custom domains require a separately configured
Core gateway; the native origin validation does not accept arbitrary destinations.

## Official contract and implementation decisions

| Area | Verified source and adapter behavior |
| --- | --- |
| Endpoint | [Cortex REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api#chat-completions-api-reference): `POST /api/v2/cortex/v1/chat/completions`. Core requests one non-streaming text completion. No SDK, SQL warehouse, agent service, or endpoint fallback. |
| Authentication | [REST authentication](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/authentication): bearer PAT, OAuth token, or externally minted key-pair JWT. Optional `X-Snowflake-Authorization-Token-Type` accepts `PROGRAMMATIC_ACCESS_TOKEN`, `OAUTH`, or `KEYPAIR_JWT`. Core neither creates nor refreshes tokens. Session tokens and workload identity token acquisition are outside this adapter. |
| Model/access | [Cortex model availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/model-availability): availability depends on product, role, account, lifecycle and region. `SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS` is the documented account check. The request retains the exact model string, including a fully qualified fine-tuned model name. A response's `model` attests only the reported identity, not immutable weights/build or a pinned deployment. Missing identity stays null. |
| Region | [Cross-region inference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cross-region-inference): the supplied account origin and account policy determine placement. Core does not enable cross-region inference or infer the actual inference region from a hostname. It does not change account grants or model access. |
| Request | [Chat reference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api#chat-completions-api-reference): exact `model`, system instructions and the complete supplied public action prompt/history in `messages`, `stream=false`. An explicit output limit uses `max_completion_tokens`; no limit is inserted by default. Snowflake currently documents a provider default of 4096, so omission does not promise unlimited output. |
| Reasoning | [Thinking and reasoning](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api#thinking-and-reasoning): explicit OpenAI effort maps to `reasoning_effort`; Claude effort or manual budget maps to `reasoning.effort` or `reasoning.max_tokens`. Auto mode leaves provider defaults intact. No arena-dependent choice, inferred budget or temperature override. Unsupported/conflicting controls fail before submission. |
| Response | [Compatibility chart](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api#detailed-compatibility-chart): one assistant `choices[].message.content` string is used. Reasoning prose is never action text. Refusal, length, tool calls, malformed/unknown terminal markers and HTTP-200 error envelopes fail with receipts. |
| Usage/cost | [Usage history](https://docs.snowflake.com/en/sql-reference/account-usage/cortex_rest_api_usage_history): canonical request accounting includes tokens and actual inference region. Core uses reported prompt/completion/total counts and documented token details, with reasoning included in completion counts. Missing categories stay unknown. Claude cached-token totals combine reads and writes, so Core does not claim a split. There is no native USD cost in this wire contract; no credit-to-dollar conversion or cost is invented. |

## Deliberate limits

Snowflake documents no Chat Completions `finish_reason` for Claude, and only
`stop` for other non-OpenAI families. Core requires an explicit `stop` before
accepting an action. **A Claude response that omits this field is rejected**;
success tests with a terminal marker do not establish Claude completeness support.
The separate Messages/Responses APIs are not silently selected. Adding another
surface would require its own wire fixtures and explicit required-limit policy.

`reasoning=enabled` requires an effort or budget. `reasoning=disabled` maps to
OpenAI effort `none`; other families fail because a disabling control is not
documented for this surface. Core does not silently ignore an explicit choice.
Fine-tuned model names do not establish their base family, so no reasoning family
is guessed for them. Explicit temperatures are forwarded for authoritative
provider validation; some models ignore or reject them.

[Model discovery exists](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/reference/cortex-inference)
at `/api/v2/cortex/models`, but this adapter does not implement its response
schema. `providers models --live` returns discovery unavailable. Configuration
preflight validates the account origin without network access. Only an explicitly
requested `--live` preflight invokes inference and may incur charges; discovery
remains unverified. No live preflight was run during development.

## Errors, retries and privacy

HTTP 400/402 are request rejection, 401 authentication failure, 403 permission
failure, 404/5xx unavailability and 429 rate limiting. A documented Snowflake
HTTP-200 session-expired code `390112` is rejected as authentication failure.
Provider prose, response headers, credentials and prompts are not copied into
receipts. Unknown error codes do not become model or billing evidence.

The existing bounded transport enforces response size and elapsed operator
deadlines without adding a generation deadline. Default provider and action
repair retries are zero. Explicit retries reuse Core's conservative safe-rejection
policy: only a verified rate rejection without work/usage/cost observations can
be replayed. An opaque Snowflake error is not enough. Timeouts and ambiguous 429s
are never automatically replayed. Snowflake does not promise a `Retry-After`
header; Core does not manufacture one.

The fixture `tests/fixtures/provider/snowflake_chat_completions_success.json` is
a redacted, synthetic instance of the documented non-streaming OpenAI-compatible
envelope and Snowflake compatibility fields, not a captured live response.
IDs, time, counts and action text are illustrative. Fault fixtures are synthetic
mutations. `tests/test_snowflake_provider.py` covers controls, aliases across
CLI/preflight/dispatch, full history, missing identity/accounting, HTTP and
semantic failures, safe retries, bounded transport, and artifact privacy.
