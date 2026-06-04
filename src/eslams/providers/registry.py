"""Model/capability registry for provider-backed game agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from eslams.providers.capabilities import ModelCapabilities

REQUESTED_PROVIDER_ORGANIZATIONS: tuple[tuple[str, str], ...] = (
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("google", "Google / DeepMind"),
    ("meta", "Meta AI"),
    ("xai", "xAI"),
    ("mistral", "Mistral AI"),
    ("deepseek", "DeepSeek"),
    ("qwen", "Alibaba / Qwen"),
    ("baidu", "Baidu"),
    ("tencent", "Tencent"),
    ("bytedance", "ByteDance / Seed"),
    ("huawei", "Huawei"),
    ("zhipu", "Zhipu AI / Z.ai"),
    ("moonshot", "Moonshot AI"),
    ("minimax", "MiniMax"),
    ("01-ai", "01.AI"),
    ("stepfun", "StepFun"),
    ("baichuan", "Baichuan AI"),
    ("sensetime", "SenseTime"),
    ("iflytek", "iFlytek"),
    ("kuaishou", "Kuaishou"),
    ("openbmb", "OpenBMB / ModelBest"),
    ("shanghai-ai-lab", "Shanghai AI Lab"),
    ("xverse", "XVERSE AI"),
    ("xiaomi", "Xiaomi"),
    ("meituan", "Meituan"),
    ("ant-group", "Ant Group"),
    ("apple", "Apple"),
    ("amazon", "Amazon / AWS"),
    ("microsoft", "Microsoft"),
    ("nvidia", "NVIDIA"),
    ("ibm", "IBM"),
    ("cohere", "Cohere"),
    ("ai21", "AI21 Labs"),
    ("reka", "Reka AI"),
    ("writer", "Writer"),
    ("inflection", "Inflection AI"),
    ("perplexity", "Perplexity"),
    ("liquid", "Liquid AI"),
    ("databricks", "Databricks / MosaicML"),
    ("snowflake", "Snowflake"),
    ("salesforce", "Salesforce AI Research"),
    ("contextual", "Contextual AI"),
    ("essential", "Essential AI"),
    ("adept", "Adept AI"),
    ("character", "Character.AI"),
    ("nous", "Nous Research"),
    ("arcee", "Arcee AI"),
    ("tii", "Technology Innovation Institute, UAE"),
    ("core42", "Core42 / Inception / G42"),
    ("ai71", "AI71"),
    ("sdaia", "SDAIA / IBM / Saudi ecosystem"),
    ("naver", "Naver"),
    ("lg", "LG AI Research"),
    ("samsung", "Samsung Research"),
    ("sk-telecom", "SK Telecom"),
    ("kakao", "Kakao"),
    ("upstage", "Upstage"),
    ("sarvam", "Sarvam AI"),
    ("krutrim", "Krutrim"),
    ("aleph-alpha", "Aleph Alpha"),
    ("lighton", "LightOn"),
    ("yandex", "Yandex"),
    ("sber", "Sber"),
    ("ai2", "Allen Institute for AI, AI2"),
    ("eleutherai", "EleutherAI"),
    ("bigscience", "BigScience / Hugging Face community"),
    ("bigcode", "BigCode / ServiceNow / Hugging Face"),
    ("baai", "BAAI, Beijing Academy of AI"),
)

PROVIDER_ALIASES = {
    "gemini": "google",
    "google-deepmind": "google",
    "vertex-ai": "google",
    "qwen": "qwen",
    "alibaba": "qwen",
    "alibaba-cn": "qwen",
    "dashscope": "qwen",
    "meta-llama": "meta",
    "moonshotai": "moonshot",
    "moonshotai-cn": "moonshot",
    "tencent-coding-plan": "tencent",
    "tencent-tokenhub": "tencent",
    "volcengine": "bytedance",
    "zhipuai": "zhipu",
    "zhipuai-coding-plan": "zhipu",
    "bailing": "ant-group",
    "inception": "core42",
    "gigachat": "sber",
    "aws": "amazon",
    "bedrock": "amazon",
    "azure": "microsoft",
    "azure-ai": "microsoft",
    "watsonx": "ibm",
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
    package = resources.files("eslams.providers").joinpath("data", filename)
    return json.loads(package.read_text(encoding="utf-8"))


def _normalize(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    return PROVIDER_ALIASES.get(normalized, normalized)
