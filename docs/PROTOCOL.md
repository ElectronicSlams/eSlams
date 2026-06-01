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
- illegal action: retry according to policy, then arena penalty
- crash: `agent_crash`
- no action: `no_action`

Core records those markers into the trace and replay-safe event stream.
