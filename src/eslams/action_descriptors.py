"""Public-safe action descriptors for interactive Arena transport."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from eslams.hashing import canonical_json
from eslams.state import ArenaState


@dataclass(frozen=True)
class ActionDescriptor:
    token: str
    label: str
    short_label: str
    verb: str
    object: str
    category: str
    group: str
    sort_key: str
    prompt_label: str
    confirm: bool = False
    disabled_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "label": self.label,
            "short_label": self.short_label,
            "verb": self.verb,
            "object": self.object,
            "category": self.category,
            "group": self.group,
            "sort_key": self.sort_key,
            "prompt_label": self.prompt_label,
            "confirm": self.confirm,
            "disabled_reason": self.disabled_reason,
        }


POSITION_NAMES_3X3 = {
    0: "top-left",
    1: "top",
    2: "top-right",
    3: "left",
    4: "center",
    5: "right",
    6: "bottom-left",
    7: "bottom",
    8: "bottom-right",
}

CONTROL_LABELS = {
    "accelerate": "Accelerate",
    "advance": "Advance",
    "all-in": "Go all-in",
    "balance": "Balance",
    "bet": "Bet",
    "brake": "Brake",
    "call": "Call",
    "check": "Check",
    "coast": "Coast",
    "cooperate": "Cooperate",
    "defect": "Defect",
    "dodge-left": "Dodge left",
    "dodge-right": "Dodge right",
    "down": "Move down",
    "fire": "Fire",
    "guard": "Guard",
    "hit": "Hit",
    "hold": "Hold",
    "hook": "Hook",
    "idle": "Idle",
    "jab": "Jab",
    "jump": "Jump",
    "left": "Move left",
    "left-step": "Step left",
    "main": "Main thrust",
    "paper": "Paper",
    "pass": "Pass",
    "resign": "Resign",
    "retreat": "Retreat",
    "right": "Move right",
    "right-step": "Step right",
    "rock": "Rock",
    "scissors": "Scissors",
    "shoot": "Shoot",
    "skate-left": "Skate left",
    "skate-right": "Skate right",
    "stand": "Stand",
    "stay": "Stay",
    "up": "Move up",
}

SUIT_SYMBOLS = {"C": "\u2663", "D": "\u2666", "H": "\u2665", "S": "\u2660"}
SUIT_NAMES = {"C": "clubs", "D": "diamonds", "H": "hearts", "S": "spades"}
CARD_RE = re.compile(r"^(A|K|Q|J|10|[2-9]|T)([CDHS])$")


def action_token(action: Any) -> str:
    """Return the stable token string used by interactive transport."""

    if isinstance(action, str):
        return action
    return canonical_json(action)


def action_descriptors(
    *,
    game_id: str,
    state: ArenaState,
    actions: list[Any],
) -> list[dict[str, Any]]:
    return [
        describe_action(game_id=game_id, state=state, action=action).to_dict()
        for action in actions
    ]


def describe_action(*, game_id: str, state: ArenaState, action: Any) -> ActionDescriptor:
    token = action_token(action)
    if isinstance(action, int):
        return _integer_descriptor(game_id, state, action, token)
    if isinstance(action, list):
        return _list_descriptor(game_id, action, token)
    if isinstance(action, str):
        return _string_descriptor(game_id, state, action, token)
    return _fallback_descriptor(token)


def _integer_descriptor(
    game_id: str,
    state: ArenaState,
    action: int,
    token: str,
) -> ActionDescriptor:
    if game_id == "connect-four":
        label = f"Drop in column {action + 1}"
        return _descriptor(
            token,
            label,
            f"Column {action + 1}",
            "drop",
            f"column {action + 1}",
            "drop_disc",
        )
    if game_id == "tic-tac-toe":
        position = POSITION_NAMES_3X3.get(action, f"square {action + 1}")
        label = f"Play {position}"
        return _descriptor(token, label, position.title(), "play", position, "mark_square")
    if game_id == "mancala":
        label = f"Sow from pit {action + 1}"
        return _descriptor(token, label, f"Pit {action + 1}", "sow", f"pit {action + 1}", "sow_pit")
    if game_id == "goofspiel":
        label = f"Play bid card {action}"
        return _descriptor(token, label, str(action), "play", f"bid card {action}", "play_card")
    if game_id == "first-price-sealed-bid-auction":
        label = f"Bid {action}"
        return _descriptor(token, label, str(action), "bid", str(action), "bid")
    rows, cols = _grid_shape(state)
    if rows and cols and 0 <= action < rows * cols:
        row = action // cols
        col = action % cols
        label = f"Place at row {row + 1}, column {col + 1}"
        return _descriptor(
            token,
            label,
            f"R{row + 1}C{col + 1}",
            "place",
            f"row {row + 1}, column {col + 1}",
            "place_piece",
        )
    label = f"Choose {action}"
    return _descriptor(token, label, str(action), "choose", str(action), "choose")


def _list_descriptor(game_id: str, action: list[Any], token: str) -> ActionDescriptor:
    if game_id == "othello" and len(action) == 2:
        row, col = action
        label = f"Place at row {int(row) + 1}, column {int(col) + 1}"
        return _descriptor(
            token,
            label,
            f"R{int(row) + 1}C{int(col) + 1}",
            "place",
            f"row {int(row) + 1}, column {int(col) + 1}",
            "place_piece",
        )
    label = "Choose " + ", ".join(str(item) for item in action)
    return _descriptor(token, label, label.removeprefix("Choose "), "choose", token, "choose")


def _string_descriptor(
    game_id: str,
    state: ArenaState,
    action: str,
    token: str,
) -> ActionDescriptor:
    chess = _chess_descriptor(state, action, token)
    if game_id == "chess" and chess is not None:
        return chess
    if game_id == "liars-dice" and re.match(r"^\d+x\d+$", action):
        count, face = action.split("x", 1)
        label = f"Bid {count} x {face}"
        return _descriptor(token, label, f"{count}x{face}", "bid", f"{count} x {face}", "bid")
    if game_id == "pentago":
        pentago = _pentago_descriptor(action, token)
        if pentago is not None:
            return pentago
    if "," in action and "-" not in action and all(part.isdigit() for part in action.split(",")):
        row, col = action.split(",", 1)
        label = f"Target row {int(row) + 1}, column {int(col) + 1}"
        return _descriptor(
            token,
            label,
            f"R{int(row) + 1}C{int(col) + 1}",
            "target",
            label[7:].lower(),
            "target_cell",
        )
    if "-" in action and re.match(r"^[a-z]?\d+[a-z]?-?[a-z]?\d+[a-z]?$", action):
        label = f"Move {action.replace('-', ' to ')}"
        return _descriptor(token, label, action, "move", action, "move_piece")
    if action.startswith("move:"):
        obj = action.split(":", 1)[1]
        label = f"Move {obj.replace('-', ' to ')}"
        return _descriptor(token, label, obj, "move", obj, "move_piece")
    colon_prefixes = ("play:", "discard:", "draw:", "call:", "bet:", "bid:", "offer:", "place:")
    if action.startswith(colon_prefixes):
        return _colon_descriptor(action, token)
    if action in CONTROL_LABELS:
        label = CONTROL_LABELS[action]
        verb = label.split()[0].lower()
        return _descriptor(token, label, label, verb, label.lower(), _category_for_verb(verb))
    return _fallback_descriptor(token)


def _chess_descriptor(state: ArenaState, action: str, token: str) -> ActionDescriptor | None:
    legal_moves = state.public_state.get("legal_moves")
    if not isinstance(legal_moves, list):
        return None
    detail = next(
        (
            item
            for item in legal_moves
            if isinstance(item, dict) and str(item.get("uci")) == action
        ),
        None,
    )
    san = str(detail.get("san")) if isinstance(detail, dict) and detail.get("san") else None
    src = action[:2]
    dst = action[2:4] if len(action) >= 4 else action
    suffix = f" ({san})" if san else ""
    label = f"Move {src} to {dst}{suffix}"
    short = san or f"{src}-{dst}"
    return _descriptor(token, label, short, "move", dst, "move_piece")


def _pentago_descriptor(action: str, token: str) -> ActionDescriptor | None:
    parts = action.split(":")
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    cell, quadrant, direction = parts
    direction_label = "clockwise" if direction == "cw" else "counter-clockwise"
    label = f"Place at cell {int(cell) + 1}, rotate quadrant {int(quadrant) + 1} {direction_label}"
    return _descriptor(
        token,
        label,
        f"{int(cell) + 1} / Q{int(quadrant) + 1} {direction.upper()}",
        "place",
        f"cell {int(cell) + 1}, quadrant {int(quadrant) + 1}",
        "place_and_rotate",
    )


def _colon_descriptor(action: str, token: str) -> ActionDescriptor:
    verb, value = action.split(":", 1)
    if verb in {"play", "discard"}:
        if value.isdigit():
            index_label = f"card {int(value) + 1}"
            label = f"{verb.capitalize()} {index_label}"
            return _descriptor(token, label, index_label.title(), verb, index_label, f"{verb}_card")
        cards = [_format_card(part.strip()) for part in value.split(",") if part.strip()]
        obj = _join_words(cards) if cards else value
        label = f"{verb.capitalize()} {obj}"
        return _descriptor(token, label, obj, verb, obj, f"{verb}_card")
    if verb == "draw":
        obj = "from deck" if value == "deck" else f"from {value}"
        label = f"Draw {obj}"
        return _descriptor(token, label, value.title(), "draw", obj, "draw_card")
    if verb == "call":
        suit = SUIT_NAMES.get(value, value)
        label = f"Call {suit}"
        return _descriptor(token, label, suit.title(), "call", suit, "call_suit")
    if verb in {"bet", "bid"}:
        label = f"{verb.capitalize()} {value}"
        return _descriptor(token, label, value, verb, value, verb)
    if verb == "offer":
        obj = " / ".join(value.split(":"))
        label = f"Offer {obj}"
        return _descriptor(token, label, obj, "offer", obj, "offer")
    if verb == "place":
        label = f"Place at point {int(value) + 1}" if value.isdigit() else f"Place {value}"
        short = f"Point {int(value) + 1}" if value.isdigit() else value
        return _descriptor(token, label, short, "place", short.lower(), "place_piece")
    return _fallback_descriptor(token)


def _fallback_descriptor(token: str) -> ActionDescriptor:
    label = _title_token(token)
    verb = label.split()[0].lower() if label else "choose"
    return _descriptor(
        token,
        label or token,
        label or token,
        verb,
        label.lower() or token,
        "action",
    )


def _descriptor(
    token: str,
    label: str,
    short_label: str,
    verb: str,
    obj: str,
    category: str,
) -> ActionDescriptor:
    group = _group_for_category(category)
    return ActionDescriptor(
        token=token,
        label=label,
        short_label=short_label,
        verb=verb,
        object=obj,
        category=category,
        group=group,
        sort_key=f"{category}:{_sort_fragment(token)}",
        prompt_label=label[0].lower() + label[1:] if label else token,
    )


def _grid_shape(state: ArenaState) -> tuple[int | None, int | None]:
    rows = state.public_state.get("rows")
    cols = state.public_state.get("cols")
    return (rows if isinstance(rows, int) else None, cols if isinstance(cols, int) else None)


def _category_for_verb(verb: str) -> str:
    if verb in {"move", "step", "skate"}:
        return "move"
    if verb in {"bet", "bid", "offer"}:
        return verb
    return "action"


def _group_for_category(category: str) -> str:
    groups = {
        "action": "Actions",
        "bet": "Bet",
        "bid": "Bid",
        "call_suit": "Call a suit",
        "choose": "Choose",
        "discard_card": "Discard a card",
        "draw_card": "Draw",
        "drop_disc": "Drop a disc",
        "mark_square": "Play a square",
        "move": "Move",
        "move_piece": "Move a piece",
        "offer": "Make an offer",
        "place_and_rotate": "Place and rotate",
        "place_piece": "Place a piece",
        "play_card": "Play a card",
        "sow_pit": "Sow seeds",
        "target_cell": "Target a cell",
    }
    return groups.get(category, "Actions")


def _format_card(value: str) -> str:
    match = CARD_RE.match(value)
    if match is None:
        return value
    rank, suit = match.groups()
    return f"{'10' if rank == 'T' else rank}{SUIT_SYMBOLS[suit]}"


def _join_words(values: list[str]) -> str:
    if len(values) <= 1:
        return values[0] if values else ""
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def _title_token(token: str) -> str:
    return token.replace(":", " ").replace("-", " ").replace("_", " ").title()


def _sort_fragment(token: str) -> str:
    return token.replace(":", "_").replace(",", "_").replace("[", "").replace("]", "")
