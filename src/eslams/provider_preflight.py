"""Configuration and explicitly requested live checks; catalogue policy is opt-in."""

from __future__ import annotations

from typing import Any

import httpx

import eslams.arenas  # noqa: F401
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.arena import registry
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import make_act_request
from eslams.provider_credentials import provider_key
from eslams.providers import load_provider_registry
from eslams.providers.poolside import API_KEY_ENV, MODELS_ENDPOINT, configuration_error
from eslams.providers.registry import PROVIDER_ALIASES

DEFAULT_PROVIDER_ENV = {
    "poolside": API_KEY_ENV,
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
}

_MODELS_ENDPOINTS = {
    "poolside": MODELS_ENDPOINT,
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
    time_budget_ms: int | None = None,
    max_output_tokens: int | None = None,
    runtime_config: ProviderRuntimeConfig | None = None,
    strict_catalogue: bool = False,
) -> dict[str, Any]:
    if not isinstance(strict_catalogue, bool):
        raise ValueError("strict_catalogue must be boolean")
    for name, value in (("time_budget_ms", time_budget_ms),
                        ("max_output_tokens", max_output_tokens)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise ValueError(f"{name} must be a positive operator choice or null")
    provider = provider.lower()
    provider_registry = load_provider_registry()
    record = provider_registry.resolve(provider, model)
    arena = registry.create(arena_id)
    state = arena.initial_state(seed=1)
    legal_actions = arena.legal_actions_for(state, state.active_player)
    credential_environment = DEFAULT_PROVIDER_ENV.get(record.provider)
    credential_error = None
    credential_present = False
    if credential_environment:
        try:
            if provider_key(credential_environment) is not None:
                credential_present = True
        except ValueError:
            credential_error = (
                "API key must contain printable ASCII without internal whitespace"
            )
    checks: dict[str, bool | None] = {
        "registry_entry": record.known,
        "adapter_available": credential_environment is not None,
        "game_agent_supported": record.allows_text_game_agent(),
        "model_lifecycle_available": (
            record.lifecycle != "retired" and record.available_from_api is not False
        ),
        "arena_available": True,
        "legal_action_available": bool(legal_actions),
        "api_key_configured": credential_present,
        "account_model_visible": None,
        "minimal_inference": False,
        "response_parsing": False,
        "usage_extraction": False,
    }
    warnings = provider_registry.warnings_for(provider, model)
    error: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    discovery_error: dict[str, Any] | None = None
    inference_invoked = False
    poolside_error = (
        configuration_error(model, runtime_config) if record.provider == "poolside" else None
    )

    if poolside_error:
        error = {"error_class": "provider_request_rejected", "message": poolside_error}
    elif credential_environment is None:
        error = {
            "error_class": "provider_adapter_unavailable",
            "message": f"Core has no inference adapter for provider {provider!r}",
        }
    elif strict_catalogue and not checks["model_lifecycle_available"]:
        error = {
            "error_class": "provider_unavailable",
            "message": f"model {model!r} is retired or marked unavailable in the registry",
        }
    elif strict_catalogue and (not record.known or not record.allows_text_game_agent()):
        error = {
            "error_class": "provider_request_rejected",
            "message": f"model {model!r} is not registered for text game actions",
        }
    elif credential_error:
        error = {"error_class": "provider_auth_failed", "message": credential_error}
    elif not live:
        warnings.append("This configuration preflight did not verify live provider availability.")
    elif not credential_environment or not credential_present:
        error = {
            "error_class": "provider_auth_failed",
            "message": f"missing API key environment variable {credential_environment}",
        }
    else:
        try:
            visible_models = provider_models_live(record.provider)
        except ProviderCallError as exc:
            visible_models = None
            discovery_error = _public_error(exc, provider=provider, model=model)
            if strict_catalogue:
                error = discovery_error
            else:
                warnings.append(
                    "Model discovery failed; explicitly requested inference is decisive."
                )
        if visible_models is None and error is None:
            warnings.append(
                "This adapter has no Models API; account visibility remains unverified."
            )
        if visible_models is not None:
            checks["account_model_visible"] = model in visible_models
            if checks["account_model_visible"] is False and strict_catalogue:
                alternatives = [item for item in visible_models if _same_model_family(model, item)][
                    :5
                ]
                error = {
                    "error_class": "provider_unavailable",
                    "message": f"model {model!r} is not visible to this provider account",
                    "available_alternatives": alternatives,
                }
            elif checks["account_model_visible"] is False:
                warnings.append("Requested model was not listed; account discovery is advisory.")
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
                time_budget_ms=time_budget_ms,
                memory_policy="current_observation_plus_public_history",
                metadata={"preflight": True, "model_execution_policy":
                          model_execution_policy(time_budget_ms, max_output_tokens)},
            )
            agent = ModelProviderAgent(
                provider=record.provider,
                model=model,
                api_key_env=credential_environment,
                max_output_tokens=max_output_tokens,
                runtime_config=runtime_config or ProviderRuntimeConfig(),
            )
            try:
                inference_invoked = True
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
        checks["adapter_available"] is True
        and (not strict_catalogue or all(checks[key] is True for key in (
            "registry_entry", "game_agent_supported", "model_lifecycle_available",
        )))
        and error is None
        and checks["arena_available"] is True
        and checks["legal_action_available"] is True
        and (
            not live
            or all(
                checks[key] is True
                for key in ("minimal_inference", "response_parsing")
            )
        )
        and (not strict_catalogue or not live or checks["account_model_visible"] is not False)
    )
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "arena_id": arena_id,
        "preflight_mode": "live" if live else "configuration_only",
        "strict_catalogue": strict_catalogue,
        "model_availability": (
            "inference_succeeded" if checks["minimal_inference"] is True else "unverified"
        ),
        "readiness": {
            "configuration_ready": (checks["adapter_available"] is True
                                    and credential_error is None and poolside_error is None),
            "inference": ("succeeded" if checks["minimal_inference"] is True else
                          "failed" if inference_invoked else "not_attempted"),
            "legal_action_observed": checks["response_parsing"] is True,
            "usage_complete": checks["usage_extraction"] is True,
            "cost_and_official_eligibility": "not_assessed",
            "meaning_of_ok": "configuration ready, and if live, one legal action observed",
        },
        "model_execution_policy": model_execution_policy(time_budget_ms, max_output_tokens),
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
    if discovery_error is not None:
        payload["discovery_error"] = discovery_error
    return payload


def provider_models_live(provider: str) -> list[str] | None:
    """Discover every model page, or fail without treating partial results as complete.

    ``None`` means the adapter has no Models API. Authentication, transport,
    HTTP and malformed/pagination failures raise a diagnostic ProviderCallError.
    """
    provider = provider.strip().lower().replace("_", "-")
    provider = PROVIDER_ALIASES.get(provider, provider)
    endpoint = _MODELS_ENDPOINTS.get(provider)
    api_key_env = DEFAULT_PROVIDER_ENV.get(provider)
    if api_key_env is None:
        raise ProviderCallError(
            f"Core has no inference adapter for provider {provider!r}",
            error_kind="provider_adapter_unavailable", provider=provider,
        )
    if endpoint is None:
        return None
    try:
        api_key = provider_key(api_key_env)
    except ValueError as exc:
        raise ProviderCallError(
            str(exc), error_kind="provider_auth_failed", provider=provider,
        ) from None
    if api_key is None:
        raise ProviderCallError(
            f"missing API key environment variable {api_key_env}",
            error_kind="provider_auth_failed", provider=provider,
        )
    headers = {"Accept": "application/json"}
    params: dict[str, str] = {}
    if provider == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        params["limit"] = "1000"
    elif provider == "google":
        headers["x-goog-api-key"] = api_key
        params["pageSize"] = "1000"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    models: list[str] = []
    cursors: set[str] = set()
    for _ in range(20):
        try:
            response = httpx.get(endpoint, headers=headers, params=dict(params), timeout=20.0)
        except httpx.TimeoutException:
            raise ProviderCallError(
                "model discovery timed out", error_kind="provider_timeout", provider=provider,
            ) from None
        except httpx.HTTPError:
            # Never expose request URLs, response bodies or echoed credentials.
            raise ProviderCallError(
                "model discovery transport failed", error_kind="provider_transport_error",
                provider=provider,
            ) from None
        if response.is_error:
            code = response.status_code
            kind = (
                "provider_auth_failed" if code in {401, 403} else
                "provider_rate_limited" if code == 429 else
                "provider_unavailable" if code >= 500 else "provider_request_rejected"
            )
            raise ProviderCallError(
                f"model discovery returned HTTP {code}", status_code=code,
                error_kind=kind, provider=provider,
            )
        try:
            payload = response.json()
        except ValueError:
            raise _discovery_schema_error(provider) from None
        if not isinstance(payload, dict):
            raise _discovery_schema_error(provider)
        rows = payload.get("models" if provider == "google" else "data")
        if not isinstance(rows, list):
            raise _discovery_schema_error(provider)
        for row in rows:
            raw = (
                row.get("name" if provider == "google" else "id")
                if isinstance(row, dict) else None
            )
            if not isinstance(raw, str) or not raw.strip():
                raise _discovery_schema_error(provider)
            if provider == "poolside" and api_key in raw:
                raise _discovery_schema_error(provider)
            models.append(raw[7:] if provider == "google" and raw.startswith("models/") else raw)
        cursor = None
        if provider == "anthropic":
            has_more = payload.get("has_more", False)
            if not isinstance(has_more, bool):
                raise _discovery_schema_error(provider)
            if has_more:
                cursor = payload.get("last_id")
        elif provider == "google":
            cursor = payload.get("nextPageToken") or None
        if cursor is None and not (provider == "anthropic" and has_more):
            return sorted(set(models))
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            raise _discovery_schema_error(provider)
        cursors.add(cursor)
        params["after_id" if provider == "anthropic" else "pageToken"] = cursor
    raise ProviderCallError(
        "model discovery exceeded the 20-page limit; visibility is unverified",
        error_kind="provider_response_schema_mismatch", provider=provider,
    )


def provider_models_result(provider: str) -> dict[str, Any]:
    """JSON-safe live discovery response shared by the CLI and local clients."""
    payload: dict[str, Any] = {"provider": provider, "mode": "live", "ok": False, "models": []}
    try:
        models = provider_models_live(provider)
        if models is None:
            raise ProviderCallError(
                "This adapter has no Models API; account visibility remains unverified",
                error_kind="provider_discovery_unavailable", provider=provider,
            )
        payload.update(ok=True, models=models)
    except ProviderCallError as exc:
        payload["error"] = _public_error(exc, provider=provider, model="")
    return payload


def _discovery_schema_error(provider: str) -> ProviderCallError:
    return ProviderCallError(
        "model discovery returned malformed data or an invalid pagination cursor; "
        "visibility is unverified",
        error_kind="provider_response_schema_mismatch", provider=provider,
    )


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
