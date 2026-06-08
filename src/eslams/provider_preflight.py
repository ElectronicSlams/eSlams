"""Provider preflight checks without mandatory network calls."""

from __future__ import annotations

import os
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.providers import load_provider_registry

DEFAULT_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
}


def provider_preflight(provider: str, model: str, arena_id: str) -> dict[str, Any]:
    provider = provider.lower()
    provider_registry = load_provider_registry()
    record = provider_registry.resolve(provider, model)
    arena = registry.create(arena_id)
    state = arena.initial_state(seed=1)
    legal_actions = arena.legal_actions_for(state, state.active_player)
    api_key_env = DEFAULT_PROVIDER_ENV.get(provider)
    api_key_configured = bool(api_key_env and os.getenv(api_key_env))
    checks = {
        "registry_entry": record.known,
        "arena_available": True,
        "legal_action_available": bool(legal_actions),
        "api_key_configured": api_key_configured,
        "api_availability_checked": False,
        "api_call_required": False,
        "response_parsing_checked": False,
        "usage_extraction_checked": False,
        "timeout_behavior_checked": False,
        "redacted_receipt_shape_checked": True,
    }
    warnings = provider_registry.warnings_for(provider, model)
    if not api_key_configured:
        warnings.append("api availability skipped because no provider API key is configured")
    else:
        warnings.append("api availability not called by no-spend preflight")
    return {
        "provider": provider,
        "model": model,
        "arena_id": arena_id,
        "ok": checks["arena_available"] and checks["legal_action_available"],
        "checks": checks,
        "warnings": warnings,
        "capability_flags": record.capability_flags,
        "sample_legal_action": legal_actions[0] if legal_actions else None,
        "receipt_shape": {
            "schema_version": "eslams.provider.receipt.v1",
            "outcome": "unavailable" if not api_key_configured else "not_called_by_preflight",
            "redaction_version": "provider-receipt-redaction-v1",
            "usage_unavailable_reason": None
            if api_key_configured
            else "api_availability_skipped_missing_key",
            "estimated_cost": {"status": "cost_unavailable"},
        },
    }
