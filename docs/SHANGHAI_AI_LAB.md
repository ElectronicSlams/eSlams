# Shanghai AI Laboratory / Atria text adapter

This is proposed adapter work for 0.7.1 on the 0.7.0 Python Core baseline. The
package version stays 0.7.0. The CLI namespace is `shanghai-ai-lab`; the only
verified model accepted by this adapter is the exact, case-sensitive
`Atria-Dawn`. Missing IDs, aliases and other models fail before a request.

## Sources and service boundaries

Research checked November 4, 2026:

- [Official Atria model release](https://github.com/atria-asi/Atria-Dawn): identifies
  Shanghai AI Laboratory as the model developer, separates hosted access from
  SGLang/vLLM deployment, and specifies the model ID. Its current China and
  international console links both point to Discovery, with different languages.
- [Atria API reference](https://api.atria-asi.ai/docs): supplies the text request,
  Bearer authentication, Chat Completions response paths, output-limit range,
  and rate-limit headers. The [service notice](https://api.atria-asi.ai/) describes
  international forwarding and recommends Discovery for mainland China or higher
  usage. A geographic execution region or data residency is not attested.
- [InternLM migration notice](https://internlm.intern-ai.org.cn/docEn/docs/service-migration/):
  the legacy API automatically routes other model IDs to Intern-S2 from November
  9, 2026 and closes January 26, 2027. This adapter never uses that endpoint.
- [Legacy Chat API](https://internlm.intern-ai.org.cn/docEn/docs/Chat/): documents
  `thinking_mode` for certain Intern models, application error codes, a 30 RPM
  default and a server-side 120-second interruption. These are not transferred
  to the separate Atria service.
- [Discovery Scientific Models](https://discovery.intern-ai.org.cn/token-plan/home):
  advertises `https://discovery-api.intern-ai.org.cn/v1`. The current document
  page had no readable browsing content and a cloud HTTP fetch returned 403.
  No Discovery request/response contract is assumed from its compatibility label.

The adapter calls the Atria operator service using its own key. Third-party
OpenRouter/AIHubMix/other routing and self-hosted model weights are separate
execution providers, even when they name the same model. No automatic switch to
Discovery, the legacy API, another model, or a self-hosted endpoint is implemented.
Generic gateway overrides and OpenRouter route controls are rejected here.

## Configuration

Set `ATRIA_API_KEY` only when deliberately requesting inference. Tests use fake
credentials and deterministic wire responses; they need no account or paid calls.

```bash
# Offline configuration check. This makes no inference or discovery request.
eslams providers preflight --provider shanghai-ai-lab --model Atria-Dawn

# Gameplay syntax; this makes real calls using your configured Atria key.
eslams run --arena tic-tac-toe --agent shanghai-ai-lab:Atria-Dawn
```

The frozen model catalogue is unchanged. Its absence of an Atria model row
remains visible as a warning; strict catalogue mode does not invent eligibility.
No documented Models API is assumed. `--live` preflight explicitly requests one
inference, with account visibility still unknown. It may incur charges.

## Wire behavior and conservative accounting

The adapter posts JSON to `https://api.atria-asi.ai/v1/chat/completions` with
`Authorization: Bearer <ATRIA_API_KEY>`. One user message contains Core's common
action instructions, observation, legal actions and full supplied public history.
Explicit history truncation is rejected. There are no arena-dependent controls.

Only a nonempty string at `choices[0].message.content` with `finish_reason=stop`
is accepted. Truncation, refusal, wrong shapes, tool calls, reported search,
pending responses, redirects and conflicting returned model IDs fail closed.
No tools, search request, fallback selector, SDK, or automatic model discovery
is added. The adapter never executes a returned tool call.

Native reasoning defaults are retained. Explicit enable/disable, effort and
budget controls are rejected: client configuration examples do not establish a
complete native reasoning contract. Explicit temperature is also rejected.
The optional caller output maximum is forwarded as `max_completion_tokens`,
validated against the documented 1–65,536 range. Omission leaves the provider
default intact. Core adds no total/read deadline; explicit caller deadlines
still apply through the existing safe transport and cancellation controls.

Only documented `usage.prompt_tokens` and `usage.completion_tokens` paths are
projected into receipts. Missing fields stay unknown. Reasoning inclusion and
cache accounting are unverified, so no total is inferred, `usage_complete` stays
false, and costs stay unavailable. No free-price assumption is made. Optional
returned model/response IDs are observations, not invented defaults; absent
model identity stays null. A returned model that differs from the request fails.
These limits do not establish Official eligibility.

HTTP 400, 401, 403, 404, 429 and 5xx use Core's existing typed errors. Error-body
accounting remains quarantined by the shared transport. The reference documents
401/429/5xx, with 429 covering either rate limits or quota exhaustion, and
`Retry-After` in seconds. Retry hints are recorded, but no verified error envelope
establishes safe replay: this adapter never marks a failure retry-permitted,
including when the caller raises the default-zero retry maximum. Ambiguous
timeouts, partial responses and malformed bodies are never replayed.

Exact active-credential echoes in parsed response strings or keys cause rejection
before action parsing. Success headers and every failure receipt, including
partial header observations, receive exact credential scrubbing in addition to
Core's standard projection/redaction. Echoed identifier fields become null.
Raw error bodies and provider prose do not become public diagnostics.

## Fixture provenance and validation

`tests/fixtures/provider/shanghai_ai_lab_atria_success.json` instantiates the
non-streaming field paths under the API reference's “Read the response” section.
Values and legal-action text are synthetic. It deliberately supplies no invented
IDs, totals, prices, cache or reasoning fields; it is not a captured live response.
Fault injections in `tests/test_shanghai_ai_lab_adapter.py` cover CLI/preflight,
dispatch, full history, omitted/explicit controls, status/transport failures,
malformed/partial bodies, missing accounting, mismatched identity, incomplete
generation and credential echoes (including JSON-escaped plain strings).

The pre-edit baseline at `270a863d10d57a0953f21924f1a0dd50159e6cf1` had
1,258 passing tests and two inherited failures:

- `test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
- `test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`

No existing tests, historical fixtures or expected arena fingerprints are changed
to make the baseline green. No live inference, account creation, credentials,
deployment, merge or release was used to validate this adapter.

Cloud checks also cover 71 adapter cases, 133 combined provider/CLI cases,
Ruff, mypy, both TypeScript packages, wheel/sdist build and Twine validation,
two identical schema exports, and all 50 arena fingerprints. During a full-suite
rerun, the existing slow-body deadline case
`test_total_http_deadline_cancels_slow_headers_and_trickled_body_in_worker[trickle]`
also failed intermittently. It passed in isolation; the complete deadline file
on both an untouched baseline worktree and the adapter branch had five passes
and only the already inherited runtime-deadline failure. This does not establish
timing stability for that existing test.
