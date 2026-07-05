"""Shared deterministic card helpers."""

from __future__ import annotations

import random

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("C", "D", "H", "S")


def standard_deck(seed: int, *, ranks: tuple[str, ...] = RANKS) -> list[str]:
    cards = [f"{rank}{suit}" for suit in SUITS for rank in ranks]
    random.Random(seed).shuffle(cards)
    return cards


def card_rank(card: str) -> str:
    return card[:-1]


def card_suit(card: str) -> str:
    return card[-1]


def rank_value(card: str, *, ranks: tuple[str, ...] = RANKS) -> int:
    return ranks.index(card_rank(card))


def card_sort_key(card: str, *, ranks: tuple[str, ...] = RANKS) -> tuple[int, int]:
    return (SUITS.index(card_suit(card)), rank_value(card, ranks=ranks))
