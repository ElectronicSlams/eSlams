#!/usr/bin/env python3
"""Render the checked-in provider/model registry inventory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eslams.providers.registry import (  # noqa: E402
    FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS,
    PLATFORM_API_DISCOVERED_PROVIDER_KEYS,
    REQUESTED_PROVIDER_ORGANIZATIONS,
    load_provider_registry,
)


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def render() -> str:
    registry = load_provider_registry()
    provider_names = dict(REQUESTED_PROVIDER_ORGANIZATIONS)
    rows = [
        record
        for record in registry.list_models()
        if record.provider in provider_names and record.available_from_api is not False
    ]
    api_verified = sum(record.available_from_api is True for record in rows)
    models_by_provider = {
        provider: [record for record in rows if record.provider == provider]
        for provider in provider_names
    }
    original_count = (
        len(provider_names)
        - len(FROZEN_OPENROUTER_DISCOVERED_PROVIDER_KEYS)
        - len(PLATFORM_API_DISCOVERED_PROVIDER_KEYS)
    )
    source_names = ", ".join(registry.sources) or "none recorded"
    lines = [
        "# Catalogued provider models (registry snapshot)",
        "",
        f"Core tracks **{len(provider_names)} canonical provider/author namespaces**. "
        f"The original {original_count} curated organizations are joined by Cursor from a "
        "platform API-discovered model row and 20 author namespaces from the release-pinned "
        "OpenRouter text-model snapshot.",
        "",
        "This file describes source-backed catalog identities, not direct-adapter or account "
        "availability. A model row means an upstream registry source or checked-in override "
        "documented the identity. Only `available_from_api=true` is an API verification signal, "
        "and public eSlams availability is controlled separately by the deployed platform catalog.",
        "",
        "Generated with `python scripts/render_provider_registry_docs.py` from "
        "`models.generated.json`, `overrides.json`, and `REQUESTED_PROVIDER_ORGANIZATIONS`.",
        "",
        f"Registry snapshot: `{registry.generated_at or 'unknown'}`",
        "",
        f"Sources: {source_names}",
        "",
        f"Catalogued rows: **{len(rows)}** ({api_verified} with `available_from_api=true`)",
        "",
        "Rows marked `available_from_api=false` are excluded. Legacy aliases normalize to the "
        "same canonical provider keys used by the public `/models/...` routes.",
        "",
        "| Provider | Model |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| {markdown_cell(provider_names[record.provider])} | `{record.model}` |"
        for record in rows
        if record.provider in provider_names
    )
    missing = [
        (provider, name)
        for provider, name in REQUESTED_PROVIDER_ORGANIZATIONS
        if not models_by_provider[provider]
    ]
    lines.extend(
        [
            "",
            "## Providers with no model rows in this Core registry snapshot",
            "",
            "These are still valid public catalog identities. Their current public pages and "
            "model inventories come from the platform's frozen OpenRouter/Bedrock reconciliation "
            "or historical catalog, not from this older Core capability snapshot.",
            "",
            "| Provider | Provider key |",
            "| --- | --- |",
        ]
    )
    lines.extend(f"| {markdown_cell(name)} | `{provider}` |" for provider, name in missing)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    (ROOT / "docs" / "REGISTRY_AVAILABLE_MODELS.md").write_text(render(), encoding="utf-8")
