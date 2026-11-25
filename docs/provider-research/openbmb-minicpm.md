# OpenBMB / MiniCPM direct API assessment

Assessed 2026-11-04 in Codex cloud against Python Core 0.7.0 at
`270a863d10d57a0953f21924f1a0dd50159e6cf1`.

## Decision

An official direct text inference service exists. A native adapter is deferred
because the accessible official material does not establish enough of its raw
response, identity, accounting, and failure contract to implement and test it
without assumptions. This is an evidence gap, not a claim that ModelBest has no
API. The `openbmb` catalog identity remains unchanged and unavailable for native
inference. No version bump, runtime changes, paid calls, account creation, or
credential use are part of this assessment.

## Verified direct service

The authoritative [OpenBMB API guide](https://github.com/OpenBMB/MiniCPM-V/blob/13151386d22afd81d1a65940657e6a624095691e/docs/api.md)
documents `POST https://api.modelbest.cn/v1/chat/completions`, JSON requests,
Bearer authentication, and API key creation at `platform.modelbest.cn`.
It lists these exact service model IDs:

- `MiniCPM-V-4.7-1B`
- `MiniCPM-V-4.7-35B-A3B`
- `MiniCPM-V-4.5-9B`
- `MiniCPM-V-4.6-1B`
- `MiniCPM-V-4.6-Thinking`
- `MiniCPM-O-4.5-9B`

Its text examples send `model` and a `messages` array and read
`choices[0].message.content`. For 4.7, thinking defaults off and is enabled using
`chat_template_kwargs.enable_thinking`; reasoning appears separately in
`message.reasoning`. The 4.6 Thinking variant may also return that field. The
guide does not define effort levels or reasoning token budgets.

The [official knowledge base](https://openbmb.cn/docs/en/guides/minicpm-v/)
links directly to this guide for API access. The
[ModelBest company site](https://modelbest.cn/en) links to OpenBMB's model repos.
Together these establish the operator's own documented service, rather than an
inference route inferred from a model author's name.

A [maintainer clarification on issue 1123](https://github.com/OpenBMB/MiniCPM-V/issues/1123)
directs callers to the updated guide and identifies the old `.co` hostname and
`MiniCPM-V-4.6-Instruct` identifier as obsolete. Historical examples must not be
treated as current endpoint or model aliases.

## Service, routing, and weights are different identities

The direct service above is distinct from third-party model routing through
OpenRouter, Hugging Face inference providers, or another operator. A router's
model ID, usage, authentication, and failover settings do not prove the direct
ModelBest contract. Core must preserve the selected provider and exact ID.

[OpenBMB/MiniCPM](https://github.com/OpenBMB/MiniCPM) publishes MiniCPM5 text-model
weights and local inference instructions. The direct API guide's inventory does
not establish MiniCPM5 service IDs. Do not rewrite a weights ID such as
`openbmb/MiniCPM5-2B` into a presumed hosted ID. Likewise, the
[official deployment guide](https://openbmb.cn/docs/en/guides/minicpm-v/minicpm-v-4.7/deploy)
describes self-hosting. A local vLLM/SGLang OpenAI-compatible server attests to
that deployment, not to ModelBest's hosted response semantics. Realtime audio
and OCR services are separate contracts and do not fill the text API gaps.

## Exact evidence gaps

| Area | What is established | What remains unverified |
| --- | --- | --- |
| Endpoint and auth | HTTPS POST, Bearer key, JSON, current `.cn` hostname | Account eligibility and current account-specific availability were not exercised. |
| Region | One published service URL | No documented selectable inference region, compute location, or geographic account restrictions were found. A `.cn` domain is not region attestation. |
| Request and history | Exact `model` plus text `messages` examples | Hosted system-message constraints, context overflow behavior, and preservation of full input history are not specified in the guide. |
| Response | Text extraction path and separate reasoning field | No complete documented success envelope or fixture, finish-state enumeration, refusal/tool-output shape, or partial-response contract. |
| Identity and routing | Published request IDs for named models | No documented response `model` semantics, immutable revision attestation, or explicit guarantee/control preventing substitution or provider fallback. A requested model must never become a fabricated resolved identity. |
| Reasoning | 4.7 opt-in switch and 4.6 Thinking ID | Hosted behavior of disabling thinking, unsupported-control rejection, and reasoning-in-output token accounting. Do not infer controls from local chat templates. |
| Errors and retries | A historical issue includes an error object | No current authoritative text-service HTTP/error matrix, Retry-After semantics, or proof that a rate rejection did no work. The historical body is not a current error contract. |
| Usage and cost | No text-service accounting schema in the guide | Token field names, totals, reasoning/cache inclusion, error/partial usage, and a versioned price card. OpenAI compatibility alone does not establish these details. Missing accounting must remain unknown, never zero or estimated from output. |

The indexed [platform privacy policy](https://platform.modelbest.cn/console/legal/privacy)
states that personal information is stored within mainland China. This is a
storage statement, not a documented inference compute region. The platform root,
console, playground, and documentation pages could not be opened by the research
browser; an ordinary cloud GET to the root failed at the network proxy with
`Tunnel connection failed: 403 Forbidden`. This was a read failure, not an
inference authorization result. No login or network restriction bypass was tried.

## Conditions for implementing the adapter

Obtain accessible operator documentation or an operator-confirmed, redacted raw
wire contract covering the gaps above. A complete documented success fixture
is required by Core's `CONTRIBUTING.md` Provider Fixture Policy; an imagined
OpenAI-style envelope would not meet that rule. No public/shared API key should
be used to collect a fixture without permission.

When that evidence is available, implement in provider-specific files with
minimal CLI, preflight, and dispatch wiring. Reuse the existing bounded transport
and receipts; keep zero default retries and repair attempts. Preserve the exact
model/provider, full history, unknown identity/accounting, provider defaults, and
operator-selected limits. Reject missing or blank model IDs and unsupported
reasoning controls before network submission. Never add automatic tools, search,
fallback, arbitrary output/time ceilings, or game-dependent reasoning policy.

Test CLI/preflight/dispatch plus documented raw success and deterministic 400,
401, 403, 404, 429, 5xx, timeout, malformed/duplicate/nonfinite JSON, interrupted,
truncated, missing usage, model mismatch, and partial-response cases. Inject the
exact configured credential into response IDs, model/header values, reasoning,
error bodies, and action text; verify it cannot enter receipts, exception fields,
action metadata, or public explanations. Existing generic redaction is not
evidence that arbitrary exact-key echoes are removed on every new adapter path.

## Repository and validation scope

The cloud image initially contained the separate Platform repository. Core was
cloned into `/workspace/eSlams`; no Platform files were edited. No `AGENTS.md`,
`.agents/skills`, or `SKILL.md` files were present in the Core checkout, and the
workspace `.agents` directory was empty. The checkout's contributor instructions
and provider fixture policy were read. This change contains only this assessment;
there is no native adapter whose wire behavior can be claimed as validated.

Cloud validation used Python 3.12.14 and an isolated `/tmp/minicpm-venv` with
Core's dev dependencies:

```text
python -m pytest tests/test_provider_wire_v06.py \
  tests/test_provider_completion_regressions.py \
  tests/test_provider_credentials_and_waits.py \
  tests/test_provider_discovery_regressions.py tests/test_agent_cli.py \
  tests/test_native_receipt_invocations.py tests/test_arena_transport.py \
  --basetemp=/tmp/minicpm-pytest
38 passed in 3.22s

python -m ruff check src/eslams/agents.py src/eslams/provider_preflight.py src/eslams/cli.py
All checks passed!
```

A configuration-only call to `provider_preflight("openbmb",
"MiniCPM-V-4.7-1B", "tic-tac-toe")` returned `ok=False`,
`adapter_available=False`, and `provider_adapter_unavailable`. The CLI's
`_provider_agent("openbmb:MiniCPM-V-4.7-1B")` returned `None`. These checks made
no provider calls. No failures occurred in the selected existing tests; the
full suite, hosted CI, and live inference were not run. `git diff --check` passed.
