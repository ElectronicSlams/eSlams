#!/usr/bin/env python3
"""Refresh the eSlams provider model registry.

The updater is deliberately dependency-light so it can run in a clean checkout.
It merges public model metadata, optional configured provider model lists, and
local overrides into `src/eslams/providers/data/models.generated.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "eslams" / "providers" / "data"
DEFAULT_OUTPUT = DATA_DIR / "models.generated.json"
DEFAULT_OVERRIDES = DATA_DIR / "overrides.json"
sys.path.insert(0, str(ROOT / "src"))
MODELS_DEV_URL = "https://models.dev/api.json"
LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)

PROVIDER_ALIASES = {
    "adept": "adept-ai",
    "ai21": "ai21-labs",
    "google": "google",
    "gemini": "google",
    "vertex_ai": "google",
    "openai": "openai",
    "anthropic": "anthropic",
    "mistral": "mistral-ai",
    "cohere": "cohere",
    "xai": "xai",
    "deepseek": "deepseek",
    "alibaba": "qwen",
    "alibaba-cn": "qwen",
    "dashscope": "qwen",
    "meta-llama": "meta",
    "moonshot": "moonshot-ai",
    "moonshotai": "moonshot-ai",
    "moonshotai-cn": "moonshot-ai",
    "tencent-coding-plan": "tencent",
    "tencent-tokenhub": "tencent",
    "volcengine": "bytedance",
    "zhipuai": "zhipu",
    "zhipuai-coding-plan": "zhipu",
    "bailing": "ant-group",
    "inception": "core42",
    "gigachat": "sber",
    "amazon": "amazon-aws",
    "amazon-bedrock": "amazon-aws",
    "amazon-nova": "amazon-aws",
    "bedrock": "amazon-aws",
    "arcee": "arcee-ai",
    "baichuan": "baichuan-ai",
    "character": "character-ai",
    "contextual": "contextual-ai",
    "databricks": "databricks-mosaicml",
    "essential": "essential-ai",
    "inflection": "inflection-ai",
    "liquid": "liquid-ai",
    "nous": "nous-research",
    "reka": "reka-ai",
    "samsung": "samsung-research",
    "sarvam": "sarvam-ai",
    "xverse": "xverse-ai",
    "azure": "microsoft",
    "azure_ai": "microsoft",
    "watsonx": "ibm",
    "perplexity": "perplexity",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update eSlams provider model registry.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated provider filter such as openai,anthropic,google.",
    )
    parser.add_argument("--skip-public", action="store_true")
    args = parser.parse_args(argv)

    provider_filter = {item.strip().lower() for item in args.providers.split(",") if item.strip()}
    records: dict[tuple[str, str], dict[str, Any]] = {}
    sources: list[str] = []

    if not args.skip_public:
        models_dev = _fetch_json(MODELS_DEV_URL)
        if isinstance(models_dev, dict):
            sources.append("models.dev")
            for record in _records_from_models_dev(models_dev):
                _merge_record(records, record, provider_filter)
        litellm = _fetch_json(LITELLM_URL)
        if isinstance(litellm, dict):
            sources.append("litellm")
            for record in _records_from_litellm(litellm):
                _merge_record(records, record, provider_filter)

    for record in _records_from_provider_apis():
        _merge_record(records, record, provider_filter)
        if "provider-api" not in sources:
            sources.append("provider-api")

    overrides = _read_json(args.overrides)
    for record in overrides.get("models", []):
        if isinstance(record, dict):
            _merge_record(
                records,
                {**record, "sources": _sources(record, "local-override")},
                provider_filter,
            )

    payload = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "sources": sources or ["local-override"],
        "organizations": _organizations(overrides),
        "models": [records[key] for key in sorted(records)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "models": len(payload["models"])}, indent=2))
    return 0


def _records_from_models_dev(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for provider_id, provider_payload in payload.items():
        if not isinstance(provider_payload, dict):
            continue
        provider = _normalize_provider(str(provider_payload.get("id") or provider_id))
        models = provider_payload.get("models")
        if not isinstance(models, dict):
            continue
        for model_id, model_payload in models.items():
            if not isinstance(model_payload, dict):
                continue
            modalities = model_payload.get("modalities")
            limit = model_payload.get("limit")
            input_modalities = (
                _strings((modalities or {}).get("input"))
                if isinstance(modalities, dict)
                else ["text"]
            )
            output_modalities = (
                _strings((modalities or {}).get("output"))
                if isinstance(modalities, dict)
                else ["text"]
            )
            mode_is_text = "text" in input_modalities and "text" in output_modalities
            records.append(
                {
                    "provider": provider,
                    "model": str(model_payload.get("id") or model_id),
                    "available_from_api": None,
                    "game_agent_supported": mode_is_text,
                    "endpoints": ["chat"],
                    "modalities": {"input": input_modalities, "output": output_modalities},
                    "supports_temperature": bool(model_payload.get("temperature", False)),
                    "supports_reasoning": bool(model_payload.get("reasoning", False)),
                    "reasoning_efforts": [],
                    "default_reasoning_effort": None,
                    "supports_google_thinking_config": False,
                    "max_output_tokens": (
                        _int((limit or {}).get("output")) if isinstance(limit, dict) else None
                    ),
                    "context_window": (
                        _int((limit or {}).get("context")) if isinstance(limit, dict) else None
                    ),
                    "last_verified_at": None,
                    "sources": ["models.dev"],
                }
            )
    return records


def _records_from_litellm(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for model_id, model_payload in payload.items():
        if model_id == "sample_spec" or not isinstance(model_payload, dict):
            continue
        provider_value = model_payload.get("litellm_provider")
        if not provider_value:
            continue
        provider = _normalize_provider(str(provider_value))
        mode = str(model_payload.get("mode", "chat"))
        text_mode = mode in {"chat", "completion", "responses"}
        records.append(
            {
                "provider": provider,
                "model": str(model_id),
                "available_from_api": None,
                "game_agent_supported": text_mode,
                "endpoints": [mode],
                "modalities": {"input": ["text"], "output": ["text"] if text_mode else []},
                "supports_temperature": True,
                "supports_reasoning": bool(model_payload.get("supports_reasoning", False)),
                "reasoning_efforts": [],
                "default_reasoning_effort": None,
                "supports_google_thinking_config": False,
                "max_output_tokens": _int(
                    model_payload.get("max_output_tokens") or model_payload.get("max_tokens")
                ),
                "context_window": _int(
                    model_payload.get("max_input_tokens") or model_payload.get("max_tokens")
                ),
                "pricing": _pricing_from_litellm(model_payload),
                "last_verified_at": None,
                "sources": ["litellm"],
            }
        )
    return records


def _records_from_provider_apis() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        data = _fetch_json(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {openai_key}"},
        )
        if isinstance(data, dict):
            for item in data.get("data", []):
                if isinstance(item, dict) and item.get("id"):
                    records.append(_api_availability_record("openai", str(item["id"])))
    google_key = os.getenv("GEMINI_API_KEY")
    if google_key:
        data = _fetch_json(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={google_key}"
        )
        if isinstance(data, dict):
            for item in data.get("models", []):
                if isinstance(item, dict) and item.get("name"):
                    model = str(item["name"]).split("/", 1)[-1]
                    records.append(_api_availability_record("google", model))
    return records


def _api_availability_record(provider: str, model: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "available_from_api": True,
        "game_agent_supported": True,
        "endpoints": [],
        "modalities": {"input": ["text"], "output": ["text"]},
        "supports_temperature": False,
        "supports_reasoning": False,
        "reasoning_efforts": [],
        "default_reasoning_effort": None,
        "supports_google_thinking_config": False,
        "max_output_tokens": None,
        "context_window": None,
        "last_verified_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "sources": ["provider-api"],
    }


def _merge_record(
    records: dict[tuple[str, str], dict[str, Any]],
    record: dict[str, Any],
    provider_filter: set[str],
) -> None:
    provider = _normalize_provider(str(record["provider"]))
    if provider_filter and provider not in provider_filter:
        return
    model = str(record["model"])
    key = (provider, model)
    existing = records.get(key, {})
    merged = {**existing, **record, "provider": provider, "model": model}
    merged["sources"] = sorted(set(_sources(existing) + _sources(record)))
    records[key] = merged


def _organizations(overrides: dict[str, Any]) -> list[dict[str, str]]:
    from eslams.providers.registry import REQUESTED_PROVIDER_ORGANIZATIONS

    organizations = dict(REQUESTED_PROVIDER_ORGANIZATIONS)
    for item in overrides.get("organizations", []):
        if isinstance(item, dict) and item.get("provider"):
            organizations[_normalize_provider(str(item["provider"]))] = str(
                item.get("name") or item["provider"]
            )
    return [
        {"provider": provider, "name": name} for provider, name in sorted(organizations.items())
    ]


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "eSlams-Core-Registry/0.1", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"warning: could not fetch {url}: {exc}", file=sys.stderr)
        return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_provider(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized, normalized)


def _sources(record: dict[str, Any], extra: str | None = None) -> list[str]:
    sources = [str(item) for item in record.get("sources", []) if item]
    if extra:
        sources.append(extra)
    return sources


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _pricing_from_litellm(payload: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "input_cost_per_token": payload.get("input_cost_per_token"),
        "output_cost_per_token": payload.get("output_cost_per_token"),
        "cache_creation_input_token_cost": payload.get("cache_creation_input_token_cost"),
        "cache_read_input_token_cost": payload.get("cache_read_input_token_cost"),
        "output_cost_per_reasoning_token": payload.get("output_cost_per_reasoning_token"),
    }
    pricing = {name: value for name, raw in fields.items() if (value := _number(raw)) is not None}
    if not pricing:
        return {}
    return {
        **pricing,
        "currency": "USD",
        "unit": "token",
        "source": "litellm",
    }


if __name__ == "__main__":
    raise SystemExit(main())
