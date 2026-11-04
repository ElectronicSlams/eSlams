# Sakana Namazu direct adapter (0.7.1 candidate)

Research checked 2026-11-04 against Core base
`270a863d10d57a0953f21924f1a0dd50159e6cf1`. Package version remains 0.7.0.

## Service and identity boundary

Sakana's [official quick start](https://console.sakana.ai/get-started) publishes
`https://api.sakana.ai`, console-issued API keys and Bearer authentication.
This adapter calls that service directly. Credentials come from `SAKANA_API_KEY`.
No regional URL or deployment-location guarantee was established from the
reviewed material. The adapter makes no region or residency claim.

The [Namazu documentation](https://console.sakana.ai/models?model=sakana-namazu)
describes a single in-house model derived from Kimi K2.6, distinct from Fugu.
Supported literal IDs are `sakana-namazu-v1.0` and `sakana-namazu` (a mutable
alias). POST `/v1/chat/completions` accepts `model` and `messages`; assistant
text is `choices[0].message.content`. Thinking defaults on and is controlled by
`chat_template_kwargs.thinking`; thinking text is `reasoning_content`.
Tools require request definitions. The adapter sends an empty tool list and
`tool_choice: none`. Provider output limits still apply when omitted by Core.

[Fugu](https://console.sakana.ai/models) routes or orchestrates pools of models.
Its outer product ID does not attest each underlying model/provider. This native
adapter rejects Fugu IDs to preserve the task's identity requirement. The same
page documents additional orchestration billing counters, which this Namazu
adapter does not interpret. Third-party gateways are separate provider routes;
they do not establish first-party inference identity. Sakana's earlier
[model-merging releases](https://sakana.ai/evolutionary-model-merge/) provide
weights/code, not a hosted API contract for those weights.

## Operation

```sh
# Set SAKANA_API_KEY privately in your shell; do not put it into an artifact.
eslams providers preflight --provider sakana --model sakana-namazu-v1.0 --arena tic-tac-toe
eslams run --help
# In commands accepting --agent, use --agent sakana:sakana-namazu-v1.0.
```

Configuration preflight is keyless and makes no network calls. Explicit `--live`
performs account model discovery and paid inference; obtain authorization before
using it. GET `/v1/models` is documented by Sakana. No live inference, credential
creation or account enrollment was performed during implementation.

Core requires an explicit model ID. It forwards the requested ID unchanged,
preserves all supplied public history, and rejects history windows, gateways,
Fugu routes and unrelated provider-routing controls. `reasoning=auto` omits the
thinking control; `enabled`/`disabled` send a boolean. Effort levels and reasoning
budgets are rejected. There is no game-based reasoning policy, fallback, default
output cap or total/read deadline. Explicit operator limits still apply.

## Wire, accounting and failure evidence

Sakana refers to the [OpenAI Chat contract](https://platform.openai.com/docs/api-reference/chat/object).
The committed fixture follows that REST envelope with synthetic redacted values
and Namazu's documented thinking extension. It is a documentation-based fixture,
not a capture from a paid request. Only one completed assistant choice is accepted;
refusal, truncation, tool calls, unknown finish reasons and malformed envelopes
cannot become an action. Missing model evidence remains null; reported mismatches
are rejected. A pinned request alone never creates response identity evidence.

Standard prompt/completion/cache/thinking counters are normalized using Core's
existing accounting contract; thinking is included in completion tokens. Missing
counters remain unavailable. Error-body observations remain quarantined. Arbitrary
cost fields are ignored, and no bundled price card is added. The
[pricing page](https://console.sakana.ai/pricing) publishes pay-as-you-go Namazu
rates, bills thinking at the output rate and charges tools separately. These
published rates are not proof of a request's measured cost.

No Sakana-specific exhaustive error schema, rate-limit header contract or safe
replay guarantee was established. HTTP failures therefore use Core's status
classification with sanitized receipts; 429 is not automatically replayed even
when an operator requests retries. Default retries and action repair remain zero.
Timeouts, transport interruptions and partial bodies are never replayed.

Exact credentials are removed from receipt IDs, including malformed/error/partial
paths. Credential-bearing action text is rejected before parsing, including JSON
escaped values. Reasoning, prompts, headers and raw private envelopes are not
copied into receipts. Deterministic tests cover these boundaries, CLI dispatch,
configuration/live-preflight stubs and native request controls. Live availability,
actual identity, latency, regional access and account billing remain unverified.

## Cloud validation

- Python 3.12: 63 Sakana cases passed. Full candidate suite: 1,321 passed,
  two inherited failures. Untouched base: 1,258 passed, the same two failures.
- Inherited failures: `test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
  expects `TimeoutError` where an observed partial-body failure raises
  `ProviderCallError`; `test_cli_fallback_failing_seat_board_win_is_only_a_board_result`
  expects `board_winner=player_1` but receives null.
- Ruff, mypy (104 source files), both TypeScript projects, all 50 arena version
  fingerprints and initial-state budgets passed. Two schema exports matched
  byte-for-byte. Wheel/sdist builds and Twine checks passed; the wheel contains
  the provider module. Configuration-only CLI preflight succeeded without a key.
- No repository `AGENTS.md` or `.agents/skills` was present. The cloud workspace's
  `.agents` directory was empty. No workflow or package-version changes were made.
