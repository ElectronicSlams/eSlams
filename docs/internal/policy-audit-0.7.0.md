# Surprising Core policies: release audit

Audit of the local Python 0.7.0rc1 source. Recommendations below are not additional implemented features or wholesale removal approval. Source symbols are stable references; final source pin/hashes live in the separate candidate manifest.

| Policy / source | Disposition and precise consequence |
|---|---|
| Runner RunConfig.time_budget_ms; ProviderRuntimeConfig.timeout_ms/read_timeout_ms; ModelProviderAgent._effective_max_output_tokens | Fixed: None by default, no upshift/sentinel. Explicit finite caller values remain. |
| agents._reasoning_enabled_for_request | Fixed: no game-name branch/default effort. Native mandatory reasoning may still occur. Explicit supported controls stay caller-owned. |
| agents._provider_prompt; core_contract.prompt_package | Fixed: full supplied provider history / versioned v3; explicit legacy v2 still slices 24 for exact compatibility. No unauthorized private-history reconstruction. |
| agents._sleep_before_retry | Fixed: no five-second rejection. Only safe caller-enabled retry with resource/cancellation/deadline checks. Not a new exponential/full-jitter distributed scheduler. |
| provider_preflight.provider_preflight | Fixed: advisory default, explicit strict mode, actual inference vs optional usage distinct; catalogue/Models-list do not authenticate availability/build identity. |
| agents._call_openrouter / ProviderRuntimeConfig.openrouter_allow_fallbacks | Retain no fallback by latest explicit decision; fix omitted false wire flag. An empty order is not a provider pin. Supplied multiple preferences and account routing still need strict consumer policy/identity evidence. Do not invent an endpoint attestation. |
| agents._call_anthropic/_reasoning_budget_tokens | Retain actual required output field and manual-mode constraints. Unknown model needs caller maximum or verified capacity; native omission is not supported by every API. New/manual/adaptive profile negotiation is not universally implemented. |
| agents._call_* temperature gating and provider-specific reasoning mappings | Remaining audit gap: an explicit temperature can be omitted for conservative/unknown capabilities. Not all generic reasoning settings have mappings on all adapters; unknown Anthropic manual/adaptive controls need an exact endpoint contract. Discuss explicit rejection vs supported forwarding in 0.7.1; do not claim generic parameter negotiation complete. |
| http_io bounded response / protocol.MAX_RESPONSE_BYTES | Retained 1 MiB response guard also bounds provider output bodies. No token cap is injected, but arbitrarily large output bodies are not promised. Trusted-host configurability is a follow-up; unsafe unbounded untrusted JSON is not a fix. Partial-body classification preserves safe headers, not invented usage. |
| protocol.MAX_PUBLIC_EXPLANATION_BYTES | Retained 16 KiB public explanation bound; resource/public-artifact rule, not reasoning-token allowance. |
| deadlines._CALL_CAPACITY | Retained 32 owned/quarantined callbacks per process. This prevents abandoned workers from exhausting a host; it is not a per-turn clock. Not configurable/distributed yet. |
| ProviderRuntimeConfig.concurrency_limit/rate_limit_per_minute | Default concurrency 1 is a process-local resource scheduler, not a universal provider rate. Distributed rate authority is not implemented by removing it. |
| arena_transport.DEFAULT_SESSION_MAX_AGE_SECONDS / _MAX_CLOCK_SKEW_SECONDS | Retained configurable signed snapshot freshness (24 h default, 60 s future skew). Long inference may need refreshed authorization; removing replay protection is unsafe. Authenticated cross-host renewal remains integration work. |
| arena_transport.MAX_ACTION_LIMIT / core_contract.DEFAULT_MAX_LEGAL_ACTIONS_SERIALIZED | Transport page size 200 is not total action count; all pages are reachable. Separately, inline core legal_action_view currently serializes first 200 with full count/hash. Review whether every consuming prompt exposes/fetches the remaining actions; do not equate pagination tests with complete inline prompt coverage. No change made here. |
| runner.max_turns / arena rules | Retain actual game horizons and explicit caller truncation. External truncation stays invalid for scoring; no material/territory winner invented to meet infrastructure budgets. |
| request_limits / nonce_store / output_lock | Retain byte/authentication/replay/writer authority. Configurable host limits remain separate; fail-closed recovery does not authorize resubmitting unknown paid inference. |
| built-in provider dispatch | Five API families plus conforming Function/HTTP extension. Catalogue entries for 90 organizations are not 90 implemented adapters. Individual additional adapters belong to 0.7.1. |

## Historical rationale found in actual source

Pinned public 0.6.2 (`a935245`) agents.py lines 854-872 explicitly justified TicTacToe/ConnectFour special handling as avoiding paid extended thinking for intentionally small public states/legal sets. Git blame attributes this to `eba67221` (2026-07-31). This is evidence of the historical comment/implementation, not proof that disabling Core control injection disabled provider-native reasoning or that the tradeoff was valid for evaluations. The release removes this game-specific automatic choice.

## Significant choices still not silently decided

PR #226 raw diagnostic score/forfeit semantics; inline legal-action completeness versus bounded previews; explicit unknown-model parameter handling; trusted-host output-byte configurability; endpoint pinning/attestation. These are recorded for owner review. No privacy route allowlist, legal-action validation, spending boundary or resource guard was removed by this audit.
