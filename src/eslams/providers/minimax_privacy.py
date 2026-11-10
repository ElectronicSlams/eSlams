"""Credential exclusion for MiniMax's provider-controlled text and identifiers."""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote, quote_plus

_JSON_ESCAPES = re.compile(r'(?:\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))+')


def _credential_variants(primary: str | None = None) -> tuple[str, ...]:
    # Include secondary provider/gateway credentials, including a primary key
    # supplied under a custom environment name. Never log these values.
    values = {primary} if primary else set()
    for name, value in os.environ.items():
        if name.upper() in {
            "ESLAMS_ARENA_SESSION_KEY_ID", "ESLAMS_RUNNER_REQUEST_KEY_ID",
            "ESLAMS_RUNNER_REQUEST_KEY_ID_PREVIOUS", "RUNNER_ARTIFACT_SIGNING_KEY_ID",
        }:
            continue  # Public credential identifiers are not credential values.
        if re.search(r"(?:^|_)(?:KEY|APIKEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?|AUTHORIZATION)"
                     r"(?:_|$)", name.upper()) and value.strip():
            values.add(value.strip())
    variants: set[str] = set()
    for value in values:
        variants.update((value, json.dumps(value)[1:-1],
                         json.dumps(value, ensure_ascii=False)[1:-1],
                         quote(value, safe=""), quote_plus(value, safe="")))
    return tuple(sorted(variants - {""}, key=len, reverse=True))


def _contains_credential_text(value: str, secrets: tuple[str, ...]) -> bool:
    if any(secret in value for secret in secrets):
        return True

    def decode(match: re.Match[str]) -> str:
        # Comparison only: the original action is never rewritten. A run of
        # escapes is decoded together so JSON surrogate pairs stay intact.
        return str(json.loads('"' + match.group(0) + '"'))

    decoded = _JSON_ESCAPES.sub(decode, value)
    return any(secret in decoded for secret in secrets)


def _action_contains_credential(text: str, secrets: tuple[str, ...]) -> bool:
    from eslams.model_actions import extract_json

    if _contains_credential_text(text, secrets):
        return True
    # Match Core's fenced/prose JSON recovery, then inspect every decoded key
    # and string value. Do not validate, choose, coerce or repair an action here.
    pending = [extract_json(text)]
    while pending:
        value = pending.pop()
        if isinstance(value, str) and _contains_credential_text(value, secrets):
            return True
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def _scrub_text(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    if _contains_credential_text(value, secrets):
        # JSON-escaped diagnostic text can contain a key without its literal
        # bytes. Do not return the encoded form or decode private error prose.
        return "MiniMax diagnostic contained configured credential material"
    return value


def _scrub_receipt(value: Any, secrets: tuple[str, ...]) -> Any:
    # Core constructs this closed receipt shape itself. Only its identifier
    # fields carry untrusted provider strings; keep trusted protocol labels and
    # enum values intact even if an unrelated short secret matches their text.
    if isinstance(value, list):
        return [_scrub_receipt(item, secrets) for item in value]
    if isinstance(value, dict):
        result = {key: _scrub_receipt(item, secrets) for key, item in value.items()}
        for key in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id"):
            if isinstance(result.get(key), str) and (
                _scrub_text(result[key], secrets) != result[key]
                or "[REDACTED]" in result[key]
            ):
                result[key] = None
        if "locked_model_id" in result and result["locked_model_id"] is None:
            result["model_identity_source"] = None
        return result
    return value
