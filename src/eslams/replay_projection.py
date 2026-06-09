"""Public-safe replay display-frame projection."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from eslams.contracts.versions import REPLAY_DISPLAY_FRAME_SCHEMA_VERSION
from eslams.events import ReplayEvent
from eslams.state import ArenaState


def display_frame_rows(events: Iterable[ReplayEvent]) -> list[dict[str, Any]]:
    return display_frame_rows_from_dicts(event.to_dict() for event in events)


def display_frame_rows_from_dicts(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if event.get("public_safe") is False:
            continue
        public_state = _dict(event.get("public_state"))
        rows.append(
            {
                "schema_version": REPLAY_DISPLAY_FRAME_SCHEMA_VERSION,
                "frame_id": f"{_str(event.get('run_id'), 'run')}:display:{index:06d}",
                "renderer_family": _renderer_family(event.get("render_hints"), public_state),
                "visibility": _str(event.get("visibility"), "public"),
                "actor_player": _optional_str(event.get("actor_player")),
                "action_label": _optional_str(event.get("action_label"))
                or _optional_action_label(event.get("action")),
                "display_cells": _display_cells(public_state),
                "summary": {
                    "turn": _int(event.get("turn_id"), index),
                    "active_player": _optional_str(event.get("active_player")),
                    "terminal": bool(event.get("terminal", False)),
                    "scores": _dict(event.get("scores")),
                    "markers": _strings(event.get("markers")),
                },
                "source_replay_event_id": _str(
                    event.get("event_id"),
                    f"{_str(event.get('run_id'), 'run')}:replay:{index:06d}",
                ),
            }
        )
    return rows


def display_frame_for_state(
    state: ArenaState,
    *,
    run_id: str,
    event_id: str,
    actor_player: str | None = None,
    action: Any | None = None,
    action_label: str | None = None,
) -> dict[str, Any]:
    """Project one live Arena state into the public replay display-frame shape."""

    rows = display_frame_rows_from_dicts(
        [
            {
                "event_id": event_id,
                "run_id": run_id,
                "turn_id": state.turn,
                "actor_player": actor_player,
                "action": action,
                "action_label": action_label,
                "active_player": state.active_player,
                "terminal": state.terminal,
                "scores": state.scores,
                "public_state": state.public_state,
                "render_hints": state.render_hints,
                "public_safe": True,
                "visibility": "public",
            }
        ]
    )
    if not rows:
        raise ValueError("live display frame projection produced no rows")
    return rows[0]


def _renderer_family(render_hints: Any, public_state: dict[str, Any]) -> str:
    hints = _dict(render_hints)
    for key in ("renderer_family", "renderer", "kind"):
        value = hints.get(key)
        if isinstance(value, str) and value:
            return value
    if "board" in public_state or "grid" in public_state:
        return "board"
    if "cards" in public_state or "hands" in public_state:
        return "cards"
    return "metadata"


def _display_cells(public_state: dict[str, Any]) -> list[dict[str, Any]]:
    board = public_state.get("board")
    if isinstance(board, list):
        return _matrix_cells(board, key="board")
    grid = public_state.get("grid")
    if isinstance(grid, list):
        return _matrix_cells(grid, key="grid")
    cells = public_state.get("cells")
    if isinstance(cells, list):
        return _list_cells(cells, key="cells")
    return [
        {"key": key, "value": _cell_value(value)}
        for key, value in sorted(public_state.items())
        if _public_scalar(value)
    ][:100]


def _matrix_cells(values: list[Any], *, key: str) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for row_index, row in enumerate(values):
        if isinstance(row, list):
            for col_index, value in enumerate(row):
                cells.append(
                    {"kind": key, "row": row_index, "col": col_index, "value": _cell_value(value)}
                )
        else:
            cells.append({"kind": key, "index": row_index, "value": _cell_value(row)})
        if len(cells) >= 400:
            break
    return cells[:400]


def _list_cells(values: list[Any], *, key: str) -> list[dict[str, Any]]:
    return [
        {"kind": key, "index": index, "value": _cell_value(value)}
        for index, value in enumerate(values[:400])
    ]


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _public_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_action_label(value: Any) -> str | None:
    return None if value is None else str(value)


def _str(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _int(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    return value if isinstance(value, int) else fallback
