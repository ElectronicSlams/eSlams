"""Deterministic advanced card and cooperative table arenas."""

from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Any

from eslams.arena import Arena
from eslams.arenas.card_utils import (
    RANKS,
    SUITS,
    card_rank,
    card_sort_key,
    card_suit,
    rank_value,
    standard_deck,
)
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")
EUCHRE_RANKS = ("9", "10", "J", "Q", "K", "A")
HANABI_COLORS = ("R", "B")
HANABI_RANKS = (1, 2, 3)


class GinRummyArena(Arena):
    id = "gin-rummy"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "description": "draw:deck, draw:discard, discard:<card>, or knock:<card>.",
    }
    max_turns = 80

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed)
        hands = {
            "player_1": sorted(deck[:7], key=_card_sort_key),
            "player_2": sorted(deck[7:14], key=_card_sort_key),
        }
        return self._state(
            hands=hands,
            deck=deck[15:],
            discard=[deck[14]],
            phase="draw",
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "hand": state.private_state_by_player[player_id]["hand"],
            "phase": state.public_state["phase"],
            "discard_top": state.public_state["discard_top"],
            "deck_count": state.public_state["deck_count"],
            "hand_counts": state.public_state["hand_counts"],
            "own_deadwood": _deadwood(state.private_state_by_player[player_id]["hand"]),
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal gin-rummy action")
        hands = _hands_from_state(state)
        deck = list(state.private_state_by_player["player_1"]["deck"])
        discard = list(state.public_state["discard"])
        phase = str(state.public_state["phase"])
        active = player_id
        outcome = None
        if phase == "draw":
            if action == "draw:deck":
                hands[player_id].append(deck.pop(0))
            else:
                hands[player_id].append(discard.pop())
            hands[player_id].sort(key=_card_sort_key)
            phase = "discard"
        else:
            card = action.split(":", 1)[1]
            hands[player_id].remove(card)
            discard.append(card)
            if action.startswith("knock:"):
                outcome = _gin_outcome(hands, player_id)
            active = _other(player_id)
            phase = "draw"
        if outcome is None and not deck:
            outcome = _gin_outcome(hands, player_id, reason="stock_empty")
        history = [
            *state.public_state["history"],
            {"player": player_id, "action": action, "phase": state.public_state["phase"]},
        ]
        return self._state(
            hands=hands,
            deck=deck,
            discard=discard,
            phase=phase,
            active=active,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        deck: list[str],
        discard: list[str],
        phase: str,
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _gin_outcome(hands, active, reason="turn_limit")
        legal = [] if terminal else _gin_legal(hands[active], deck, discard, phase)
        return _table_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            public_state={
                "phase": phase,
                "discard": discard,
                "discard_top": discard[-1] if discard else None,
                "deck_count": len(deck),
                "hand_counts": _hand_counts(hands),
                "history": history,
            },
            private_state=_private_hands(hands, deck),
            legal={player: (legal if player == active else []) for player in PLAYERS},
            scores=_winner_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="card-table",
        )


class EuchreArena(Arena):
    id = "euchre"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {"type": "string", "description": "call:<suit>, pass, or play:<card>."}
    max_turns = 16

    def initial_state(self, seed: int) -> ArenaState:
        deck = _euchre_deck(seed)
        hands = {
            "player_1": sorted(deck[:5], key=_card_sort_key),
            "player_2": sorted(deck[5:10], key=_card_sort_key),
        }
        upcard = deck[10]
        return self._state(
            hands=hands,
            trump=None,
            upcard=upcard,
            phase="call",
            active="player_1",
            dealer="player_2",
            current_trick=[],
            tricks={"player_1": 0, "player_2": 0},
            passes=[],
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _trick_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal euchre action")
        hands = _hands_from_state(state)
        trump = state.public_state["trump"]
        phase = str(state.public_state["phase"])
        active = _other(player_id)
        passes = list(state.public_state["passes"])
        tricks = dict(state.public_state["tricks"])
        current_trick = list(state.public_state["current_trick"])
        history = list(state.public_state["history"])
        outcome = None
        if phase == "call":
            if action == "pass":
                passes.append(player_id)
                if len(passes) >= 2:
                    trump = _suit(str(state.public_state["upcard"]))
                    phase = "play"
                    active = "player_1"
                    history.append({"phase": "call", "trump": trump, "reason": "upcard_default"})
            else:
                trump = action.split(":", 1)[1]
                phase = "play"
                active = "player_1"
                history.append({"phase": "call", "player": player_id, "trump": trump})
        else:
            card = action.split(":", 1)[1]
            hands[player_id].remove(card)
            current_trick.append({"player": player_id, "card": card})
            if len(current_trick) == 2:
                winner = _euchre_trick_winner(current_trick, str(trump))
                tricks[winner] += 1
                history.append({"winner": winner, "cards": current_trick, "trump": trump})
                current_trick = []
                active = winner
        if phase == "play" and not any(hands[player] for player in PLAYERS):
            outcome = _trick_count_outcome(tricks, reason="hands_empty")
        return self._state(
            hands=hands,
            trump=trump,
            upcard=str(state.public_state["upcard"]),
            phase=phase,
            active=active,
            dealer=str(state.public_state["dealer"]),
            current_trick=current_trick,
            tricks=tricks,
            passes=passes,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        trump: str | None,
        upcard: str,
        phase: str,
        active: str,
        dealer: str,
        current_trick: list[dict[str, str]],
        tricks: dict[str, int],
        passes: list[str],
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _trick_count_outcome(tricks, reason="turn_limit")
        legal = [] if terminal else _euchre_legal(hands[active], phase, trump, current_trick)
        return _table_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            public_state={
                "phase": phase,
                "dealer": dealer,
                "upcard": upcard,
                "trump": trump,
                "passes": passes,
                "current_trick": current_trick,
                "tricks": tricks,
                "hand_counts": _hand_counts(hands),
                "history": history,
            },
            private_state=_private_hands(hands, []),
            legal={player: (legal if player == active else []) for player in PLAYERS},
            scores=_winner_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="trick-card-table",
        )


class CribbageArena(Arena):
    id = "cribbage"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {"type": "string", "description": "Discard two cards as discard:<card>,<card>."}
    max_turns = 2

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed + 211)
        hands = {
            "player_1": sorted(deck[:6], key=_card_sort_key),
            "player_2": sorted(deck[6:12], key=_card_sort_key),
        }
        return self._state(
            hands=hands,
            discards={"player_1": [], "player_2": []},
            starter=deck[12],
            dealer="player_2",
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "hand": state.private_state_by_player[player_id]["hand"],
            "starter": state.public_state["starter"],
            "dealer": state.public_state["dealer"],
            "discard_counts": state.public_state["discard_counts"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal cribbage action")
        hands = _hands_from_state(state)
        discards = {player: list(cards) for player, cards in state.public_state["discards"].items()}
        cards = action.split(":", 1)[1].split(",")
        for card in cards:
            hands[player_id].remove(card)
        discards[player_id] = cards
        active = _other(player_id)
        outcome = None
        if all(len(discards[player]) == 2 for player in PLAYERS):
            outcome = _cribbage_outcome(
                hands,
                discards,
                str(state.public_state["starter"]),
                str(state.public_state["dealer"]),
            )
        history = [*state.public_state["history"], {"player": player_id, "action": action}]
        return self._state(
            hands=hands,
            discards=discards,
            starter=str(state.public_state["starter"]),
            dealer=str(state.public_state["dealer"]),
            active=active,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        discards: dict[str, list[str]],
        starter: str,
        dealer: str,
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _cribbage_outcome(hands, discards, starter, dealer, reason="turn_limit")
        legal = [] if terminal else _cribbage_legal(hands[active])
        return _table_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            public_state={
                "starter": starter,
                "dealer": dealer,
                "discards": discards,
                "discard_counts": {player: len(cards) for player, cards in discards.items()},
                "hand_counts": _hand_counts(hands),
                "history": history,
            },
            private_state=_private_hands(hands, []),
            legal={player: (legal if player == active else []) for player in PLAYERS},
            scores=_winner_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="card-table",
        )


class HanabiArena(Arena):
    id = "hanabi"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "description": "play:<index>, discard:<index>, or hint:<player>:<color-or-rank>.",
    }
    max_turns = 60

    def initial_state(self, seed: int) -> ArenaState:
        deck = _hanabi_deck(seed)
        hands = {"player_1": deck[:4], "player_2": deck[4:8]}
        return self._state(
            hands=hands,
            deck=deck[8:],
            fireworks=dict.fromkeys(HANABI_COLORS, 0),
            discard=[],
            clues=8,
            lives=3,
            active="player_1",
            turn=0,
            seed=seed,
            hints={"player_1": [[], [], [], []], "player_2": [[], [], [], []]},
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        other = _other(player_id)
        return {
            "you_are": player_id,
            "own_hand_size": len(state.private_state_by_player[player_id]["hand"]),
            "own_hints": state.public_state["hints"][player_id],
            "visible_partner_hand": state.private_state_by_player[player_id][
                "visible_partner_hand"
            ],
            "partner": other,
            "fireworks": state.public_state["fireworks"],
            "discard": state.public_state["discard"],
            "clues": state.public_state["clues"],
            "lives": state.public_state["lives"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal hanabi action")
        hands = _hanabi_hands_from_state(state)
        deck = list(state.private_state_by_player[player_id]["deck"])
        fireworks = dict(state.public_state["fireworks"])
        discard = list(state.public_state["discard"])
        clues = int(state.public_state["clues"])
        lives = int(state.public_state["lives"])
        hints = {
            player: [list(items) for items in state.public_state["hints"][player]]
            for player in PLAYERS
        }
        event: dict[str, Any] = {"player": player_id, "action": action}
        if action.startswith("play:"):
            index = int(action.split(":", 1)[1])
            card = hands[player_id].pop(index)
            hints[player_id].pop(index)
            color, rank = _hanabi_parts(card)
            if fireworks[color] + 1 == rank:
                fireworks[color] = rank
                event["result"] = "played"
            else:
                discard.append(card)
                lives -= 1
                event["result"] = "misplay"
            _hanabi_draw(hands, hints, deck, player_id)
        elif action.startswith("discard:"):
            index = int(action.split(":", 1)[1])
            card = hands[player_id].pop(index)
            hints[player_id].pop(index)
            discard.append(card)
            clues = min(8, clues + 1)
            event["discarded"] = card
            _hanabi_draw(hands, hints, deck, player_id)
        else:
            _, target, clue = action.split(":", 2)
            clues -= 1
            for index, card in enumerate(hands[target]):
                color, rank = _hanabi_parts(card)
                if clue == color or clue == str(rank):
                    hints[target][index].append(clue)
            event["target"] = target
            event["clue"] = clue
        outcome = _hanabi_outcome(fireworks, lives, deck, hands)
        history = [*state.public_state["history"], event]
        return self._state(
            hands=hands,
            deck=deck,
            fireworks=fireworks,
            discard=discard,
            clues=clues,
            lives=lives,
            active=_other(player_id),
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            hints=hints,
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        deck: list[str],
        fireworks: dict[str, int],
        discard: list[str],
        clues: int,
        lives: int,
        active: str,
        turn: int,
        seed: int,
        hints: dict[str, list[list[str]]],
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _hanabi_result(fireworks, reason="turn_limit")
        legal = [] if terminal else _hanabi_legal(hands[active], active, clues)
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "fireworks": fireworks,
                "discard": discard,
                "clues": clues,
                "lives": lives,
                "deck_count": len(deck),
                "hand_counts": _hand_counts(hands),
                "hints": hints,
                "history": history,
            },
            private_state_by_player=_hanabi_private_state(hands, deck),
            legal_actions_by_player={
                player: (legal if player == active and not terminal else []) for player in PLAYERS
            },
            scores=_hanabi_scores(outcome, fireworks),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"hanabi:{seed}"),
            render_hints={"renderer": "hanabi-table"},
            metadata={"seed": seed},
        )


def _table_state(
    *,
    arena_id: str,
    turn: int,
    active: str,
    seed: int,
    public_state: dict[str, Any],
    private_state: dict[str, dict[str, Any]],
    legal: dict[str, list[str]],
    scores: dict[str, float],
    terminal: bool,
    outcome: dict[str, Any] | None,
    renderer: str,
) -> ArenaState:
    return ArenaState(
        state_id=f"state_{turn:06d}",
        turn=turn,
        active_player=active,
        public_state=public_state,
        private_state_by_player=private_state,
        legal_actions_by_player=legal,
        scores=scores,
        terminal=terminal,
        outcome=outcome,
        rng_commitment=sha256_text(f"{arena_id}:{seed}"),
        render_hints={"renderer": renderer},
        metadata={"seed": seed},
    )


def _deck(seed: int) -> list[str]:
    return standard_deck(seed)


def _euchre_deck(seed: int) -> list[str]:
    cards = [f"{rank}{suit}" for suit in SUITS for rank in EUCHRE_RANKS]
    random.Random(seed).shuffle(cards)
    return cards


def _hanabi_deck(seed: int) -> list[str]:
    cards = [f"{color}{rank}" for color in HANABI_COLORS for rank in HANABI_RANKS for _ in range(2)]
    random.Random(seed).shuffle(cards)
    return cards


def _private_hands(hands: dict[str, list[str]], deck: list[str]) -> dict[str, dict[str, Any]]:
    return {player: {"hand": list(hands[player]), "deck": list(deck)} for player in PLAYERS}


def _hands_from_state(state: ArenaState) -> dict[str, list[str]]:
    return {player: list(state.private_state_by_player[player]["hand"]) for player in PLAYERS}


def _hand_counts(hands: dict[str, list[str]]) -> dict[str, int]:
    return {player: len(cards) for player, cards in hands.items()}


def _gin_legal(hand: list[str], deck: list[str], discard: list[str], phase: str) -> list[str]:
    if phase == "draw":
        legal = []
        if deck:
            legal.append("draw:deck")
        if discard:
            legal.append("draw:discard")
        return legal
    legal = [f"discard:{card}" for card in hand]
    legal.extend(f"knock:{card}" for card in hand if _deadwood(_without_card(hand, card)) <= 10)
    return legal


def _without_card(hand: list[str], card: str) -> list[str]:
    cards = list(hand)
    cards.remove(card)
    return cards


def _deadwood(hand: list[str]) -> int:
    if not hand:
        return 0
    rank_groups: dict[str, list[str]] = {}
    suit_groups: dict[str, list[str]] = {}
    for card in hand:
        rank_groups.setdefault(_rank(card), []).append(card)
        suit_groups.setdefault(_suit(card), []).append(card)
    meld_cards: set[str] = set()
    for cards in rank_groups.values():
        if len(cards) >= 3:
            meld_cards.update(cards)
    for cards in suit_groups.values():
        ordered = sorted(cards, key=lambda card: RANKS.index(_rank(card)))
        run: list[str] = []
        previous = -3
        for card in ordered:
            value = RANKS.index(_rank(card))
            if value == previous + 1:
                run.append(card)
            else:
                if len(run) >= 3:
                    meld_cards.update(run)
                run = [card]
            previous = value
        if len(run) >= 3:
            meld_cards.update(run)
    return sum(_deadwood_value(card) for card in hand if card not in meld_cards)


def _gin_outcome(
    hands: dict[str, list[str]],
    knocker: str,
    *,
    reason: str = "knock",
) -> dict[str, Any]:
    deadwood = {player: _deadwood(cards) for player, cards in hands.items()}
    opponent = _other(knocker)
    if reason == "knock" and deadwood[opponent] <= deadwood[knocker]:
        winner = opponent
        reason = "undercut"
    elif deadwood["player_1"] == deadwood["player_2"]:
        winner = None
    else:
        winner = "player_1" if deadwood["player_1"] < deadwood["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "deadwood": deadwood}


def _euchre_legal(
    hand: list[str],
    phase: str,
    trump: str | None,
    current_trick: list[dict[str, str]],
) -> list[str]:
    if phase == "call":
        return ["pass", *[f"call:{suit}" for suit in SUITS]]
    legal_cards = _follow_effective_suit(hand, str(trump), current_trick)
    return [f"play:{card}" for card in legal_cards]


def _follow_effective_suit(
    hand: list[str],
    trump: str,
    current_trick: list[dict[str, str]],
) -> list[str]:
    if not current_trick:
        return list(hand)
    led = _euchre_suit(current_trick[0]["card"], trump)
    suited = [card for card in hand if _euchre_suit(card, trump) == led]
    return suited or list(hand)


def _euchre_trick_winner(current_trick: list[dict[str, str]], trump: str) -> str:
    led = _euchre_suit(current_trick[0]["card"], trump)

    def key(play: dict[str, str]) -> tuple[int, int]:
        card = play["card"]
        suit = _euchre_suit(card, trump)
        if suit == trump:
            return (2, _euchre_rank_value(card, trump))
        if suit == led:
            return (1, _euchre_rank_value(card, trump))
        return (0, _euchre_rank_value(card, trump))

    return max(current_trick, key=key)["player"]


def _euchre_suit(card: str, trump: str) -> str:
    if _rank(card) == "J" and _same_color(_suit(card), trump):
        return trump
    return _suit(card)


def _euchre_rank_value(card: str, trump: str) -> int:
    rank = _rank(card)
    suit = _suit(card)
    if rank == "J" and suit == trump:
        return 100
    if rank == "J" and _same_color(suit, trump):
        return 99
    return EUCHRE_RANKS.index(rank)


def _same_color(first: str, second: str) -> bool:
    return first in "HD" and second in "HD" or first in "CS" and second in "CS"


def _trick_count_outcome(tricks: dict[str, int], *, reason: str) -> dict[str, Any]:
    if tricks["player_1"] == tricks["player_2"]:
        winner = None
    else:
        winner = "player_1" if tricks["player_1"] > tricks["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "tricks": tricks}


def _cribbage_legal(hand: list[str]) -> list[str]:
    return [
        "discard:" + ",".join(cards)
        for cards in itertools.combinations(sorted(hand, key=_card_sort_key), 2)
    ]


def _cribbage_outcome(
    hands: dict[str, list[str]],
    discards: dict[str, list[str]],
    starter: str,
    dealer: str,
    *,
    reason: str = "showdown",
) -> dict[str, Any]:
    hand_scores = {player: _cribbage_hand_score([*hands[player], starter]) for player in PLAYERS}
    crib_cards = [*discards["player_1"], *discards["player_2"], starter]
    hand_scores[dealer] += _cribbage_hand_score(crib_cards)
    if hand_scores["player_1"] == hand_scores["player_2"]:
        winner = None
    else:
        winner = "player_1" if hand_scores["player_1"] > hand_scores["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "hand_scores": hand_scores, "starter": starter}


def _cribbage_hand_score(cards: list[str]) -> int:
    values = [_crib_value(card) for card in cards]
    score = 0
    for size in range(2, len(cards) + 1):
        for combo in itertools.combinations(values, size):
            if sum(combo) == 15:
                score += 2
    counts = Counter(_rank(card) for card in cards)
    score += sum(count * (count - 1) for count in counts.values() if count >= 2)
    ordered = sorted({RANKS.index(_rank(card)) for card in cards})
    run = 1
    best_run = 0
    for previous, current in zip(ordered, ordered[1:]):
        if current == previous + 1:
            run += 1
            best_run = max(best_run, run)
        else:
            run = 1
    if best_run >= 3:
        score += best_run
    suits = [_suit(card) for card in cards[:-1]]
    if suits and len(set(suits)) == 1:
        score += 4
        if _suit(cards[-1]) == suits[0]:
            score += 1
    return score


def _hanabi_legal(hand: list[str], active: str, clues: int) -> list[str]:
    legal = [f"play:{index}" for index in range(len(hand))]
    legal.extend(f"discard:{index}" for index in range(len(hand)))
    if clues > 0:
        target = _other(active)
        legal.extend(f"hint:{target}:{color}" for color in HANABI_COLORS)
        legal.extend(f"hint:{target}:{rank}" for rank in HANABI_RANKS)
    return legal


def _hanabi_private_state(
    hands: dict[str, list[str]],
    deck: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        player: {
            "hand": list(hands[player]),
            "visible_partner_hand": list(hands[_other(player)]),
            "deck": list(deck),
        }
        for player in PLAYERS
    }


def _hanabi_hands_from_state(state: ArenaState) -> dict[str, list[str]]:
    return {player: list(state.private_state_by_player[player]["hand"]) for player in PLAYERS}


def _hanabi_parts(card: str) -> tuple[str, int]:
    return card[0], int(card[1:])


def _hanabi_draw(
    hands: dict[str, list[str]],
    hints: dict[str, list[list[str]]],
    deck: list[str],
    player: str,
) -> None:
    if deck:
        hands[player].append(deck.pop(0))
        hints[player].append([])


def _hanabi_outcome(
    fireworks: dict[str, int],
    lives: int,
    deck: list[str],
    hands: dict[str, list[str]],
) -> dict[str, Any] | None:
    if all(value == max(HANABI_RANKS) for value in fireworks.values()):
        return _hanabi_result(fireworks, reason="perfect_fireworks")
    if lives <= 0:
        return _hanabi_result(fireworks, reason="lives_exhausted")
    if not deck and not any(hands[player] for player in PLAYERS):
        return _hanabi_result(fireworks, reason="deck_and_hands_empty")
    return None


def _hanabi_result(fireworks: dict[str, int], *, reason: str) -> dict[str, Any]:
    score = sum(fireworks.values())
    max_score = len(HANABI_COLORS) * max(HANABI_RANKS)
    return {
        "winner": "player_1" if score >= max_score else None,
        "reason": reason,
        "cooperative_score": score,
        "max_score": max_score,
    }


def _hanabi_scores(
    outcome: dict[str, Any] | None,
    fireworks: dict[str, int],
) -> dict[str, float]:
    score = int(outcome.get("cooperative_score", 0)) if outcome else sum(fireworks.values())
    normalized = float(score) / float(len(HANABI_COLORS) * max(HANABI_RANKS))
    return {"player_1": normalized, "player_2": normalized}


def _trick_observation(state: ArenaState, player_id: str) -> dict[str, Any]:
    return {
        "you_are": player_id,
        "hand": state.private_state_by_player[player_id]["hand"],
        "hand_counts": state.public_state["hand_counts"],
        "phase": state.public_state["phase"],
        "trump": state.public_state["trump"],
        "upcard": state.public_state["upcard"],
        "current_trick": state.public_state["current_trick"],
        "tricks": state.public_state["tricks"],
        "legal_actions": state.legal_actions_by_player[player_id],
        "scores": state.scores,
    }


def _winner_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    return {winner: 1.0, _other(winner): 0.0}


def _rank(card: str) -> str:
    return card_rank(card)


def _suit(card: str) -> str:
    return card_suit(card)


def _rank_value(card: str) -> int:
    return rank_value(card)


def _deadwood_value(card: str) -> int:
    rank = _rank(card)
    if rank in {"J", "Q", "K"}:
        return 10
    if rank == "A":
        return 1
    return int(rank)


def _crib_value(card: str) -> int:
    return min(10, _deadwood_value(card))


def _card_sort_key(card: str) -> tuple[int, int]:
    return card_sort_key(card)


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
