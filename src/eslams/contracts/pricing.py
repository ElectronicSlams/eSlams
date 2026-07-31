"""Immutable references to reviewed pricing or provider-native cost contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from eslams.contracts.versions import PRICE_CARD_REFERENCE_SCHEMA_VERSION

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class PriceCardReference:
    rate_card_id: str
    rate_card_hash: str
    provider: str
    model: str
    currency: str
    source_uri: str
    complete: bool
    effective_at: str | None = None
    retrieved_at: str | None = None
    schema_version: str = PRICE_CARD_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.rate_card_id:
            raise ValueError("rate_card_id is required")
        if not _SHA256_PATTERN.fullmatch(self.rate_card_hash):
            raise ValueError("rate_card_hash must be sha256:<64 lowercase hex characters>")
        if self.currency != "USD":
            raise ValueError("only USD price-card references are supported")
        if not self.provider or not self.model or not self.source_uri:
            raise ValueError("provider, model, and source_uri are required")
        if not self.complete:
            raise ValueError("price-card reference must be complete")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "rateCardId": self.rate_card_id,
            "rateCardHash": self.rate_card_hash,
            "provider": self.provider,
            "model": self.model,
            "currency": self.currency,
            "sourceUri": self.source_uri,
            "effectiveAt": self.effective_at,
            "retrievedAt": self.retrieved_at,
            "complete": self.complete,
        }


def validate_price_card_reference(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        PriceCardReference(
            rate_card_id=str(value.get("rateCardId") or ""),
            rate_card_hash=str(value.get("rateCardHash") or ""),
            provider=str(value.get("provider") or ""),
            model=str(value.get("model") or ""),
            currency=str(value.get("currency") or ""),
            source_uri=str(value.get("sourceUri") or ""),
            effective_at=(
                str(value["effectiveAt"]) if value.get("effectiveAt") is not None else None
            ),
            retrieved_at=(
                str(value["retrievedAt"]) if value.get("retrievedAt") is not None else None
            ),
            complete=value.get("complete") is True,
        )
    except (TypeError, ValueError):
        return False
    return value.get("complete") is True


def no_secret_example() -> dict[str, Any]:
    return PriceCardReference(
        rate_card_id="example-provider-cost-contract:v1",
        rate_card_hash="sha256:" + "0" * 64,
        provider="mock",
        model="mock-legal-action",
        currency="USD",
        source_uri="https://example.invalid/pricing",
        effective_at=None,
        retrieved_at=None,
        complete=True,
    ).to_dict()
