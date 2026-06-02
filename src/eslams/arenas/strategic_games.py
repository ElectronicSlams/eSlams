"""Deterministic private-state and game-theory arenas."""

from __future__ import annotations

import random
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState


class BlackjackArena(Arena):
    id = "blackjack"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "enum": ["hit", "stand"],
        "description": "Player action. Dealer policy is deterministic: hit until 17.",
    }
    max_turns = 12

    def initial_state(self, seed: int) -> ArenaState:
        deck = _deck(seed)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        return self._state(
            player_hand=player,
            dealer_hand=dealer,
            deck=deck,
            turn=0,
            seed=seed,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "player_hand": state.public_state["player_hand"],
            "dealer_upcard": state.public_state["dealer_upcard"],
            "player_total": _hand_value(state.public_state["player_hand"]),
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if player_id != "player_1":
            raise ValueError("blackjack dealer is controlled by arena policy")
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal blackjack action")
        player_hand = list(state.public_state["player_hand"])
        dealer_hand = list(state.private_state_by_player["player_2"]["dealer_hand"])
        deck = list(state.private_state_by_player["player_2"]["deck"])
        outcome = None
        if action == "hit":
            player_hand.append(deck.pop())
            if _hand_value(player_hand) > 21:
                outcome = {
                    "winner": "player_2",
                    "reason": "player_bust",
                    "dealer_hand": dealer_hand,
                }
        else:
            while _hand_value(dealer_hand) < 17 and deck:
                dealer_hand.append(deck.pop())
            outcome = _blackjack_outcome(player_hand, dealer_hand)
        return self._state(
            player_hand=player_hand,
            dealer_hand=dealer_hand,
            deck=deck,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        player_hand: list[int],
        dealer_hand: list[int],
        deck: list[int],
        turn: int,
        seed: int,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _blackjack_outcome(player_hand, dealer_hand, reason="max_turns")
        public_dealer = dealer_hand if terminal else [dealer_hand[0]]
        legal = [] if terminal else ["hit", "stand"]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player="player_1",
            public_state={
                "player_hand": player_hand,
                "dealer_upcard": dealer_hand[0],
                "dealer_hand": public_dealer,
            },
            private_state_by_player={
                "player_1": {},
                "player_2": {"dealer_hand": dealer_hand, "deck": deck},
            },
            legal_actions_by_player={"player_1": legal, "player_2": []},
            scores=_win_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"blackjack:{seed}"),
            render_hints={"renderer": "card-table"},
            metadata={"seed": seed},
        )


class FirstPriceSealedBidAuctionArena(Arena):
    id = "first-price-sealed-bid-auction"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 0,
        "maximum": 10,
        "description": "Submit a sealed integer bid from 0 to 10.",
    }
    max_turns = 2

    def initial_state(self, seed: int) -> ArenaState:
        valuations = {"player_1": 6 + seed % 5, "player_2": 6 + (seed * 3) % 5}
        return self._state(
            turn=0,
            active="player_1",
            seed=seed,
            valuations=valuations,
            pending_bid=None,
            revealed=None,
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "private_value": state.private_state_by_player[player_id]["valuation"],
            "item": state.public_state["item"],
            "revealed_bids": state.public_state["revealed_bids"],
            "legal_bids": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal auction bid")
        valuations = {
            player: int(private["valuation"])
            for player, private in state.private_state_by_player.items()
        }
        if player_id == "player_1":
            return self._state(
                turn=state.turn + 1,
                active="player_2",
                seed=int(state.metadata["seed"]),
                valuations=valuations,
                pending_bid=action,
                revealed=None,
                outcome=None,
            )
        first_bid = int(state.private_state_by_player["player_1"]["pending_bid"])
        bids = {"player_1": first_bid, "player_2": action}
        winner = "player_1" if bids["player_1"] >= bids["player_2"] else "player_2"
        utilities = {
            player: float(max(0, valuations[player] - bids[player])) if player == winner else 0.0
            for player in self.players
        }
        outcome = {
            "winner": winner,
            "reason": "highest_bid",
            "bids": bids,
            "valuations": valuations,
            "utilities": utilities,
        }
        return self._state(
            turn=state.turn + 1,
            active="player_1",
            seed=int(state.metadata["seed"]),
            valuations=valuations,
            pending_bid=None,
            revealed=bids,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        valuations: dict[str, int],
        pending_bid: int | None,
        revealed: dict[str, int] | None,
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None
        legal = [] if terminal else list(range(11))
        private = {
            player: {"valuation": valuations[player]}
            for player in self.players
        }
        if pending_bid is not None:
            private["player_1"]["pending_bid"] = pending_bid
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"item": "single_item", "revealed_bids": revealed or {}},
            private_state_by_player=private,
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_utility_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"first-price-sealed-bid-auction:{seed}"),
            render_hints={"renderer": "auction-table"},
            metadata={"seed": seed},
        )


class GoofspielArena(Arena):
    id = "goofspiel"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "integer",
        "minimum": 1,
        "maximum": 5,
        "description": "Bid one remaining card for the current prize.",
    }
    max_turns = 10

    def initial_state(self, seed: int) -> ArenaState:
        prizes = [1, 2, 3, 4, 5]
        random.Random(seed).shuffle(prizes)
        return self._state(
            turn=0,
            active="player_1",
            seed=seed,
            prizes=prizes,
            hands={"player_1": [1, 2, 3, 4, 5], "player_2": [1, 2, 3, 4, 5]},
            scores={"player_1": 0, "player_2": 0},
            pending_bid=None,
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "current_prize": state.public_state["current_prize"],
            "remaining_hand": state.private_state_by_player[player_id]["hand"],
            "round_history": state.public_state["round_history"],
            "legal_bids": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, int) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal goofspiel bid")
        prizes = list(state.private_state_by_player["player_1"]["prizes"])
        hands = {
            player: list(private["hand"])
            for player, private in state.private_state_by_player.items()
        }
        scores = {player: int(value) for player, value in state.public_state["points"].items()}
        history = list(state.public_state["round_history"])
        hands[player_id].remove(action)
        if player_id == "player_1":
            return self._state(
                turn=state.turn + 1,
                active="player_2",
                seed=int(state.metadata["seed"]),
                prizes=prizes,
                hands=hands,
                scores=scores,
                pending_bid=action,
                history=history,
                outcome=None,
            )
        first_bid = int(state.private_state_by_player["player_1"]["pending_bid"])
        prize = prizes.pop(0)
        winner = None
        if first_bid > action:
            scores["player_1"] += prize
            winner = "player_1"
        elif action > first_bid:
            scores["player_2"] += prize
            winner = "player_2"
        history.append(
            {
                "prize": prize,
                "bids": {"player_1": first_bid, "player_2": action},
                "winner": winner,
            }
        )
        outcome = _point_total_outcome(scores, "all_prizes_awarded") if not prizes else None
        return self._state(
            turn=state.turn + 1,
            active="player_1",
            seed=int(state.metadata["seed"]),
            prizes=prizes,
            hands=hands,
            scores=scores,
            pending_bid=None,
            history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        prizes: list[int],
        hands: dict[str, list[int]],
        scores: dict[str, int],
        pending_bid: int | None,
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None
        current_prize = prizes[0] if prizes else None
        private: dict[str, dict[str, Any]] = {
            player: {"hand": hands[player], "prizes": list(prizes)}
            for player in self.players
        }
        if pending_bid is not None:
            private["player_1"]["pending_bid"] = pending_bid
        legal = [] if terminal else list(hands[active])
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "current_prize": current_prize,
                "points": scores,
                "round_history": history,
            },
            private_state_by_player=private,
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_point_scores(outcome, total=15),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"goofspiel:{seed}"),
            render_hints={"renderer": "card-table"},
            metadata={"seed": seed},
        )


class LiarsDiceArena(Arena):
    id = "liars-dice"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^(challenge|[1-9][0-9]*x[1-6])$",
        "description": "Raise a bid like '3x5' or challenge the previous bid.",
    }
    max_turns = 20

    def initial_state(self, seed: int) -> ArenaState:
        rng = random.Random(seed)
        dice = {
            "player_1": [rng.randint(1, 6) for _ in range(5)],
            "player_2": [rng.randint(1, 6) for _ in range(5)],
        }
        return self._state(
            turn=0,
            active="player_1",
            seed=seed,
            dice=dice,
            current_bid=None,
            bid_history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "your_dice": state.private_state_by_player[player_id]["dice"],
            "dice_per_player": 5,
            "current_bid": state.public_state["current_bid"],
            "bid_history": state.public_state["bid_history"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal liar's dice action")
        dice = {
            player: list(private["dice"])
            for player, private in state.private_state_by_player.items()
        }
        current_bid = state.public_state["current_bid"]
        history = list(state.public_state["bid_history"])
        outcome = None
        if action == "challenge":
            if not isinstance(current_bid, dict):
                raise ValueError("cannot challenge without a bid")
            count = sum(
                die == int(current_bid["face"])
                for values in dice.values()
                for die in values
            )
            bidder = str(current_bid["player"])
            challenger = player_id
            winner = bidder if count >= int(current_bid["count"]) else challenger
            outcome = {
                "winner": winner,
                "reason": "challenge_resolved",
                "bid": current_bid,
                "actual_count": count,
                "dice": dice,
            }
        else:
            count, face = _parse_bid(action)
            current_bid = {"player": player_id, "count": count, "face": face}
            history.append(current_bid)
        return self._state(
            turn=state.turn + 1,
            active=_other(player_id),
            seed=int(state.metadata["seed"]),
            dice=dice,
            current_bid=current_bid if outcome is None else current_bid,
            bid_history=history,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        dice: dict[str, list[int]],
        current_bid: dict[str, Any] | None,
        bid_history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        if outcome is None and turn >= self.max_turns:
            outcome = {"winner": None, "reason": "max_turns", "dice": dice}
        terminal = outcome is not None
        legal = [] if terminal else _liars_dice_legal_actions(current_bid)
        public_dice = dice if terminal else {}
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={
                "current_bid": current_bid,
                "bid_history": bid_history,
                "revealed_dice": public_dice,
            },
            private_state_by_player={player: {"dice": dice[player]} for player in self.players},
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_win_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"liars-dice:{seed}"),
            render_hints={"renderer": "dice-table"},
            metadata={"seed": seed},
        )


class BargainingArena(Arena):
    id = "bargaining"
    version = "1.0.0"
    players = ("player_1", "player_2")
    action_schema = {
        "type": "string",
        "pattern": "^(accept|reject|offer:(0|10|20|30|40|50|60|70|80|90|100))$",
        "description": "Offer a player_1 share in increments of 10, accept, or reject.",
    }
    max_turns = 8

    def initial_state(self, seed: int) -> ArenaState:
        reserves = {"player_1": 20 + (seed % 3) * 10, "player_2": 20 + (seed % 4) * 10}
        return self._state(
            turn=0,
            active="player_1",
            seed=seed,
            reserves=reserves,
            last_offer=None,
            transcript=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "private_reserve_share": state.private_state_by_player[player_id]["reserve_share"],
            "last_offer": state.public_state["last_offer"],
            "transcript": state.public_state["transcript"],
            "legal_actions": state.legal_actions_by_player[player_id],
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal bargaining action")
        reserves = {
            player: int(private["reserve_share"])
            for player, private in state.private_state_by_player.items()
        }
        last_offer = state.public_state["last_offer"]
        transcript = list(state.public_state["transcript"])
        outcome = None
        if action == "accept" and isinstance(last_offer, dict):
            outcome = _split_outcome(int(last_offer["player_1_share"]), "accepted")
        elif action == "reject":
            outcome = _no_deal_outcome("rejected")
        else:
            share = int(action.split(":", 1)[1])
            last_offer = {"player": player_id, "player_1_share": share}
            transcript.append(last_offer)
        next_active = _other(player_id)
        if outcome is None and state.turn + 1 >= self.max_turns:
            outcome = _no_deal_outcome("deadline")
        return self._state(
            turn=state.turn + 1,
            active=next_active,
            seed=int(state.metadata["seed"]),
            reserves=reserves,
            last_offer=last_offer,
            transcript=transcript,
            outcome=outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        reserves: dict[str, int],
        last_offer: dict[str, Any] | None,
        transcript: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None
        legal = [] if terminal else [f"offer:{share}" for share in range(0, 101, 10)]
        if not terminal and last_offer and last_offer.get("player") != active:
            legal = ["accept", "reject", *legal]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"last_offer": last_offer, "transcript": transcript},
            private_state_by_player={
                player: {"reserve_share": reserves[player]} for player in self.players
            },
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_utility_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"bargaining:{seed}"),
            render_hints={"renderer": "negotiation-table"},
            metadata={"seed": seed},
        )


class NegotiationArena(BargainingArena):
    id = "negotiation"
    version = "1.0.0"
    action_schema = {
        "type": "string",
        "pattern": "^(accept|reject|offer:(20|40|60|80|100):(1|2|3))$",
        "description": "Offer price and delivery speed, e.g. 'offer:60:2'.",
    }
    max_turns = 8

    def initial_state(self, seed: int) -> ArenaState:
        reserves = {"player_1": 40, "player_2": 40 + (seed % 3) * 10}
        return self._state(
            turn=0,
            active="player_1",
            seed=seed,
            reserves=reserves,
            last_offer=None,
            transcript=[],
            outcome=None,
        )

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal negotiation action")
        reserves = {
            player: int(private["reserve_share"])
            for player, private in state.private_state_by_player.items()
        }
        last_offer = state.public_state["last_offer"]
        transcript = list(state.public_state["transcript"])
        outcome = None
        if action == "accept" and isinstance(last_offer, dict):
            outcome = _negotiation_outcome(
                price=int(last_offer["price"]),
                delivery=int(last_offer["delivery"]),
            )
        elif action == "reject":
            outcome = _no_deal_outcome("rejected")
        else:
            _, raw_price, raw_delivery = action.split(":")
            last_offer = {
                "player": player_id,
                "price": int(raw_price),
                "delivery": int(raw_delivery),
            }
            transcript.append(last_offer)
        if outcome is None and state.turn + 1 >= self.max_turns:
            outcome = _no_deal_outcome("deadline")
        return self._state(
            turn=state.turn + 1,
            active=_other(player_id),
            seed=int(state.metadata["seed"]),
            reserves=reserves,
            last_offer=last_offer,
            transcript=transcript,
            outcome=outcome,
        )

    def _state(
        self,
        *,
        turn: int,
        active: str,
        seed: int,
        reserves: dict[str, int],
        last_offer: dict[str, Any] | None,
        transcript: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None
        offers = [
            f"offer:{price}:{delivery}"
            for price in (20, 40, 60, 80, 100)
            for delivery in (1, 2, 3)
        ]
        legal = [] if terminal else offers
        if not terminal and last_offer and last_offer.get("player") != active:
            legal = ["accept", "reject", *offers]
        return ArenaState(
            state_id=f"state_{turn:06d}",
            turn=turn,
            active_player=active,
            public_state={"last_offer": last_offer, "transcript": transcript},
            private_state_by_player={
                player: {"reserve_share": reserves[player]} for player in self.players
            },
            legal_actions_by_player={
                player: (legal if player == active else []) for player in self.players
            },
            scores=_utility_scores(outcome),
            terminal=terminal,
            outcome=outcome,
            rng_commitment=sha256_text(f"negotiation:{seed}"),
            render_hints={"renderer": "negotiation-table"},
            metadata={"seed": seed},
        )


def _deck(seed: int) -> list[int]:
    ranks = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    rng = random.Random(seed)
    rng.shuffle(ranks)
    return ranks


def _hand_value(hand: list[int]) -> int:
    total = sum(hand)
    aces = sum(card == 11 for card in hand)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _blackjack_outcome(
    player_hand: list[int],
    dealer_hand: list[int],
    *,
    reason: str = "stand",
) -> dict[str, Any]:
    player_total = _hand_value(player_hand)
    dealer_total = _hand_value(dealer_hand)
    winner = None
    if dealer_total > 21 or player_total > dealer_total:
        winner = "player_1"
    elif dealer_total > player_total:
        winner = "player_2"
    return {
        "winner": winner,
        "reason": "dealer_bust" if dealer_total > 21 else reason,
        "player_total": player_total,
        "dealer_total": dealer_total,
        "dealer_hand": dealer_hand,
    }


def _liars_dice_legal_actions(current_bid: dict[str, Any] | None) -> list[str]:
    actions: list[str] = []
    min_count = 1
    min_face = 1
    if current_bid:
        actions.append("challenge")
        min_count = int(current_bid["count"])
        min_face = int(current_bid["face"]) + 1
    for count in range(min_count, 11):
        for face in range(1, 7):
            if current_bid and count == min_count and face < min_face:
                continue
            actions.append(f"{count}x{face}")
    return actions


def _parse_bid(action: str) -> tuple[int, int]:
    raw_count, raw_face = action.split("x")
    count = int(raw_count)
    face = int(raw_face)
    if count < 1 or face not in range(1, 7):
        raise ValueError("invalid liar's dice bid")
    return count, face


def _split_outcome(player_1_share: int, reason: str) -> dict[str, Any]:
    utilities = {
        "player_1": float(player_1_share),
        "player_2": float(100 - player_1_share),
    }
    winner = None
    if utilities["player_1"] > utilities["player_2"]:
        winner = "player_1"
    elif utilities["player_2"] > utilities["player_1"]:
        winner = "player_2"
    return {
        "winner": winner,
        "reason": reason,
        "player_1_share": player_1_share,
        "utilities": utilities,
    }


def _negotiation_outcome(price: int, delivery: int) -> dict[str, Any]:
    buyer_utility = max(0.0, float(120 - price - delivery * 10))
    seller_utility = max(0.0, float(price - 20 + (3 - delivery) * 5))
    winner = None
    if buyer_utility > seller_utility:
        winner = "player_1"
    elif seller_utility > buyer_utility:
        winner = "player_2"
    return {
        "winner": winner,
        "reason": "accepted",
        "price": price,
        "delivery": delivery,
        "utilities": {"player_1": buyer_utility, "player_2": seller_utility},
    }


def _no_deal_outcome(reason: str) -> dict[str, Any]:
    return {"winner": None, "reason": reason, "utilities": {"player_1": 0, "player_2": 0}}


def _point_total_outcome(scores: dict[str, int], reason: str) -> dict[str, Any]:
    winner = None
    if scores["player_1"] > scores["player_2"]:
        winner = "player_1"
    elif scores["player_2"] > scores["player_1"]:
        winner = "player_2"
    return {"winner": winner, "reason": reason, "points": dict(scores)}


def _point_scores(outcome: dict[str, Any] | None, *, total: int) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    points = outcome.get("points")
    if not isinstance(points, dict):
        return _win_scores(outcome)
    return {
        "player_1": float(points["player_1"]) / total,
        "player_2": float(points["player_2"]) / total,
    }


def _utility_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    utilities = outcome.get("utilities")
    if not isinstance(utilities, dict):
        return _win_scores(outcome)
    total = float(utilities["player_1"]) + float(utilities["player_2"])
    if total <= 0:
        return {"player_1": 0.0, "player_2": 0.0}
    return {
        "player_1": float(utilities["player_1"]) / total,
        "player_2": float(utilities["player_2"]) / total,
    }


def _win_scores(outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return {"player_1": 0.0, "player_2": 0.0}
    if outcome.get("winner") is None:
        return {"player_1": 0.5, "player_2": 0.5}
    winner = str(outcome["winner"])
    loser = _other(winner)
    return {winner: 1.0, loser: 0.0}


def _other(player_id: str) -> str:
    return "player_2" if player_id == "player_1" else "player_1"
