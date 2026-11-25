"""Keep credential-bearing or ambiguous action text out of provider results."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any
from urllib.parse import quote, quote_plus

from eslams.model_actions import extract_json


def credential_encodings(credentials: Collection[str]) -> set[str]:
    return {
        variant
        for value in credentials if value
        for variant in (value, quote(value, safe=""), quote_plus(value, safe=""))
    }


def contains_credential(value: Any, credentials: Collection[str]) -> bool:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(secret in item for secret in credentials):
                return True
        elif isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def _validate_nesting(value: Any) -> None:
    pending = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, (dict, list)):
            if depth > 64:
                raise ValueError("action JSON exceeds inspection limits")
            children = item.values() if isinstance(item, dict) else item
            pending.extend((child, depth + 1) for child in children)


def validate_provider_action_text(
    text: str, credentials: Collection[str], receipt: dict[str, Any],
    *, provider: str, model: str,
) -> None:
    from eslams.agents import ProviderCallError

    try:
        decoded = extract_json(text, reject_duplicate_fields=True)
        _validate_nesting(decoded)
        credential_found = (
            contains_credential(text, credentials) or contains_credential(decoded, credentials)
        )
    except (ValueError, RecursionError, OverflowError):
        detail = "Provider action JSON could not be safely inspected"
    else:
        if not credential_found:
            return
        detail = "Provider action text contains credential material"
    raise ProviderCallError(
        detail, error_kind="provider_response_schema_mismatch", provider=provider, model=model,
        receipt={**receipt, "outcome": "provider_response_schema_mismatch"},
    )
