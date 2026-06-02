# Arenas

An arena is more than a game engine. It defines:

- rules and state transitions
- canonical public/private state
- legal actions
- observations
- illegal action policy
- timeout policy
- scoring
- replay and broadcast hints
- verification requirements

Built-in public smoke arenas:

- `checkers`
- `chess`
- `connect-four`
- `gomoku`
- `hex`
- `mancala`
- `othello`
- `pentago`
- `prisoners-dilemma`
- `rock-paper-scissors`
- `tic-tac-toe`
- `ultimate-tic-tac-toe`

The public catalogue is intentionally adapter-based. eSlams owns the canonical state, trace, replay, and scoring contract even when the game logic is powered by an external library.
