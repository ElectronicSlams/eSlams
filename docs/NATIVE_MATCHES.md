# Opt-in native multi-unit matches

A native match carries one engine, event journal and final result across consecutive units. Three units form one block. The shipped keyless route supports 22 arenas and one to twenty blocks; ordinary `eslams run`, its v1 artifacts and protocol, and historical game rules are unchanged.

```sh
eslams native run --arena rock-paper-scissors --blocks 2 --run-id local-six --out local-six.eslams
eslams native verify local-six.eslams
eslams native replay local-six.eslams --out local-six.html
```

The CLI uses first-legal local policies and makes no service or provider calls. It is a reproducible integration path, not a claim that Platform matches, provider agents, official evals, or the HF historical archive use this runtime. `--memoryless` restricts the public journal supplied to the policy to the current unit. Fixed positions are default; rotation is supported only by the opted-in matrix and Poker profiles.

## History and scoring

The supported Python entry point `eslams.native_runner.run_local_native` accepts local, trusted Python policy callbacks, one per stable seat. Each receives its game-specific, version-pinned current observation (`current_game_json`), legal actions, a safe public journal, and its own accepted observations/actions in chronological order (`own_decision_history`). No other seat's decision history is passed. Each unit's shared journal contains ordered, typed actions and table facts that are visible at that point in the game. It deliberately excludes unrevealed card and tile draws, concealed hands, individual hints, dice, reserves, and raw state. Cribbage shows discard counts without naming the crib cards; Goofspiel reveals bids as a pair after both are committed; Blackjack reveals the dealer hand only at settlement. Matrix actions are sealed until settlement. Poker includes only verified public table facts and the active seat's own cards and completed hands. Hanabi shows the legally visible partner hand, never its own hidden cards. With `history=False`, the callback is given only current-unit facts. The runner does not isolate untrusted Python code or erase memory independently retained by a callback.

For hidden-information games, custom policies require separately held private match authority (or the Auction-specific authority below). The public `seed` option is for reproducible scripted runs; it is insufficient for deriving competitive private deals. No private seed, authority, current private facts, or seat-history hash is included in the public archive.

```python
from eslams.native_runner import NativeProfile, run_local_native

def policy(view):
    if view.round_index > 3 and view.own_decision_history:
        return "defect"
    return "cooperate"

result = run_local_native(
    NativeProfile("prisoners-dilemma", blocks=2),
    "local-adaptation",
    seat_policies={"player_1": policy, "player_2": policy},
    policy_ids={"player_1": "example-policy-v1", "player_2": "example-policy-v1"},
)
```
 An invalid or interrupted match has a diagnostic journal and no final score. Do not combine scores across score policies or treat a privacy-redacted final score as zero.

Sealed-bid Auction has a separate `2.0.0-native` rules adapter, outside the legacy score comparison. Its per-seat values have the same uniform 6–10 marginal as the legacy game, but private independent domain draws. Use `--auction-authority-file` with an operator-controlled, owner-only local file containing 32–128 private bytes. Do not place the file in source control, command output, or a shared artifact. Only the active seat receives its own current valuation. Public artifacts omit both bids, allocations, settlement utilities and aggregate score. First-price allocation and signed utilities are available only to the trusted in-process controller.

## Artifact and custody

The public archive uses kind `eslams.native-match.public.v1`, a closed manifest and a canonical sequential JSONL event journal. The explicit `native verify` command checks layout, digest and permitted sequence, and cannot prove redacted private mechanics or establish publisher authenticity. No legacy validator auto-detects this format. The offline HTML shows the public journal, not hidden boards or inputs.

Python can capture an authenticated private continuation at a settled boundary and restore it with the same profile, run, rule identity, history mode, stable policy identities and custody material. Custody objects contain previous raw actions and must not be serialized into a public archive. A checkpoint is not an inference replay or authorization to repeat a provider action. The trusted local callback and keyless CLI paths are available here; there is no provider, service, or Platform enablement.
