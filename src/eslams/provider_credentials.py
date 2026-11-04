"""Normalize environment credentials without revealing their contents."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE_CREDENTIALS: ContextVar[tuple[str, ...]] = ContextVar("provider_credentials", default=())


@contextmanager
def credential_redaction(*values: str) -> Iterator[None]:
    """Keep exact credential values local to one provider invocation."""
    credentials = tuple(sorted({*_ACTIVE_CREDENTIALS.get(), *filter(None, values)},
                               key=len, reverse=True))
    token = _ACTIVE_CREDENTIALS.set(credentials)
    try:
        yield
    finally:
        _ACTIVE_CREDENTIALS.reset(token)


def contains_credentials(value: str) -> bool:
    return any(credential in value for credential in _ACTIVE_CREDENTIALS.get())


def redact_credentials(value: str) -> str:
    for credential in _ACTIVE_CREDENTIALS.get():
        value = value.replace(credential, "[REDACTED]")
    return value


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
