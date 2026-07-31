"""Provider model capability records.

The registry is intentionally conservative: optional adapter parameters are
disabled unless a model record explicitly enables them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CapabilityFlagMap = dict[str, dict[str, Any]]
MODEL_LIFECYCLES = {"active", "deprecated", "retired", "alias", "account-dependent"}


@dataclass(frozen=True)
class ModelCapabilities:
    provider: str
    model: str
    available_from_api: bool | None = None
    game_agent_supported: bool = False
    endpoints: list[str] = field(default_factory=list)
    modalities: dict[str, list[str]] = field(
        default_factory=lambda: {"input": ["text"], "output": ["text"]}
    )
    supports_temperature: bool = False
    supports_reasoning: bool = False
    reasoning_efforts: list[str] = field(default_factory=list)
    default_reasoning_effort: str | None = None
    supported_reasoning_modes: list[str] = field(default_factory=list)
    accepted_control_fields: list[str] = field(default_factory=list)
    default_reasoning_track: str | None = None
    reasoning_track_kind: str = "provider_native"
    unsupported_reasoning_control_reason: str | None = None
    http_agent_payload_guidance: dict[str, Any] = field(default_factory=dict)
    supports_google_thinking_config: bool = False
    max_output_tokens: int | None = None
    context_window: int | None = None
    last_verified_at: str | None = None
    sources: list[str] = field(default_factory=list)
    known: bool = True
    capability_flags: CapabilityFlagMap = field(default_factory=dict)
    allowed_games: list[str] = field(default_factory=list)
    unsupported_games: list[str] = field(default_factory=list)
    launch_status: str = "not_evaluated"
    eligibility_reasons: list[str] = field(default_factory=list)
    source_model_id: str | None = None
    public_slug: str | None = None
    display_name: str | None = None
    modality_summary: str | None = None
    pricing: dict[str, Any] = field(default_factory=dict)
    lifecycle: str = "account-dependent"
    anthropic_thinking_mode: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ModelCapabilities:
        modalities = value.get("modalities")
        if not isinstance(modalities, dict):
            modalities = {"input": ["text"], "output": ["text"]}
        game_agent_supported = bool(value.get("game_agent_supported", False))
        provider = str(value["provider"]).lower()
        model = str(value["model"])
        supports_reasoning = bool(value.get("supports_reasoning", False))
        anthropic_thinking_mode = _anthropic_thinking_mode(
            value.get("anthropic_thinking_mode"),
            provider=provider,
            model=model,
            supports_reasoning=supports_reasoning,
        )
        reasoning_efforts = _strings(value.get("reasoning_efforts"))
        default_reasoning_effort = _optional_str(value.get("default_reasoning_effort"))
        supports_google_thinking_config = bool(value.get("supports_google_thinking_config", False))
        accepted_control_fields = _strings(value.get("accepted_control_fields")) or (
            _provider_control_fields(
                provider,
                supports_reasoning=supports_reasoning,
                supports_google_thinking_config=supports_google_thinking_config,
                anthropic_thinking_mode=anthropic_thinking_mode,
            )
        )
        supported_reasoning_modes = _strings(value.get("supported_reasoning_modes")) or (
            reasoning_efforts if reasoning_efforts else ["native-default"]
        )
        default_reasoning_track = _optional_str(value.get("default_reasoning_track")) or (
            default_reasoning_effort or supported_reasoning_modes[0]
        )
        reasoning_track_kind = _reasoning_track_kind(
            value.get("reasoning_track_kind"),
            accepted_control_fields=accepted_control_fields,
        )
        unsupported_reasoning_control_reason = _unsupported_control_reason(
            value.get("unsupported_reasoning_control_reason"),
            game_agent_supported=game_agent_supported,
            accepted_control_fields=accepted_control_fields,
        )
        return cls(
            provider=provider,
            model=model,
            available_from_api=_optional_bool(value.get("available_from_api")),
            game_agent_supported=game_agent_supported,
            endpoints=_strings(value.get("endpoints")),
            modalities={
                "input": _strings(modalities.get("input")),
                "output": _strings(modalities.get("output")),
            },
            supports_temperature=bool(value.get("supports_temperature", False)),
            supports_reasoning=supports_reasoning,
            reasoning_efforts=reasoning_efforts,
            default_reasoning_effort=default_reasoning_effort,
            supported_reasoning_modes=supported_reasoning_modes,
            accepted_control_fields=accepted_control_fields,
            default_reasoning_track=default_reasoning_track,
            reasoning_track_kind=reasoning_track_kind,
            unsupported_reasoning_control_reason=unsupported_reasoning_control_reason,
            http_agent_payload_guidance=_http_agent_payload_guidance(
                value.get("http_agent_payload_guidance"),
                accepted_control_fields=accepted_control_fields,
                default_reasoning_track=default_reasoning_track,
                reasoning_track_kind=reasoning_track_kind,
                unsupported_reasoning_control_reason=unsupported_reasoning_control_reason,
            ),
            supports_google_thinking_config=supports_google_thinking_config,
            max_output_tokens=_optional_int(value.get("max_output_tokens")),
            context_window=_optional_int(value.get("context_window")),
            last_verified_at=_optional_str(value.get("last_verified_at")),
            sources=_strings(value.get("sources")),
            known=bool(value.get("known", True)),
            capability_flags=_capability_flags(
                value.get("capability_flags"),
                game_agent_supported=game_agent_supported,
            ),
            allowed_games=_strings(value.get("allowed_games")),
            unsupported_games=_strings(value.get("unsupported_games")),
            launch_status=_launch_status(value.get("launch_status"), game_agent_supported),
            eligibility_reasons=_strings(value.get("eligibility_reasons")),
            source_model_id=_optional_str(value.get("source_model_id")) or str(value["model"]),
            public_slug=_optional_str(value.get("public_slug"))
            or _public_slug(str(value["provider"]), str(value["model"])),
            display_name=_optional_str(value.get("display_name")) or str(value["model"]),
            modality_summary=_optional_str(value.get("modality_summary"))
            or _modality_summary(modalities),
            pricing=_safe_mapping(value.get("pricing")),
            lifecycle=_lifecycle(value.get("lifecycle"), value.get("available_from_api")),
            anthropic_thinking_mode=anthropic_thinking_mode,
        )

    @classmethod
    def unknown(cls, provider: str, model: str) -> ModelCapabilities:
        return cls(
            provider=provider.lower(),
            model=model,
            available_from_api=None,
            game_agent_supported=False,
            endpoints=[],
            supports_temperature=False,
            supports_reasoning=False,
            supported_reasoning_modes=["native-default"],
            accepted_control_fields=[],
            default_reasoning_track="native-default",
            reasoning_track_kind="provider_native",
            unsupported_reasoning_control_reason="unknown_model",
            http_agent_payload_guidance=_http_agent_payload_guidance(
                None,
                accepted_control_fields=[],
                default_reasoning_track="native-default",
                reasoning_track_kind="provider_native",
                unsupported_reasoning_control_reason="unknown_model",
            ),
            supports_google_thinking_config=False,
            sources=["unknown-model"],
            known=False,
            capability_flags=_capability_flags(None, game_agent_supported=False),
            launch_status="not_evaluated",
            eligibility_reasons=["unknown_model"],
            source_model_id=model,
            public_slug=_public_slug(provider, model),
            display_name=model,
            modality_summary="unknown",
            pricing={},
            lifecycle="account-dependent",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "available_from_api": self.available_from_api,
            "game_agent_supported": self.game_agent_supported,
            "endpoints": list(self.endpoints),
            "modalities": {
                "input": list(self.modalities.get("input", [])),
                "output": list(self.modalities.get("output", [])),
            },
            "supports_temperature": self.supports_temperature,
            "supports_reasoning": self.supports_reasoning,
            "reasoning_efforts": list(self.reasoning_efforts),
            "default_reasoning_effort": self.default_reasoning_effort,
            "supported_reasoning_modes": list(self.supported_reasoning_modes),
            "accepted_control_fields": list(self.accepted_control_fields),
            "default_reasoning_track": self.default_reasoning_track,
            "reasoning_track_kind": self.reasoning_track_kind,
            "unsupported_reasoning_control_reason": self.unsupported_reasoning_control_reason,
            "http_agent_payload_guidance": dict(self.http_agent_payload_guidance),
            "supports_google_thinking_config": self.supports_google_thinking_config,
            "max_output_tokens": self.max_output_tokens,
            "context_window": self.context_window,
            "last_verified_at": self.last_verified_at,
            "sources": list(self.sources),
            "known": self.known,
            "capability_flags": {
                key: dict(value) for key, value in sorted(self.capability_flags.items())
            },
            "allowed_games": list(self.allowed_games),
            "unsupported_games": list(self.unsupported_games),
            "launch_status": self.launch_status,
            "eligibility_reasons": list(self.eligibility_reasons),
            "source_model_id": self.source_model_id,
            "public_slug": self.public_slug,
            "display_name": self.display_name,
            "modality_summary": self.modality_summary,
            "pricing": dict(self.pricing),
            "lifecycle": self.lifecycle,
            "anthropic_thinking_mode": self.anthropic_reasoning_mode(),
        }

    def allows_text_game_agent(self) -> bool:
        return (
            self.game_agent_supported
            and "text" in self.modalities.get("input", [])
            and "text" in self.modalities.get("output", [])
        )

    def reasoning_payload(self) -> dict[str, str] | None:
        effort = self.default_reasoning_effort
        if not self.supports_reasoning or not effort:
            return None
        if self.reasoning_efforts and effort not in self.reasoning_efforts:
            return None
        return {"effort": effort}

    def capability_enabled(self, capability: str) -> bool:
        value = self.capability_flags.get(capability, {})
        return value.get("enabled") is True

    def anthropic_reasoning_mode(self) -> str | None:
        return _anthropic_thinking_mode(
            self.anthropic_thinking_mode,
            provider=self.provider,
            model=self.model,
            supports_reasoning=self.supports_reasoning,
        )


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, (str, int, float, bool)) or item is None
    }


def _lifecycle(value: Any, available_from_api: Any) -> str:
    if isinstance(value, str) and value in MODEL_LIFECYCLES:
        return value
    if available_from_api is True:
        return "active"
    if available_from_api is False:
        return "retired"
    return "account-dependent"


def _anthropic_thinking_mode(
    value: Any,
    *,
    provider: str,
    model: str,
    supports_reasoning: bool,
) -> str | None:
    if isinstance(value, str) and value in {"manual", "adaptive", "default"}:
        return value
    if provider != "anthropic" or not supports_reasoning:
        return None
    match = re.search(r"claude-(?:[a-z]+-)?([45])(?:[.-]([0-9]+))?", model.lower())
    if match is not None:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        if major >= 5 or (major == 4 and 7 <= minor < 100):
            return "adaptive"
    return "manual"


def _provider_control_fields(
    provider: str,
    *,
    supports_reasoning: bool,
    supports_google_thinking_config: bool,
    anthropic_thinking_mode: str | None,
) -> list[str]:
    if provider == "openai" and supports_reasoning:
        return ["reasoning_effort"]
    if provider in {"google", "gemini"} and supports_google_thinking_config:
        return ["thinkingBudget", "thinkingLevel"]
    if provider == "anthropic" and anthropic_thinking_mode == "manual":
        return ["thinking_budget_tokens"]
    if provider == "anthropic" and anthropic_thinking_mode == "adaptive":
        return ["adaptive_thinking"]
    return []


def _reasoning_track_kind(value: Any, *, accepted_control_fields: list[str]) -> str:
    if isinstance(value, str) and value in {"provider_controlled", "provider_native"}:
        return value
    return "provider_controlled" if accepted_control_fields else "provider_native"


def _unsupported_control_reason(
    value: Any,
    *,
    game_agent_supported: bool,
    accepted_control_fields: list[str],
) -> str | None:
    if isinstance(value, str) and value:
        return value
    if game_agent_supported and not accepted_control_fields:
        return "provider_control_not_supported"
    return None


def _http_agent_payload_guidance(
    value: Any,
    *,
    accepted_control_fields: list[str],
    default_reasoning_track: str | None,
    reasoning_track_kind: str,
    unsupported_reasoning_control_reason: str | None,
) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {
        "accepted_control_fields": list(accepted_control_fields),
        "default_reasoning_track": default_reasoning_track,
        "reasoning_track_kind": reasoning_track_kind,
        "unsupported_reasoning_control_reason": unsupported_reasoning_control_reason,
        "http_agent_rule": "omit unsupported provider controls from /act payloads",
    }


def _capability_flags(
    value: Any,
    *,
    game_agent_supported: bool,
) -> CapabilityFlagMap:
    defaults: CapabilityFlagMap = {
        "arena": {
            "enabled": game_agent_supported,
            "reason": None if game_agent_supported else "not_game_agent_supported",
        },
        "battlefield": {
            "enabled": game_agent_supported,
            "reason": None if game_agent_supported else "not_game_agent_supported",
        },
        "official_eval": {
            "enabled": False,
            "reason": "not_evaluated",
        },
    }
    if not isinstance(value, dict):
        return defaults
    merged: CapabilityFlagMap = dict(defaults)
    for key in ("official_eval", "battlefield", "arena"):
        raw = value.get(key)
        if isinstance(raw, dict):
            enabled = raw.get("enabled")
            reason = raw.get("reason")
            merged[key] = {
                "enabled": enabled if isinstance(enabled, bool) else defaults[key]["enabled"],
                "reason": reason if isinstance(reason, str) else defaults[key]["reason"],
            }
        elif isinstance(raw, bool):
            merged[key] = {"enabled": raw, "reason": None if raw else "not_supported"}
    return merged


def _launch_status(value: Any, game_agent_supported: bool) -> str:
    if isinstance(value, str) and value:
        return value
    return "ready" if game_agent_supported else "not_evaluated"


def _public_slug(provider: str, model: str) -> str:
    return f"{provider}-{model}".lower().replace("_", "-").replace("/", "-").replace(":", "-")


def _modality_summary(modalities: dict[str, Any]) -> str:
    inputs = ",".join(_strings(modalities.get("input"))) or "unknown"
    outputs = ",".join(_strings(modalities.get("output"))) or "unknown"
    return f"input:{inputs}; output:{outputs}"
