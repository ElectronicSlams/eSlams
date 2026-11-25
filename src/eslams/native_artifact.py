"""Verify the shape, integrity and sequencing of an explicitly native public match."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_STORED, BadZipFile, ZipFile

from eslams.arenas import registry
from eslams.hashing import canonical_json, sha256_text
from eslams.native_auction import NativeSealedBidAuction
from eslams.native_public_facts import valid_shared_facts
from eslams.native_rounds_demo import (
    DEMO_MAX_BLOCKS,
    NATIVE_ARTIFACT_KIND,
    NativeEvent,
)
from eslams.native_scope_demo import NATIVE_SCOPE
from eslams.output import staged_file, write_text_file

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
_MANIFEST = {
    "kind", "run_id", "arena_id", "rules_version", "blocks", "planned_rounds",
    "completed_rounds", "status", "score_quanta", "seat_ids", "position_policy",
    "utility_policy", "utility_quanta_per_point", "history_gate", "history_policy",
    "event_stream_sha256",
}
_EVENT = set(NativeEvent(0, "", 0, 0, 0).public_document())
_ACTIONS = {
    "check", "bet", "call", "fold", "raise", "bet:2", "bet:4", "raise:4", "all-in",
    "rock", "paper", "scissors", "cooperate", "defect",
}


@dataclass(frozen=True)
class NativeReplay:
    manifest: dict[str, Any]
    events: tuple[dict[str, Any], ...]

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.manifest["kind"],
            "arena_id": self.manifest["arena_id"],
            "completed_rounds": self.manifest["completed_rounds"],
            "status": self.manifest["status"],
            "event_count": len(self.events),
            "verification_scope": "public_layout_digest_sequence_not_private_mechanics",
        }


def _must(condition: bool) -> None:
    if not condition:
        raise ValueError("native replay contract failed")


def _doc(text: str) -> dict[str, Any]:
    def pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj = dict(pairs)
        _must(len(obj) == len(pairs))
        return obj

    val = json.loads(text, object_pairs_hook=pairs)
    if not isinstance(val, dict) or canonical_json(val) != text:
        raise ValueError("noncanonical native replay JSON")
    return val


def _ints(obj: Any, length: int, *, nonnegative: bool = False) -> bool:
    return isinstance(obj, list) and len(obj) == length and all(
        type(n) is int and (not nonnegative or n >= 0) for n in obj
    )


def _reader(data: bytes) -> NativeReplay:
    _must(len(data) <= MAX_ARCHIVE_BYTES)
    with ZipFile(BytesIO(data)) as z:
        files = z.infolist()
        _must([f.filename for f in files] == ["manifest.json", "public/events.jsonl"])
        _must(all(f.compress_type == ZIP_STORED and not f.flag_bits & 1
                  and stat.S_IFMT(f.external_attr >> 16) in (0, stat.S_IFREG)
                  for f in files))
        _must(sum(f.file_size for f in files) <= MAX_ARCHIVE_BYTES)
        manifest = z.read(files[0]).decode("utf-8")
        stream = z.read(files[1]).decode("utf-8")
    _must(manifest.endswith("\n") and stream.endswith("\n"))
    m = _doc(manifest[:-1])
    _must(set(m) == _MANIFEST and m["kind"] == NATIVE_ARTIFACT_KIND)
    _must(type(m["arena_id"]) is str and m["arena_id"] in NATIVE_SCOPE)
    a = NATIVE_SCOPE[m["arena_id"]]
    auction = m["arena_id"] == NativeSealedBidAuction.id
    rules = registry.create(m["arena_id"])
    _must(m["seat_ids"] == list(rules.players))
    _must(m["rules_version"] == (NativeSealedBidAuction.version if auction else rules.version))
    seats = rules.players
    ident = m["run_id"]
    _must(type(ident) is str and 0 < len(ident) <= 64 and ident.replace("-", "").isalnum())
    blocks = m["blocks"]
    _must(type(blocks) is int and 1 <= blocks <= DEMO_MAX_BLOCKS)
    planned, completed = m["planned_rounds"], m["completed_rounds"]
    _must(type(planned) is int and planned == blocks * 3
          and type(completed) is int and 0 <= completed <= planned)
    _must(m["utility_policy"] == a.score_basis and m["history_gate"] == a.history_gate)
    _must(type(m["utility_quanta_per_point"]) is int
          and m["utility_quanta_per_point"] == a.denominator)
    poker = a.history_gate == "poker_allowlist"
    matrix = a.history_gate == "sealed_action_reveal"
    action_kind = ("sealed_action" if matrix or auction else
                   "action" if poker else "redacted_unit_action")
    _must(m["history_policy"] in ("full_authorized", "memoryless_across_hands"))
    _must(m["position_policy"] == "fixed"
          or (poker or matrix) and m["position_policy"] == "rotation")
    _must(m["event_stream_sha256"] == sha256_text(stream))
    lines = stream[:-1].split("\n")
    _must(2 <= len(lines) <= planned * (rules.max_turns + 2) + 1)
    events: list[dict[str, Any]] = []
    r, g, turn, settled = 0, 0, 0, 0
    previous, opening = "", ""
    totals = [0] * len(seats)
    terminal = False
    for i, line in enumerate(lines):
        e = _doc(line)
        _must(set(e) == _EVENT and type(e["event_seq"]) is int and e["event_seq"] == i)
        _must(not terminal and all(type(e[k]) is int
                                   for k in ("round_index", "round_turn", "global_action_index")))
        k = e["kind"]
        if k == "round_opened":
            _must(previous in ("", "round_settled") and r < planned and e["actor"] in seats)
            opening = e["actor"]
            r += 1
            turn = 0
        elif k == action_kind:
            _must(previous in ("round_opened", action_kind) and e["actor"] in seats)
            _must(bool(turn) or e["actor"] == opening)
            g += 1
            turn += 1
            _must(turn <= rules.max_turns)
        elif k == "round_settled":
            _must(previous == action_kind and e["actor"] is None and settled + 1 == r)
            settled += 1
            if not auction:
                _must(_ints(e["utility"], len(seats)))
                totals = [x + y for x, y in zip(totals, e["utility"])]
        elif k == "match_finalized":
            _must(previous == "round_settled" and r == settled == planned and e["actor"] is None)
            _must(e["utility"] == ([] if auction else totals))
            terminal = True
        elif k == "match_invalid":
            _must(previous in ("round_opened", action_kind) and e["actor"] is None)
            terminal = True
        else:
            raise ValueError("unknown native event kind")
        _must((e["round_index"], e["global_action_index"], e["round_turn"]) == (r, g, turn))
        _must(e["utility"] == [] or not auction and k in ("round_settled", "match_finalized"))
        _must(e["revealed"] == [] or matrix and k == "round_settled"
              and len(e["revealed"]) == len(seats)
              and all(type(v) is str and v in _ACTIONS for v in e["revealed"]))
        _must(e["action"] is None if k != "action" else
              type(e["action"]) is str and e["action"] in _ACTIONS)
        facts = e["game_facts"]
        _must(valid_shared_facts(m["arena_id"], k, facts))
        if m["arena_id"] == "goofspiel" and k in (
            "round_opened", "redacted_unit_action", "round_settled"
        ):
            _must(len(facts["round_history"]) == turn // 2)
            if k != "round_opened":
                previous_facts = events[-1]["game_facts"]
                _must(facts["round_history"][:len(previous_facts["round_history"])] ==
                      previous_facts["round_history"])
                if turn % 2:
                    _must(facts["current_prize"] == previous_facts["current_prize"]
                          and facts["points"] == previous_facts["points"])
        if k == "round_settled" and facts:
            previous_facts = events[-1]["game_facts"]
            _must(all(previous_facts[key] == value for key, value in facts.items()
                      if key != "dealer_hand"))
        allowed_reason = (
            ("beats", "draw", "payoff_matrix") if matrix else ("fold", "showdown") if poker
            else ("settled_native_unit",)
        ) if k == "round_settled" else (
            ("invalid_action", "policy_error", "interrupted") if k == "match_invalid" else (None,)
        )
        _must(e["reason"] in allowed_reason)
        cards = e["board"]
        _must(isinstance(cards, list) and len(cards) <= 5 and
              all(type(c) is str and len(c) == 2 and c[0] in "23456789TJQKA" and c[1] in "CDHS"
                  for c in cards) and (poker and k in ("round_opened", "action", "round_settled")
                                      or cards == []))
        table = poker and k in ("round_opened", "action")
        _must(type(e["pot"]) is int and e["pot"] >= 0 if table else e["pot"] is None)
        _must(_ints(e["stacks"], len(seats) if table else 0, nonnegative=True))
        _must(_ints(e["committed"], len(seats) if table else 0, nonnegative=True))
        _must(isinstance(e["folded"], list) and len(e["folded"]) <= len(seats)
              and all(type(s) is str and s in seats for s in e["folded"])
              and (table or e["folded"] == []))
        _must(e["street"] in ("preflop", "board", "flop", "turn", "river", "showdown")
              if poker and k == "action" else e["street"] is None)
        events.append(e)
        previous = k
    _must(terminal and settled == completed)
    _must(m["status"] == ("complete" if previous == "match_finalized" else "invalid"))
    _must(m["score_quanta"] is None if auction or previous == "match_invalid"
          else _ints(m["score_quanta"], len(seats)) and m["score_quanta"] == totals)
    return NativeReplay(m, tuple(events))


def verify_native_replay(data: bytes) -> NativeReplay:
    try:
        return _reader(data)
    except (BadZipFile, RecursionError, OverflowError, TypeError) as exc:
        raise ValueError("invalid native replay layout") from exc


def read_native_replay(path: Path) -> NativeReplay:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("native replay requires a bounded regular file")
    with path.open("rb") as file:
        return verify_native_replay(file.read(MAX_ARCHIVE_BYTES + 1))


def write_native_replay(path: Path, data: bytes) -> Path:
    verify_native_replay(data)
    with staged_file(path) as temporary:
        temporary.write_bytes(data)
    return path.resolve()


def render_native_replay(path: Path, output: Path) -> Path:
    replay = read_native_replay(path)
    title = escape(str(replay.manifest["arena_id"]))
    rows: list[str] = []
    for e in replay.events:
        details = [e[key] for key in ("actor", "action", "reason") if e[key] is not None]
        if e["board"]:
            details.append("Board: " + " ".join(e["board"]))
        if e["revealed"]:
            details.append("Revealed: " + ", ".join(e["revealed"]))
        if e["game_facts"]:
            details.append(canonical_json(e["game_facts"]))
        cells = [e["event_seq"], e["round_index"], e["kind"].replace("_", " "), "; ".join(details)]
        rows.append("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in cells) + "</tr>")
    text = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Native match replay</title><main><h1>' + title + '</h1>'
        '<p>Public event journal. Sealed or private fields are not shown.</p>'
        "<table><caption>Recorded public events</caption><thead><tr><th>Event</th>"
        "<th>Unit</th><th>Type</th><th>Public details</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></main>\n"
    )
    return write_text_file(output, text, sources=[path])
