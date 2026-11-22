"""Closed native table facts; fields with hidden or not-yet-revealed content are excluded."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from eslams.state import ArenaState

Check = Callable[[Any], bool]
_SEATS = ("player_1", "player_2", "player_3", "player_4")
_CARD = r"(?:10|[2-9TJQKA])[CDHS]"
_DOU = rf"(?:{_CARD}|BJ|RJ)"
_TILE = r"[BCD][1-9]"


def _number(a: int, b: int = 1000) -> Check:
    return lambda v: type(v) is int and a <= v <= b


def _one(*options: Any) -> Check:
    return lambda v: any(type(v) is type(a) and v == a for a in options)


def _pattern(pattern: str) -> Check:
    return lambda v: type(v) is str and len(v) <= 100 and re.fullmatch(pattern, v) is not None


def _many(item: Check, limit: int) -> Check:
    return lambda v: isinstance(v, list) and len(v) <= limit and all(item(x) for x in v)


def _obj(**keys: Check) -> Check:
    return lambda v: isinstance(v, dict) and set(v) == set(keys) and all(
        options(v[k]) for k, options in keys.items()
    )


def _nullable(rule: Check) -> Check:
    return lambda v: v is None or rule(v)


def _count(seats: int) -> Check:
    return _obj(**dict.fromkeys(_SEATS[:seats], _number(0)))


_seat = _one(*_SEATS)
_card = _pattern(_CARD)
_trick = _many(_obj(player=_seat, card=_card), 4)
_bid = _nullable(_obj(player=_seat, count=_number(1, 10), face=_number(1, 6)))
_offer = _nullable(_obj(player=_seat, player_1_share=_number(0, 100)))
_negotiation = _nullable(_obj(player=_seat, price=_number(20, 100), delivery=_number(1, 3)))
_gof = _obj(
    prize=_number(1, 5),
    bids=_obj(player_1=_number(1, 5), player_2=_number(1, 5)),
    winner=_nullable(_seat),
)
_recorded_play = _nullable(
    _obj(player=_seat, cards=_many(_pattern(_DOU), 20),
         kind=_one("single", "pair", "triple", "straight", "bomb", "rocket"),
         rank=_number(0, 20))
)
_TABLE: dict[str, dict[str, Check]] = {
    "blackjack": {"player_hand": _many(_number(1, 11), 18),
                  "dealer_upcard": _number(1, 11)},
    "shedding-card-game": {"discard": _card, "deck_count": _number(0, 52),
                          "hand_counts": _count(2)},
    "crazy-eights": {"discard": _card, "deck_count": _number(0, 52),
                    "hand_counts": _count(2), "wild_rank": _nullable(_pattern(r"8"))},
    "gin-rummy": {"phase": _one("draw", "discard"), "discard_top": _nullable(_card),
                  "deck_count": _number(0, 52), "hand_counts": _count(2)},
    "hearts": {"hand_counts": _count(2), "current_trick": _trick, "penalties": _count(2)},
    "spades": {"hand_counts": _count(2), "current_trick": _trick, "tricks": _count(2)},
    "euchre": {"phase": _one("call", "play"), "dealer": _seat, "upcard": _card,
               "trump": _nullable(_pattern(r"[CDHS]")), "passes": _many(_seat, 2),
               "current_trick": _trick, "tricks": _count(2), "hand_counts": _count(2)},
    "cribbage": {"starter": _card, "dealer": _seat, "discard_counts": _count(2),
                 "hand_counts": _count(2)},
    "hanabi": {"fireworks": _obj(R=_number(0, 3), B=_number(0, 3)),
               "clues": _number(0, 8), "lives": _number(0, 3),
               "deck_count": _number(0, 30), "hand_counts": _count(2),
               "discard": _many(_pattern(r"[RB][1-3]"), 30)},
    "mahjong": {"wall_count": _number(0, 108), "hand_counts": _count(4)},
    "dou-dizhu": {"landlord": _seat, "hand_counts": _count(3),
                  "last_play": _recorded_play, "last_owner": _nullable(_seat),
                  "passes": _many(_seat, 3)},
    "bridge": {"contract": _obj(level=_number(2, 4), strain=_one("S", "H", "D", "C", "NT"),
                                target=_number(8, 10)),
               "declarer": _seat, "current_trick": _trick, "hand_counts": _count(4),
               "tricks": _obj(NS=_number(0, 13), EW=_number(0, 13))},
    "goofspiel": {"current_prize": _nullable(_number(1, 5)), "points": _count(2),
                  "round_history": _many(_gof, 5)},
    "liars-dice": {"current_bid": _bid, "bid_history": _many(
        _obj(player=_seat, count=_number(1, 10), face=_number(1, 6)), 70)},
    "bargaining": {"last_offer": _offer},
    "negotiation": {"last_offer": _negotiation},
}
_MOVE: dict[str, Check] = {
    "blackjack": _one("hit", "stand"),
    "shedding-card-game": _pattern(rf"draw|pass|play:{_CARD}"),
    "crazy-eights": _pattern(rf"draw|pass|play:{_CARD}(?::[CDHS])?"),
    "gin-rummy": _pattern(rf"draw:(?:discard|deck)|(?:discard|knock):{_CARD}"),
    "hearts": _pattern(rf"play:{_CARD}"),
    "spades": _pattern(rf"play:{_CARD}"),
    "euchre": _pattern(rf"pass|call:[CDHS]|play:{_CARD}"),
    "cribbage": _one("private_discard"),
    "hanabi": _pattern(r"(?:play|discard):[0-5]|hint:player_[12]:[RB123]"),
    "mahjong": _pattern(rf"mahjong|discard:{_TILE}"),
    "dou-dizhu": _pattern(rf"pass|play:{_DOU}(?:,{_DOU}){{0,19}}"),
    "bridge": _pattern(rf"play:{_CARD}"),
    "goofspiel": _one("sealed_bid"),
    "liars-dice": _pattern(r"challenge|(?:[1-9]|10)x[1-6]"),
    "bargaining": _pattern(r"accept|reject|offer:(?:0|[1-9]0|100)"),
    "negotiation": _pattern(r"accept|reject|offer:(?:[2-9]0|100):[1-3]"),
}
_FACT_KINDS = {"round_opened", "redacted_unit_action", "round_settled"}


def valid_shared_facts(game: str, kind: str, facts: Any) -> bool:
    if game not in _TABLE or kind not in _FACT_KINDS:
        return isinstance(facts, dict) and not facts
    layout = dict(_TABLE[game])
    if kind == "redacted_unit_action":
        layout["move"] = _MOVE[game]
    if game == "blackjack" and kind == "round_settled":
        layout["dealer_hand"] = _many(_number(1, 11), 18)
    if not _obj(**layout)(facts):
        return False
    return game != "bridge" or bool(facts["contract"]["target"] == facts["contract"]["level"] + 6)


def shared_facts(game: str, kind: str, state: ArenaState, action: object = None) -> dict[str, Any]:
    if game not in _TABLE or kind not in _FACT_KINDS:
        return {}
    # Copy only named table fields. Never use raw state, history, outcome or action menus.
    p = state.public_state
    facts = {key: deepcopy(p[key]) for key in _TABLE[game]}
    if kind == "redacted_unit_action":
        if game == "cribbage":
            facts["move"] = "private_discard"
        elif game == "goofspiel":
            facts["move"] = "sealed_bid"
        else:
            facts["move"] = action
    if game == "blackjack" and kind == "round_settled":
        if not state.terminal:
            raise ValueError("dealer reveal must be terminal")
        facts["dealer_hand"] = deepcopy(p["dealer_hand"])
    if not valid_shared_facts(game, kind, facts):
        raise ValueError("unsupported native public facts")
    return facts
