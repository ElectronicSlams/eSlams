# Direct Perceptron adapter

This adapter targets the next 0.7.1 review from Core 0.7.0 without changing the
package version. Research checked 2026-11-04. No live inference or real provider
credentials were used; game strength, account entitlement, latency, deployment
region, and billed cost remain unverified.

## Contract and evidence

| Concern | Official evidence and adapter behavior |
| --- | --- |
| Endpoint and authentication | [Quickstart](https://docs.perceptron.inc/perceptron-mk1.5): `POST https://api.perceptron.inc/v1/chat/completions`, JSON, `Authorization: Bearer $PERCEPTRON_API_KEY`. No SDK/provider auto-selection, fal, router fallback, or replacement model. |
| Region | The quickstart specifies one public hostname; these sources establish no regional hostname selector or data-residency guarantee. Core's Bedrock region setting has no effect here. An explicitly configured existing gateway override still changes the destination and is represented in receipts. |
| Model and lifecycle | [Mk1.5 model card](https://docs.perceptron.inc/perceptron-mk1.5/models/perceptron-mk1.5), [release notes](https://docs.perceptron.inc/perceptron-mk1.5/changelog), and [official SDK README](https://github.com/perceptron-ai-inc/perceptron/blob/5607603b55fa4d57cc11e6a0f11912801f841dd8/README.md): current IDs `perceptron-mk1.5` and `perceptron-mk1`; Mk1.5 released 2026-09-25. Preview ID was renamed; Isaac IDs retired on the direct API. Core never rewrites an old ID to a new one. |
| Text suitability | [Mk1 reference](https://docs.perceptron.inc/perceptron-mk1/api-reference/endpoint/chat-completions) explicitly supports text-only responses. Mk1.5 accepts text input and emits text. This establishes a text-game protocol fit, not measured game ability. Detection and asynchronous egocentric annotation services are separate products, unused here. |
| Request | Exact nonblank model ID, `messages` containing Core's ordinary system instructions and public ActRequest prompt. Full supplied public history by default. Only explicit operator controls add `temperature`, `max_completion_tokens`, or reasoning fields. No media, tools, search, or agent loop is enabled. |
| Response and identity | [Official SDK chat wire parser](https://github.com/perceptron-ai-inc/perceptron/blob/5607603b55fa4d57cc11e6a0f11912801f841dd8/src/perceptron/chat.py): `object: chat.completion`, one indexed assistant choice, final text at `choices[0].message.content`. Response `model` alone supplies `locked_model_id`; missing or secret-bearing identity stays null. Requested model and provider stay distinct from resolved identity. `x-trace-id` is a correlation ID, not model attestation. |
| Reasoning | [Mk1.5 reasoning guide](https://docs.perceptron.inc/perceptron-mk1.5/capabilities/thinking): explicit `reasoning_effort` values `none`, `minimal`, `low`, `medium`, `high`; `minimal` currently maps server-side to `low`, while Core sends the exact chosen tier. Mk1 uses documented `vision_config.enable_thinking` booleans. Native defaults mean neither field is sent. Enabling Mk1.5 reasoning requires a tier; token budgets and unverified model-specific controls fail before IO. No game selects a tier. |
| Finality and tools | Only `finish_reason: stop` with nonempty final text is accepted, following the reasoning guide's completed-answer example. `length`, refusal/filtering, tool calls (including calls alongside `stop`), missing/unknown finish reasons, and malformed shapes fail with receipts. The SDK also calls `interrupted` complete, but the guide's stricter `stop` check is used here; such responses are rejected, never silently applied. Reasoning content is neither joined to action text nor persisted. |
| Usage | [Tokenization guide](https://docs.perceptron.inc/perceptron-mk1.5/guides/tokenization): `usage.prompt_tokens`, `completion_tokens`, `total_tokens`; completion includes reasoning, cache tokens are a subset of input. Optional breakdowns remain unknown when absent. Shared normalization validates numeric observations and labels any derived total. Missing usage stays unavailable. No OpenRouter prices, SDK convenience properties, or guessed token counts feed receipts; cost stays unavailable without verified pricing. |
| Errors and retry | [Error guide](https://docs.perceptron.inc/perceptron-mk1.5/guides/error-messages) and [SDK HTTP error parser](https://github.com/perceptron-ai-inc/perceptron/blob/5607603b55fa4d57cc11e6a0f11912801f841dd8/src/perceptron/_transport.py): errors use HTTP status and an `error` object with `message`, `type`, `param`, `code`. 400/401/403/404 need corrected request/auth/access/model; 429 distinguishes `insufficient_quota` from `rate_limit_error`; 5xx and transport failures can be ambiguous. Core defaults to zero retries. Optional shared safe retries require an unambiguous rate rejection without work/usage observations and respect `Retry-After`; quota, 5xx, timeout, malformed, and partial responses are never automatically replayed. Error-body accounting is quarantined and never becomes verified pricing or model identity. |
| Service lifecycle | [Services overview](https://docs.perceptron.inc/services/index) separates model inference from Detect and Egocentric jobs. This adapter creates no jobs, uploads, polling loops, or persistent provider resources. Core closes each HTTP transport request using its existing cancellation, bounded response, and deadline machinery. No total/read deadline or output maximum is added by default. The existing connection safety timeout remains. |

The fixture `tests/fixtures/provider/perceptron_chat_completions_success.json`
is a synthetic redacted game action in the official raw envelope, derived from
the pinned SDK's `tests/_http_mock.py:completion` and `chat.py` wire parser plus
the tokenization guide's usage fields. It is not a captured paid inference or
evidence of game performance. Fault cases preserve that envelope where applicable.
Credential-bearing final answers are rejected, including escaped JSON strings;
credential-bearing receipt observations are removed on success, HTTP errors,
invalid JSON, and transport failures after headers arrive.
Redaction snapshots the selected credential and nonempty configured environment
values whose names identify API/access keys, tokens, secrets, passwords, or
credentials. These secondary values are used only for redaction and never added
to requests or receipts. A discovery response containing such a value in a model
ID fails as a whole; no redacted ID or apparently complete partial list is returned.

## Use

Offline configuration check (no key or network required):

```bash
eslams providers preflight --provider perceptron --model perceptron-mk1.5 --arena tic-tac-toe
```

To run after separately authorizing paid use, export `PERCEPTRON_API_KEY` in the
process environment and choose the model explicitly:

```bash
eslams run --arena tic-tac-toe --agent perceptron:perceptron-mk1.5 --opponent first-legal
```

`perceptron`, `perceptron:`, and whitespace-only IDs fail; there is no default
model. Unknown nonblank IDs pass through exactly with native reasoning defaults;
unsupported reasoning settings fail locally. Historical/renamed IDs are not
silently upgraded. Account visibility is advisory by default; `--strict-catalogue`
retains Core's opt-in policy. The two direct model records are documentation
metadata, with availability and pricing deliberately unverified.

`eslams providers models --provider perceptron --live` queries the documented
Models API. Preflight `--live` also submits inference and can incur charges;
configuration-only success does not authorize or prove inference. CLI
`--reasoning auto` keeps native defaults; `--reasoning disabled` explicitly
disables reasoning. Mk1 also accepts CLI `--reasoning enabled`. Mk1.5 effort
tiers are configured through Python's `ProviderRuntimeConfig(reasoning_effort=...)`;
the existing CLI has no effort-tier flag, so `--reasoning enabled` alone fails
for Mk1.5 instead of choosing an arbitrary tier.

## Cloud validation

Base: `ElectronicSlams/eSlams` at
`270a863d10d57a0953f21924f1a0dd50159e6cf1`, Python 3.12. No Core `AGENTS.md`
or `.agents/skills` was present. The environment initially contained the separate
Platform checkout; it was left unchanged and Core was cloned separately.

- Final provider test file: **77 passed**, including CLI run/artifact dispatch,
  offline and mocked-live preflight, Models discovery, exact requests, native
  defaults, full history, unsupported settings, errors, retry safety, and
  credential echoes across success/error/malformed/partial responses.
- Full suite: **1,334 passed, 2 failed** in 83.65 seconds. This run includes
  the first 76 provider cases; the subsequently added CLI artifact case passed
  with the complete 77-case provider file. The earlier README-link regression
  was corrected and its test rerun successfully (98 focused checks passed).
- Both remaining failures also reproduce against a pristine detached checkout
  of the base commit: `tests/test_elapsed_deadline_regressions.py::test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
  and `tests/test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`.
  The first expects `TimeoutError` while Core emits a receipt-bearing
  `ProviderCallError` after response headers; the second expects `player_1`
  but observes a null board winner. They were left outside this adapter's scope.
- An initial full run also had a process-death checkpoint failure and a wheel
  provenance failure while the working tree was being edited. Both passed on
  pristine rerun and in the final full suite; they are not counted as confirmed
  inherited defects.
- Repository-wide Ruff and mypy passed; both TypeScript packages type-checked
  with TypeScript 5.5.4. Two schema exports matched byte-for-byte. Wheel/sdist
  built and `twine check` passed. All 50 arena behavior fingerprints and initial
  budgets passed; the ten-iteration keyless Tic Tac Toe benchmark completed.

Other Python/OS matrices, replay browser tests, live account/model visibility,
paid inference, merge, deployment, and release were not run. The draft PR uses
`[skip ci]` on its head commit, following
[GitHub's documented skip behavior](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs),
to avoid hosted push/pull-request workflows; workflow configuration is unchanged.

Follow-up cross-draft review: 60 additional cases cover missing/blank IDs,
unsupported explicit budgets (including zero), whitespace-provider preflight,
selected/default/secondary credential echoes in identifiers and final actions,
HTTP/body errors, malformed and partial transport responses, and discovery.
Twenty-nine of these cases failed against the original draft. The fixed tree
passes all 137 Perceptron cases and 146 focused provider/discovery checks.
The full suite passes 1,395 tests with only the same two inherited failures
listed above (92.81 seconds); repository-wide Ruff and mypy also pass.
Full supplied history, zero default retries, and the no-replay rule for observed
work remain covered by the original tests. Only synthetic credentials and mocked
provider IO were used for this review; no hosted CI, merge, or release was run.
