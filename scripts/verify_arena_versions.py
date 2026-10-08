"""Detect deterministic arena behavior changes without a version bump.

Fingerprints cover legal-action order, canonical states, terminal outcomes and
scores for four seeds under first-legal and seeded-random policies. A bounded
nonterminal trajectory remains diagnostic; this does not establish game fidelity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.hashing import canonical_json
from eslams.state import ArenaState

FINGERPRINT_FORMAT = "eslams.arena-behavior-fingerprints.v1"
FLOAT_DECIMAL_PLACES = 10


def normalize_fingerprint(value: Any) -> Any:
    """Normalize libm's last-bit drift for this diagnostic, never engine state."""
    if isinstance(value, float):
        normalized = round(value, FLOAT_DECIMAL_PLACES)
        return 0.0 if normalized == 0.0 else normalized
    elif isinstance(value, dict):
        return {key: normalize_fingerprint(item) for key, item in value.items()}
    elif isinstance(value, (list, tuple)):
        return [normalize_fingerprint(item) for item in value]
    return value


def fingerprint_json(value: Any) -> str:
    return canonical_json(normalize_fingerprint(value))


def fingerprint_state(state: ArenaState) -> dict[str, Any]:
    value = state.to_dict()
    # The derived raw hash preserves libm differences; hash the normalized
    # source fields here instead. Runtime state hashes remain exact.
    value.pop("state_hash")
    return value


def fingerprints() -> dict[str, dict[str, str]]:
    rows = {}
    for name in registry.list():
        arena = registry.create(name)
        digest = hashlib.sha256()
        for seed in range(4):
            for policy in ("first-legal", "random"):
                rng = random.Random(seed)
                state = arena.initial_state(seed)
                digest.update(
                    fingerprint_json([seed, policy, fingerprint_state(state)]).encode("utf-8")
                )
                for _ in range(512):
                    if state.terminal:
                        break
                    legal = arena.legal_actions_for(state, state.active_player)
                    if not legal:
                        raise ValueError(f"{name}: nonterminal state has no legal actions")
                    action = legal[0] if policy == "first-legal" else rng.choice(legal)
                    state = arena.apply_action(state, state.active_player, action)
                    digest.update(
                        fingerprint_json([legal, action, fingerprint_state(state)]).encode("utf-8")
                    )
                digest.update(fingerprint_json(arena.score(state)).encode("utf-8"))
        rows[name] = {"version": arena.version, "sha256": digest.hexdigest()}
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("fixtures/arena_versions.json"))
    parser.add_argument("--write", type=Path, help="Write reviewed fingerprints to a new file.")
    args = parser.parse_args()
    current = fingerprints()
    if args.write is not None:
        with args.write.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "format": FINGERPRINT_FORMAT,
                        "float_decimal_places": FLOAT_DECIMAL_PLACES,
                        "arenas": current,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        print(f"Wrote fingerprints for {len(current)} arenas")
        return
    document = json.loads(args.baseline.read_text(encoding="utf-8"))
    if (document["format"], document["float_decimal_places"]) != (
        FINGERPRINT_FORMAT,
        FLOAT_DECIMAL_PLACES,
    ):
        raise ValueError("fingerprint format changed; review the diagnostic baseline")
    baseline = document["arenas"]
    if current.keys() != baseline.keys():
        raise ValueError("arena roster changed; review and record its version fingerprints")
    for name, row in current.items():
        before = baseline[name]
        if row["version"] == before["version"] and row["sha256"] != before["sha256"]:
            raise ValueError(f"{name}: behavior changed without bumping arena version")
        if row["version"] != before["version"]:
            raise ValueError(f"{name}: version changed; review and update its fingerprint baseline")
    print(f"Verified versioned behavior fingerprints for {len(current)} arenas")


if __name__ == "__main__":
    main()
