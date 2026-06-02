"""Compact deterministic tile/card catalogue arenas."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from eslams.arena import Arena
from eslams.hashing import sha256_text
from eslams.state import ArenaState

MAHJONG_PLAYERS = ("player_1", "player_2", "player_3", "player_4")
DOU_DIZHU_PLAYERS = ("player_1", "player_2", "player_3")
BRIDGE_PLAYERS = ("player_1", "player_2", "player_3", "player_4")

CARD_RANKS = ("3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A", "2")
CARD_SUITS = ("C", "D", "H", "S")
BRIDGE_RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
BRIDGE_SUITS = ("C", "D", "H", "S")
BRIDGE_ORDER = {rank: index for index, rank in enumerate(BRIDGE_RANKS)}
DOU_DIZHU_ORDER = {rank: index for index, rank in enumerate(CARD_RANKS + ("BJ", "RJ"))}


class MahjongArena(Arena):
    """Two-deck, four-player draw-discard Mahjong adapter."""

    id = "mahjong"
    version = "1.0.0"
    players = MAHJONG_PLAYERS
    action_schema = {
        "type": "string",
        "description": "Declare mahjong or discard one tile as discard:<tile>.",
    }
    max_turns = 96

    def initial_state(self, seed: int) -> ArenaState:
        wall = _mahjong_wall(seed)
        hands = {
            player: _sorted_tiles(wall[index * 10 : (index + 1) * 10])
            for index, player in enumerate(self.players)
        }
        wall = wall[40:]
        hands["player_1"].append(wall.pop(0))
        hands["player_1"] = _sorted_tiles(hands["player_1"])
        return self._state(hands, wall, "player_1", 0, seed, [], None)

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "hand": state.private_state_by_player[player_id]["hand"],
            "wall_count": state.public_state["wall_count"],
            "discard_pile": state.public_state["discard_pile"],
            "hand_counts": state.public_state["hand_counts"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal mahjong action")
        hands = _hands_from_private(state, self.players, "hand")
        wall = list(state.private_state_by_player[player_id]["wall"])
        discard_pile = list(state.public_state["discard_pile"])
        outcome: dict[str, Any] | None = None
        active = _next_player(self.players, player_id)

        if action == "mahjong":
            outcome = {
                "winner": player_id,
                "reason": "complete_hand",
                "hand": list(hands[player_id]),
            }
        else:
            tile = action.split(":", 1)[1]
            hands[player_id].remove(tile)
            discard_pile.append({"player": player_id, "tile": tile})
            if wall:
                hands[active].append(wall.pop(0))
                hands[active] = _sorted_tiles(hands[active])
            elif _all_players_at_base_count(hands, expected=10):
                outcome = _mahjong_deadwood_outcome(hands, "wall_exhausted")

        return self._state(
            hands,
            wall,
            active,
            state.turn + 1,
            int(state.metadata["seed"]),
            discard_pile,
            outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        hands: dict[str, list[str]],
        wall: list[str],
        active: str,
        turn: int,
        seed: int,
        discard_pile: list[dict[str, str]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _mahjong_deadwood_outcome(hands, "turn_limit")
            terminal = True
        legal = [] if terminal else _mahjong_legal(hands[active])
        return _hidden_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            players=self.players,
            public_state={
                "wall_count": len(wall),
                "discard_pile": discard_pile,
                "hand_counts": {player: len(hands[player]) for player in self.players},
            },
            private_state={
                player: {"hand": list(hands[player]), "wall": list(wall)}
                for player in self.players
            },
            legal={player: (legal if player == active else []) for player in self.players},
            scores=_winner_scores(self.players, outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="tile-table",
        )


class DouDizhuArena(Arena):
    """Three-player Dou Dizhu shedding adapter with legal combination safety."""

    id = "dou-dizhu"
    version = "1.0.0"
    players = DOU_DIZHU_PLAYERS
    action_schema = {
        "type": "string",
        "description": (
            "Play a legal combination as play:<card,...> or pass when contesting a trick."
        ),
    }
    max_turns = 120

    def initial_state(self, seed: int) -> ArenaState:
        deck = _dou_dizhu_deck(seed)
        landlord = self.players[seed % len(self.players)]
        hands = {
            player: _sorted_dou_cards(deck[index * 17 : (index + 1) * 17])
            for index, player in enumerate(self.players)
        }
        kitty = deck[51:]
        hands[landlord] = _sorted_dou_cards(hands[landlord] + kitty)
        return self._state(
            hands=hands,
            active=landlord,
            turn=0,
            seed=seed,
            landlord=landlord,
            last_play=None,
            last_owner=None,
            passes=[],
            history=[],
            outcome=None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "role": "landlord" if player_id == state.public_state["landlord"] else "farmer",
            "hand": state.private_state_by_player[player_id]["hand"],
            "hand_counts": state.public_state["hand_counts"],
            "last_play": state.public_state["last_play"],
            "passes": state.public_state["passes"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal dou-dizhu action")
        hands = _hands_from_private(state, self.players, "hand")
        history = list(state.public_state["history"])
        landlord = str(state.public_state["landlord"])
        last_play = _copy_last_play(state.public_state["last_play"])
        last_owner = state.public_state["last_owner"]
        passes = list(state.public_state["passes"])
        outcome: dict[str, Any] | None = None

        if action == "pass":
            passes.append(player_id)
            if len(passes) >= len(self.players) - 1 and last_owner:
                active = str(last_owner)
                last_play = None
                passes = []
            else:
                active = _next_player(self.players, player_id)
        else:
            cards = action.split(":", 1)[1].split(",")
            for card in cards:
                hands[player_id].remove(card)
            combination = _dou_combination(cards)
            if combination is None:
                raise ValueError("illegal dou-dizhu combination")
            last_play = {
                "player": player_id,
                "cards": _sorted_dou_cards(cards),
                "kind": combination[0],
                "rank": combination[1],
            }
            last_owner = player_id
            passes = []
            active = _next_player(self.players, player_id)
            if not hands[player_id]:
                winner_role = "landlord" if player_id == landlord else "farmers"
                outcome = {"winner": player_id, "winner_role": winner_role, "reason": "empty_hand"}

        history.append({"player": player_id, "action": action, "remaining": len(hands[player_id])})
        return self._state(
            hands=hands,
            active=active,
            turn=state.turn + 1,
            seed=int(state.metadata["seed"]),
            landlord=landlord,
            last_play=last_play,
            last_owner=last_owner,
            passes=passes,
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
        landlord: str,
        last_play: dict[str, Any] | None,
        last_owner: str | None,
        passes: list[str],
        history: list[dict[str, Any]],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _dou_dizhu_count_outcome(hands, landlord)
            terminal = True
        legal = [] if terminal else _dou_legal_actions(hands[active], last_play, active, last_owner)
        return _hidden_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            players=self.players,
            public_state={
                "landlord": landlord,
                "hand_counts": {player: len(hands[player]) for player in self.players},
                "last_play": last_play,
                "last_owner": last_owner,
                "passes": passes,
                "history": history,
            },
            private_state={player: {"hand": list(hands[player])} for player in self.players},
            legal={player: (legal if player == active else []) for player in self.players},
            scores=_dou_scores(self.players, landlord, outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="card-table",
        )


class BridgeArena(Arena):
    """Four-player contract-bridge play-phase adapter."""

    id = "bridge"
    version = "1.0.0"
    players = BRIDGE_PLAYERS
    action_schema = {
        "type": "string",
        "description": "Play a legal card as play:<card>, following suit when able.",
    }
    max_turns = 52

    def initial_state(self, seed: int) -> ArenaState:
        deck = _standard_deck(seed)
        hands = {
            player: _sorted_bridge_cards(deck[index * 13 : (index + 1) * 13])
            for index, player in enumerate(self.players)
        }
        contract = _bridge_contract(seed)
        declarer = self.players[seed % len(self.players)]
        active = _next_player(self.players, declarer)
        return self._state(
            hands,
            active,
            0,
            seed,
            contract,
            declarer,
            [],
            [],
            {"NS": 0, "EW": 0},
            None,
        )

    def observation_for(self, state: ArenaState, player_id: str) -> dict[str, Any]:
        return {
            "you_are": player_id,
            "partnership": _bridge_side(player_id),
            "hand": state.private_state_by_player[player_id]["hand"],
            "contract": state.public_state["contract"],
            "declarer": state.public_state["declarer"],
            "current_trick": state.public_state["current_trick"],
            "trick_history": state.public_state["trick_history"],
            "tricks": state.public_state["tricks"],
            "hand_counts": state.public_state["hand_counts"],
            "legal_actions": state.legal_actions_by_player[player_id],
            "scores": state.scores,
        }

    def apply_action(self, state: ArenaState, player_id: str, action: Any) -> ArenaState:
        if not isinstance(action, str) or not self.is_legal(state, player_id, action):
            raise ValueError("illegal bridge action")
        hands = _hands_from_private(state, self.players, "hand")
        card = action.split(":", 1)[1]
        hands[player_id].remove(card)
        current_trick = list(state.public_state["current_trick"])
        history = list(state.public_state["trick_history"])
        tricks = dict(state.public_state["tricks"])
        contract = dict(state.public_state["contract"])
        declarer = str(state.public_state["declarer"])
        current_trick.append({"player": player_id, "card": card})
        active = _next_player(self.players, player_id)

        if len(current_trick) == 4:
            winner = _bridge_trick_winner(current_trick, contract["strain"])
            side = _bridge_side(winner)
            tricks[side] += 1
            history.append({"winner": winner, "side": side, "cards": current_trick})
            current_trick = []
            active = winner

        outcome = _bridge_outcome_if_done(hands, tricks, contract, declarer)
        return self._state(
            hands,
            active,
            state.turn + 1,
            int(state.metadata["seed"]),
            contract,
            declarer,
            current_trick,
            history,
            tricks,
            outcome,
        )

    def score(self, state: ArenaState) -> dict[str, float]:
        return dict(state.scores)

    def _state(
        self,
        hands: dict[str, list[str]],
        active: str,
        turn: int,
        seed: int,
        contract: dict[str, Any],
        declarer: str,
        current_trick: list[dict[str, str]],
        history: list[dict[str, Any]],
        tricks: dict[str, int],
        outcome: dict[str, Any] | None,
    ) -> ArenaState:
        terminal = outcome is not None or turn >= self.max_turns
        if outcome is None and terminal:
            outcome = _bridge_final_outcome(tricks, contract, declarer, "turn_limit")
            terminal = True
        legal_cards = [] if terminal else _bridge_legal_cards(hands[active], current_trick)
        legal = [f"play:{card}" for card in legal_cards]
        return _hidden_state(
            arena_id=self.id,
            turn=turn,
            active=active,
            seed=seed,
            players=self.players,
            public_state={
                "contract": contract,
                "declarer": declarer,
                "current_trick": current_trick,
                "trick_history": history,
                "tricks": tricks,
                "hand_counts": {player: len(hands[player]) for player in self.players},
            },
            private_state={player: {"hand": list(hands[player])} for player in self.players},
            legal={player: (legal if player == active else []) for player in self.players},
            scores=_bridge_scores(self.players, outcome),
            terminal=terminal,
            outcome=outcome,
            renderer="trick-card-table",
        )


def _hidden_state(
    *,
    arena_id: str,
    turn: int,
    active: str,
    seed: int,
    players: Sequence[str],
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
        render_hints={"renderer": renderer, "players": list(players)},
        metadata={"seed": seed},
    )


def _standard_deck(seed: int) -> list[str]:
    cards = [f"{rank}{suit}" for suit in BRIDGE_SUITS for rank in BRIDGE_RANKS]
    random.Random(seed).shuffle(cards)
    return cards


def _mahjong_wall(seed: int) -> list[str]:
    tiles = [
        f"{suit}{value}"
        for suit in ("B", "C", "D")
        for value in range(1, 10)
        for _ in range(4)
    ]
    random.Random(seed).shuffle(tiles)
    return tiles


def _mahjong_legal(hand: list[str]) -> list[str]:
    legal = [f"discard:{tile}" for tile in sorted(set(hand), key=_tile_key)]
    if _is_compact_mahjong(hand):
        return ["mahjong"] + legal
    return legal


def _is_compact_mahjong(hand: list[str]) -> bool:
    if len(hand) != 11:
        return False
    counts = Counter(hand)
    for pair, count in list(counts.items()):
        if count < 2:
            continue
        reduced = Counter(counts)
        reduced[pair] -= 2
        if _can_make_melds(reduced):
            return True
    return False


def _can_make_melds(counts: Counter[str]) -> bool:
    remaining = sum(counts.values())
    if remaining == 0:
        return True
    tile = min((item for item, count in counts.items() if count > 0), key=_tile_key)
    if counts[tile] >= 3:
        counts[tile] -= 3
        if _can_make_melds(counts):
            counts[tile] += 3
            return True
        counts[tile] += 3
    suit, value = tile[0], int(tile[1])
    run = [f"{suit}{value + offset}" for offset in range(3)]
    if value <= 7 and all(counts.get(item, 0) > 0 for item in run):
        for item in run:
            counts[item] -= 1
        if _can_make_melds(counts):
            for item in run:
                counts[item] += 1
            return True
        for item in run:
            counts[item] += 1
    return False


def _mahjong_deadwood_outcome(hands: dict[str, list[str]], reason: str) -> dict[str, Any]:
    deadwood = {player: _mahjong_deadwood(hand) for player, hand in hands.items()}
    best = min(deadwood.values())
    winners = [player for player, value in deadwood.items() if value == best]
    return {
        "winner": winners[0] if len(winners) == 1 else None,
        "reason": reason,
        "deadwood": deadwood,
    }


def _mahjong_deadwood(hand: list[str]) -> int:
    counts = Counter(hand)
    score = 0
    for tile, count in counts.items():
        score += int(tile[1]) * count
    for tile, count in counts.items():
        if count >= 2:
            score -= int(tile[1])
    return score


def _all_players_at_base_count(hands: dict[str, list[str]], expected: int) -> bool:
    return all(len(hand) == expected for hand in hands.values())


def _dou_dizhu_deck(seed: int) -> list[str]:
    cards = [f"{rank}{suit}" for suit in CARD_SUITS for rank in CARD_RANKS]
    cards.extend(["BJ", "RJ"])
    random.Random(seed).shuffle(cards)
    return cards


def _dou_legal_actions(
    hand: list[str],
    last_play: dict[str, Any] | None,
    active: str,
    last_owner: str | None,
) -> list[str]:
    actions: list[str] = []
    baseline = None if last_owner == active else last_play
    for cards in _candidate_dou_plays(hand):
        combo = _dou_combination(cards)
        if combo and _beats(combo, baseline):
            actions.append("play:{}".format(",".join(_sorted_dou_cards(cards))))
    if baseline is not None:
        actions.append("pass")
    return sorted(actions, key=lambda item: (item == "pass", len(item), item))


def _candidate_dou_plays(hand: list[str]) -> list[list[str]]:
    by_rank: dict[str, list[str]] = {}
    for card in hand:
        by_rank.setdefault(_dou_rank(card), []).append(card)
    plays: list[list[str]] = []
    for cards in by_rank.values():
        plays.append(cards[:1])
        if len(cards) >= 2:
            plays.append(cards[:2])
        if len(cards) >= 3:
            plays.append(cards[:3])
        if len(cards) == 4:
            plays.append(cards[:4])
    if "BJ" in hand and "RJ" in hand:
        plays.append(["BJ", "RJ"])
    return plays


def _dou_combination(cards: list[str]) -> tuple[str, int] | None:
    ranks = [_dou_rank(card) for card in cards]
    counts = Counter(ranks)
    if sorted(ranks) == ["BJ", "RJ"]:
        return ("rocket", DOU_DIZHU_ORDER["RJ"])
    if len(counts) != 1:
        return None
    rank = DOU_DIZHU_ORDER[ranks[0]]
    size = len(cards)
    if size == 1:
        return ("single", rank)
    if size == 2:
        return ("pair", rank)
    if size == 3:
        return ("triple", rank)
    if size == 4:
        return ("bomb", rank)
    return None


def _beats(combo: tuple[str, int], baseline: dict[str, Any] | None) -> bool:
    if baseline is None:
        return True
    kind, rank = combo
    base_kind = str(baseline["kind"])
    base_rank = int(baseline["rank"])
    if kind == "rocket":
        return base_kind != "rocket"
    if kind == "bomb" and base_kind not in {"bomb", "rocket"}:
        return True
    return kind == base_kind and rank > base_rank


def _copy_last_play(last_play: Any) -> dict[str, Any] | None:
    return dict(last_play) if isinstance(last_play, dict) else None


def _dou_dizhu_count_outcome(hands: dict[str, list[str]], landlord: str) -> dict[str, Any]:
    landlord_count = len(hands[landlord])
    farmer_best = min(len(hand) for player, hand in hands.items() if player != landlord)
    if landlord_count <= farmer_best:
        return {"winner": landlord, "winner_role": "landlord", "reason": "turn_limit_count"}
    return {"winner": None, "winner_role": "farmers", "reason": "turn_limit_count"}


def _dou_scores(
    players: Sequence[str],
    landlord: str,
    outcome: dict[str, Any] | None,
) -> dict[str, float]:
    if outcome is None:
        return dict.fromkeys(players, 0.0)
    role = outcome.get("winner_role")
    if role == "landlord":
        return {player: (1.0 if player == landlord else 0.0) for player in players}
    if role == "farmers":
        return {player: (0.0 if player == landlord else 1.0) for player in players}
    return _winner_scores(players, outcome)


def _bridge_contract(seed: int) -> dict[str, Any]:
    strains = ("S", "H", "D", "C", "NT")
    level = 2 + (seed % 3)
    strain = strains[(seed // 3) % len(strains)]
    return {"level": level, "strain": strain, "target": level + 6}


def _bridge_legal_cards(hand: list[str], current_trick: list[dict[str, str]]) -> list[str]:
    if not current_trick:
        return list(hand)
    lead_suit = _card_suit(current_trick[0]["card"])
    suited = [card for card in hand if _card_suit(card) == lead_suit]
    return suited if suited else list(hand)


def _bridge_trick_winner(current_trick: list[dict[str, str]], strain: str) -> str:
    lead_suit = _card_suit(current_trick[0]["card"])
    best = current_trick[0]
    for play in current_trick[1:]:
        if _bridge_card_beats(play["card"], best["card"], lead_suit, strain):
            best = play
    return best["player"]


def _bridge_card_beats(card: str, incumbent: str, lead_suit: str, strain: str) -> bool:
    suit = _card_suit(card)
    incumbent_suit = _card_suit(incumbent)
    if strain != "NT" and suit == strain and incumbent_suit != strain:
        return True
    if strain != "NT" and incumbent_suit == strain and suit != strain:
        return False
    if suit == incumbent_suit:
        return BRIDGE_ORDER[_card_rank(card)] > BRIDGE_ORDER[_card_rank(incumbent)]
    return bool(incumbent_suit != lead_suit and suit == lead_suit)


def _bridge_outcome_if_done(
    hands: dict[str, list[str]],
    tricks: dict[str, int],
    contract: dict[str, Any],
    declarer: str,
) -> dict[str, Any] | None:
    if any(hands[player] for player in hands):
        return None
    return _bridge_final_outcome(tricks, contract, declarer, "contract_result")


def _bridge_final_outcome(
    tricks: dict[str, int],
    contract: dict[str, Any],
    declarer: str,
    reason: str,
) -> dict[str, Any]:
    declarer_side = _bridge_side(declarer)
    made = tricks[declarer_side] >= int(contract["target"])
    winning_side = declarer_side if made else ("EW" if declarer_side == "NS" else "NS")
    return {
        "winner": winning_side,
        "reason": reason,
        "contract": contract,
        "tricks": tricks,
        "made": made,
    }


def _bridge_scores(players: Sequence[str], outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return dict.fromkeys(players, 0.0)
    winner = outcome.get("winner")
    if winner not in {"NS", "EW"}:
        return dict.fromkeys(players, 0.5)
    return {player: (1.0 if _bridge_side(player) == winner else 0.0) for player in players}


def _bridge_side(player: str) -> str:
    return "NS" if player in {"player_1", "player_3"} else "EW"


def _winner_scores(players: Sequence[str], outcome: dict[str, Any] | None) -> dict[str, float]:
    if outcome is None:
        return dict.fromkeys(players, 0.0)
    winner = outcome.get("winner")
    if winner is None:
        return dict.fromkeys(players, 0.5)
    return {player: (1.0 if player == winner else 0.0) for player in players}


def _hands_from_private(
    state: ArenaState,
    players: Sequence[str],
    key: str,
) -> dict[str, list[str]]:
    return {player: list(state.private_state_by_player[player][key]) for player in players}


def _next_player(players: Sequence[str], player: str) -> str:
    return players[(players.index(player) + 1) % len(players)]


def _sorted_tiles(tiles: Iterable[str]) -> list[str]:
    return sorted(tiles, key=_tile_key)


def _tile_key(tile: str) -> tuple[str, int]:
    return (tile[0], int(tile[1]))


def _sorted_bridge_cards(cards: Iterable[str]) -> list[str]:
    return sorted(cards, key=lambda card: (_card_suit(card), BRIDGE_ORDER[_card_rank(card)]))


def _sorted_dou_cards(cards: Iterable[str]) -> list[str]:
    return sorted(cards, key=lambda card: (DOU_DIZHU_ORDER[_dou_rank(card)], card))


def _card_rank(card: str) -> str:
    return card[:-1]


def _card_suit(card: str) -> str:
    return card[-1]


def _dou_rank(card: str) -> str:
    if card in {"BJ", "RJ"}:
        return card
    return card[:-1]
