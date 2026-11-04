# Inception Labs Mercury adapter (planned 0.7.1)

Verified against public documentation on 2026-11-04. No authenticated discovery
or inference was performed. This change keeps the package version at 0.7.0.

## Identity and setup

`inception:<exact-model-id>` selects Inception Labs' direct API. Provider aliases
`inception-labs` and `inceptionlabs` select the same adapter; underscores and case
are normalized. The model string is passed unchanged, including unlisted IDs.
The CLI default is `mercury-3`. There is no alternate provider or model fallback.

```bash
export INCEPTION_API_KEY='<your-key>'
eslams providers preflight --provider inception --model mercury-2 --arena tic-tac-toe
```

This preflight is configuration only. Using `--live` explicitly requests account
discovery and inference and can incur charges. Core never loads `.env` itself.

[Authentication](https://docs.inceptionlabs.ai/get-started/authentication) uses a
Platform API key in an Authorization bearer header. The
[chat reference](https://docs.inceptionlabs.ai/api-reference/chat/create-a-chat-completion)
specifies POST `https://api.inceptionlabs.ai/v1/chat/completions`, JSON `model`
and `messages`, and the assistant text at `choices[0].message.content`.
[Chat-model discovery](https://docs.inceptionlabs.ai/api-reference/models/list-chat-models)
uses GET `https://api.inceptionlabs.ai/v1/chat/completions/models` and `data[].id`.

Inception Labs Mercury is distinct from
[Core42 Compass](https://www.core42.ai/compass/documentation/compass-models), whose
catalogue includes G42 Inception's Seraj. Core's old `inception -> core42` alias
was misleading for Mercury and is removed in runtime and registry-update paths.
Historical frozen `core42` Mercury catalogue rows remain for compatibility and
are not evidence of direct Core42 support. `core42` still has no native adapter.
Broker IDs such as `openrouter:inception/mercury-2` retain their broker identity.

## Controls and accounting

The [model catalogue](https://docs.inceptionlabs.ai/get-started/models) documents
chat models `mercury-2`, `mercury-2.5` and `mercury-3`. Mercury Edit 2 uses FIM/edit
endpoints and Mercury Decide uses decisions; those protocols are outside this
chat adapter. Voice is enterprise access. Local chat records describe documented
capabilities, not verified account availability or official eligibility.

Core sends non-streaming messages containing the standard action instructions
and full supplied agent-visible history. Caller-selected history windows remain
available. No game selects a reasoning mode. Explicit output limits use
`max_completion_tokens`; otherwise Core omits token limits. Provider defaults
and context ceilings still apply. Explicit temperature is forwarded unchanged.

[Reasoning efforts](https://docs.inceptionlabs.ai/capabilities/reasoning-efforts)
documents `instant`, `low`, `medium`, and `high`. Core forwards only an explicit
`reasoning_effort`, leaving defaults to Inception. That page describes `low` for
Mercury 3 and `medium` for Mercury 2/2.5; the chat schema advertises `medium`
generically. Core does not resolve that documentation discrepancy by imposing a
default. Other providers' thinking budgets are rejected before sending.

The [usage FAQ](https://docs.inceptionlabs.ai/resources/faq) documents nested
cached/reasoning counts; the chat reference also shows flat
`cached_input_tokens` and `reasoning_tokens`. Both forms use Core's numeric
normalizer. Reasoning is included in completion tokens, and cache reads are a
subset of prompt tokens; neither is added again. Missing counts stay unknown,
and malformed numeric counts retain validation diagnostics. Inception does not
report dollar costs. This adapter supplies no inferred price card or cost from
promotional list prices. Missing response model identity remains null; a
different response model is preserved as the observed identity.

## Failures, retries and fixtures

[Error documentation](https://docs.inceptionlabs.ai/resources/error-codes) lists
400 (request/context), 401 (auth), 402 (billing), 404 (model/account), 429 (rate),
and server errors. Core retains sanitized status/request IDs and receipts,
including usage observed on semantic failures. Error/refusal prose, summaries,
warnings, credentials, prompts and raw response bodies are excluded from public
receipts. Legal-looking truncated, filtered, tool-call or unfinished text cannot
be applied as a game action.

The [FAQ](https://docs.inceptionlabs.ai/resources/faq) recommends backoff for 429
and 503. Core retains its stricter attempt policy: **zero retries by default**;
explicit retries require a definitive 429 rejection with no observed work.
Ambiguous transport failures, malformed errors, 5xx or observed generation/usage
are never automatically replayed. Each permitted physical retry gets its own
receipt. Inference uses the existing cancellable transport, caller deadlines and
connect/write safety settings, without a new total/read thinking cap.

`tests/fixtures/provider/inception_chat_completions_success.json` preserves the
documented chat success envelope (ID, object, timestamp, model, choices and flat
usage); only assistant prose is replaced with deterministic `{"action": 0}`.
Other tests inject synthetic faults into that envelope. All tests are keyless.
They cover aliases across CLI/preflight/dispatch, discovery, full history,
explicit controls, identity, flat/nested/missing usage, privacy, HTTP errors,
timeouts, malformed JSON, semantic failures and definitive/ambiguous 429s.
