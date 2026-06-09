"""Core-owned public game catalogue metadata.

This mirrors the Platform V4 public game catalogue without importing Platform
code at runtime. Runtime/debug labels may be derived elsewhere; these rows are
the hosted-product display contract.
"""

from __future__ import annotations

from dataclasses import dataclass

PUBLIC_CATEGORY_LABELS = {
    "board": "Board & Strategy",
    "card": "Card & Hidden-Info",
    "gametheory": "Social & Economic",
    "rl": "Control & Arcade",
}


@dataclass(frozen=True)
class PublicGameMetadata:
    game_id: str
    name: str
    category: str
    variant: str
    difficulty: str
    maturity: str
    players: int = 2

    @property
    def category_label(self) -> str:
        return PUBLIC_CATEGORY_LABELS[self.category]

    @property
    def variant_label(self) -> str:
        return variant_label(self.variant)

    @property
    def short_description(self) -> str:
        return f"{self.name} Arena game for public play, replay review, and evaluation planning."


PUBLIC_GAME_CATALOGUE: tuple[PublicGameMetadata, ...] = (
    PublicGameMetadata("chess", "Chess", "board", "standard", "hard", "playable"),
    PublicGameMetadata("go", "Go", "board", "board_9x9", "hard", "playable"),
    PublicGameMetadata("connect-four", "Connect Four", "board", "standard", "easy", "playable"),
    PublicGameMetadata("tic-tac-toe", "Tic-Tac-Toe", "board", "standard", "easy", "playable"),
    PublicGameMetadata("othello", "Othello", "board", "standard", "medium", "playable"),
    PublicGameMetadata("checkers", "Checkers", "board", "standard", "medium", "playable"),
    PublicGameMetadata("shogi", "Shogi", "board", "standard", "hard", "playable"),
    PublicGameMetadata("xiangqi", "Xiangqi", "board", "standard", "hard", "playable"),
    PublicGameMetadata("gomoku", "Gomoku", "board", "standard", "medium", "playable"),
    PublicGameMetadata("hex", "Hex", "board", "standard", "hard", "playable"),
    PublicGameMetadata("mancala", "Mancala", "board", "standard", "easy", "playable"),
    PublicGameMetadata(
        "nine-mens-morris",
        "Nine Men's Morris",
        "board",
        "standard",
        "medium",
        "playable",
    ),
    PublicGameMetadata("pentago", "Pentago", "board", "standard", "medium", "playable"),
    PublicGameMetadata(
        "ultimate-tic-tac-toe",
        "Ultimate Tic-Tac-Toe",
        "board",
        "standard",
        "medium",
        "playable",
    ),
    PublicGameMetadata("battleship", "Battleship", "board", "standard", "easy", "playable"),
    PublicGameMetadata("backgammon", "Backgammon", "board", "standard", "medium", "playable"),
    PublicGameMetadata(
        "blackjack",
        "Blackjack",
        "card",
        "core_hit_stand_s17",
        "easy",
        "playable",
    ),
    PublicGameMetadata(
        "leduc-holdem",
        "Leduc Hold'em",
        "card",
        "core_standard_leduc",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "limit-texas-holdem",
        "Limit Texas Hold'em",
        "card",
        "core_heads_up_limit",
        "hard",
        "playable",
    ),
    PublicGameMetadata(
        "no-limit-texas-holdem",
        "No-Limit Texas Hold'em",
        "card",
        "core_profiled_no_limit",
        "hard",
        "playable",
    ),
    PublicGameMetadata(
        "shedding-card-game",
        "Shedding Card Game",
        "card",
        "core_rank_suit_shedding",
        "easy",
        "playable",
        4,
    ),
    PublicGameMetadata(
        "gin-rummy",
        "Gin Rummy",
        "card",
        "core_compact_gin",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "mahjong",
        "Mahjong",
        "card",
        "core_compact_draw_discard",
        "hard",
        "playable",
        4,
    ),
    PublicGameMetadata(
        "dou-dizhu",
        "Dou Dizhu",
        "card",
        "core_landlord_shedding",
        "hard",
        "playable",
        3,
    ),
    PublicGameMetadata(
        "bridge",
        "Bridge",
        "card",
        "core_contract_play",
        "hard",
        "playable",
        4,
    ),
    PublicGameMetadata("hearts", "Hearts", "card", "core_penalty_tricks", "medium", "playable", 4),
    PublicGameMetadata("spades", "Spades", "card", "core_trump_tricks", "medium", "playable", 4),
    PublicGameMetadata("euchre", "Euchre", "card", "core_call_and_play", "medium", "playable", 4),
    PublicGameMetadata(
        "cribbage",
        "Cribbage",
        "card",
        "core_discard_showdown",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "crazy-eights",
        "Crazy Eights",
        "card",
        "core_wild_eight_shedding",
        "easy",
        "playable",
        4,
    ),
    PublicGameMetadata("hanabi", "Hanabi", "card", "core_compact_hanabi", "hard", "playable", 4),
    PublicGameMetadata(
        "prisoners-dilemma",
        "Prisoner's Dilemma",
        "gametheory",
        "core_one_shot_matrix",
        "easy",
        "playable",
    ),
    PublicGameMetadata(
        "bargaining",
        "Bargaining",
        "gametheory",
        "core_bilateral_split",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "negotiation",
        "Negotiation",
        "gametheory",
        "core_price_delivery_grid",
        "hard",
        "playable",
    ),
    PublicGameMetadata(
        "first-price-sealed-bid-auction",
        "First-Price Sealed-Bid Auction",
        "gametheory",
        "core_two_bidder_private_values",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "liars-dice",
        "Liar's Dice",
        "card",
        "core_single_round",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "goofspiel",
        "Goofspiel",
        "card",
        "core_five_card_goofspiel",
        "medium",
        "playable",
    ),
    PublicGameMetadata(
        "rock-paper-scissors",
        "Rock Paper Scissors",
        "gametheory",
        "core_one_shot_hidden_commit",
        "easy",
        "playable",
    ),
    PublicGameMetadata("taxi", "Taxi", "rl", "standard", "easy", "playable", 1),
    PublicGameMetadata("frozen-lake", "Frozen Lake", "rl", "standard", "easy", "playable", 1),
    PublicGameMetadata("cliff-walking", "Cliff Walking", "rl", "standard", "easy", "playable", 1),
    PublicGameMetadata("cartpole", "CartPole", "rl", "standard", "easy", "playable", 1),
    PublicGameMetadata("mountain-car", "Mountain Car", "rl", "standard", "medium", "playable", 1),
    PublicGameMetadata("lunar-lander", "Lunar Lander", "rl", "standard", "medium", "playable", 1),
    PublicGameMetadata("car-racing", "Car Racing", "rl", "standard", "hard", "playable", 1),
    PublicGameMetadata("bipedal-walker", "Bipedal Walker", "rl", "standard", "hard", "playable", 1),
    PublicGameMetadata("paddle-ball", "Paddle Ball", "rl", "standard", "easy", "playable", 1),
    PublicGameMetadata("alien-shooter", "Alien Shooter", "rl", "standard", "medium", "playable", 1),
    PublicGameMetadata(
        "boxing-style-arena",
        "Boxing Style Arena",
        "rl",
        "standard",
        "medium",
        "playable",
        1,
    ),
    PublicGameMetadata(
        "ice-hockey-style-arena",
        "Ice Hockey Style Arena",
        "rl",
        "standard",
        "medium",
        "playable",
        1,
    ),
)

PUBLIC_GAME_CATALOGUE_BY_ID = {row.game_id: row for row in PUBLIC_GAME_CATALOGUE}


def variant_label(variant: str) -> str:
    token = variant.removeprefix("core_")
    replacements = {
        "s17": "S17",
        "9x9": "9x9",
    }
    words = [replacements.get(part, part.capitalize()) for part in token.split("_")]
    return " ".join(words)
