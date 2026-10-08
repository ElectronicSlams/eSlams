"""Normalize environment credentials without revealing their contents."""

from __future__ import annotations

import os


def provider_key(environment_name: str) -> str | None:
    value = os.getenv(environment_name, "").strip()
    if not value:
        return None
    if any(not 33 <= ord(character) <= 126 for character in value):
        raise ValueError(
            f"API key environment variable {environment_name} must contain printable ASCII "
            "without internal whitespace"
        )
    return value
