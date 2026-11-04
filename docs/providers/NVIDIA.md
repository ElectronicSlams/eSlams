# NVIDIA hosted inference

Research checked 2026-11-04 for the proposed 0.7.1 adapter, against Core 0.7.0.
The package version is unchanged. This adapter is suitable for authorized
development, testing and evaluation; production entitlement is **not verified**.

## Service and entitlement

The [NVIDIA NIM FAQ](https://docs.api.nvidia.com/nim/docs/product) limits Developer
Program access to research, development, testing and prototyping. Serving real
end users counts as production. Its production path requires an AI Enterprise
license. [NVIDIA's developer page](https://developer.nvidia.com/nim) directs
production deployments to licensed infrastructure or dedicated partner endpoints.
An AI Enterprise license does not, by itself, establish permission to use this
particular shared hosted endpoint for production.

The [API Trial Terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)
§1.2 exclude production use of both the trial service and generated content;
§4.3 restrict sensitive personal information; §3 describes data collection;
§8 permits service changes or withdrawal. Do not assume zero retention,
confidential processing, unlimited throughput or an SLA. Check the terms shown
to the actual account and the selected model's license before use. The adapter
does not certify entitlement or accept terms for the operator.

The [Lightning model card](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b)
identifies the OpenMDW 1.1 model license separately from the trial service terms.
Its global deployment geography is not a hosted data-residency guarantee. No
regional endpoint selector or regional residency commitment was verified for
`integrate.api.nvidia.com`; no region is invented or borrowed from Bedrock.

## Exact identity and authentication

Use `nvidia:<exact-model-id>`; aliases `nvidia-nim` and `nvidia-hosted` select the
same NVIDIA-hosted adapter and canonical receipt provider `nvidia`. All require
an explicit nonblank model ID. Model IDs retain case, namespaces and revisions;
Core does not prefix, translate, substitute, shorten or fall back to another model.
These aliases do not select local NIM containers or a partner's inference service.

The [hosted Lightning example](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b)
currently lists `nvidia/nemotron-3.5-lightning-30b-a3b` with an available Free
Endpoint, API-key authentication and reasoning output. Obtain a key through
NVIDIA's account flow and explicitly export `NVIDIA_API_KEY`. Core sends it only
as `Authorization: Bearer …` (never in a URL). This work used synthetic keys only.

Older [Super 49B v1.5](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5)
and [Nemotron 3 Nano](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b)
Free Endpoints are marked deprecated. A documentation page or frozen registry
entry does not prove current account availability. Core's frozen catalogue is
unchanged; this new example may be an unknown local record and strict catalogue
preflight may reject it. Standard preflight permits explicit unknown IDs.

```bash
# Offline configuration check: makes no inference request.
eslams providers preflight --provider nvidia \
  --model nvidia/nemotron-3.5-lightning-30b-a3b --arena tic-tac-toe

# Inference requires separate operator authorization and an exported key.
eslams run --arena tic-tac-toe \
  --agent nvidia:nvidia/nemotron-3.5-lightning-30b-a3b --opponent first-legal
```

An explicitly requested `--live` preflight makes an inference request. This
adapter has no verified account Models listing wired in: visibility remains
unknown, and `providers models --provider nvidia --live` reports discovery
unavailable. Successful inference proves one response, not production entitlement,
stable weights, a hardware pin, model immutability or complete cost accounting.

## Wire contract and reasoning

The [Lightning API reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b-infer)
specifies `POST https://integrate.api.nvidia.com/v1/chat/completions`, Bearer auth,
`model`, and `messages`. Core requests `stream: false` and JSON, with a system
instruction and user message containing the standard observation/action prompt
and full public history. There is no automatic history window, output cap,
total/read deadline, reasoning budget, effort, sampling override or game-specific
reasoning policy. Existing transport connect and response-resource limits remain.
Explicit operator output/temperature choices pass through; NVIDIA may reject them.
Omitted limits leave NVIDIA's native constraints in effect.

Lightning documents `max_tokens` 1–32768 (default 16384) and `reasoning_budget`
-1–32768 (default 16384). Core omits both by default. Existing runtime contracts
accept positive reasoning budgets; they cannot express -1. An explicit budget
maps to the top-level `reasoning_budget` for this exact Lightning ID only.
Explicit `reasoning=enabled/disabled` maps to
`chat_template_kwargs.enable_thinking` for Lightning and
[Bolt E4B](https://build.nvidia.com/nvidia/nemotron-3.5-bolt-e4b).
Other explicit reasoning controls/models fail preflight and transport before
submission; none are silently dropped or inferred from a game's name.

NVIDIA declares OpenAI compatibility. Core accepts one completed assistant
`choices[0].message.content` string with `finish_reason: stop` using the
[Chat Completions response contract](https://developers.openai.com/api/reference/resources/chat).
Separate `reasoning_content` is never parsed as an action or copied into receipts.
Refusal/filtering, truncation and tool/pending results cannot apply an action,
even when their text contains a legal-looking action. Missing/unknown finish
markers, malformed JSON and ambiguous multiple choices fail closed.

## Errors, retries, receipts and privacy

The NVIDIA API reference documents HTTP 202 (pending), 422 (validation), and 500
(invocation error). The adapter reports pending without polling or resubmitting.
Core's HTTP policy additionally handles 401 authentication, 403 permission,
402/422 request rejection, 404/5xx unavailability, and 429 rate limiting. These
additional classifications are defensive transport policy, not a claim that
every model documents every error envelope. There is no verified fixed account
quota, universal RPM limit or guaranteed Retry-After header.

Default retries and action repairs are zero. Optional retries use Core's existing
rule: a definitive 429 rejection with no work/accounting observation may retry;
ambiguous bodies, observed generation/usage, partial bodies, timeouts and 5xx
never authorize automatic replay. Retry-After is honored only within explicit
operator limits. There is no provider or model fallback.

Receipts use `nvidia_chat_completions` / `nvidia-chat-completions-raw-v1`.
Only a returned `model` supplies `locked_model_id`; absence remains null.
Reported prompt/completion/total tokens and optional cache/reasoning counters
are normalized. Missing usage/totals stay unknown; reasoning inclusion is not
assumed, nor are reasoning tokens estimated from text. No hosted rate card or
per-request cost was verified. Cost remains unavailable without valid accounting;
free developer access is not a measured zero-dollar receipt.

Raw bodies, error/refusal prose and reasoning are excluded from receipts. Exact
environment credential values (including secondary secrets) echoed in receipt
strings are removed; redacted identity fields become null. The existing bounded
reader retains only safe header evidence after incomplete bodies. Synthetic
success/error/refusal/malformed/partial-body tests inspect persisted artifacts.

## Verification

`tests/test_nvidia_provider.py` and `tests/fixtures/provider/nvidia/chat_success.json`
contain synthetic documented-shape data, not live NVIDIA captures. They exercise
the real bounded reader with HTTPX MockTransport, all aliases, explicit controls,
full history, missing accounting/identity, no fallback, retries, semantic failures,
and primary/secondary credential echoes. No NVIDIA key was obtained or used;
account availability, entitlement, actual latency, actual billing, quotas and
regional placement remain unverified.

Cloud validation used Python 3.12.14. The final provider/transport subset passed
284 tests, including 78 NVIDIA cases. The broader suite passed 1329 tests and
failed two existing cases before the last focused additions:
`test_provider_runtime_deadline_records_failed_attempt_and_bounds_queue_retry_waits`
and `test_cli_fallback_failing_seat_board_win_is_only_a_board_result`. Both failures
reproduced in an unmodified worktree at base
`270a863d10d57a0953f21924f1a0dd50159e6cf1`; they are not suppressed or repaired here.
Ruff, mypy, both TypeScript package checks, wheel/sdist build and Twine checks,
two byte-identical schema exports, 50 arena fingerprints and initial-state
observation/prompt budget checks passed. No hosted CI, live inference, deployment,
merge or release is part of this validation.
