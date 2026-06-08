"""No-secret safety scanning for public replay and publication outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DENIED_KEY_RE = re.compile(
    r"(^|[_.-])"
    r"(private|provider|prompt|response|token|request|header|secret|api[-_]?key|debug|raw)"
    r"($|[_.-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SafetyIssue:
    path: str
    key: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "key": self.key, "reason": self.reason}


def scan_public_payload(payload: Any, *, root: str = "$") -> list[SafetyIssue]:
    """Recursively reject keys that can carry private/provider internals."""

    issues: list[SafetyIssue] = []
    _scan(payload, root=root, issues=issues)
    return issues


def assert_public_payload_safe(payload: Any, *, root: str = "$") -> None:
    issues = scan_public_payload(payload, root=root)
    if issues:
        issue = issues[0]
        raise ValueError(f"unsafe public payload key at {issue.path}: {issue.key}")


def _scan(payload: Any, *, root: str, issues: list[SafetyIssue]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            path = f"{root}.{key_text}"
            if DENIED_KEY_RE.search(key_text):
                issues.append(
                    SafetyIssue(
                        path=path,
                        key=key_text,
                        reason="public payload keys must not expose private/provider/debug data",
                    )
                )
            _scan(value, root=path, issues=issues)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _scan(value, root=f"{root}[{index}]", issues=issues)
