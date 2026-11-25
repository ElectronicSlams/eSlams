"""Configuration and explicitly requested live checks; catalogue policy is opt-in."""

from __future__ import annotations

from typing import Any

import httpx

import eslams.arenas  # noqa: F401
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.arena import registry
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.contracts.usage import aggregate_provider_receipts
from eslams.execution_policy import model_execution_policy
from eslams.protocol import make_act_request
from eslams.provider_credentials import provider_key
from eslams.providers import (
    ai21,
    azure,
    baichuan,
    cohere,
    contextual,
    databricks,
    deepseek,
    fireworks,
    load_provider_registry,
    longcat,
    moonshot,
    morph,
    perceptron,
    relace,
    sakana,
    upstage,
    writer,
    xai,
)
from eslams.providers.arcee import API_KEY_ENV as ARCEE_API_KEY_ENV
from eslams.providers.arcee import MODELS_ENDPOINT as ARCEE_MODELS_ENDPOINT
from eslams.providers.arcee import validate_configuration as validate_arcee_configuration
from eslams.providers.baichuan import API_KEY_ENV as BAICHUAN_API_KEY_ENV
from eslams.providers.huawei import API_KEY_ENV as HUAWEI_API_KEY_ENV
from eslams.providers.huawei import MODELS_ENDPOINT as HUAWEI_MODELS_ENDPOINT
from eslams.providers.huawei import contains_credential as huawei_contains_credential
from eslams.providers.huawei import credential_values as huawei_credential_values
from eslams.providers.huawei import validate_config as validate_huawei_config
from eslams.providers.inception import API_KEY_ENV as INCEPTION_API_KEY_ENV
from eslams.providers.inception import MODELS_ENDPOINT as INCEPTION_MODELS_ENDPOINT
from eslams.providers.inception import configuration_error as inception_configuration_error
from eslams.providers.inception import credential_echo as inception_credential_echo
from eslams.providers.inception import validate_model_id as validate_inception_model_id
from eslams.providers.minimax import API_KEY_ENV as MINIMAX_API_KEY_ENV
from eslams.providers.mistral import API_KEY_ENV as MISTRAL_API_KEY_ENV
from eslams.providers.mistral import MODELS_ENDPOINT as MISTRAL_MODELS_ENDPOINT
from eslams.providers.mistral import configuration_error as mistral_configuration_error
from eslams.providers.mistral import contains_credential as mistral_contains_credential
from eslams.providers.mistral import discovery_guard as mistral_discovery_guard
from eslams.providers.nvidia import validate_options as validate_nvidia_options
from eslams.providers.perplexity import API_KEY_ENV as PERPLEXITY_API_KEY_ENV
from eslams.providers.perplexity import MODELS_ENDPOINT as PERPLEXITY_MODELS_ENDPOINT
from eslams.providers.perplexity import discover_models as discover_perplexity_models
from eslams.providers.perplexity import validate_config as validate_perplexity_config
from eslams.providers.poolside import API_KEY_ENV, MODELS_ENDPOINT
from eslams.providers.poolside import configuration_error as poolside_configuration_error
from eslams.providers.qwen import canonicalize_provider as canonicalize_qwen_provider
from eslams.providers.qwen import generation_endpoint as qwen_generation_endpoint
from eslams.providers.qwen import validate_controls as qwen_validate_controls
from eslams.providers.qwen import validate_model as qwen_validate_model
from eslams.providers.registry import PROVIDER_ALIASES
from eslams.providers.reka import API_KEY_ENV as REKA_API_KEY_ENV
from eslams.providers.reka import MODELS_ENDPOINT as REKA_MODELS_ENDPOINT
from eslams.providers.reka import configuration_error as reka_configuration_error
from eslams.providers.reka import credential_echo as reka_credential_echo
from eslams.providers.sensenova import configuration_error as sensenova_configuration_error
from eslams.providers.shanghai_ai_lab import validate_configuration as validate_shanghai_ai_lab
from eslams.providers.snowflake import connection_settings as snowflake_connection_settings
from eslams.providers.stepfun import API_KEY_ENV as STEPFUN_API_KEY_ENV
from eslams.providers.stepfun import MODELS_ENDPOINT as STEPFUN_MODELS_ENDPOINT
from eslams.providers.stepfun import validate_configuration as validate_stepfun_configuration
from eslams.providers.stepfun import validate_model_id as validate_stepfun_model_id
from eslams.providers.tencent_hunyuan import RETIREMENT_WARNING
from eslams.providers.writer import API_KEY_ENV as WRITER_API_KEY_ENV
from eslams.providers.writer import MODELS_ENDPOINT as WRITER_MODELS_ENDPOINT
from eslams.providers.zai import API_KEY_ENVS

DEFAULT_PROVIDER_ENV = {
    "deepseek": deepseek.API_KEY_ENV,
    ai21.PROVIDER_ID: ai21.API_KEY_ENV,
    "perceptron": perceptron.API_KEY_ENV,
    "qwen": "DASHSCOPE_API_KEY",
    moonshot.PROVIDER_ID: moonshot.API_KEY_ENV,
    "arcee-ai": ARCEE_API_KEY_ENV,
    "azure": azure.API_KEY_ENV,
    longcat.PROVIDER_ID: longcat.API_KEY_ENV,
    "baidu": "QIANFAN_API_KEY",
    "byteplus": "BYTEPLUS_API_KEY",
    "mistral-ai": MISTRAL_API_KEY_ENV,
    "xai": xai.API_KEY_ENV,
    "cohere": "COHERE_API_KEY",
    "writer": WRITER_API_KEY_ENV,
    **API_KEY_ENVS,
    "poolside": API_KEY_ENV,
    "baichuan-ai": BAICHUAN_API_KEY_ENV,
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "inception": INCEPTION_API_KEY_ENV,
    "bedrock": "AWS_BEARER_TOKEN_BEDROCK",
    "liquid-ai": "LIQUID_API_KEY",
    "upstage": "UPSTAGE_API_KEY",
    "stepfun": STEPFUN_API_KEY_ENV,
    "reka-ai": REKA_API_KEY_ENV,
    "watsonx": "WATSONX_API_KEY",
    "tencent-hunyuan": "TENCENTCLOUD_SECRET_ID",
    "sensetime": "SENSENOVA_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "apodex": "APODEX_API_KEY",
    "shanghai-ai-lab": "ATRIA_API_KEY",
    "ibm-rhai": "IBM_RHAI_API_KEY",
    "sarvam-ai": "SARVAM_API_KEY",
    "minimax": MINIMAX_API_KEY_ENV,
    "fireworks": fireworks.API_KEY_ENV,
    databricks.PROVIDER_ID: databricks.API_KEY_ENV,
    "snowflake": "SNOWFLAKE_TOKEN",
    "iflytek": "IFLYTEK_API_PASSWORD",
    "xiaomi": "MIMO_API_KEY",
    "perplexity": PERPLEXITY_API_KEY_ENV,
    "krutrim": "KRUTRIM_CLOUD_API_KEY",
    "kuaishou": "STREAMLAKE_API_KEY",
    "kwaipilot": "STREAMLAKE_API_KEY",
    "relace": relace.API_KEY_ENV,
    "naver": "CLOVASTUDIO_API_KEY",
    "contextual-ai": contextual.API_KEY_ENV,
    "sakana": sakana.API_KEY_ENV,
    "ant-group": "ANT_LING_API_KEY",
    "morph": morph.API_KEY_ENV,
    "huawei": HUAWEI_API_KEY_ENV,
}

_MODELS_ENDPOINTS = {
    "deepseek": deepseek.MODELS_ENDPOINT,
    "perceptron": perceptron.MODELS_ENDPOINT,
    "huawei": HUAWEI_MODELS_ENDPOINT,
    moonshot.PROVIDER_ID: moonshot.MODELS_ENDPOINT,
    "arcee-ai": ARCEE_MODELS_ENDPOINT,
    "reka-ai": REKA_MODELS_ENDPOINT,
    longcat.PROVIDER_ID: longcat.MODELS_ENDPOINT,
    "baidu": "https://qianfan.baidubce.com/v2/models",
    "mistral-ai": MISTRAL_MODELS_ENDPOINT,
    "xai": xai.MODELS_ENDPOINT,
    "writer": WRITER_MODELS_ENDPOINT,
    "poolside": MODELS_ENDPOINT,
    "openai": "https://api.openai.com/v1/models",
    "apodex": "https://api.apodex.ai/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "inception": INCEPTION_MODELS_ENDPOINT,
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "relace": relace.MODELS_ENDPOINT,
    "sakana": sakana.MODELS_ENDPOINT,
    "morph": morph.MODELS_ENDPOINT,
    "stepfun": STEPFUN_MODELS_ENDPOINT,
    "xiaomi": "https://api.xiaomimimo.com/v1/models",
    "perplexity": PERPLEXITY_MODELS_ENDPOINT,
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
    if provider in baichuan.ALIASES and not isinstance(model, str):
        raise ValueError("Baichuan requires an exact provider-native model ID")
    if provider == "perplexity":
        validate_perplexity_config(model, runtime_config)
    provider = longcat.normalize_provider(provider)
    if provider == longcat.PROVIDER_ID:
        longcat.validate_configuration(model, runtime_config)
    from eslams.providers.watsonx import configuration_error as watsonx_configuration_error
    from eslams.providers.watsonx import normalize_alias
    from eslams.providers.watsonx import validate_model as validate_watsonx_model
    watsonx_problem = None
    if normalize_alias(provider) == "watsonx":
        validate_watsonx_model(model)
        watsonx_problem = watsonx_configuration_error(runtime_config)
    configuration_error: dict[str, Any] | None = None
    if PROVIDER_ALIASES.get(provider, provider) == "baidu":
        from eslams.providers.baidu import reasoning_controls, validate_model

        validate_model(model)
        try:
            reasoning_controls(model, runtime_config)
        except ProviderCallError as exc:
            configuration_error = _public_error(exc, provider=provider, model=model)
    if provider.strip().replace("_", "-") in {"hunyuan", "tencent-hunyuan"}:
        provider = "tencent-hunyuan"
    from eslams.providers.byteplus import canonical_provider
    from eslams.providers.byteplus import configuration_error as byteplus_configuration_error

    if canonical_provider(provider) and (
        byteplus_error := byteplus_configuration_error(model, runtime_config)
    ):
        raise ValueError(byteplus_error)
    provider = canonicalize_qwen_provider(provider)
    if provider.strip() == "stepfun":
        provider = "stepfun"
    provider = deepseek.canonical_provider(provider)
    provider_config_error = (deepseek.configuration_error(model, runtime_config)
                             if provider == "deepseek" else None)
    provider = xai.canonical_provider(provider.lower())
    if provider == "xai":
        xai.validate_model(model)
        xai_error = xai.configuration_error(runtime_config)
        if xai_error is not None:
            configuration_error = {"error_class": "provider_request_rejected", "message": xai_error}
    if provider.strip().replace("_", "-") in {"liquid", "liquid-ai"}:
        from eslams.providers.liquid import validate_config as liquid_validate_config

        provider = "liquid-ai"
        liquid_validate_config(model, runtime_config)
    if provider == "apodex":
        from eslams.providers.apodex import validate_configuration

        try:
            validate_configuration(model, runtime_config)
        except ValueError as exc:
            configuration_error = {"error_class": "provider_request_rejected", "message": str(exc)}
    if provider.strip().replace("_", "-") == "shanghai-ai-lab":
        validate_shanghai_ai_lab(model, runtime_config, max_output_tokens=max_output_tokens)
    from eslams.providers.ibm_rhai import configuration_error as ibm_configuration_error
    from eslams.providers.ibm_rhai import normalize_alias, validate_model
    provider = normalize_alias(provider)
    config_error = None
    if provider == "ibm-rhai":
        validate_model(model)
        config_error = ibm_configuration_error(runtime_config)
    mistral_error = (
        mistral_configuration_error(model, runtime_config)
        if provider.strip().replace("_", "-") in {"mistral", "mistral-ai"} else None
    )
    provider = cohere.canonical_provider(provider) or provider
    if provider == "cohere":
        cohere.validate_model(model)
        cohere_error = cohere.configuration_error(model, runtime_config)
        if cohere_error is not None:
            configuration_error = {
                "error_class": "provider_request_rejected", "message": cohere_error,
            }
    sarvam_error: dict[str, Any] | None = None
    normalized_provider = provider.replace("_", "-")
    if PROVIDER_ALIASES.get(normalized_provider, normalized_provider) == "sarvam-ai":
        from eslams.providers.sarvam import validate_configuration
        from eslams.providers.sarvam import validate_model as validate_sarvam_model

        validate_sarvam_model(model)
        try:
            validate_configuration(model, runtime_config)
        except ProviderCallError as exc:
            sarvam_error = _public_error(exc, provider=provider, model=model)
    if provider in writer.ALIASES:
        writer.validate_model(model)
    writer_config_error = (
        writer.configuration_error(runtime_config) if provider in writer.ALIASES else None
    )
    from eslams.providers.minimax import configuration_error as minimax_configuration_error
    minimax_error = (
        minimax_configuration_error(model, runtime_config) if provider == "minimax" else None
    )
    registry_model = (
        "" if (provider_config_error or mistral_error or minimax_error)
        and not isinstance(model, str) else model
    )
    if provider == "krutrim":
        from eslams.providers.krutrim import validate_config as validate_krutrim_config

        validate_krutrim_config(model, runtime_config)
    if provider == "sakana":
        sakana.validate_config(model, runtime_config or ProviderRuntimeConfig())
    if provider in {"ai21", ai21.PROVIDER_ID}:
        ai21.validate_config(model, runtime_config)
    if provider in {"kuaishou", "kwaipilot"}:
        from eslams.providers.kuaishou import validate_configuration

        validate_configuration(model, runtime_config)
    if provider == "relace":
        relace.validate_configuration(model, runtime_config)
    if provider == "naver":
        from eslams.providers.naver import validate_settings as naver_validate_settings

        naver_validate_settings(model, runtime_config or ProviderRuntimeConfig())
    if provider.strip() == "perceptron":
        provider = "perceptron"
        perceptron.validate_settings(model, runtime_config)
    if provider == "morph":
        morph.validate_configuration(model, runtime_config or ProviderRuntimeConfig())
    if provider.strip() == "huawei":
        provider = "huawei"
        validate_huawei_config(model, runtime_config or ProviderRuntimeConfig())
    provider_registry = load_provider_registry()
    normalized_provider = provider.strip().replace("_", "-")
    if PROVIDER_ALIASES.get(normalized_provider, normalized_provider) == "ant-group":
        from eslams.providers.ant_ling import validate_config as ant_ling_validate_config

        ant_ling_validate_config(model, runtime_config or ProviderRuntimeConfig())
    record = provider_registry.resolve(provider, registry_model)
    if record.provider == contextual.PROVIDER_ID:
        contextual.validate_configuration(model, runtime_config, max_output_tokens)
    adapter_configuration_error = (
        sensenova_configuration_error(model, runtime_config)
        if record.provider == "sensetime" else None
    )
    arena = registry.create(arena_id)
    state = arena.initial_state(seed=1)
    legal_actions = arena.legal_actions_for(state, state.active_player)
    credential_environment = DEFAULT_PROVIDER_ENV.get(record.provider)
    credential_error = None
    if record.provider == "qwen":
        qwen_validate_model(model)
    elif record.provider == upstage.PROVIDER_ID:
        upstage.validate_model(model)
    elif record.provider == "stepfun":
        validate_stepfun_model_id(model)
    elif record.provider == "inception":
        validate_inception_model_id(model)

    if provider_config_error is not None:
        configuration_error = {
            "error_class": "provider_request_rejected", "message": provider_config_error,
        }
    try:
        if record.provider == "qwen":
            qwen_validate_controls(runtime_config)
            qwen_generation_endpoint()
        elif record.provider == upstage.PROVIDER_ID:
            upstage.reasoning_effort(runtime_config)
        elif record.provider == "stepfun":
            validate_stepfun_configuration(model, runtime_config)
        elif record.provider == "arcee-ai":
            validate_arcee_configuration(model, runtime_config)
        elif record.provider == "inception":
            message = inception_configuration_error(runtime_config)
            if message is not None:
                raise ValueError(message)
        elif record.provider == "reka-ai":
            message = reka_configuration_error(model, runtime_config)
            if message is not None:
                raise ValueError(message)
        elif record.provider == "azure":
            credential_environment = azure.credential_environment()
            azure.endpoint(runtime_config)
            if not model or not model.strip():
                raise ValueError("Azure requires an explicit deployment name")
    except ProviderCallError as exc:
        configuration_error = _public_error(exc, provider=provider, model=model)
    except ValueError as exc:
        configuration_error = {"error_class": "provider_request_rejected", "message": str(exc)}
    credential_present = False
    if credential_environment:
        try:
            if provider_key(credential_environment) is not None:
                credential_present = True
            if record.provider == "tencent-hunyuan":
                from eslams.providers.tencent_hunyuan import credentials

                credentials()
                if not credential_present:
                    raise ValueError("native Hunyuan requires a primary credential")
        except ValueError:
            credential_error = (
                "API key must contain printable ASCII without internal whitespace"
            )
            if record.provider == "tencent-hunyuan":
                credential_present = False
                credential_error = (
                    "native Hunyuan requires valid TENCENTCLOUD_SECRET_ID/SECRET_KEY "
                    "and optional TOKEN/REGION"
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
    warnings = provider_registry.warnings_for(provider, registry_model)
    control_error = None
    if record.provider == "tencent-hunyuan":
        from eslams.providers.tencent_hunyuan import validate_controls

        warnings.append(RETIREMENT_WARNING)
        try:
            validate_controls(model, runtime_config or ProviderRuntimeConfig(), max_output_tokens)
        except ValueError as exc:
            control_error = str(exc)
    connection_error = None
    if record.provider == "snowflake":
        try:
            snowflake_connection_settings()
            checks["account_endpoint_configured"] = True
        except ValueError as exc:
            checks["account_endpoint_configured"] = False
            connection_error = str(exc)
    databricks_error = None
    if record.provider == databricks.PROVIDER_ID:
        try:
            databricks.invocation_endpoint(model)
        except ValueError as exc:
            databricks_error = str(exc)
        checks["workspace_endpoint_configured"] = databricks_error is None
    error: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    discovery_error: dict[str, Any] | None = None
    inference_invoked = False
    option_error = (
        validate_nvidia_options(model, runtime_config) if record.provider == "nvidia" else None
    )
    poolside_error = (
        poolside_configuration_error(model, runtime_config)
        if record.provider == "poolside" else None
    )
    baichuan_error = None
    if record.provider == baichuan.PROVIDER_ID:
        try:
            baichuan.validate_controls(model, runtime_config)
        except ProviderCallError as exc:
            baichuan_error = _public_error(exc, provider=provider, model=model)

    if sarvam_error is not None:
        error = sarvam_error
    elif configuration_error is not None:
        error = configuration_error
    elif writer_config_error:
        error = {"error_class": "provider_request_rejected", "message": writer_config_error}
    elif option_error:
        error = {"error_class": "provider_request_rejected", "message": option_error}
    elif poolside_error:
        error = {"error_class": "provider_request_rejected", "message": poolside_error}
    elif credential_environment is None:
        error = {
            "error_class": "provider_adapter_unavailable",
            "message": f"Core has no inference adapter for provider {provider!r}",
        }
    elif watsonx_problem:
        error = {"error_class": "provider_request_rejected", "message": watsonx_problem}
    elif config_error:
        error = {"error_class": "provider_request_rejected", "message": config_error}
    elif mistral_error:
        error = {"error_class": "provider_request_rejected", "message": mistral_error}
    elif minimax_error:
        error = {"error_class": "provider_request_rejected", "message": minimax_error}
    elif baichuan_error is not None:
        error = baichuan_error
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
    elif databricks_error:
        error = {"error_class": "provider_request_rejected", "message": databricks_error}
    elif credential_error:
        error = {"error_class": "provider_auth_failed", "message": credential_error}
    elif control_error:
        error = {"error_class": "provider_request_rejected", "message": control_error}
    elif adapter_configuration_error:
        error = {"error_class": "provider_request_rejected",
                 "message": adapter_configuration_error}
    elif connection_error:
        error = {"error_class": "provider_request_rejected", "message": connection_error}
    elif not live:
        warnings.append("This configuration preflight did not verify live provider availability.")
    elif not credential_environment or not credential_present:
        error = {
            "error_class": "provider_auth_failed",
            "message": f"missing API key environment variable {credential_environment}",
        }
    else:
        try:
            visible_models = provider_models_live(provider)
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
                "Adapter model discovery is unavailable; account visibility remains unverified."
                 if record.provider == "watsonx" else
                "Model discovery is not implemented; account visibility remains unverified."
                if record.provider == "ibm-rhai" else
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
                provider=(provider if record.provider == moonshot.PROVIDER_ID
                          else record.provider),
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
                checks["usage_extraction"] = (
                    isinstance(usage, dict)
                    and not usage.get("usage_validation_errors")
                    and all(_is_int(usage.get(key))
                            for key in ("input_tokens", "output_tokens", "total_tokens"))
                )
                if record.provider == longcat.PROVIDER_ID and isinstance(usage, dict):
                    checks["usage_extraction"] = (
                        checks["usage_extraction"] is True
                        and isinstance(usage.get("reasoning_included_in_output"), bool)
                        and not usage.get("usage_validation_errors")
                    )
                if record.provider == "xai" and isinstance(usage, dict):
                    checks["usage_extraction"] = checks["usage_extraction"] and (
                        isinstance(usage.get("reasoning_included_in_output"), bool)
                        and usage.get("usage_validation_errors") == []
                    )
                if record.provider == baichuan.PROVIDER_ID and isinstance(usage, dict):
                    checks["usage_extraction"] = (
                        checks["usage_extraction"] is True
                        and not usage.get("usage_validation_errors")
                    )
                if record.provider == "perplexity":
                    checks["usage_extraction"] = (
                        isinstance(receipt, dict)
                        and aggregate_provider_receipts([receipt])[0]["usageComplete"] is True
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
    # This host has numeric counters but no verified reasoning-inclusion contract.
    usage_complete = checks["usage_extraction"] is True and record.provider != "ibm-rhai"
    if record.provider == baichuan.PROVIDER_ID:
        usage = receipt.get("usage") if isinstance(receipt, dict) else None
        usage_complete = (usage_complete and isinstance(usage, dict)
                          and isinstance(usage.get("reasoning_included_in_output"), bool))
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
            "configuration_ready": (
                checks["adapter_available"] is True and credential_error is None
                and configuration_error is None and control_error is None
                and adapter_configuration_error is None and option_error is None
                and config_error is None and sarvam_error is None and mistral_error is None
                and writer_config_error is None and minimax_error is None
                and connection_error is None and databricks_error is None
                and poolside_error is None and baichuan_error is None
                and (record.provider != "watsonx" or error is None)
            ),
            "inference": ("succeeded" if checks["minimal_inference"] is True else
                          "failed" if inference_invoked else "not_attempted"),
            "legal_action_observed": checks["response_parsing"] is True,
            "usage_complete": usage_complete,
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
            "usage_complete": usage_complete,
        },
    }
    if error is not None:
        payload["error"] = error
    if discovery_error is not None:
        payload["discovery_error"] = discovery_error
    return payload


@mistral_discovery_guard
def provider_models_live(provider: str) -> list[str] | None:
    """Discover every model page, or fail without treating partial results as complete.

    ``None`` means the adapter has no Models API. Authentication, transport,
    HTTP and malformed/pagination failures raise a diagnostic ProviderCallError.
    """
    regional_endpoint = moonshot.models_endpoint(provider)
    provider = provider.strip().lower().replace("_", "-")
    provider = PROVIDER_ALIASES.get(provider, provider)
    if provider == "xai" and not xai.credentials_scoped():
        with xai.credential_scope(environment_name=xai.API_KEY_ENV):
            return provider_models_live(provider)
    if provider == "cohere":
        return cohere.models_live()
    if provider == "writer":
        return writer.models_live()
    endpoint = (regional_endpoint if provider == moonshot.PROVIDER_ID
                else _MODELS_ENDPOINTS.get(provider))
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
    relace_credentials = relace.credential_values(api_key) if provider == "relace" else ()
    sakana_credentials = sakana.credential_values(api_key) if provider == "sakana" else ()
    discovery_credentials = morph.credential_values(api_key_env) if provider == "morph" else ()
    huawei_credentials = (
        huawei_credential_values(api_key, api_key_env) if provider == "huawei" else ()
    )
    apodex_credentials: tuple[str, ...] = ()
    if provider == "apodex":
        from eslams.providers.apodex import redaction_credentials

        apodex_credentials = redaction_credentials(api_key)
    if provider == "perplexity":
        return discover_perplexity_models(api_key)
    headers = {"Accept": "application/json"}
    params: dict[str, str] = {}
    if provider == "anthropic":
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        params["limit"] = "1000"
    elif provider == "google":
        headers["x-goog-api-key"] = api_key
        params["pageSize"] = "1000"
    elif provider == "xiaomi":
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    models: list[str] = []
    credentials = perceptron.credential_values(api_key) if provider == "perceptron" else ()
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
            payload = morph.discovery_payload(response) if provider == "morph" else response.json()
        except (ValueError, UnicodeError, RecursionError):
            raise _discovery_schema_error(provider) from None
        if not isinstance(payload, dict):
            raise _discovery_schema_error(provider)
        rows = payload.get("models" if provider in {"google", "writer"} else "data")
        if not isinstance(rows, list):
            raise _discovery_schema_error(provider)
        for row in rows:
            raw = (
                row.get("name" if provider == "google" else "id")
                if isinstance(row, dict) else None
            )
            if not isinstance(raw, str) or not raw.strip():
                raise _discovery_schema_error(provider)
            if provider == "deepseek" and deepseek.has_credential_echo(
                raw, deepseek.credential_values(api_key),
            ):
                raise _discovery_schema_error(provider)
            if provider == "relace" and relace.contains_credential(raw, relace_credentials):
                raise _discovery_schema_error(provider)
            if provider == "perceptron" and perceptron.contains_credential(raw, credentials):
                raise _discovery_schema_error(provider)
            if provider == "sakana" and sakana.contains_credential(raw, sakana_credentials):
                raise _discovery_schema_error(provider)
            if provider == "morph" and morph.contains_credentials(raw, discovery_credentials):
                raise _discovery_schema_error(provider)
            if provider == "huawei" and huawei_contains_credential(raw, huawei_credentials):
                raise _discovery_schema_error(provider)
            if provider == moonshot.PROVIDER_ID and api_key in raw:
                raise _discovery_schema_error(provider)
            if provider == "inception" and inception_credential_echo(raw, api_key):
                raise _discovery_schema_error(provider)
            if provider == "reka-ai" and reka_credential_echo(raw):
                raise _discovery_schema_error(provider)
            if provider == longcat.PROVIDER_ID and longcat.credential_echo(
                raw, longcat.credential_values(api_key, api_key_env),
            ):
                raise _discovery_schema_error(provider)
            if provider == "baidu":
                from eslams.providers.baidu import contains_credential, credential_values

                if contains_credential(raw, credential_values(api_key)):
                    raise _discovery_schema_error(provider)
            if any(secret in raw for secret in apodex_credentials):
                raise _discovery_schema_error(provider)
            if provider == "mistral-ai" and mistral_contains_credential(raw, api_key):
                raise _discovery_schema_error(provider)
            if provider == "xai" and xai.contains_credential(raw):
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
    provider = xai.canonical_provider(provider)
    provider = cohere.canonical_provider(provider) or provider
    payload: dict[str, Any] = {"provider": provider, "mode": "live", "ok": False, "models": []}
    try:
        models = provider_models_live(provider)
        if models is None:
            from eslams.providers.ibm_rhai import normalize_alias
            raise ProviderCallError(
                "Model discovery is not implemented; account visibility remains unverified"
                if normalize_alias(provider.lower()) == "ibm-rhai" else
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
