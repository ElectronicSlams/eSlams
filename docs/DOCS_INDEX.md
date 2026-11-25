# Core documentation

| Purpose | Canonical source |
| --- | --- |
| Published install and keyless/BYO-key lab workflow | [LABS.md](LABS.md) |
| Local development, tests and contribution process | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Sample checksums, classifications and expected validation | [SAMPLE_CLASSIFICATION.md](SAMPLE_CLASSIFICATION.md) |
| Private/public custody and verification claims | [PUBLIC_CUSTODY.md](PUBLIC_CUSTODY.md), [SECURITY.md](../SECURITY.md) |
| Platform Labs handoff | [LABS_PAGE_CONTRACT.md](LABS_PAGE_CONTRACT.md) |
| Act protocol and failure/deadline behavior | [PROTOCOL.md](PROTOCOL.md) |
| Unscored recovered board positions and historical uncertainty | [BOARD_RECOVERY.md](BOARD_RECOVERY.md) |
| Chess continuation, lineage and accounting | [CHESS_CONTINUATION.md](CHESS_CONTINUATION.md) |
| Artifact profiles, signatures and migration boundaries | [ARTIFACTS.md](ARTIFACTS.md) |
| Arenas, compact fidelity and ruleset version history | [ARENAS.md](ARENAS.md), [ARENA_VERSIONING.md](ARENA_VERSIONING.md) |
| Provider wire controls, credentials and discovery | [PROVIDERS.md](PROVIDERS.md), [Azure Foundry](AZURE_FOUNDRY.md), [native xAI](PROVIDER_XAI.md), [Z.ai/Zhipu](PROVIDER_ZAI.md) |
| Liquid AI direct text adapter and source evidence | [LIQUID_AI.md](LIQUID_AI.md) |

| Kuaishou / KwaiPilot KAT direct text adapter | [providers/KUAISHOU.md](providers/KUAISHOU.md) |

| NAVER Cloud HyperCLOVA X adapter and official API evidence | [providers/NAVER.md](providers/NAVER.md) |

| Direct Perceptron contract and research evidence | [PERCEPTRON.md](PERCEPTRON.md) |

| Sakana Namazu direct API and research boundaries | [PROVIDER_SAKANA.md](PROVIDER_SAKANA.md) |

| Direct Ant Group / Bailing / Ant Ling adapter evidence | [ANT_LING.md](providers/ANT_LING.md) |
| Moonshot/Kimi native API, regions and fixture provenance | [PROVIDER_MOONSHOT.md](PROVIDER_MOONSHOT.md) |
| StepFun direct API scope and fixture provenance | [STEPFUN.md](providers/STEPFUN.md) |
| Inception Labs Mercury direct adapter (planned 0.7.1) | [INCEPTION.md](INCEPTION.md) |
| Reka direct adapter research and usage | [PROVIDER_REKA.md](PROVIDER_REKA.md) |
| IBM Cloud watsonx.ai host adapter and IAM | [PROVIDER_WATSONX.md](PROVIDER_WATSONX.md) |

| Meituan LongCat native API, controls and accounting limits | [providers/LONGCAT.md](providers/LONGCAT.md) |

| Native Baidu Qianfan adapter, direct endpoint scope and source provenance | [BAIDU_QIANFAN.md](BAIDU_QIANFAN.md) |

| Shanghai AI Lab Atria adapter scope and evidence | [SHANGHAI_AI_LAB.md](SHANGHAI_AI_LAB.md) |
| Red Hat AI Inference on IBM Cloud host adapter | [PROVIDER_IBM_RHAI.md](PROVIDER_IBM_RHAI.md) |
| Native Cohere adapter research and limits | [Cohere](providers/cohere.md) |
| Writer direct API contract and limitations | [WRITER.md](WRITER.md) |
| Fireworks direct inference and fixture provenance | [FIREWORKS.md](FIREWORKS.md) |
| Snowflake Cortex adapter and official wire references | [providers/SNOWFLAKE.md](providers/SNOWFLAKE.md) |
| Poolside direct inference and verified contract limits | [POOLSIDE.md](POOLSIDE.md) |
| Versioned integration contracts | [PLATFORM_CONTRACTS.md](PLATFORM_CONTRACTS.md) |
| Registry snapshot and capability caveats | [REGISTRY_AVAILABLE_MODELS.md](REGISTRY_AVAILABLE_MODELS.md) |
| Backlog dispositions and verification evidence | [BACKLOG_RESOLUTION.md](BACKLOG_RESOLUTION.md), [resolution ledger](backlog-resolution.json) |

The lab guide pins Core 0.6.2 and requires Python 3.10+. Release changes and
migration boundaries are recorded in [CHANGELOG.md](../CHANGELOG.md). Local validation and green tests do not confer Official trust.

- [Native DeepSeek adapter](providers/DEEPSEEK.md): API evidence, configuration, limits and offline fixtures.
- [Opt-in native multi-unit matches](NATIVE_MATCHES.md)
