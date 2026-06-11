"""Canonical JSON hashing utilities used by states, traces, and artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    """Return deterministic JSON for hashing and signing."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def state_hash(state: Any) -> str:
    """Return the canonical Core state hash for an ArenaState or state snapshot."""

    if hasattr(state, "state_hash"):
        value = state.state_hash
        if isinstance(value, str):
            return value
    if isinstance(state, Mapping):
        snapshot = dict(state)
        snapshot.pop("state_hash", None)
        return sha256_json(snapshot)
    return sha256_json(state)


def action_hash(action: Any) -> str:
    """Return a deterministic hash for a Core action payload."""

    return sha256_json({"action": action})


def legal_action_hash(actions: list[Any]) -> str:
    """Return a deterministic hash for an ordered legal-action set."""

    return sha256_json({"legal_actions": actions})


def observation_hash(observation: Any) -> str:
    """Return a deterministic hash for an observation view."""

    return sha256_json({"observation": observation})


def prompt_hash(prompt_package: Any) -> str:
    """Return a deterministic hash for a generated prompt package."""

    return sha256_json({"prompt_package": prompt_package})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def without_none(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}
