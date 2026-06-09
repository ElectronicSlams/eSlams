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

- `alien-shooter`
- `backgammon`
- `bargaining`
- `battleship`
- `bipedal-walker`
- `blackjack`
- `boxing-style-arena`
- `bridge`
- `car-racing`
- `cartpole`
- `checkers`
- `chess`
- `cliff-walking`
- `connect-four`
- `crazy-eights`
- `cribbage`
- `dou-dizhu`
- `euchre`
- `first-price-sealed-bid-auction`
- `frozen-lake`
- `gin-rummy`
- `go`
- `gomoku`
- `goofspiel`
- `hanabi`
- `hearts`
- `hex`
- `ice-hockey-style-arena`
- `leduc-holdem`
- `liars-dice`
- `limit-texas-holdem`
- `lunar-lander`
- `mahjong`
- `mancala`
- `mountain-car`
- `negotiation`
- `nine-mens-morris`
- `no-limit-texas-holdem`
- `othello`
- `paddle-ball`
- `pentago`
- `prisoners-dilemma`
- `rock-paper-scissors`
- `shedding-card-game`
- `shogi`
- `spades`
- `taxi`
- `tic-tac-toe`
- `ultimate-tic-tac-toe`
- `xiangqi`

The public catalogue is intentionally adapter-based. eSlams owns the canonical state, trace, replay, and scoring contract even when the game logic is powered by an external library.

Core can emit public-safe catalogue and renderer metadata for all 50 arenas:

```bash
eslams catalogue games --json
eslams catalogue renderers --json
eslams arena smoke --all --json
```

Every game has explicit browser play, replay, official eval, renderer family,
timeline completeness, and coming-soon or absence metadata so Platform does not
need to invent display states.

## Live Arena Session Transport

Core v0.3.0 exposes fast server-to-server Arena session helpers:

- `start_session(game_slug, variant, seed, players, options=None)`
- `step_session(session_state, player_id, action_token)`
- `legal_actions_page(session_state, player_id, query=None, limit=50, cursor=None)`

These helpers are intentionally lightweight. They do not call models, export
artifacts, export replay packages, persist sessions, store secrets, or know
about Cloudflare. They own legality, state transition, hash verification,
public display frames, public-safe events, and legal action descriptors.

`session_state` is trusted Platform/server state and may contain hidden cards or
other private state. Browser-safe fields are `public_state`, `display_frame`,
`legal_action_descriptors`, `events`, actor metadata, terminal/outcome fields,
and timing. Live `display_frame` uses the same projection shape as
`replay/display_frames.jsonl`, so Platform can render live play and replay with
one UI contract.

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
