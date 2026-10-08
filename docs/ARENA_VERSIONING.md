# Arena behavior versions

Rules, legal-action order, state transitions, terminal outcomes and scoring
are versioned behavior. Change an arena version whenever any of these changes,
even if the change fixes a bug. Record the producer Core version and commit
together with arena version when comparing historical results.

## Historical 0.5.1 ambiguity

Core 0.5.1 changed card rank/deck ordering, Backgammon bear-off die consumption,
Chess repetition handling, multiplayer poker, Blackjack, Bargaining, Crazy
Eights and Prisoner's Dilemma scoring without changing all affected arena
versions. The tagged `v0.5.0...v0.5.1` diff confirms behavior changes. Repeated
version strings across those releases do **not** identify identical rules.

Existing historical artifacts retain their original bytes and declared
versions. Inspect them using an isolated producer installation and its exact
commit. Do not mix their results based on arena version alone or validate them
against today's rules as though the producer were the same. Current strict
validation rejects replay or terminal inconsistencies; it does not repair the
historical version collision.

The consolidation assigns distinct current versions to the remaining affected
1.0.0 arenas, while retaining the versions already advanced for other repairs:

| Arena | Proposed current version |
| --- | --- |
| Backgammon | 1.1.0 |
| Bargaining | 1.0.1 |
| Blackjack | 1.0.1 |
| Crazy Eights | 1.0.1 |
| Cribbage | 1.1.0 |
| Euchre | 1.0.1 |
| Gin Rummy | 1.0.1 |
| Hearts | 1.0.1 |
| Leduc Hold'em | 1.0.1 |
| Limit Texas Hold'em | 1.0.1 |
| No-Limit Texas Hold'em | 1.0.1 |
| Shedding Card Game | 1.0.1 |
| Spades | 1.0.1 |
| Chess | 1.2.0 |
| Prisoner's Dilemma | 1.0.1 |

These are unreleased source versions. The already published 0.6.1 wheel does
not acquire them.

## Behavior guard

`python scripts/verify_arena_versions.py` checks reviewed fingerprints in
`fixtures/arena_versions.json` on every native CI interpreter/OS. They include
canonical states, legal actions and ordering, selected actions, outcomes and
scores for four seeds under first-legal and seeded-random policies. Each path
is bounded at 512 actions; a nonterminal path is diagnostic. This is a drift
guard, not exhaustive proof of game correctness or full-fidelity rules.

The versioned diagnostic format rounds floating values to ten decimal places
and hashes source state fields instead of their redundant raw `state_hash`.
Platform math libraries can differ in the final bits of trigonometric results
(observed in Mountain Car), even when visible state and behavior agree. Integer
actions, order and terminal outcomes stay exact. This normalization affects
only this diagnostic; runtime state hashes, replay validation and the separate
native byte-parity gate remain exact. It cannot detect numeric changes below
its declared precision.

For an intentional behavior change, bump the arena version, inspect the
changed trajectories and write candidate fingerprints with
`--write <new-file>`. Review the diff before replacing the baseline. Never
update a hash at the same version merely to silence a failure. Add targeted
rules regressions when the trajectories alone do not exercise the bug.
