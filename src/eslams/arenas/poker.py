"""Deterministic compact poker arenas."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, cast

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2", "player_3", "player_4")
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
SUITS = ("C", "D", "H", "S")


class LeducHoldemArena(Arena):
    id = "leduc-holdem"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["check", "bet", "call", "fold", "raise"],
        "description": "Leduc action for the current betting state.",
    }
    max_turns = 24

    def initial_state(self, seed: int) -> ArenaState:
        deck = _leduc_deck(seed)
        hole = {player: [deck.pop(0)] for player in PLAYERS}
        return self._state(
            hole=hole,
            deck=deck,
            board=[],
            street="preflop",
            active="player_1",
            pot=len(PLAYERS),
            committed=dict.fromkeys(PLAYERS, 1),
            stacks=dict.fromkeys(PLAYERS, 9),
            folded=[],
            street_actions=[],
            history=[],
            turn=0,
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _poker_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        return _apply_poker_action(self, state, player_id, action, limit_bet=2, no_limit=False)

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(self, **kwargs: Any) -> ArenaState:
        return _poker_state(arena=self, evaluator=_leduc_winner, board_cards=1, **kwargs)


class LimitTexasHoldemArena(Arena):
    id = "limit-texas-holdem"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "enum": ["check", "bet", "call", "fold", "raise"],
        "description": "Fixed-limit table Hold'em action.",
    }
    max_turns = 32

    def initial_state(self, seed: int) -> ArenaState:
        deck = _standard_deck(seed)
        hole = {player: [deck.pop(0), deck.pop(0)] for player in PLAYERS}
        return self._state(
            hole=hole,
            deck=deck,
            board=[],
            street="preflop",
            active="player_1",
            pot=len(PLAYERS),
            committed=dict.fromkeys(PLAYERS, 1),
            stacks=dict.fromkeys(PLAYERS, 19),
            folded=[],
            street_actions=[],
            history=[],
            turn=0,
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _poker_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        return _apply_poker_action(self, state, player_id, action, limit_bet=2, no_limit=False)

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(self, **kwargs: Any) -> ArenaState:
        return _poker_state(arena=self, evaluator=_texas_winner, board_cards=5, **kwargs)


class NoLimitTexasHoldemArena(LimitTexasHoldemArena):
    id = "no-limit-texas-holdem"
    action_schema = {
        "type": "string",
        "enum": ["check", "bet:2", "bet:4", "call", "fold", "raise:4", "all-in"],
        "description": "No-limit table Hold'em action with profiled bet sizes.",
    }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        return _apply_poker_action(self, state, player_id, action, limit_bet=2, no_limit=True)


def _apply_poker_action(
    arena: Any,
    state: ArenaState,
    player_id: str,
    action: Any,
    *,
    limit_bet: int,
    no_limit: bool,
) -> ArenaState:
    if not isinstance(action, str) or not arena.is_legal(state, player_id, action):
        raise ValueError(f"illegal {arena.id} action")
    hole = {player: list(state.private_state_by_player[player]["hole"]) for player in PLAYERS}
    deck = list(state.private_state_by_player["player_1"]["deck"])
    board = list(state.public_state["board"])
    pot = int(state.public_state["pot"])
    committed = dict(state.public_state["committed"])
    stacks = dict(state.public_state["stacks"])
    folded = list(state.public_state.get("folded", []))
    history = list(state.public_state["history"])
    street_actions = list(state.metadata["street_actions"])
    street = str(state.public_state["street"])
    outcome = None
    active = _next_player(player_id, folded=folded)
    to_call = _to_call(committed, player_id, folded=folded)

    if action == "fold":
        if player_id not in folded:
            folded.append(player_id)
        remaining = _active_players(folded)
        street_actions.append(action)
        if len(remaining) == 1:
            outcome = {
                "winner": remaining[0],
                "reason": "fold",
                "pot": pot,
                "board": board,
                "folded": folded,
            }
        else:
            active = _next_player(player_id, folded=folded)
    elif action in {"check", "call"}:
        amount = 0
        if action == "call" and to_call:
            amount = min(to_call, stacks[player_id])
            stacks[player_id] -= amount
            committed[player_id] += amount
        pot += amount
        street_actions.append(action)
        if _street_closed(street_actions, committed, folded):
            street, board, deck, committed, street_actions, active, outcome = _advance_street(
                arena=arena,
                hole=hole,
                board=board,
                deck=deck,
                committed=committed,
                folded=folded,
                street=street,
                active=active,
                pot=pot,
            )
    elif action in {"bet", "raise", "bet:2", "bet:4", "raise:4", "all-in"}:
        amount = _bet_amount(action, player_id, stacks, to_call, limit_bet, no_limit)
        stacks[player_id] -= amount
        committed[player_id] += amount
        pot += amount
        street_actions = [action]

    history.append(
        {
            "player": player_id,
            "action": action,
            "street": state.public_state["street"],
            "pot": pot,
        }
    )
    return cast(
        ArenaState,
        arena._state(
            hole=hole,
            deck=deck,
            board=board,
            street=street,
            active=active,
            pot=pot,
            committed=committed,
            stacks=stacks,
            folded=folded,
            street_actions=street_actions,
            history=history,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        ),
    )


def _poker_state(
    *,
    arena: Any,
    evaluator: Any,
    board_cards: int,
    hole: dict[str, list[str]],
    deck: list[str],
    board: list[str],
    street: str,
    active: str,
    pot: int,
    committed: dict[str, int],
    stacks: dict[str, int],
    folded: list[str],
    street_actions: list[str],
    history: list[dict[str, Any]],
    turn: int,
    seed: int,
    outcome: dict[str, Any] | None,
) -> ArenaState:
    terminal = outcome is not None or turn >= arena.max_turns
    if outcome is None and (terminal or street == "showdown"):
        outcome = evaluator(hole, board, pot, folded=folded)
        terminal = True
    legal = (
        []
        if terminal or active in folded
        else _legal_poker_actions(
            active,
            committed,
            stacks,
            street_actions,
            folded=folded,
            no_limit=arena.id.startswith("no-limit"),
        )
    )
    return ArenaState(
        state_id=f"state_{turn:06d}",
        turn=turn,
        active_player=active,
        public_state={
            "street": street,
            "board": board,
            "pot": pot,
            "committed": committed,
            "stacks": stacks,
            "folded": folded,
            "history": history,
        },
        private_state_by_player={
            player: {"hole": hole[player], "deck": list(deck)} for player in PLAYERS
        },
        legal_actions_by_player={player: (legal if player == active else []) for player in PLAYERS},
        scores=_winner_scores(outcome),
        terminal=terminal,
        outcome=outcome,
        rng_commitment=sha256_text(f"{arena.id}:{seed}"),
        render_hints={"renderer": "poker-table"},
        metadata={"seed": seed, "street_actions": street_actions},
    )


def _poker_observation(state: ArenaState, player_id: str) -> dict[str, Any]:
    return {
        "you_are": player_id,
        "hole": state.private_state_by_player[player_id]["hole"],
        "street": state.public_state["street"],
        "board": state.public_state["board"],
        "pot": state.public_state["pot"],
        "stacks": state.public_state["stacks"],
        "committed": state.public_state["committed"],
        "folded": state.public_state.get("folded", []),
        "history": state.public_state["history"],
        "legal_actions": state.legal_actions_by_player[player_id],
        "scores": state.scores,
    }


def _advance_street(
    *,
    arena: Any,
    hole: dict[str, list[str]],
    board: list[str],
    deck: list[str],
    committed: dict[str, int],
    folded: list[str],
    street: str,
    active: str,
    pot: int,
) -> tuple[str, list[str], list[str], dict[str, int], list[str], str, dict[str, Any] | None]:
    committed = dict.fromkeys(PLAYERS, 0)
    if arena.id == "leduc-holdem":
        if street == "preflop":
            board = [deck.pop(0)]
            return "board", board, deck, committed, [], active, None
        return (
            "showdown",
            board,
            deck,
            committed,
            [],
            active,
            _leduc_winner(hole, board, pot, folded=folded),
        )
    if street == "preflop":
        board = [deck.pop(0), deck.pop(0), deck.pop(0)]
        return "flop", board, deck, committed, [], active, None
    if street == "flop":
        board.append(deck.pop(0))
        return "turn", board, deck, committed, [], active, None
    if street == "turn":
        board.append(deck.pop(0))
        return "river", board, deck, committed, [], active, None
    return (
        "showdown",
        board,
        deck,
        committed,
        [],
        active,
        _texas_winner(hole, board, pot, folded=folded),
    )


def _legal_poker_actions(
    active: str,
    committed: dict[str, int],
    stacks: dict[str, int],
    street_actions: list[str],
    *,
    folded: list[str],
    no_limit: bool,
) -> list[str]:
    to_call = _to_call(committed, active, folded=folded)
    if stacks[active] <= 0:
        return ["fold"] if to_call else ["check"]
    if to_call:
        actions = ["call", "fold"]
        can_raise = (
            not any(action.startswith("raise") for action in street_actions)
            and stacks[active] > to_call
        )
        if can_raise:
            actions.append("raise:4" if no_limit else "raise")
        return actions
    if no_limit:
        actions = ["check", "all-in"]
        if stacks[active] >= 2:
            actions.insert(1, "bet:2")
        if stacks[active] >= 4:
            actions.insert(2, "bet:4")
        return actions
    return ["check", "bet"]


def _bet_amount(
    action: str,
    player_id: str,
    stacks: dict[str, int],
    to_call: int,
    limit_bet: int,
    no_limit: bool,
) -> int:
    if action == "all-in":
        return stacks[player_id]
    if no_limit and ":" in action:
        return min(stacks[player_id], to_call + int(action.split(":", 1)[1]))
    return min(stacks[player_id], to_call + limit_bet)


def _street_closed(street_actions: list[str], committed: dict[str, int], folded: list[str]) -> bool:
    active_players = _active_players(folded)
    active_committed = [committed[player] for player in active_players]
    if not active_committed or max(active_committed) != min(active_committed):
        return False
    return len(street_actions) >= len(active_players)


def _to_call(committed: dict[str, int], player_id: str, *, folded: list[str]) -> int:
    active_committed = [committed[player] for player in _active_players(folded)]
    return max(active_committed or [0]) - committed[player_id]


def _leduc_deck(seed: int) -> list[str]:
    cards = ["JH", "JS", "QH", "QS", "KH", "KS"]
    random.Random(seed).shuffle(cards)
    return cards


def _standard_deck(seed: int) -> list[str]:
    cards = [f"{rank}{suit}" for rank in RANKS for suit in SUITS]
    random.Random(seed).shuffle(cards)
    return cards


def _leduc_winner(
    hole: dict[str, list[str]],
    board: list[str],
    pot: int,
    *,
    folded: list[str],
) -> dict[str, Any]:
    board_rank = _rank(board[0]) if board else ""
    active_players = _active_players(folded)
    values = {
        player: (1 if _rank(cards[0]) == board_rank else 0, RANKS.index(_rank(cards[0])))
        for player, cards in hole.items()
        if player in active_players
    }
    winner = _compare_values(values)
    return {
        "winner": winner,
        "reason": "showdown",
        "pot": pot,
        "board": board,
        "folded": folded,
        "hand_values": values,
    }


def _texas_winner(
    hole: dict[str, list[str]],
    board: list[str],
    pot: int,
    *,
    folded: list[str],
) -> dict[str, Any]:
    active_players = _active_players(folded)
    values = {
        player: _best_five_value(cards + board)
        for player, cards in hole.items()
        if player in active_players
    }
    winner = _compare_values(values)
    return {
        "winner": winner,
        "reason": "showdown",
        "pot": pot,
        "board": board,
        "folded": folded,
        "hand_values": values,
    }


def _best_five_value(cards: list[str]) -> tuple[int, list[int]]:
    ranks = [_rank_value(card) for card in cards]
    suits = [_suit(card) for card in cards]
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    flush = next((suit for suit in SUITS if suits.count(suit) >= 5), None)
    straight_high = _straight_high(sorted(set(ranks), reverse=True))
    if flush:
        flush_ranks = sorted(
            {_rank_value(card) for card in cards if _suit(card) == flush},
            reverse=True,
        )
        flush_straight = _straight_high(flush_ranks)
        if flush_straight is not None:
            return (8, [flush_straight])
    if groups[0][0] == 4:
        return (7, [groups[0][1], _best_kickers(counts, exclude={groups[0][1]}, n=1)[0]])
    if groups[0][0] == 3 and len(groups) > 1 and groups[1][0] >= 2:
        return (6, [groups[0][1], groups[1][1]])
    if flush:
        return (
            5,
            sorted(
                (_rank_value(card) for card in cards if _suit(card) == flush),
                reverse=True,
            )[:5],
        )
    if straight_high is not None:
        return (4, [straight_high])
    if groups[0][0] == 3:
        return (
            3,
            [groups[0][1], *_best_kickers(counts, exclude={groups[0][1]}, n=2)],
        )
    if groups[0][0] == 2 and len(groups) > 1 and groups[1][0] == 2:
        return (
            2,
            [
                groups[0][1],
                groups[1][1],
                *_best_kickers(
                    counts,
                    exclude={groups[0][1], groups[1][1]},
                    n=1,
                ),
            ],
        )
    if groups[0][0] == 2:
        return (
            1,
            [groups[0][1], *_best_kickers(counts, exclude={groups[0][1]}, n=3)],
        )
    return (0, sorted(ranks, reverse=True)[:5])


def _best_kickers(counts: Counter[int], *, exclude: set[int], n: int) -> list[int]:
    return [rank for rank in sorted(counts, reverse=True) if rank not in exclude][:n]


def _straight_high(ranks: list[int]) -> int | None:
    values = set(ranks)
    if 12 in values:
        values.add(-1)
    for high in range(12, 2, -1):
        if all(value in values for value in range(high - 4, high + 1)):
            return high
    return None


def _compare_values(values: dict[str, Any]) -> str | None:
    if not values:
        return None
    ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _winner_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return dict.fromkeys(PLAYERS, 0.0)
    folded = [str(player) for player in outcome.get("folded", [])]
    active_players = _active_players(folded)
    if outcome.get("winner") is None:
        share = 1.0 / len(active_players) if active_players else 0.0
        return {player: (share if player in active_players else 0.0) for player in PLAYERS}
    winner = str(outcome["winner"])
    return {player: (1.0 if player == winner else 0.0) for player in PLAYERS}


def _rank(card: str) -> str:
    return card[:-1]


def _suit(card: str) -> str:
    return card[-1]


def _rank_value(card: str) -> int:
    return RANKS.index(_rank(card))


def _active_players(folded: list[str]) -> list[str]:
    folded_set = set(folded)
    return [player for player in PLAYERS if player not in folded_set]


def _next_player(player_id: str, *, folded: list[str]) -> str:
    active_players = _active_players(folded)
    if not active_players:
        return player_id
    start_index = PLAYERS.index(player_id) if player_id in PLAYERS else -1
    for offset in range(1, len(PLAYERS) + 1):
        candidate = PLAYERS[(start_index + offset) % len(PLAYERS)]
        if candidate in active_players:
            return candidate
    return active_players[0]
