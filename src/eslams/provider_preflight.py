"""Registry-only and live provider readiness checks."""

from __future__ import annotations

import os
from typing import Any

import httpx

import eslams.arenas  # noqa: F401
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.arena import registry
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import make_act_request
from eslams.providers import load_provider_registry

DEFAULT_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
}

_MODELS_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
}


def provider_preflight(
    provider: str,
    model: str,
    arena_id: str,
    *,
    live: bool = False,
) -> dict[str, Any]:
    provider = provider.lower()
    provider_registry = load_provider_registry()
    record = provider_registry.resolve(provider, model)
    arena = registry.create(arena_id)
    state = arena.initial_state(seed=1)
    legal_actions = arena.legal_actions_for(state, state.active_player)
    api_key_env = DEFAULT_PROVIDER_ENV.get(provider)
    api_key_configured = bool(api_key_env and os.getenv(api_key_env))
    checks: dict[str, bool | None] = {
        "registry_entry": record.known,
        "arena_available": True,
        "legal_action_available": bool(legal_actions),
        "api_key_configured": api_key_configured,
        "account_model_visible": None,
        "minimal_inference": False,
        "response_parsing": False,
        "usage_extraction": False,
    }
    warnings = provider_registry.warnings_for(provider, model)
    error: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None

    if not live:
        warnings.append("This registry-only preflight did not verify live provider availability.")
    elif not api_key_env or not api_key_configured:
        error = {
            "error_class": "provider_auth_failed",
            "message": f"missing API key environment variable {api_key_env or 'unknown'}",
        }
    else:
        visible_models = provider_models_live(provider)
        if visible_models is not None:
            checks["account_model_visible"] = model in visible_models
            if checks["account_model_visible"] is False:
                alternatives = [item for item in visible_models if _same_model_family(model, item)][
                    :5
                ]
                error = {
                    "error_class": "provider_unavailable",
                    "message": f"model {model!r} is not visible to this provider account",
                    "available_alternatives": alternatives,
                }
        if error is None:
            request = make_act_request(
                run_id="preflight_live",
                episode_id="episode_001",
                turn_id=state.turn,
                arena_id=arena.id,
                arena_version=arena.version,
                agent_id=f"{provider}-{model}",
                agent_version="preflight-v1",
                active_player=state.active_player,
                observation=arena.observation_for(state, state.active_player),
                legal_actions=legal_actions,
                action_schema=arena.action_schema,
                history=[],
                time_budget_ms=30_000,
                memory_policy="current_observation_plus_public_history",
                metadata={"preflight": True},
            )
            agent = ModelProviderAgent(
                provider=provider,
                model=model,
                api_key_env=api_key_env,
                max_output_tokens=128,
                runtime_config=ProviderRuntimeConfig(
                    timeout_ms=30_000,
                    read_timeout_ms=30_000,
                    max_retries=0,
                    reasoning="disabled",
                ),
            )
            try:
                response = agent.act(request)
                checks["minimal_inference"] = True
                checks["response_parsing"] = response.action in legal_actions
                receipt = agent.last_receipt
                usage = receipt.get("usage") if isinstance(receipt, dict) else None
                checks["usage_extraction"] = isinstance(usage, dict) and all(
                    _is_int(usage.get(key))
                    for key in ("input_tokens", "output_tokens", "total_tokens")
                )
            except (ProviderCallError, TimeoutError) as exc:
                error = _public_error(exc, provider=provider, model=model)

    required = (
        checks["registry_entry"] is True
        and checks["arena_available"] is True
        and checks["legal_action_available"] is True
        and (
            not live
            or all(
                checks[key] is True
                for key in ("minimal_inference", "response_parsing", "usage_extraction")
            )
        )
        and (not live or checks["account_model_visible"] is not False)
    )
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "arena_id": arena_id,
        "preflight_mode": "live" if live else "registry_only",
        "ok": required,
        "checks": checks,
        "warnings": warnings,
        "capability_flags": record.capability_flags,
        "lifecycle": record.lifecycle,
        "sample_legal_action": legal_actions[0] if legal_actions else None,
        "receipt_shape": {
            "schema_version": "eslams.provider.receipt.v2",
            "outcome": receipt.get("outcome") if isinstance(receipt, dict) else "not_called",
            "redaction_version": "provider-receipt-redaction-v1",
            "usage_complete": checks["usage_extraction"] is True,
        },
    }
    if error is not None:
        payload["error"] = error
    return payload


def provider_models_live(provider: str) -> list[str] | None:
    provider = provider.lower()
    endpoint = _MODELS_ENDPOINTS.get(provider)
    api_key_env = DEFAULT_PROVIDER_ENV.get(provider)
    api_key = os.getenv(api_key_env) if api_key_env else None
    if endpoint is None or api_key is None:
        return None
    headers = {"Accept": "application/json"}
    params: dict[str, str] = {}
    if provider == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    elif provider in {"google", "gemini"}:
        params["key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = httpx.get(endpoint, headers=headers, params=params, timeout=20.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    rows = payload.get("data") if provider not in {"google", "gemini"} else payload.get("models")
    if not isinstance(rows, list):
        return None
    models: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("id") if provider not in {"google", "gemini"} else row.get("name")
        if isinstance(raw, str) and raw:
            models.append(raw.split("/", 1)[-1] if raw.startswith("models/") else raw)
    return sorted(set(models))


def _public_error(exc: BaseException, *, provider: str, model: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "status_code": getattr(exc, "status_code", None),
        "error_class": getattr(exc, "error_kind", "provider_timeout"),
        "message": str(exc)[:500],
    }


def _same_model_family(requested: str, candidate: str) -> bool:
    return requested.split("-20", 1)[0].split(":", 1)[0] in candidate


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
