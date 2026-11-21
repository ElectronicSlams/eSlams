# LightOn direct inference assessment — 2026-11-04

## Decision

Direct LightOn text inference is documented. A native adapter satisfying this
task's exact-model, exact-provider and no-fallback requirements is **blocked on
contract evidence**, not classified as nonexistent. No inference adapter,
credential handling, catalogue claim, shared wiring or version change is proposed.

The decisive gap is an atomic way to select a concrete model while disabling
alias resolution and fallback. A preflight snapshot cannot establish that property
for a later request. Returning a different model and rejecting it after generation
would detect some substitutions, but would not prevent unwanted inference.

## Official evidence and remaining gaps

| Area | Established evidence | Limit / consequence |
| --- | --- | --- |
| Endpoint and authentication | [V3 chat reference](https://docs.lighton.ai/api-reference-v3/models/generate-a-chat-completion) documents `POST https://paradigm.lighton.ai/api/v3/chat/completions`, Bearer authorization, required `model` and `messages`, optional `max_tokens`, and non-streaming JSON or SSE. | These are documentation observations, not successful live requests. No credentials or paid inference were used. |
| Exact selection | The same V3 reference states that a company alias wins over a concrete model with the same technical name. Otherwise selection uses the model technical name. | Its published request fields show no alias-bypass, concrete-model UUID selection or disable-fallback control. This is the primary implementation gate. |
| Fallback | [Alias routing preview](https://docs.lighton.ai/api-reference-v3/models/preview-alias-routing) reports a primary, ordered fallbacks and unhealthy exclusions; it simulates request-time selection. [Alias membership](https://docs.lighton.ai/api-reference-v3/models/add-model-to-alias) defines priority 0 as primary, 1 as first fallback. | Preview is not a binding inference reservation. No documented request-time lock or routing version precondition was found. Do not infer one or mutate the customer's aliases. |
| Model access | [Model visibility guide](https://docs.lighton.ai/en/developer-resources/chat-and-ai-models/models-list) requires a Paradigm account key, model configuration and permission. The profile can create keys subject to administrator rights. | An example name is not account entitlement. No account-visible catalogue was queried. |
| API generation | [V2 model listing](https://docs.lighton.ai/api-reference-v2/models/list-available-models) is deprecated and points to `GET /api/v3/models`. [V2 completion](https://docs.lighton.ai/api-reference-v2/models/generate-a-text-completion) points to V3 chat. | Do not implement a new integration against V2 merely because its older examples are easier to retrieve. |
| Model identity | [Managed-model creation](https://docs.lighton.ai/api-reference-v3-instance/models/create-a-managed-ml-model-instance-admin) shows `alfred-ft5`, `hosted_vllm/alfred-ft5`, and a LightOn model endpoint in its example. [Managed-model updates](https://docs.lighton.ai/api-reference-v3-instance/models/update-a-managed-ml-model-instance-admin) expose endpoint, deployment type and model configuration. | Managed deployments and example endpoint strings are not immutable weights or per-response execution-provider attestations. No model build or backend identity is fabricated. |
| Regional identity | [LightOn API offering](https://lighton.ai/api) advertises EU sovereign hosting and EU residency by default, with separate enterprise regional deployments. [Privacy policy §6.1](https://developers.lighton.ai/legal/privacy-policy) describes processing primarily in France or Europe. | Neither establishes a particular request's region. There is no verified regional selector or per-response region contract here. Region remains unknown absent deployment evidence. |
| Text-game suitability | [Alfred Frontier 5](https://docs.lighton.ai/en/developer-resources/lighton-models/alfred-ft5) is a LightOn-tuned 32B vision-language model supporting text, instructions and planning, with a documented 32,768-token context. [Alfred Sovereign 5](https://docs.lighton.ai/en/developer-resources/lighton-models/alfred-sv5) is 24B with the same stated context size and instruction/structured-output support. | These are plausible text-agent candidates, not measured game-readiness claims. Full supplied history may exceed provider context; silent truncation or a game-specific reasoning policy would be unacceptable. |
| Reasoning | [Chat quick guide](https://docs.lighton.ai/en/developer-resources/api-fundamentals/quick-guide) demonstrates ordinary text messages. [Agent API](https://docs.lighton.ai/en/developer-resources/chat-and-ai-models/agent-api) describes an orchestration loop containing reasoning and tool calls. | The latter is a separate service contract, not evidence for an inference `reasoning_effort`, budget, off switch, or reasoning-token inclusion rule. No such controls are invented. |
| Response, accounting, failures | V3 describes response `id`, `object`, `created`, `model`, `choices` and optional `usage`. Its rendered 200 example repeats a request rather than supplying a usable success fixture. | A complete, authoritative nested choices/usage/error contract could not be retrieved. No missing tokens, cached/reasoning counts, cost, response ID or model identity is inferred. |

## Direct service versus routing and local hosting

LightOn's managed Alfred deployments are evidence of a direct LightOn offering;
the word "proxy" in its inference documentation does not by itself mean a
third-party commercial service. However, Paradigm is also configurable as a
gateway. [Company custom models](https://docs.lighton.ai/api-reference-v3-company/models/create-a-custom-model)
accept external LiteLLM identifiers and custom endpoints, including local
OpenAI-compatible servers. Receiving a response from a LightOn URL alone cannot
prove that inference used LightOn-operated Alfred weights. Alias routing adds a
separate substitution risk.

The official [LightOnOCR repository](https://github.com/lightonai/LightOnOCR)
demonstrates locally served image-to-document models. Those weights, vLLM
localhost examples and third-party hosts are not the direct general text service
being assessed. The retrieval `/search`, document `/parse` and `/extract`, and
orchestrated thread/Agent APIs are not substitutes for an unassisted game agent.

## Evidence needed before implementation

1. An official request-time contract that selects a concrete LightOn-hosted model
   without alias collision or model/provider fallback, or a provider-attested
   dedicated deployment with an equivalent enforceable guarantee. A mutable
   catalogue snapshot is insufficient.
2. A complete versioned raw REST schema or redacted documented success envelope:
   nested messages/choices, completion status, exact returned identity, usage
   fields, reasoning inclusion, and all documented failure envelopes. The public
   documentation index advertises OpenAPI files, but the linked YAML and live
   schemas could not be retrieved during this review. This is a retrieval
   limitation, not proof that those contracts do not exist.
3. Chat-specific 400/401/403/404/429/5xx error semantics, rejection-versus-work
   evidence, any retry guidance and request-ID headers. No chat-specific
   Retry-After guarantee was established. [Parse errors](https://docs.lighton.ai/api-reference-v3/models/parse-a-document-to-markdown)
   show structured error bodies, and aliases show maintenance 503s, but neither
   proves chat uses the same complete contract. Do not borrow another endpoint's
   errors or assume OpenAI compatibility establishes identical behavior.
4. For strict runs, deployment/model access and region evidence. No credential
   acquisition, live discovery or paid smoke test is authorized by this report.

A later adapter must use the existing safe transport/receipt path and default to
zero retries and repairs; omit output/read/total limits unless explicitly chosen;
keep exact identifiers and full supplied history; reject missing/blank model IDs
and unsupported reasoning controls before submission; and send no tools/search.
Missing accounting stays unknown. Even optional retries require definitive safe
rejection, never partial bodies, transport ambiguity or observed work. Credential
echo tests must cover every receipt/action string on success, errors, malformed
and partial responses. These are implementation requirements, not completed
LightOn validations.

## Cloud validation and repository state

- Target: `ElectronicSlams/eSlams`, Python Core **0.7.0**.
- Tested source HEAD: `270a863d10d57a0953f21924f1a0dd50159e6cf1`.
- Python 3.12.14, pytest 9.2.0, HTTPX 0.28.1.
- **90 passed, 0 failed, 0 errors, 0 skipped** in 6.099 seconds across the
  selected existing provider registry, catalogue, discovery, credentials/waits,
  raw-wire, completion, attempt-contract, model-agent and CLI suites.
- No inherited failures occurred in that selection. The full suite, distribution
  consumers, native OS/runtime matrix, live provider tests, merge and release
  were not run. Existing-provider raw-wire passes do not validate LightOn.
  The elapsed-deadline listener tests remain excluded.
- No LightOn wire fixture or adapter tests were fabricated to cover the missing
  contract. Additional socket-guarded checks confirmed offline and live-flag
  preflight return `provider_adapter_unavailable` without inference; CLI preflight
  exits 1; CLI agent dispatch returns no adapter; direct provider dispatch raises
  `provider_unavailable`. Network attempts: zero. `git diff --check` passed.

Reproduce the selected test run from the repository root in its dev environment:

```bash
python -m pytest -q \
  tests/test_provider_registry.py tests/test_provider_catalogue_regressions.py \
  tests/test_provider_discovery_regressions.py tests/test_provider_credentials_and_waits.py \
  tests/test_provider_wire_v06.py tests/test_provider_completion_regressions.py \
  tests/test_provider_attempt_contract_v06.py tests/test_model_agents.py \
  tests/test_agent_cli.py tests/test_cli_errors.py tests/test_cli_run_and_catalogue.py \
  --basetemp=/tmp/lighton-pytest \
  --junitxml=/tmp/lighton-cloud-tests.xml
```
