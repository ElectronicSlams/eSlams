# eSlams Act Protocol

The first-class agent integration is `POST /act`.

The request is strict and versioned with `protocol_version: "eslams-act-v1"`. Agents receive only their allowed observation, a legal action list, public history according to the memory policy, and a time budget. The arena owns legality. The runner owns retries, failures, traces, scoring, artifacts, and replay generation.

Required response field:

```json
{ "action": "e2e4" }
```

Optional response fields:

```json
{
  "confidence": 0.82,
  "public_explanation": "Develops a central pawn.",
  "metadata": {}
}
```

Deterministic failures:

- invalid JSON: retry once in platform mode, then `invalid_action`
- timeout: `timeout`
- illegal action: `illegal_action`
- crash: `agent_crash`
- no action: `no_action`

Core records those markers into the trace and replay-safe event stream. Runner
failure policy is explicit:

```bash
eslams run --on-agent-error invalid-match --on-illegal-action invalid-match
eslams run --on-agent-error forfeit --on-illegal-action forfeit
eslams run --on-agent-error fallback --on-illegal-action fallback
```

`fallback` is the smoke/demo default and chooses the arena's deterministic
failure action. `invalid-match` records the run as not valid for scoring.
`forfeit` ends the match with the other player as winner and also records the
run as not valid for scoring.

## Provider-Backed Agents

Provider-backed agents still speak the same `/act` protocol. Core keeps provider
runtime concerns outside the public action contract and records them as
redacted provider receipts:

- timeout, connect timeout, read timeout
- retry count and retry backoff
- synchronous concurrency limit
- rate limit per minute
- generic gateway/base URL routing
- gateway mode and redacted gateway request ids
- normalized usage and explicit unavailable reasons
- pricing provenance and `cost_unavailable` when pricing is not configured

Provider receipts use `eslams.provider.receipt.v1`. Public replay exports never
include raw prompts, raw responses, request headers, tokens, API keys, or debug
provider payloads.

Run a no-spend provider preflight:

```bash
eslams providers preflight --provider openai --model gpt-5-mini --arena tic-tac-toe
```
