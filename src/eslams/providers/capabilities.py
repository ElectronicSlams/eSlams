"""Provider model capability records.

The registry is intentionally conservative: optional adapter parameters are
disabled unless a model record explicitly enables them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ModelCapabilities:
        modalities = value.get("modalities")
        if not isinstance(modalities, dict):
            modalities = {"input": ["text"], "output": ["text"]}
        return cls(
            provider=str(value["provider"]).lower(),
            model=str(value["model"]),
            available_from_api=_optional_bool(value.get("available_from_api")),
            game_agent_supported=bool(value.get("game_agent_supported", False)),
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
