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

## Chess Observation Contract

The chess arena is powered by `python-chess` and exposes rule-derived context
without engine evaluation:

- FEN, side to move, active player, fullmove number, and halfmove clock
- SAN history plus last move in UCI and SAN
- legal moves in UCI and SAN with capture, check, checkmate, promotion,
  castling, and en-passant flags
- material table, material balance, king status, draw-claim status, terminal
  reason, winner, and final validation

Chess replay rendering uses board coordinates, side-colored pieces, highlighted
last-move squares, FEN, terminal reason, winner, side to move, legal count,
check/checkmate status, and score.
