"""Stable machine keys and public labels for policy-driving concepts."""

from __future__ import annotations

import re
from typing import Any


def policy_key(value: str | None, *, fallback: str) -> str:
    source = value or fallback
    source = source.split(":", 1)[0]
    key = re.sub(r"[^a-z0-9]+", "_", source.lower()).strip("_")
    return key or fallback


def policy_label(value: str | None, *, fallback: str) -> str:
    source = value or fallback
    return source.replace("_", " ").replace("-", " ").title()


def keyed_label(
    *,
    key_name: str,
    label_name: str,
    value: str | None,
    fallback: str,
) -> dict[str, Any]:
    return {
        key_name: policy_key(value, fallback=fallback),
        label_name: value or policy_label(fallback, fallback=fallback),
    }


def artifact_profile_label(profile: str) -> str:
    labels = {
        "runner_bundle": "Runner Bundle",
        "official_bundle": "Official Bundle",
        "battlefield_bundle": "Battlefield Bundle",
        "public_replay_package": "Public Replay Package",
    }
    return labels.get(profile, policy_label(profile, fallback="unknown"))


def publication_kind_label(kind: str) -> str:
    labels = {
        "official-proof": "Official Proof",
        "battlefield-sample": "Battlefield Sample",
        "uploaded-replay": "Uploaded Replay",
    }
    return labels.get(kind, policy_label(kind, fallback="unknown"))
