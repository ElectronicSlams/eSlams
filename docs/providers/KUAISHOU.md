# Kuaishou / KwaiPilot KAT direct text adapter

This adapter is proposed for 0.7.1 on the Python Core 0.7.0 codebase; package
versions remain unchanged. Both `kuaishou:MODEL` and `kwaipilot:MODEL` use
Kuaishou's StreamLake text inference service and preserve the requested provider
namespace and exact model string. They do not route through OpenRouter or other
resellers. No hosted inference was performed during implementation.

## Product and contract evidence

Checked 2026-11-04 against these official sources:

| Source | What it establishes |
| --- | --- |
| [KwaiPilot KAT announcement](https://kwaipilot.github.io/KAT-Coder/) | KAT coding language models, StreamLake access, and the older endpoint-specific Claude Code proxy. |
| [International inference API](https://www.streamlake.ai/document/DOC/mj9z6fh8lxn87i86jrp) | Direct POST endpoint, bearer authentication, request fields, nonstreaming response, usage details, and `ResponseMeta` errors. |
| [International integration guide](https://www.streamlake.ai/document/DOC/mg6k6nlp8j6qxicx4c9) | Separate pay-as-you-go and Coding Plan URLs; `kat-coder-pro-v2.5` as a current model ID. |
| [API key management](https://www.streamlake.ai/document/DOC/mkaylxzkso38sqxcpa) | Keys are managed in the Vanchin console. |
| [Inference endpoints](https://www.streamlake.ai/document/DOC/mgrm41pindmnfe5wgmj) | Preset KAT endpoints and account-created endpoints; endpoints must be running. |
| [China quickstart](https://www.streamlake.com/document/WANQING/me6yi4shauyxx5fhdtv) | China host, `WQ_API_KEY` example, project-scoped keys, and exact inference endpoint IDs in `model`. |
| [China text inference](https://www.streamlake.com/document/WANQING/me6z3u08sjus2mzplbj) | China wire contract and token details. |
| [OpenAI protocol controls](https://www.streamlake.com/document/WANQING/mq6k66r6xgqwnfbd8t) | Ordered conversation history, optional output controls, and model-dependent `enable_thinking`; this does not establish KAT-specific control support. |
| [International errors](https://www.streamlake.ai/document/DOC/mkf81ayc461ilb15zid), [China errors](https://www.streamlake.com/document/WANQING/mhyk52ofkyit2gaim3a) | Invalid keys can be HTTP 400, permissions/balance errors are 403, missing resources 404, throttling 429, and server failures 5xx. Error prose can echo an API key. |
| [Kling developer platform](https://kling.ai/dev) | Kling serves image/video generation. A text prompt for media generation is not a text-completion API. |

The open-weight KAT model's local serving examples are not a hosted provider
contract. Kling credentials, media endpoints, and reseller model IDs are not
interchangeable with StreamLake text inference credentials or endpoint IDs.

## Configuration

Explicitly export `STREAMLAKE_API_KEY` using the key from the selected service's
console. Core does not load `.env` files. Do not paste credentials into commands,
model IDs, receipt fields, or repository files.

`ESLAMS_STREAMLAKE_REGION` selects exactly one service:

| Value | Request URL |
| --- | --- |
| `international` (default when omitted) | `https://vanchin.streamlake.ai/api/gateway/v1/endpoints/chat/completions` |
| `cn` | `https://wanqing.streamlakeapi.com/api/gateway/v1/endpoints/chat/completions` |

A blank or unrecognized region fails locally. These names select documented
service hosts; they do not assert physical processing location or data residency.
Use a key and model/endpoint ID provisioned for that service. There is no region
failover. Coding Plan URLs, Claude Code proxies, and custom gateways are not
supported by this adapter. Only the documented pay-as-you-go API is selected.

Configuration-only preflight makes no inference request:

```bash
eslams providers preflight --provider kwaipilot \
  --model kat-coder-pro-v2.5 --arena tic-tac-toe
```

For China, set `ESLAMS_STREAMLAKE_REGION=cn` and supply the exact inference point
ID from that console. The adapter requires a nonblank model/endpoint ID and never
substitutes a default. It does not trim, case-fold, prepend a reseller namespace,
or rewrite the model. `kuaishou:ep-...` uses the same selected service while
retaining `kuaishou` in receipts.

After deliberately authorizing inference spending, operators can use `--live`
on preflight or `--agent kwaipilot:kat-coder-pro-v2.5` on `eslams run`. Neither
was invoked against a real provider for this work. No documented public Models
API was established; live model discovery returns unavailable. Catalogue
membership remains advisory and no new model availability or pricing record is
invented. Strict catalogue mode may reject an unregistered endpoint.

## Request, response, and accounting

Requests contain the exact `model`, a system message, a user message holding the
full supplied ActRequest history, and `stream: false`. No tools, search,
fallback, repair, reasoning control, output maximum, or total/read deadline is
enabled by default. The shared transport retains its connection timeout and
bounded response-body safety checks. An operator can explicitly supply an
output maximum (`max_tokens`), deadline, or temperature (0–1, the common
documented range). Explicit history windows and proxy routes are rejected.

Only native-default reasoning (`reasoning="auto"`) is supported. Explicit
enabled/disabled, effort, and budget settings fail before HTTP: the generic
hybrid-model parameter does not attest those controls for KAT. Arena/game names
never select reasoning behavior.

A successful answer requires HTTP 200, `object: chat.completion`, one candidate
at index zero, assistant text, and `finish_reason: stop`. Length termination,
filtering/refusal, tool calls, unknown finish states, and malformed envelopes
cannot produce an accepted action. Action parsing uses Core's existing legal
action checks. Every physical attempt retains an invocation-scoped receipt.

The requested model is retained separately from `locked_model_id`, which comes
only from the response's `model`. A missing, blank, malformed, or credential-
bearing identity remains unknown. A custom endpoint ID is not proof of its
underlying model or an immutable model revision.

Only documented `prompt_tokens`, `completion_tokens`, `total_tokens`,
`prompt_tokens_details.cached_tokens`, and
`completion_tokens_details.reasoning_tokens` are normalized. Missing counts
remain unknown, including missing totals; reasoning inclusion remains unknown
because the source does not explicitly attest it. No absent count becomes zero.
The adapter does not infer a price or trust arbitrary response `cost` fields.
Incomplete accounting does not turn configuration readiness into official
eligibility. Error-body usage observations stay quarantined as unverified.

HTTP failures, `ResponseMeta` errors, malformed JSON, transport failures, and
partial responses preserve sanitized observations. Provider error prose is
discarded. Known credential echoes are removed from opaque identifiers and
headers; credential-bearing action text (including escaped JSON) is rejected.
Secrets, prompts, and raw private responses are not copied into receipts.

Redaction snapshots the active credential and other configured credential
variables ending in `_KEY`, `_TOKEN`, `_SECRET`, `_PASSWORD`, `_CREDENTIAL`, or
`_CREDENTIALS`, plus the standard Bedrock bearer variable. This covers a custom
active key alongside `STREAMLAKE_API_KEY`, `WQ_API_KEY`, and secondary provider
keys. These values are used only to suppress echoes, never as extra request
credentials. Plain, JSON-escaped, and URL-encoded credential echoes are checked;
credential-bearing IDs become unknown rather than a replacement identity.

Retries default to zero. No published non-billable rejection/replay guarantee
was established, so this adapter never automatically replays a failed physical
request, even when a generic retry maximum is set. `Retry-After` is diagnostic;
it is not permission to replay an ambiguous request.

## Fixture provenance and verification

`tests/fixtures/provider/kuaishou_chat_completions_success.json` follows the
international documentation's raw nonstreaming example. The request ID and
assistant text are replaced with public test values; the model is the ID in
the official integration guide. Token counts and detail fields retain the
documented example shape. It is a deterministic contract fixture, not a captured
paid response. Fault-injection fixtures preserve that envelope or the documented
`ResponseMeta` error envelope.

`tests/test_kuaishou_provider.py` covers both namespaces and service hosts,
exact IDs, full history, operator controls, CLI/preflight/dispatch, missing
credentials, errors, refusal/truncation, malformed/partial responses, missing
identity/accounting, conservative retries, and credential echoes. These tests
use synthetic credentials and mocked transport only.

Cloud validation on Python 3.12.14, based on
`270a863d10d57a0953f21924f1a0dd50159e6cf1`:

- Focused adapter and environment-reference tests: 56 passed, including a CLI
  run that writes sanitized native receipts.
- Full suite: 1,312 passed, two inherited failures, two duplicate-ZIP-entry
  warnings. The subsequently added CLI run test also passed in the focused run.
- Both failures reproduced on a separate untouched checkout of that base:
  `test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
  and `test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`.
  The former expects a timeout where the observed partial-response path raises
  `ProviderCallError`; the latter expects a diagnostic board winner that is null.
- Ruff, mypy (104 source files), both pinned TypeScript checks, wheel/sdist build,
  Twine metadata checks, arena fingerprints, and initial-state budgets passed.
- Two schema exports were byte-identical; package version remains 0.7.0.

No paid inference, real provider credentials, merge, release, deployment,
browser smoke, dependency audit, or isolated distribution-consumer run was
performed. A passing fixture test does not establish live account availability.

An independent follow-up audit confirmed the original redactor missed secondary
configured keys and corrected that boundary. Follow-up checks: 125 adapter and
environment-reference tests passed, plus 147 existing wire, completion,
invocation-receipt, safe-retry, credential/wait, and unbounded-policy tests.
Ruff and mypy (104 source files) passed again. New cases exercise both provider
namespaces, missing/blank IDs, unsupported reasoning budgets in configuration
and live preflight and reconfigured agents, and active/secondary credential
echoes across success, errors, malformed/partial responses, discovery and action
text. The full suite was not repeated; its two inherited failures above remain
disclosed. Hosted CI, paid inference, merge and release remain unperformed.
