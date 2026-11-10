# MiniMax direct adapter (0.7.1 work)

This adapter targets Core's next release without changing the package version
from 0.7.0. It lives in `src/eslams/providers/minimax.py`; shared changes only
connect dispatch, transport error observation, receipt metadata, usage, CLI and
configuration preflight. No generated registry snapshot is refreshed.

## Verified official contract

Research date: 2026-11-04. These are documentation checks, not account-access or
live-inference evidence. Fixtures are synthetic examples of the documented wire
shape and contain no provider credentials or captured private responses.

| Concern | Official contract and adapter behavior |
| --- | --- |
| Direct API | `POST https://api.minimax.io/v1/chat/completions`, JSON with `Authorization: Bearer <API key>`. This is MiniMax's own service, independent of the OpenAI SDK and OpenRouter. |
| Surface | Use the current [Chat Completions endpoint](https://platform.minimax.io/docs/api-reference/text-chat-openai). The older [`/v1/text/chatcompletion_v2`](https://platform.minimax.io/docs/api-reference/text-post) is documented as deprecated. |
| Request | Exact model ID, system/user `messages`, `stream: false`, and `reasoning_split: true`. Only an explicit operator output maximum adds `max_completion_tokens`. No tools or routing/fallback instructions. |
| Response | One `choices[0]` with an assistant message and string `content`; completion must end with `finish_reason: stop`. Read identity from response `model`, response ID from `id`, and usage from `usage`. |
| Semantic failure | Check MiniMax's `base_resp.status_code`, input/output sensitivity flags, refusal and finish fields before accepting any action, including a legal-looking partial action. |

The [current model list](https://platform.minimax.io/docs/faq/models) lists
`MiniMax-M3.1-Flash` and `MiniMax-M3`. An explicit nonblank model ID is required;
`MiniMax-M3.1-Flash` is an example, not a CLI default. M3.1 Flash gets a small hand-maintained capability override;
account visibility stays unknown. Explicit unknown IDs are sent unchanged.
Broker-prefixed IDs in the broader catalogue are not translated to direct IDs.

The model-list page contains conflicting retirement information: its notice says
M2.5/M2.7 pay-as-you-go access ends November 18, 2026, while its retired table
already lists those families. It also says subscription requests using those
names are automatically routed to M3.1 Flash from October 19. Use exact current
IDs and a suitable pay-as-you-go account for identity-sensitive work. Core never
rewrites IDs, and rejects a response declaring a different model. A missing
response identity remains null and cannot establish official eligibility.

## Region and credentials

`minimax` is the supported provider namespace (case-insensitive); no additional
region/plan aliases are introduced. The international host is the default.
MiniMax's [mainland China documentation](https://platform.minimax.cn/docs/api-reference/text-chat-openai)
uses `https://api.minimax.cn/v1/chat/completions`. Keys must belong to the selected
service region; [MiniMax's region troubleshooting](https://platform.minimax.io/docs/m-plan/faq)
distinguishes global and mainland keys. Core never infers a region from key text
or switches hosts after authentication failures.

Core reads only `MINIMAX_API_KEY` for this route. Obtain the intended credential
from the [official account setup](https://platform.minimax.io/docs/guides/quickstart-preparation).
Pay-as-you-go and subscription resources have different account semantics. Core
does not inspect a key to attest its billing plan or model availability.

An operator may explicitly use the existing endpoint override in Python:

```python
from eslams.agents import ModelProviderAgent
from eslams.contracts.provider import ProviderRuntimeConfig

agent = ModelProviderAgent(
    provider="minimax",
    model="MiniMax-M3.1-Flash",
    api_key_env="MINIMAX_API_KEY",
    runtime_config=ProviderRuntimeConfig(
        gateway_base_url="https://api.minimax.cn",
        gateway_mode="generic_base_url",
    ),
)
```

This is an explicit destination choice. Only the documented path is appended;
Core does not try another host. Region access and data residency are not attested
by a successful fixture or a receipt's gateway mode.

## Reasoning, history and privacy

The [official SDK contract](https://platform.minimax.io/docs/api-reference/text-openai-api)
separates reasoning with `reasoning_split: true`. This controls formatting, not
reasoning activation. M3.1 Flash always reasons; its supported effort levels are
`low`, `medium`, `high`, `xhigh`, and `max`. Unsupported effort values fail
configuration preflight and dispatch locally. Effort is rejected for M3 and
unknown IDs because real depth tuning is not documented for them. `reasoning=auto`
leaves native defaults untouched. Explicit enabled thinking sends `thinking.type=adaptive`
for the documented models. Disabled thinking is rejected for M3.1 Flash and
unknown models; exact `MiniMax-M3` sends `thinking.type=disabled` as documented. No game or registry recommendation selects effort.
M3 sampling is fixed upstream, so the adapter omits temperature and top-p.
Explicit token budgets from other providers, including zero and the Gemini
-1 sentinel, fail locally before discovery or transport.

Each `/act` is a fresh conversation containing the entire actor-authorized public
history supplied by the caller, unless the operator explicitly selected Core's
existing history window. It does not retain private conversation state across
actions, seats or runs.

If the operator enables action repair, that continuation includes the complete
assistant message, including `reasoning_content` and any `reasoning_details`,
before the repair prompt. This follows the [full-message preservation guidance](https://platform.minimax.io/docs/guides/text-m3-function-call).
Reasoning stays in an invocation-local context, including concurrent calls, and
is discarded when the action finishes or fails. It
is never used as action text or stored in receipts/public artifacts. Inline
`<think>` output violates the requested separated format and is rejected.
Tool calls are rejected; Core does not run a tool loop.

## Errors, retries and accounting

The [official error table](https://platform.minimax.io/docs/api-reference/errorcode)
defines native codes. The adapter classifies authentication (`1004`, `2049`),
sensitivity/refusal (`1026`, `1027`, `1046`), throttling, transient service errors,
timeouts, unavailable models and request/quota errors. Unknown nonzero native
codes fail closed. Provider error/refusal prose never enters diagnostics.

Classification alone does not authorize a replay. Core defaults to zero retries.
With explicit retries, only a complete bare `base_resp` rate rejection (`1002`)
or a narrowly verified OpenAI-style rate error can be replayed. Any generation
ID, usage, cost, choice, extension, malformed/conflicting classifier or partial
body blocks replay. HTTP 5xx and ambiguous timeouts are not automatically retried,
even where the provider suggests retrying later. `Retry-After` and existing
operator deadline/admission policies apply. Receipts retain actual HTTP status,
including HTTP-200 semantic errors, and every physical attempt remains separate.

MiniMax documents [model/interface-dependent RPM and TPM limits](https://platform.minimax.io/docs/guides/rate-limits).
Core does not hard-code those mutable account limits. Shared transport provides
bounded untrusted response parsing, cancellation, concurrency admission and
operator-selected time limits. Total/read/output limits remain absent by default;
provider limits still apply. No automatic action repair follows refusal,
truncation or malformed provider envelopes.

Usage maps only documented `prompt_tokens`, `completion_tokens`, `total_tokens`,
`prompt_tokens_details.cached_tokens`, and
`completion_tokens_details.reasoning_tokens`. Reasoning is included in output
and is not added twice. Shared canonical total derivation is labelled when a
provider total is absent; missing input/output/cache/reasoning counts remain
unknown. [MiniMax's caching contract](https://platform.minimax.io/docs/api-reference/text-prompt-caching)
defines cached tokens as a subset of total prompt tokens. Negative, malformed
and incoherent usage remains visibly incomplete. Error-body observations are
quarantined and cannot establish cost or model identity.

No reviewed MiniMax price card or measured request cost is supplied by this
change. Cost stays unavailable rather than assuming zero or inventing rates.
A configured receipt alone does not make a run eligible for official scoring.

## Commands and verification

Configuration-only checks are keyless and make no inference request:

```bash
eslams providers preflight --provider minimax --model MiniMax-M3.1-Flash --arena tic-tac-toe
eslams providers models --provider minimax
python -m pytest tests/test_minimax_provider.py
```

No documented account Models API was verified for this adapter. Live discovery
reports that limitation; it does not invent visibility from the catalogue.
Only if the operator explicitly authorizes paid inference and configures the
credential should they run `providers preflight ... --live` or:

```bash
eslams run --arena tic-tac-toe --agent minimax:MiniMax-M3.1-Flash --opponent first-legal
```

Tests cover exact request/auth/identity, full history and default limits, explicit
effort/output controls, repair reasoning retention and cleanup, native and HTTP
errors, definitive and ambiguous 429s, malformed/duplicate/partial JSON, refusal,
truncation, regional override, namespace consistency, incomplete accounting and
artifact privacy and isolation of concurrent repair reasoning. They use synthetic
local transport doubles, not paid inference.

## Cloud validation record

Linux, Python 3.12.14, 2026-11-04; base commit
`270a863d10d57a0953f21924f1a0dd50159e6cf1`.

| Check | Result |
| --- | --- |
| MiniMax raw-wire/integration suite | 111 passed |
| Focused MiniMax, existing native wire/completion/receipt and README checks | 130 passed |
| Full Python suite | 1,369 passed, **2 failed**; not a passing full-suite result |
| Untouched-base full suite | 1,258 passed, **2 failed** |
| Ruff / mypy | Passed; mypy checked 104 source files |
| Versioned arena fingerprints | Passed for 50 arenas |
| Schema export | Passed |
| Wheel and source archive build | Passed; adapter/registry and source docs/tests included |
| Offline CLI preflight / model listing / default and case spelling checks | Passed; no inference |

The two failures were independently reproduced in a detached, unchanged base
checkout with `PYTHONPATH` pointing at that checkout's `src`:

- `tests/test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
  expects a timeout exception but receives `ProviderCallError` after observed
  partial-response custody.
- `tests/test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`
  expects `board_winner == player_1` but receives null in this environment.

These failures remain unresolved and are not marked passed or excluded from
the full-suite count. No paid inference, provider secret use, hosted workflow
dispatch, merge, deployment, version bump or release was performed for validation.

## QA correction verification (2026-11-10)

The [current official chat schema](https://platform.minimax.io/docs/api-reference/text-chat-openai)
confirms the forced-thinking and effort restrictions above. The mainland
[official schema](https://platform.minimax.cn/docs/api-reference/text-chat-openai)
currently uses `api.minimax.cn`; the review's `api.minimaxi.com` spelling is not
the current documented endpoint. No automatic regional choice is added.

Opaque primary and secondary credentials, raw and JSON-decoded keys/values,
are excluded before Core action parsing or repair. Provider-controlled receipt
identifiers are suppressed on success, errors, malformed and partial responses;
transport prose is fixed and private exception contexts are discarded. Explicit
repair still keeps full private assistant history, and receipts keep observed
usage. Removing a contaminated identifier does not grant safe replay.

Existing provider tests were updated to assert the corrected explicit control
semantics, not skipped. Historical validation above describes the original
draft; correction-pass results and exact head are recorded in the PR description.
