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

`session_state` is a signed server-only Platform/server envelope. Set
`ESLAMS_ARENA_SESSION_SECRET` to a secret of at least 32 characters on every
process that creates or steps a live session. A missing, empty, or short secret
fails closed. Do not forward the envelope to browsers. The envelope is an HMAC,
not encryption. For the active human recipient, browser-safe fields are `public_state`,
`display_frame`, `legal_action_descriptors`, `events`, actor metadata,
terminal/outcome fields, and timing. Live `display_frame` uses the same
projection shape as
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

Session privacy: the HMAC envelope is base64 JSON containing full private state,
not encryption. Keep `session_state` on trusted servers; never stream it to a
browser. Legal action lists/descriptors are emitted only for the active human
recipient and must be privately routed to that person. Model-seat lists stay
inside the trusted runner, obtainable from the server-side state. Public views
omit legal action lists. Pending sealed actions and their explanations remain
hidden until the arena reveal phase.

## Compact Hanabi cooperative rules

Hanabi 1.1.0 uses two colors, three ranks and four copies of each card, with two
controlled seats sharing the same normalized team score. It is a compact variant,
not the complete commercial deck. `winner` is always null; `team_success` indicates
perfect fireworks. The last draw starts exactly one further turn for each seat,
and discards are illegal while all eight clues are available. These timing and
clue rules follow the [publisher rulebook](https://cdn.svc.asmodee.net/production-asmodeees/uploads/2023/06/Hanabi_Reglamento_ES.pdf).

Shogi 1.0.1 corrects the initial bishop/rook files and applies own-king safety to
moves and drops, consistent with the [Japan Shogi Association's check rules](https://www.shogi.or.jp/knowledge/shogi/04.php). Xiangqi 1.0.1 also checks general
safety after every move. These remain compact adapters: Shogi pawn-drop mate,
repetition/impasse and Xiangqi perpetual check/chase adjudication are not modeled.
Historical ruleset versions and artifact bytes are unchanged.

All public arena `initial_state(seed)` calls require a Python integer excluding
booleans. Zero, negative integers and large integers are supported. JSON/session
callers must send an integer, rather than a string or floating-point seed. The
seed metadata and RNG commitment remain constant after actions.

## Corrected standard rule boundaries

Cribbage 1.0.1 counts ace-low runs with physical-card multiplicity, nobs and
hand/crib flushes according to the [ACC show scoring chart](https://www.cribbage.org/NewSite/rules/rulebook_2025.pdf).
It remains a single-hand compact discard/show variant without pegging or a
121-point match. Dealer balance is tracked separately in issue #96.

Pentago 1.0.1 ends immediately on a placement win, ignoring the rotation part
of that action. Otherwise it rotates and checks both players; simultaneous
lines draw, following the [publisher's rules guide](https://bville.com.ua/userfiles/files/Manual/41501104_pentago_rules.pdf).
Othello 1.0.1 finishes only when neither seat can place, following the
[World Othello Federation](https://www.worldothello.org/about/about-othello/othello-rules/official-rules/english).
Its 120-action runner horizon accommodates 60 placements and intervening passes.

Chess 1.2.0 uses automatic fivefold/75-move draws rather than forcing optional
claims. `claim-draw` is legal when the current position qualifies; an intended
move claim uses `claim-draw:<uci>` only when that legal move would produce a
qualifying repetition or fifty-move position. The intended move is declared,
not played. Checkmate takes precedence. `legal_uci` and SAN/move descriptors
remain actual moves; the full `legal_actions` list also includes claims. These
conditions use [python-chess's rule checks](https://python-chess.readthedocs.io/en/latest/core.html).

The three table poker arenas use 1.0.1 rules: only tied best hands share the
normalized showdown score, and a final fold closes a betting round when all
remaining commitments match. They retain their compact ante-based table,
profiled bet sizes and normalized winner shares; these scores are not net chip
returns or a full side-pot accounting implementation.
