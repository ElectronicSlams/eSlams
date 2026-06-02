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

- `bargaining`
- `blackjack`
- `checkers`
- `chess`
- `connect-four`
- `first-price-sealed-bid-auction`
- `gomoku`
- `goofspiel`
- `hex`
- `liars-dice`
- `mancala`
- `negotiation`
- `othello`
- `pentago`
- `prisoners-dilemma`
- `rock-paper-scissors`
- `tic-tac-toe`
- `ultimate-tic-tac-toe`

The public catalogue is intentionally adapter-based. eSlams owns the canonical state, trace, replay, and scoring contract even when the game logic is powered by an external library.
