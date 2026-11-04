# Z.ai and Zhipu direct APIs (0.7.1 candidate)

This adapter uses standard, separately billed API keys. It performs no fallback.
Choose the service explicitly; the namespace determines the host and credential:

| Agent | Service | Credential | POST endpoint |
| --- | --- | --- | --- |
| `zai:glm-5.3` | Z.ai international | `ZAI_API_KEY` | `https://api.z.ai/api/paas/v4/chat/completions` |
| `zhipu:glm-5.3` | Zhipu/BigModel China | `ZHIPU_API_KEY` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` |

Both use Bearer authentication. These service labels identify routing, and do
not certify data residency. Keys are never tried against the other service.
See the official [Z.ai quick start](https://docs.z.ai/guides/overview/quick-start)
and [Zhipu HTTP guide](https://docs.bigmodel.cn/cn/guide/develop/http/introduction).

`z.ai` and `z-ai` alias only `zai`; `zhipuai` aliases only `zhipu`.
The former catalogue alias `zhipuai-coding-plan` has been removed: it must not
activate standard API billing. Coding Plan namespaces and endpoints remain
unsupported. This is an intentional compatibility change to catalogue alias
lookup. Existing literal standard-service model IDs are preserved, including
unknown IDs; vendor-prefixed catalogue names are never stripped or rewritten.
The CLI defaults to `glm-5.3` only when no model is supplied.

```bash
# Offline configuration check: no network or inference.
eslams providers preflight --provider zai --model glm-5.3

# Export the appropriate standard API key yourself before a paid run.
eslams run --arena tic-tac-toe --agent zai:glm-5.3 --opponent first-legal
```

`--live` preflight performs inference and can incur charges. No documented Models
API is assumed: live discovery reports unavailable and account visibility stays
unverified. Catalogue membership does not prove access. Official reference text
models include `glm-5.3`, `glm-5.2`, `glm-5.1`, `glm-5`, `glm-4.7`, and `glm-4.6`;
overrides record those models as account-dependent, without asserted prices.

## Request and completion handling

The adapter sends non-streaming `model`/`messages`, including Core's system
instructions and complete supplied public game history in its existing prompt.
It does not retain hidden reasoning across game actions or synthesize assistant
reasoning history. Preserved-thinking mode (`clear_thinking: false`) and tool
execution are outside this text-action adapter. Z.ai's [thinking guide](https://docs.z.ai/guides/capabilities/thinking-mode)
requires exact historical reasoning blocks when that mode is used.

Automatic reasoning omits controls. Explicit `reasoning=enabled/disabled` maps
to `thinking.type`, and explicit `reasoning_effort` passes through unchanged.
GLM-5.3 forces thinking; a disabled request is submitted unchanged and any
endpoint rejection retains an attempt receipt. Token-budget thinking controls
are rejected before submission. No arena determines reasoning policy.
Provider defaults and restrictions still apply. No Core output or total/read
time limit is introduced; caller output limits map to `max_tokens`. Existing
connect/write protection, explicit deadlines and cancellation remain in force.

Only one complete assistant text choice with `finish_reason: stop` is accepted.
Sensitive/refusal, length/context truncation, network interruption, tool output,
missing completion fields and malformed envelopes fail before action parsing.
The official [Z.ai REST reference](https://docs.z.ai/api-reference/llm/chat-completion)
and [Zhipu REST reference](https://docs.bigmodel.cn/api-reference/模型-api/对话补全)
are the wire-shape sources.

## Receipts, accounting and retries

Response `model` alone attests resolved identity; absent identity stays null.
Usage reads documented prompt, completion, total and cached-prompt counters.
Missing total is not derived, and missing reasoning/cache-write counts,
reasoning inclusion and cost remain unknown. Extra cost or reasoning telemetry
is not promoted into canonical accounting. Unknown reasoning inclusion can
prevent official accounting eligibility even when an action succeeds.

Shared transport and invocation-scoped receipt custody handle every submitted
attempt. HTTP failures retain status and safe request IDs; business errors in
HTTP 200 also fail. Error-body observations remain quarantined. Private error
prose and `reasoning_content` never enter receipts or public artifacts.

Default transport retries and action repairs are both zero. Explicit retries
can replay only HTTP 429 envelopes containing a documented `1302` request-rate
or `1305` overload rejection, without extra fields or work evidence. Balance
`1113`, plan limits, malformed errors, timeouts, transport failures and 5xx are
never automatically replayed. Retry-After and caller deadlines use the shared
implementation. See official [error codes](https://docs.z.ai/api-reference/api-code).

## Verification and fixture provenance

Researched 2026-11-04. `zai_chat_completions_success.json` is a redacted,
deterministic instance of the documented REST envelope, not captured inference
or an SDK convenience object. IDs, content and counts are synthetic; its private
reasoning sentinel tests exclusion. The same envelope tests the China route.
Fault-injection cases preserve that shape where applicable. No credentials or
paid inference were used for verification.

The text model's GLM-5.3 guide currently shows a Coding endpoint in its protocol
table, while the standard API reference and quick start show `/api/paas/v4`.
This adapter follows the latter standard API sources and never substitutes
Coding Plan routing. Live availability remains unverified.
