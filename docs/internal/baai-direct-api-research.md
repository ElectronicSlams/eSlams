# BAAI direct inference API assessment

Research date: 2026-11-04 (UTC). Target: Python Core 0.7.0, preparing
individual adapters for 0.7.1 without changing the package version.
Inspected source: `270a863d10d57a0953f21924f1a0dd50159e6cf1`.

## Decision

**Blocked: a current BAAI-operated text inference contract was not established.**
Do not register a native `baai` adapter or borrow another operator's endpoint,
authentication, response envelope, model identity or accounting rules.
This is an evidence gap, not a claim that BAAI has never offered API services.

## Official evidence and operator distinction

1. [BAAI's official system overview](https://www.baai.ac.cn/zh-cn/system)
   lists Aquila/Tele-FLM language models, BGE embedding models and open source
   training/inference infrastructure. It does not establish a developer text
   inference endpoint. This page and the ModelHub are JavaScript applications;
   direct browser extraction returned no readable body. Search-index material
   was available, so incomplete access must not be described as a complete audit
   of every page or a proof of service absence.
2. [ModelHub's privacy policy](https://model.baai.ac.cn/privacy-policy), dated
   July 4, 2022 in indexed text, identifies ModelHub as BAAI-operated and discusses
   collecting application details for API services. This is a relevant first-party
   service lead. It does not identify the current callable text model, inference
   URL, credential protocol, availability or wire contract. The policy alone
   cannot justify an adapter or establish current API access.
3. [The official Aquila2 repository](https://github.com/FlagAI-Open/Aquila2)
   publishes base/chat model downloads and local prediction examples, including
   Transformers loading and offline private deployment. The
   [BAAI AquilaChat2-7B model card](https://huggingface.co/BAAI/AquilaChat2-7B)
   likewise documents loading weights and running prediction locally. Hugging
   Face's generated deployment examples use localhost. A downloadable model ID
   is not a BAAI service's resolved-model attestation. The card's Inference
   Providers panel reported no deployment for this particular model when read;
   that observation does not establish availability of all other BAAI models.
4. [BGE's official documentation](https://bge-model.com/) describes embedding
   models and rerankers. Its API link documents FlagEmbedding classes/functions.
   Python inference APIs and retrieval outputs do not establish a hosted
   generative-text service that can return an eSlams action.
5. [Baidu Qianfan's AquilaChat-7B documentation](https://intl.cloud.baidu.com/zh/doc/WENXINWORKSHOP/s/cmemg5da5)
   explicitly documents a POST endpoint under
   `aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/aquilachat_7b`.
   This is an operator contract published by Baidu for a BAAI-developed model.
   It does not establish a direct BAAI-operated API. This assessment did not
   invoke that endpoint or attest current account availability.
6. [Opper's BAAI page](https://opper.ai/baai) distinguishes BAAI as model maker
   from routes operated by DeepInfra and Berget. Its listed US/EU regions refer
   to those routes. [OpenRouter's BGE-M3 page](https://openrouter.ai/baai/bge-m3)
   describes embeddings served by Parasail/DeepInfra and routing/failover.
   These are first-party statements by the respective routing services, not
   evidence of BAAI's endpoint, region or no-fallback guarantee. An embedding
   vector is also not a generative text action.

The institute, a model author namespace, a model download host, a locally
deployed server and a commercial inference operator must retain their separate
identities. Articles on `hub.baai.ac.cn` about other companies' APIs do not
establish BAAI service operation. No contract was inferred from similarly named
providers or from a generic OpenAI-compatible example.

## Exact missing contract

| Required evidence | Result for a current direct BAAI text API |
| --- | --- |
| Operator and endpoint | ModelHub operation is established by its policy; a callable BAAI text inference origin, method and route are unverified. |
| Authentication and access | The policy describes applications; key issuance, header/signature format and current account access are unverified. No credential variable is invented. |
| Region | Service availability, processing location and selectable regional endpoints are unverified. BAAI's address and a broker's route region are insufficient. |
| Exact model/provider identity | No current API model catalogue, exact callable model ID, response identity field or pinned endpoint identity rule was established. |
| Request/full history | No text request schema, role/history representation or context overflow/truncation behavior was established. |
| Response/completion | No documented raw success envelope, finish/refusal semantics, streaming termination or partial-body rules were established. |
| Reasoning and tools | No documented reasoning controls, reasoning accounting or guarantee about implicit tool/search execution was established. Neither intrinsic reasoning nor tool behavior is assumed. |
| Errors | No BAAI inference contract for 400/401/403/404/429/5xx, HTTP-200 application errors, timeouts or malformed bodies was established. |
| Retry and routing | No idempotency/non-execution evidence, retry headers, physical-attempt accounting or enforceable no-fallback semantics was established. |
| Usage and cost | No input/output/cache/reasoning token schema, inclusion rules, request IDs, price contract or missing-accounting semantics were established. |

To unblock implementation, obtain current first-party BAAI text inference docs
and redacted raw request/success/error examples covering these fields. API
access or paid inference additionally requires explicit authorization. A demo,
service-application policy or weight license cannot substitute for this evidence.

## Core inspection and validation

The selected cloud environment initially contained `makriman/eSlamsPlatform`
at `0fa7dfe227fe545036694c915a6b727eb4ee844a`. That checkout was left untouched.
The Core repository was cloned separately. No Core `AGENTS.md`, `.agents/skills`
or `SKILL.md` was present; `/workspace/.agents` was empty. `CONTRIBUTING.md`,
the provider guide, release audit and workflow definitions were inspected.

At the inspected Core head, `baai` is an organization entry with zero native
model rows. Offline CLI preflight for `BAAI/AquilaChat2-7B` returns
`provider_adapter_unavailable`, `adapter_available: false`,
`model_availability: unverified` and `inference: not_attempted`.
The CLI provider factory returns no native adapter for that specification.
An independent check patched both inference transport and discovery GETs to
raise if called; these checks completed without network inference/discovery.

Cloud validation used Python 3.12.14 with an isolated editable dev installation:

- 271 existing tests passed across registry, CLI, preflight/discovery, documented
  raw-wire fixtures, completion/error handling, native receipts, credential
  handling, partial/non-2xx bodies, safe retries and unbounded policy.
- `python -m ruff check .` passed.
- `python -m mypy src/eslams` passed for 101 source files.
- The selected tests emitted one inherited Starlette HTTPX deprecation warning.
- Broader baseline command:
  `python -m pytest --basetemp=/tmp/eslams-baai-baseline --ignore=tests/test_elapsed_deadline_regressions.py`
  completed with **1253 passed, 1 failed, 2 warnings** in 85.58 seconds.
  The inherited failure is
  `tests/test_invalid_run_surfaces_v063.py::test_cli_fallback_failing_seat_board_win_is_only_a_board_result`
  (line 286): `summary.board_winner` was `None`, expected `player_1`.
  No runtime or existing test file was changed for this research.

No BAAI raw-wire fixtures were manufactured. A BAAI-specific privacy, reasoning,
identity or usage implementation cannot be validated without its real contract.
This change records research only: no runtime/shared wiring, model registry,
version, output/time limits, retry defaults or workflow changes.

The prior task history records a restriction on the elapsed-deadline test area;
`tests/test_elapsed_deadline_regressions.py` was excluded from broader validation.
The selected passing tests do not clear that restriction or attest the entire
baseline. No live inference, credential lookup, model download/execution,
deployment, merge or release was performed.
