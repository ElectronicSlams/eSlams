"""Deterministic compact card-game arenas."""

from __future__ import annotations

from typing import Any

from eslams.arena import Arena
from eslams.arenas.card_utils import (
    card_rank,
    card_sort_key,
    card_suit,
    rank_value,
    standard_deck,
)
from eslams.hashing import sha256_text
from eslams.state import ArenaState

PLAYERS = ("player_1", "player_2")


class SheddingCardGameArena(Arena):
    id = "shedding-card-game"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {
        "type": "string",
        "description": "Play a matching card as play:<card>, draw, or pass when the deck is empty.",
    }
    max_turns = 80

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed)
        hands = {"player_1": sorted(deck[:5]), "player_2": sorted(deck[5:10])}
        discard = deck[10]
        return self._state(
            hands=hands,
            deck=deck[11:],
            discard=discard,
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _shedding_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal shedding-card-game action")
        hands = _hands_from_state(state)
        deck = list(state.private_state_by_player["player_1"]["deck"])
        discard = str(state.public_state["discard"])
        history = list(state.public_state["history"])
        if action.startswith("play:"):
            card = action.split(":", 1)[1]
            hands[player_id].remove(card)
            discard = card
        elif action == "draw" and deck:
            hands[player_id].append(deck.pop(0))
            hands[player_id].sort(key=_card_sort_key)
        history.append({"player": player_id, "action": action, "discard": discard})
        outcome = _empty_hand_outcome(hands, player_id)
        opponent_has_no_play = not any(
            self._playable_cards_for_blocked(hands[_other(player_id)], discard)
        )
        if outcome is None and action == "pass" and opponent_has_no_play:
            outcome = _fewest_cards_outcome(hands, "blocked")
        return self._state(
            hands=hands,
            deck=deck,
            discard=discard,
            active=_other(player_id),
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
        discard: str,
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _fewest_cards_outcome(hands, "turn_limit")
        legal = [] if terminal else _shedding_legal(hands[active], discard, deck)
        return _card_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            public_state={
                "discard": discard,
                "deck_count": len(deck),
                "hand_counts": _hand_counts(hands),
                "history": history,
            },
            private_state=_private_state(hands, deck),
            legal={player: (legal if player == active else []) for player in self.players},
            scores=_winner_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="card-table",
        )

    def _playable_cards_for_blocked(self, hand: list[str], discard: str) -> list[str]:
        return _playable_cards(hand, discard)


class CrazyEightsArena(SheddingCardGameArena):
    id = "crazy-eights"
    action_schema = {
        "type": "string",
        "description": "Play a matching card or any eight as play:<card>, draw, or pass.",
    }

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed + 97)
        hands = {"player_1": sorted(deck[:5]), "player_2": sorted(deck[5:10])}
        discard = next(card for card in deck[10:] if _rank(card) != "8")
        deck.remove(discard)
        for card in hands["player_1"] + hands["player_2"]:
            if card in deck:
                deck.remove(card)
        return self._state(
            hands=hands,
            deck=deck,
            discard=discard,
            active="player_1",
            turn=0,
            seed=seed,
            history=[],
            outcome=None,
        )

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        deck: list[str],
        discard: str,
        active: str,
        turn: int,
        seed: int,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _fewest_cards_outcome(hands, "turn_limit")
        legal = [] if terminal else _crazy_eights_legal(hands[active], discard, deck)
        return _card_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            public_state={
                "discard": discard,
                "deck_count": len(deck),
                "hand_counts": _hand_counts(hands),
                "wild_rank": "8",
                "history": history,
            },
            private_state=_private_state(hands, deck),
            legal={player: (legal if player == active else []) for player in self.players},
            scores=_winner_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="card-table",
        )

    def _playable_cards_for_blocked(self, hand: list[str], discard: str) -> list[str]:
        return _crazy_eights_playable_cards(hand, discard)


class HeartsArena(Arena):
    id = "hearts"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {"type": "string", "description": "Play a card as play:<card>."}
    max_turns = 26

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed)
        hands = {"player_1": sorted(deck[:13]), "player_2": sorted(deck[13:26])}
        return self._state(
            hands=hands,
            active="player_1",
            turn=0,
            seed=seed,
            current_trick=[],
            penalties={"player_1": 0, "player_2": 0},
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _trick_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal hearts action")
        card = action.split(":", 1)[1]
        hands = _hands_from_state(state)
        hands[player_id].remove(card)
        penalties = dict(state.public_state["penalties"])
        current_trick = list(state.public_state["current_trick"])
        history = list(state.public_state["trick_history"])
        current_trick.append({"player": player_id, "card": card})
        active = _other(player_id)
        if len(current_trick) == 2:
            winner = _trick_winner(current_trick, trump=None)
            trick_penalty = sum(_heart_penalty(play["card"]) for play in current_trick)
            penalties[winner] += trick_penalty
            history.append({"winner": winner, "cards": current_trick, "penalty": trick_penalty})
            current_trick = []
            active = winner
        outcome = _trick_game_outcome(hands, penalties, lower_is_better=True)
        return self._state(
            hands=hands,
            active=active,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            current_trick=current_trick,
            penalties=penalties,
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        active: str,
        turn: int,
        seed: int,
        current_trick: list[dict[str, str]],
        penalties: dict[str, int],
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        return _trick_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            hands=hands,
            current_trick=current_trick,
            scores_public=penalties,
            history=history,
            outcome=outcome,
            max_turns=self.max_turns,
            legal_cards=_follow_suit_legal(hands[active], current_trick),
            score_fn=_winner_scores,
        )


class SpadesArena(Arena):
    id = "spades"
    version = "1.0.0"
    players = PLAYERS
    action_schema = {"type": "string", "description": "Play a card as play:<card>; spades trump."}
    max_turns = 26

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed + 31)
        hands = {"player_1": sorted(deck[:13]), "player_2": sorted(deck[13:26])}
        return self._state(
            hands=hands,
            active="player_1",
            turn=0,
            seed=seed,
            current_trick=[],
            tricks={"player_1": 0, "player_2": 0},
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return _trick_observation(state, player_id)

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal spades action")
        card = action.split(":", 1)[1]
        hands = _hands_from_state(state)
        hands[player_id].remove(card)
        tricks = dict(state.public_state["tricks"])
        current_trick = list(state.public_state["current_trick"])
        history = list(state.public_state["trick_history"])
        current_trick.append({"player": player_id, "card": card})
        active = _other(player_id)
        if len(current_trick) == 2:
            winner = _trick_winner(current_trick, trump="S")
            tricks[winner] += 1
            history.append({"winner": winner, "cards": current_trick})
            current_trick = []
            active = winner
        outcome = _trick_game_outcome(hands, tricks, lower_is_better=False)
        return self._state(
            hands=hands,
            active=active,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            current_trick=current_trick,
            tricks=tricks,
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        hands: dict[str, list[str]],
        active: str,
        turn: int,
        seed: int,
        current_trick: list[dict[str, str]],
        tricks: dict[str, int],
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        return _trick_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            hands=hands,
            current_trick=current_trick,
            scores_public=tricks,
            history=history,
            outcome=outcome,
            max_turns=self.max_turns,
            legal_cards=_follow_suit_legal(hands[active], current_trick),
            score_fn=_winner_scores,
            scores_label="tricks",
        )


def _deck(seed: int) -> list[str]:
    return standard_deck(seed)


def _card_state(
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


def _trick_state(
    *,
    arena_id: str,
    turn: int,
    active: str,
    seed: int,
    hands: dict[str, list[str]],
    current_trick: list[dict[str, str]],
    scores_public: dict[str, int],
    history: list[dict[str, Any]],
    outcome: dict[str, Any] | None,
    max_turns: int,
    legal_cards: list[str],
    score_fn: Any,
    scores_label: str = "penalties",
) -> ArenaState:
    terminal = outcome is not None or turn >= max_turns
    if outcome is None and terminal:
        outcome = _trick_game_outcome(
            hands,
            scores_public,
            lower_is_better=scores_label == "penalties",
            reason="turn_limit",
        )
    legal = [] if terminal else [f"play:{card}" for card in legal_cards]
    public_state = {
        "hand_counts": _hand_counts(hands),
        "current_trick": current_trick,
        "trick_history": history,
        scores_label: scores_public,
    }
    return _card_state(
        arena_id=arena_id,
        turn=turn,
        active=active,
        seed=seed,
        public_state=public_state,
        private_state=_private_state(hands, []),
        legal={player: (legal if player == active else []) for player in PLAYERS},
        scores=score_fn(outcome),
        terminal=terminal,
        outcome=outcome,
        renderer="trick-card-table",
    )


def _shedding_observation(state: ArenaState, player_id: str) -> dict[str, Any]:
    return {
        "you_are": player_id,
        "hand": state.private_state_by_player[player_id]["hand"],
        "discard": state.public_state["discard"],
        "deck_count": state.public_state["deck_count"],
        "hand_counts": state.public_state["hand_counts"],
        "legal_actions": state.legal_actions_by_player[player_id],
        "scores": state.scores,
    }


def _trick_observation(state: ArenaState, player_id: str) -> dict[str, Any]:
    return {
        "you_are": player_id,
        "hand": state.private_state_by_player[player_id]["hand"],
        "hand_counts": state.public_state["hand_counts"],
        "current_trick": state.public_state["current_trick"],
        "trick_history": state.public_state["trick_history"],
        "legal_actions": state.legal_actions_by_player[player_id],
        "scores": state.scores,
    }


def _private_state(hands: dict[str, list[str]], deck: list[str]) -> dict[str, dict[str, Any]]:
    return {player: {"hand": list(hands[player]), "deck": list(deck)} for player in PLAYERS}


def _hands_from_state(state: ArenaState) -> dict[str, list[str]]:
    return {player: list(state.private_state_by_player[player]["hand"]) for player in PLAYERS}


def _hand_counts(hands: dict[str, list[str]]) -> dict[str, int]:
    return {player: len(cards) for player, cards in hands.items()}


def _shedding_legal(hand: list[str], discard: str, deck: list[str]) -> list[str]:
    playable = [f"play:{card}" for card in _playable_cards(hand, discard)]
    if playable:
        return playable
    return ["draw"] if deck else ["pass"]


def _crazy_eights_legal(hand: list[str], discard: str, deck: list[str]) -> list[str]:
    playable = [f"play:{card}" for card in _crazy_eights_playable_cards(hand, discard)]
    if playable:
        return playable
    return ["draw"] if deck else ["pass"]


def _crazy_eights_playable_cards(hand: list[str], discard: str) -> list[str]:
    return [
        card
        for card in hand
        if _rank(card) == "8" or _rank(card) == _rank(discard) or _suit(card) == _suit(discard)
    ]


def _playable_cards(hand: list[str], discard: str) -> list[str]:
    return [card for card in hand if _rank(card) == _rank(discard) or _suit(card) == _suit(discard)]


def _follow_suit_legal(hand: list[str], current_trick: list[dict[str, str]]) -> list[str]:
    if not current_trick:
        return list(hand)
    led_suit = _suit(current_trick[0]["card"])
    suited = [card for card in hand if _suit(card) == led_suit]
    return suited or list(hand)


def _trick_winner(current_trick: list[dict[str, str]], trump: str | None) -> str:
    led_suit = _suit(current_trick[0]["card"])

    def key(play: dict[str, str]) -> tuple[int, int]:
        card = play["card"]
        if trump and _suit(card) == trump:
            return (2, _rank_value(card))
        if _suit(card) == led_suit:
            return (1, _rank_value(card))
        return (0, _rank_value(card))

    return max(current_trick, key=key)["player"]


def _trick_game_outcome(
    hands: dict[str, list[str]],
    scores: dict[str, int],
    *,
    lower_is_better: bool,
    reason: str = "hands_empty",
) -> dict[str, Any] | None:
    if any(hands[player] for player in PLAYERS):
        return None
    first = scores["player_1"]
    second = scores["player_2"]
    if first == second:
        winner = None
    elif lower_is_better:
        winner = "player_1" if first < second else "player_2"
    else:
        winner = "player_1" if first > second else "player_2"
    return {"winner": winner, "reason": reason, "totals": dict(scores)}


def _empty_hand_outcome(hands: dict[str, list[str]], player_id: str) -> dict[str, Any] | None:
    if hands[player_id]:
        return None
    return {"winner": player_id, "reason": "empty_hand", "hand_counts": _hand_counts(hands)}


def _fewest_cards_outcome(hands: dict[str, list[str]], reason: str) -> dict[str, Any]:
    counts = _hand_counts(hands)
    if counts["player_1"] == counts["player_2"]:
        winner = None
    else:
        winner = "player_1" if counts["player_1"] < counts["player_2"] else "player_2"
    return {"winner": winner, "reason": reason, "hand_counts": counts}


def _winner_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}


def _heart_penalty(card: str) -> int:
    if card == "QS":
        return 13
    return 1 if _suit(card) == "H" else 0


def _rank(card: str) -> str:
    return card_rank(card)


def _suit(card: str) -> str:
    return card_suit(card)


def _rank_value(card: str) -> int:
    return rank_value(card)


def _card_sort_key(card: str) -> tuple[int, int]:
    return card_sort_key(card)


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
