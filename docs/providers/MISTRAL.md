# Native Mistral AI adapter

This adapter calls Mistral AI's own developer API. It is independent of
OpenRouter, Bedrock, Azure, Vertex, self-hosted weights and model authorship.
Canonical provider: `mistral-ai`; alias: `mistral` (also normalized from
`mistral_ai`). Registry lookup, CLI construction, preflight, dispatch and receipts
use the canonical provider for execution. Existing CLI/preflight display fields
can retain the operator's spelling.

## Configuration

Export `MISTRAL_API_KEY` only when deliberately making a live call. Core reads
the environment with its existing printable-ASCII credential validation; it
does not load `.env` files. Authentication is `Authorization: Bearer <key>`.
No extra dependency or Mistral SDK is required.

```bash
# Offline configuration check; no provider request:
eslams providers preflight --provider mistral --model mistral-small-latest --arena tic-tac-toe

# Explicit account discovery; contacts Mistral, no inference:
eslams providers models --provider mistral-ai --live

# Explicit inference; can incur provider charges:
eslams providers preflight --provider mistral-ai --model mistral-small-latest --arena tic-tac-toe --live

eslams run --arena tic-tac-toe --seat-agent player_1=mistral:mistral-small-latest \
  --seat-agent player_2=first-legal --output-dir runs
```

An explicit, nonblank model ID is required by the agent, preflight and CLI;
bare `mistral`/`mistral-ai` and an empty `mistral:` selection fail rather than
selecting a default. An explicit model is forwarded byte-for-byte, including
dated and fine-tuned IDs. No alias-to-dated-model guess, different-model retry
or provider fallback is performed. A `latest` model can change upstream; use a
dated model when a stable requested ID is needed. A successful answer must
report a nonblank `model` exactly equal to the requested ID. A conflicting model
is rejected without action repair or retry. There is no inferred alias mapping:
even a legitimate alias-to-dated resolution is rejected if the IDs differ.
Missing response `model` is also rejected and remains null in the receipt;
a missing response `id` remains unknown without inventing one.
The response model attests only what Mistral reports; it does not prove a
particular physical backend.

## Verified API scope

Research checked on 2026-11-04 against these official sources:

| Source | Finding and implementation decision |
| --- | --- |
| [Chat REST API](https://docs.mistral.ai/api/endpoint/chat) | Global `POST https://api.mistral.ai/v1/chat/completions`, bearer auth, `model`, system/user messages, non-streaming JSON response. Optional `max_tokens`, temperature and `reasoning_effort` are endpoint controls. |
| [Models REST API](https://docs.mistral.ai/api/endpoint/models) | `GET https://api.mistral.ai/v1/models` returns account-visible `data[].id`; this endpoint documents no pagination. Model cards distinguish `completion_chat` from FIM, embeddings and other capabilities. Discovery lists IDs, without inferring chat suitability. |
| [Chat messages](https://docs.mistral.ai/studio/conversations/chat-completion) | Assistant content may be a string or typed chunks. Only final text is parsed as an eSlams action. System instructions and full visible history are sent using Core's existing prompt contract. |
| [Structured output](https://docs.mistral.ai/inference/conversations/structured-output/custom) and [Chat API](https://docs.mistral.ai/api/endpoint/chat) | JSON object/schema modes and function calling exist. They are deliberately not enabled here: arena action schemas vary, support differs by model, and Core already validates legal actions. No tools are advertised or executed; unsolicited tool calls are rejected. |
| [Current official model catalogue](https://docs.mistral.ai/getting-started/models) | Model availability is dynamic. This adapter supports text-producing chat models available to the configured account, not every Mistral-authored model or broker entry. No registry regeneration or new capability claims accompany this change. |
| [Official SDK wire schema, pinned commit](https://github.com/mistralai/client-python/tree/d3da3bd3c63d0502449e1e765bc2d3c16d0d2f1d/src/mistralai/client/models) | `chatcompletionchoice.py` defines `stop`, `length`, `model_length`, `error`, `tool_calls`; `thinkchunk.py` defines typed thinking chunks; `usageinfo.py` defines raw token counters. SDK defaults are not raw accounting evidence. |
| [API usage/limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) and [Known limitations](https://docs.mistral.ai/resources/known-limitations) | Account/model limits and context constraints remain authoritative. HTTP 429 is a rate-limit outcome; context overflow can be HTTP 400. Limits are not invented locally. |
| [Regional inference](https://docs.mistral.ai/inference/regional-inference) | Global `api.mistral.ai` makes no specific inference-location commitment. EU `api.eu.mistral.ai` and US `api.us.mistral.ai` have region-specific model availability, feature restrictions and an upcharge. This adapter and its discovery use the global endpoint only. |
| [API pricing](https://docs.mistral.ai/inference/pricing) | Rates distinguish input, cached input and output; currency, standard/batch/priority service and regional inference affect prices. No static price or free-tier assumption is encoded. |

Use the account Models API to check the selected model, and its model card for
chat capability. The frozen Core registry is advisory unless strict catalogue
policy is explicitly requested. A new/unknown model can be called as explicitly
selected; an embeddings, OCR, moderation, audio, retired or otherwise unsupported
model is subject to authoritative endpoint rejection. OpenRouter-qualified names
are not translated to native IDs.

## Behavior and limits

The adapter reuses Core's bounded HTTP transport, invocation-scoped attempts,
deadlines/cancellation, rate/concurrency guards, receipt redaction and action
validation. It adds no total output/time limit. `max_tokens` is omitted unless
the operator or ActRequest supplies a bound. Provider defaults and context
limits still apply. Full supplied history is preserved; the existing explicit
`history_window_turns` option can reduce it. No game selects reasoning policy.
An explicit temperature or `reasoning_effort` is forwarded unchanged, with the
endpoint deciding whether the selected model accepts it. `prompt_mode`, generic
reasoning enable/disable flags, reasoning budgets, tools, multimodal inputs,
streaming, Responses/Agents, FIM and regional inference are not implemented as
Mistral controls. Generic gateway rewriting remains a separate Core transport
feature and provides no regional-discovery or residency guarantee.
Explicit `reasoning_budget_tokens` and `gemini_thinking_budget` values, including
zero and the Gemini -1 sentinel, fail configuration preflight and agent execution
before credentials, discovery or inference. They are never silently discarded.

Only a single assistant choice with terminal `stop` and answer text is accepted.
`length`/`model_length` are `provider_output_truncated`; `error` is unavailable;
tool calls are rejected. Missing/unknown finish reasons, invalid choice/message
shapes and unsupported chunks fail closed. Typed `thinking` blocks are skipped
and never parsed as actions. Defensive refusal/content-filter detection is also
included; those extension fields are not advertised as native capabilities.
HTTP 200 error envelopes are rejected before action parsing. Legal-looking
partial text never rescues an incomplete response.

Core's HTTP classification applies: 400/422 request rejected, 401 authentication,
403 permission, 404/5xx unavailable, 429 rate limited; timeouts and transport
errors keep their existing outcomes. Private error prose is never copied to
receipts. Successful-envelope usage and response identity survive semantic and
action failures. HTTP-error-body observations remain quarantined under the
shared provenance contract.

Provider output is scrubbed against the active primary key (including custom
credential environment names) and configured environment values whose names
contain credential components such as KEY, TOKEN, SECRET, PASSWORD or CREDENTIAL.
Literal, JSON-escaped and URL-escaped echoes are covered. Contaminated response,
request, gateway and resolved-model IDs become unknown; contaminated discovery
model IDs fail validation. Action text is scrubbed before action parsing and
metadata generation. Malformed bodies, partial transport observations and error
receipts use the same boundary; raw exception chains are not retained. These
rules cover configured known values, not unknown credentials or arbitrary
encodings. They do not rewrite outgoing credentials or the supplied history.
Removing a contaminated ID does not permit replay of an observed attempt.

Default retries are zero. Even with an operator retry count, only the shared
narrow, definitive rate-rejection evidence permits replay; accepted work,
usage/identity/cost observations, 5xx, timeouts and ambiguous bodies do not.
In particular, a flat Mistral-style rate error does not establish that evidence
and is not automatically replayed. `Retry-After` is retained; no adapter-specific
retry loop or inferred idempotency guarantee is added. Explicit action repair
uses Core's separate attempt kind and preserves all attempts.

Usage maps only raw `prompt_tokens`, `completion_tokens`, `total_tokens` to Core
input/output/total counters. Missing counters stay unknown; malformed counters
and inconsistent totals are marked by the shared validator. Cache and reasoning
breakdowns, reasoning inclusion, and native cost are unknown. SDK default zeros
and undocumented extra cost/token fields are not used. The existing receipt
accounting code can derive totals with explicit provenance, but never fills
missing input/output with zero. The frozen author catalogue also contains
third-party/broker rates; the adapter excludes that pricing from direct-route
receipts. Without a verified direct rate card, estimated cost is
`cost_unavailable`; a successful
action is not a claim of complete accounting or Official eligibility.

## Fixture provenance and validation

`tests/fixtures/provider/mistral_chat_completions_success.json` is a keyless,
synthetic instantiation of the documented raw Chat Completion envelope, using
invented IDs/content/counts. The chunks fixture follows the official typed
text/thinking schemas pinned above. `mistral_rate_limited.json` is a synthetic
flat-error fault fixture; it does not establish a guaranteed universal error
body schema. Other mutations in `tests/test_mistral_provider.py` are explicitly
fault injections. No fixture is a paid or authenticated capture.

Cloud validation covers the canonical/alias paths through the registry,
preflight, CLI, dispatch and native execution, full history, explicit controls,
string/chunk answers, malformed/truncated JSON and completions, refusal, tools,
HTTP 200 errors, 400/401/403/404/422/429/5xx, timeout/transport ambiguity, safe
retry evidence, credential/privacy boundaries, missing identity/usage/cost,
and generated success/failure artifacts. No live Mistral call was made.
`tests/test_mistral_provider_security.py` adds explicit-model/budget validation
and primary/secondary credential echo cases across success, errors, malformed
or partial responses, discovery, identifiers and raw/decoded action text.
Identity regressions reject missing, blank and conflicting returned model IDs,
including a different dated ID for a requested alias, while preserving usage.

Integration note for parallel adapter PRs: narrow insertions touch `agents.py`
(imports, canonicalization, dispatch, endpoint/parser maps, usage projection),
`provider_preflight.py` (credential/discovery maps), `cli.py` (agent defaults),
`.env.example`, `docs/PROVIDERS.md` and `CHANGELOG.md`. Preserve all other adapter
entries when resolving nearby conflicts. Re-run checks on the final combined
commit. The registry, package version, schemas and workflows are unchanged.

Validation caveat at the 0.7.0 base (`270a863`): unchanged `main` reproduces
`test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
(observed-body timeout raises `ProviderCallError`, test expects `TimeoutError`)
and `test_cli_fallback_failing_seat_board_win_is_only_a_board_result` (board
winner is null, test expects player 1). Neither test nor shared behavior is
modified here. An initial parallel full-suite run also observed the existing
slow-header socket-disconnect timing test fail; that test passed in isolation.
These are reported validation blockers, not waived release gates.
