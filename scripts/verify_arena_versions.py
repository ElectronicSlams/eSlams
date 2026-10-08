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

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.hashing import canonical_json


def fingerprints() -> dict[str, dict[str, str]]:
    rows = {}
    for name in registry.list():
        arena = registry.create(name)
        digest = hashlib.sha256()
        for seed in range(4):
            for policy in ("first-legal", "random"):
                rng = random.Random(seed)
                state = arena.initial_state(seed)
                digest.update(canonical_json([seed, policy, state.to_dict()]).encode("utf-8"))
                for _ in range(512):
                    if state.terminal:
                        break
                    legal = arena.legal_actions_for(state, state.active_player)
                    if not legal:
                        raise ValueError(f"{name}: nonterminal state has no legal actions")
                    action = legal[0] if policy == "first-legal" else rng.choice(legal)
                    state = arena.apply_action(state, state.active_player, action)
                    digest.update(canonical_json([legal, action, state.to_dict()]).encode("utf-8"))
                digest.update(canonical_json(arena.score(state)).encode("utf-8"))
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
            handle.write(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"Wrote fingerprints for {len(current)} arenas")
        return
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
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
