"""Model/capability registry for provider-backed game agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, cast

from eslams.providers.capabilities import ModelCapabilities

REQUESTED_PROVIDER_ORGANIZATIONS: tuple[tuple[str, str], ...] = (
    ("qwen", "Alibaba / Qwen"),
    ("anthropic", "Anthropic"),
    ("cursor", "Cursor"),
    ("deepseek", "DeepSeek"),
    ("google", "Google / DeepMind"),
    ("meta", "Meta AI"),
    ("openai", "OpenAI"),
    ("xai", "xAI"),
    ("01-ai", "01.AI"),
    ("ant-group", "Ant Group"),
    ("baidu", "Baidu"),
    ("bytedance", "ByteDance / Seed"),
    ("huawei", "Huawei"),
    ("iflytek", "iFlytek"),
    ("kuaishou", "Kuaishou"),
    ("meituan", "Meituan"),
    ("minimax", "MiniMax"),
    ("openbmb", "OpenBMB / ModelBest"),
    ("sensetime", "SenseTime"),
    ("shanghai-ai-lab", "Shanghai AI Lab"),
    ("stepfun", "StepFun"),
    ("tencent", "Tencent"),
    ("xiaomi", "Xiaomi"),
    ("zhipu", "Zhipu AI / Z.ai"),
    ("adept-ai", "Adept AI"),
    ("ai21-labs", "AI21 Labs"),
    ("ai71", "AI71"),
    ("aion-labs", "Aion Labs"),
    ("aleph-alpha", "Aleph Alpha"),
    ("ai2", "Allen Institute for AI, AI2"),
    ("amazon-aws", "Amazon / AWS"),
    ("anthracite-org", "Anthracite Org"),
    ("apple", "Apple"),
    ("arcee-ai", "Arcee AI"),
    ("baai", "BAAI, Beijing Academy of AI"),
    ("baichuan-ai", "Baichuan AI"),
    ("bigcode", "BigCode / ServiceNow / Hugging Face"),
    ("bigscience", "BigScience / Hugging Face community"),
    ("character-ai", "Character.AI"),
    ("cognitivecomputations", "Cognitive Computations"),
    ("cohere", "Cohere"),
    ("contextual-ai", "Contextual AI"),
    ("core42", "Core42 / Inception / G42"),
    ("databricks-mosaicml", "Databricks / MosaicML"),
    ("deepcogito", "DeepCogito"),
    ("eleutherai", "EleutherAI"),
    ("essential-ai", "Essential AI"),
    ("gryphe", "Gryphe"),
    ("ibm", "IBM"),
    ("ibm-granite", "IBM Granite"),
    ("inclusionai", "InclusionAI"),
    ("inflection-ai", "Inflection AI"),
    ("kakao", "Kakao"),
    ("krutrim", "Krutrim"),
    ("kwaipilot", "KwaiPilot"),
    ("lg", "LG AI Research"),
    ("lighton", "LightOn"),
    ("liquid-ai", "Liquid AI"),
    ("mancer", "Mancer"),
    ("microsoft", "Microsoft"),
    ("mistral-ai", "Mistral AI"),
    ("moonshot-ai", "Moonshot AI"),
    ("morph", "Morph"),
    ("naver", "Naver"),
    ("nex-agi", "Nex AGI"),
    ("nous-research", "Nous Research"),
    ("nvidia", "NVIDIA"),
    ("openrouter", "OpenRouter"),
    ("perceptron", "Perceptron"),
    ("perplexity", "Perplexity"),
    ("poolside", "Poolside"),
    ("reka-ai", "Reka AI"),
    ("relace", "Relace"),
    ("sakana", "Sakana AI"),
    ("salesforce", "Salesforce AI Research"),
    ("samsung-research", "Samsung Research"),
    ("sao10k", "Sao10K"),
    ("sarvam-ai", "Sarvam AI"),
    ("sber", "Sber"),
    ("sdaia", "SDAIA / IBM / Saudi ecosystem"),
    ("sk-telecom", "SK Telecom"),
    ("snowflake", "Snowflake"),
    ("tii", "Technology Innovation Institute, UAE"),
    ("thedrummer", "TheDrummer"),
    ("thinkingmachines", "Thinking Machines"),
    ("undi95", "Undi95"),
    ("upstage", "Upstage"),
    ("writer", "Writer"),
    ("xverse-ai", "XVERSE AI"),
    ("yandex", "Yandex"),
)

# The public catalog grew from the original 69 curated organizations by adding
# Cursor's API-discovered Composer row and 20 author namespaces present in the
# release-pinned OpenRouter text-model snapshot. Keeping this provenance
# explicit prevents a display-only provider from being added without a source.
PLATFORM_API_DISCOVERED_PROVIDER_KEYS: tuple[str, ...] = ("cursor",)
FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS: tuple[str, ...] = (
    "aion-labs",
    "anthracite-org",
    "cognitivecomputations",
    "deepcogito",
    "gryphe",
    "ibm-granite",
    "inclusionai",
    "kwaipilot",
    "mancer",
    "morph",
    "nex-agi",
    "openrouter",
    "perceptron",
    "poolside",
    "relace",
    "sakana",
    "sao10k",
    "thedrummer",
    "thinkingmachines",
    "undi95",
)

PROVIDER_ALIASES = {
    "adept": "adept-ai",
    "ai21": "ai21-labs",
    "gemini": "google",
    "google-deepmind": "google",
    "vertex-ai": "google",
    "qwen": "qwen",
    "alibaba": "qwen",
    "alibaba-cn": "qwen",
    "dashscope": "qwen",
    "meta-llama": "meta",
    "amazon": "amazon-aws",
    "amazon-bedrock": "bedrock",
    "amazon-nova": "amazon-aws",
    "arcee": "arcee-ai",
    "baichuan": "baichuan-ai",
    "character": "character-ai",
    "contextual": "contextual-ai",
    "databricks": "databricks-mosaicml",
    "essential": "essential-ai",
    "inflection": "inflection-ai",
    "liquid": "liquid-ai",
    "mistral": "mistral-ai",
    "moonshot": "moonshot-ai",
    "moonshotai": "moonshot-ai",
    "moonshotai-cn": "moonshot-ai",
    "nous": "nous-research",
    "reka": "reka-ai",
    "samsung": "samsung-research",
    "sarvam": "sarvam-ai",
    "tencent-coding-plan": "tencent",
    "tencent-tokenhub": "tencent",
    "volcengine": "bytedance",
    "zhipuai": "zhipu",
    "zhipuai-coding-plan": "zhipu",
    "bailing": "ant-group",
    "inception": "core42",
    "gigachat": "sber",
    "aws": "amazon-aws",
    "bedrock": "bedrock",
    "azure": "microsoft",
    "azure-ai": "microsoft",
    "watsonx": "ibm",
    "xverse": "xverse-ai",
}


@dataclass(frozen=True)
class ProviderRegistry:
    models: dict[tuple[str, str], ModelCapabilities]
    organizations: dict[str, str]
    generated_at: str | None = None
    sources: tuple[str, ...] = ()

    def get(self, provider: str, model: str) -> ModelCapabilities | None:
        return self.models.get((_normalize(provider), model))

    def resolve(self, provider: str, model: str) -> ModelCapabilities:
        return self.get(provider, model) or ModelCapabilities.unknown(_normalize(provider), model)

    def list_models(
        self,
        *,
        provider: str | None = None,
        game_agent_supported: bool | None = None,
    ) -> list[ModelCapabilities]:
        records = list(self.models.values())
        if provider is not None:
            normalized = _normalize(provider)
            records = [record for record in records if record.provider == normalized]
        if game_agent_supported is not None:
            records = [
                record
                for record in records
                if record.allows_text_game_agent() is game_agent_supported
            ]
        return sorted(records, key=lambda item: (item.provider, item.model))

    def warnings_for(
        self,
        provider: str,
        model: str,
        *,
        api_key_env: str | None = None,
    ) -> list[str]:
        record = self.get(provider, model)
        warnings: list[str] = []
        if record is None:
            warnings.append(f"provider model {provider}:{model} is not in the registry")
            return warnings
        if record.available_from_api is False:
            warnings.append(f"provider model {provider}:{model} is marked unavailable from API")
        if record.lifecycle in {"deprecated", "retired"}:
            warnings.append(f"provider model {provider}:{model} lifecycle is {record.lifecycle}")
        if not record.allows_text_game_agent():
            warnings.append(f"provider model {provider}:{model} is not marked game_agent_supported")
        if api_key_env:
            warnings.append(f"requires API key environment variable {api_key_env}")
        return warnings


@lru_cache(maxsize=1)
def load_provider_registry() -> ProviderRegistry:
    generated = _load_package_json("models.generated.json")
    overrides = _load_package_json("overrides.json")
    return _registry_from_payloads(generated, overrides)


def load_provider_registry_from_paths(
    generated_path: Path,
    overrides_path: Path | None = None,
) -> ProviderRegistry:
    generated = json.loads(generated_path.read_text(encoding="utf-8"))
    overrides = (
        json.loads(overrides_path.read_text(encoding="utf-8"))
        if overrides_path and overrides_path.exists()
        else {}
    )
    return _registry_from_payloads(generated, overrides)


def _registry_from_payloads(
    generated: dict[str, Any],
    overrides: dict[str, Any],
) -> ProviderRegistry:
    organizations = dict(REQUESTED_PROVIDER_ORGANIZATIONS)
    for item in generated.get("organizations", []):
        if isinstance(item, dict) and isinstance(item.get("provider"), str):
            organizations[_normalize(item["provider"])] = str(item.get("name") or item["provider"])
    for item in overrides.get("organizations", []):
        if isinstance(item, dict) and isinstance(item.get("provider"), str):
            organizations[_normalize(item["provider"])] = str(item.get("name") or item["provider"])

    records: dict[tuple[str, str], dict[str, Any]] = {}
    for source in (generated, overrides):
        for item in source.get("models", []):
            if not isinstance(item, dict) or not item.get("provider") or not item.get("model"):
                continue
            key = (_normalize(str(item["provider"])), str(item["model"]))
            merged = {**records.get(key, {}), **item, "provider": key[0], "model": key[1]}
            records[key] = merged

    return ProviderRegistry(
        models={key: ModelCapabilities.from_mapping(value) for key, value in records.items()},
        organizations=organizations,
        generated_at=(
            generated.get("generated_at")
            if isinstance(generated.get("generated_at"), str)
            else None
        ),
        sources=tuple(str(item) for item in generated.get("sources", []) if item),
    )


def _load_package_json(filename: str) -> dict[str, Any]:
    package = resources.files("eslams.providers").joinpath("data").joinpath(filename)
    return cast(dict[str, Any], json.loads(package.read_text(encoding="utf-8")))


def _normalize(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized, normalized)
