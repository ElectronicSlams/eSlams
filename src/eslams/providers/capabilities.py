"""Provider model capability records.

The registry is intentionally conservative: optional adapter parameters are
disabled unless a model record explicitly enables them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CapabilityFlagMap = dict[str, dict[str, Any]]


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

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ModelCapabilities:
        modalities = value.get("modalities")
        if not isinstance(modalities, dict):
            modalities = {"input": ["text"], "output": ["text"]}
        game_agent_supported = bool(value.get("game_agent_supported", False))
        return cls(
            provider=str(value["provider"]).lower(),
            model=str(value["model"]),
            available_from_api=_optional_bool(value.get("available_from_api")),
            game_agent_supported=game_agent_supported,
            endpoints=_strings(value.get("endpoints")),
            modalities={
                "input": _strings(modalities.get("input")),
                "output": _strings(modalities.get("output")),
            },
            supports_temperature=bool(value.get("supports_temperature", False)),
            supports_reasoning=bool(value.get("supports_reasoning", False)),
            reasoning_efforts=_strings(value.get("reasoning_efforts")),
            default_reasoning_effort=_optional_str(value.get("default_reasoning_effort")),
            supports_google_thinking_config=bool(
                value.get("supports_google_thinking_config", False)
            ),
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
