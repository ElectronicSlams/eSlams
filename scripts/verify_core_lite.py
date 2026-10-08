"""Generate Python authority fixtures and compare the compiled TypeScript runtime.

Run with ``python scripts/verify_core_lite.py /path/to/core-lite/index.js`` after
compiling Core-lite. No npm runtime dependency, network, keys, or model calls.
"""

from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.arena_transport import deserialize_state, serialize_state
from eslams.core_contract import core_step


def response(game: str, state: dict[str, Any], action: Any) -> dict[str, Any]:
    return core_step({
        "coreContractVersion": "2.0", "gameId": game, "rulesetVersion": "standard",
        "state": state, "action": action, "requestId": "core-lite",
        "includeLegalActions": "ids",
    })


def fixtures() -> dict[str, Any]:
    initial: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    outcomes: dict[str, set[Any]] = {}
    shapes = [lambda a: a, str, lambda a: {"actionId": str(a)},
              lambda a: {"action_id": str(a)}, lambda a: {"token": str(a)},
              lambda a: {"compact": str(a)}, lambda a: {"payload": a}]
    for game in ("tic-tac-toe", "connect-four"):
        arena = registry.create(game)
        outcomes[game] = set()
        for seed in (0, 1, -1, 2, 7, 42, 12345, 2**31, 2**40, 2**53 - 1, -(2**53 - 1)):
            state = arena.initial_state(seed)
            initial.append({"game": game, "seed": str(seed), "state": serialize_state(state)})
        # Deterministic games, including both winners and a draw in each arena.
        for trial in range(160):
            rng = random.Random(trial)
            seed = (0, -1, 1, 2**40)[trial % 4]
            state = arena.initial_state(seed)
            while not state.terminal:
                legal = arena.legal_actions_for(state, state.active_player)
                if trial >= 40:
                    nonwinning = [a for a in legal if not arena.apply_action(
                        state, state.active_player, a).outcome]
                    legal = nonwinning or legal
                raw = rng.choice(legal)
                action = shapes[len(steps) % len(shapes)](raw)
                snapshot = serialize_state(state)
                expected = response(game, snapshot, action)
                assert expected["ok"]
                steps.append({"game": game, "state": snapshot, "action": action,
                              "expected": expected})
                state = deserialize_state(expected["state"])
            outcomes[game].add(state.outcome["winner"])
            if trial >= 40 and outcomes[game] == {None, "player_1", "player_2"}:
                break
        assert outcomes[game] == {None, "player_1", "player_2"}, outcomes
        snapshot = serialize_state(state)
        steps.append({"game": game, "state": snapshot, "action": 0,
                      "expected": response(game, snapshot, 0)})
        snapshot = serialize_state(arena.initial_state(0))
        for action in (True, False, None, -1, 100, 0.5, "99", {"actionId": "99"}, {}):
            steps.append({"game": game, "state": snapshot, "action": action,
                          "expected": response(game, snapshot, action)})
        # Additional un-hashed transport diagnostics must not change the state hash.
        decorated = {**snapshot, "rehydration_diagnostics": {"status": "verified"}}
        steps.append({"game": game, "state": decorated, "action": "0",
                      "expected": response(game, decorated, "0")})
        unicode_state = copy.deepcopy(snapshot)
        unicode_state["metadata"].update({"note": "棋盤 🎮 café", "\uffff": "one", "😀": "two"})
        unicode_state.pop("state_hash")
        unicode_state = serialize_state(deserialize_state(unicode_state))
        steps.append({"game": game, "state": unicode_state, "action": 0,
                      "expected": response(game, unicode_state, 0)})
    return {"initial": initial, "steps": steps}


NODE_CHECK = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
const runtime = await import(pathToFileURL(process.argv[2]));
const { createInitialState, applyAction, stateHash } = runtime;
const fixtures = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
for (const row of fixtures.initial) {
  assert.deepEqual(createInitialState(row.game, 'standard', row.seed), row.state);
}
function deterministic(response) {
  const value = structuredClone(response);
  delete value.timingsMs;
  if (value.replayEvent) {
    delete value.replayEvent.timestamp;
    delete value.replayEvent.timingsMs;
  }
  if (value.error) delete value.error.message;
  return value;
}
for (const [index, row] of fixtures.steps.entries()) {
  const original = structuredClone(row.state);
  const actual = applyAction(row.state, row.action);
  assert.deepEqual(deterministic(actual), deterministic(row.expected), `step ${index}`);
  assert.deepEqual(row.state, original, 'applyAction mutated its input');
}
for (const seed of ['', 'abc', '1e3', '1.9', '1x', ' ', '9007199254740992', '-9007199254740992']) {
  assert.throws(() => createInitialState('tic-tac-toe', 'standard', seed));
}
assert.throws(() => createInitialState('unknown'));
assert.throws(() => createInitialState('tic-tac-toe', 'unsupported'));
for (const game of ['tic-tac-toe', 'connect-four']) {
  const fresh = createInitialState(game, 'standard', '0');
  const malformed = [null, {}, {...fresh, public_state: undefined},
    {...fresh, public_state: {...fresh.public_state, board: 'garbage'}},
    {...fresh, public_state: {...fresh.public_state, board: []}},
    {...fresh, legal_actions_by_player: null}, {...fresh, metadata: {seed: NaN}},
    {...fresh, state_hash: 'sha256:stale'}];
  for (const state of malformed) {
    const result = applyAction(state, 0);
    assert.equal(result.ok, false);
    assert.equal(result.error.recoverable, false);
    assert.equal(result.state, null);
  }
  if (game === 'connect-four') {
    const short = structuredClone(fresh);
    short.public_state.board.pop();
    short.state_hash = stateHash(short);
    assert.equal(applyAction(short, 0).ok, false);
  }
}
console.log(JSON.stringify({initial: fixtures.initial.length, steps: fixtures.steps.length,
  seeds: 'zero, negative, large safe integers', outcomes: 'both winners and draw',
  parity: 'all deterministic response fields', malformed: 'contained'}));
"""


def main() -> None:
    runtime = Path(sys.argv[1]).resolve()
    assert runtime.is_file(), runtime
    with tempfile.TemporaryDirectory(prefix="eslams-core-lite-") as folder:
        root = Path(folder)
        fixture = root / "fixtures.json"
        fixture.write_text(json.dumps(fixtures(), ensure_ascii=False), encoding="utf-8")
        check = root / "check.mjs"
        check.write_text(NODE_CHECK, encoding="utf-8")
        subprocess.run(["node", str(check), str(runtime), str(fixture)], check=True)


if __name__ == "__main__":
    main()
