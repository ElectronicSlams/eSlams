"""Isolated native transition proof. No legacy Runner, HTTP protocol, or archive auto-reader."""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from io import BytesIO
from typing import Any
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from eslams.arena import Arena
from eslams.arenas import registry
from eslams.arenas.matrix_games import RockPaperScissorsArena
from eslams.arenas.poker import LeducHoldemArena, LimitTexasHoldemArena, NoLimitTexasHoldemArena
from eslams.contracts.versions import NATIVE_MANIFEST_SCHEMA_VERSION
from eslams.hashing import canonical_json, sha256_json, sha256_text
from eslams.native_auction import NativeSealedBidAuction
from eslams.native_observation import closed_fact_bytes, seat_facts
from eslams.native_public_facts import shared_facts
from eslams.native_scope_demo import NATIVE_SCOPE
from eslams.state import ArenaState

_GAMES: dict[str, Callable[[], Arena]] = {
    "rock-paper-scissors": RockPaperScissorsArena,
    "leduc-holdem": LeducHoldemArena,
    "limit-texas-holdem": LimitTexasHoldemArena,
    "no-limit-texas-holdem": NoLimitTexasHoldemArena,
}
_ACTIONS = frozenset((
    "check", "bet", "call", "fold", "raise", "bet:2", "bet:4", "raise:4", "all-in",
    "rock", "paper", "scissors", "cooperate", "defect",
))
_STREETS = frozenset(("preflop", "board", "flop", "turn", "river", "showdown"))
NATIVE_ARTIFACT_KIND = NATIVE_MANIFEST_SCHEMA_VERSION
DEMO_MAX_BLOCKS = 20  # Local journal harness bound only; not a proposed release limit.


@dataclass(frozen=True)
class NativeProfile:
    arena_id: str
    blocks: int = 1
    seed: int = 1
    rotate_positions: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.arena_id, str) or self.arena_id not in NATIVE_SCOPE:
            raise ValueError("native demo profile not available")
        if not NATIVE_SCOPE[self.arena_id].enabled_for_keyless:
            raise ValueError("selected scoped arena requires a verified privacy rule profile")
        if (
            type(self.blocks) is not int or not 1 <= self.blocks <= DEMO_MAX_BLOCKS
        ):
            raise ValueError("blocks must be a positive integer <= 20 in this local harness")
        if type(self.seed) is not int or type(self.rotate_positions) is not bool:
            raise ValueError("untyped native match settings")

    @property
    def round_count(self) -> int:
        return self.blocks * 3


@dataclass(frozen=True)
class NativeEvent:
    event_seq: int
    kind: str
    round_index: int
    global_action_index: int
    round_turn: int
    actor: str | None = None
    action: str | None = None
    street: str | None = None
    pot: int | None = None
    board: tuple[str, ...] = ()
    stacks: tuple[int, ...] = ()
    committed: tuple[int, ...] = ()
    folded: tuple[str, ...] = ()
    utility: tuple[int, ...] = ()
    revealed: tuple[str, ...] = ()
    reason: str | None = None
    game_facts_json: str = "{}"

    def public_document(self) -> dict[str, Any]:
        return {
            "event_seq": self.event_seq, "kind": self.kind, "round_index": self.round_index,
            "global_action_index": self.global_action_index, "round_turn": self.round_turn,
            "actor": self.actor, "action": self.action, "street": self.street, "pot": self.pot,
            "board": self.board, "stacks": self.stacks, "committed": self.committed,
            "folded": self.folded, "utility": self.utility, "revealed": self.revealed,
            "reason": self.reason, "game_facts": json.loads(self.game_facts_json),
        }


@dataclass(frozen=True)
class SeatHand:
    round_index: int
    own_cards: tuple[str, ...]


@dataclass(frozen=True)
class SeatDecision:
    round_index: int
    global_action_index: int
    round_turn: int
    observation_json: str = field(repr=False)
    action_json: str = field(repr=False)


@dataclass(frozen=True)
class NativeState:
    """Authoritative in-process match state, deliberately not serializable to public output."""

    unit: ArenaState = field(repr=False)
    round_index: int
    global_actions: int
    seat_for_position: tuple[str, ...]
    totals: tuple[int, ...] = field(repr=False)
    events: tuple[NativeEvent, ...]
    own_prior: tuple[tuple[SeatHand, ...], ...] = field(repr=False)
    completed: int = 0
    finalized: bool = False
    invalid: bool = False
    _audit_actions: tuple[str, ...] = field(default=(), repr=False)
    _seat_history: tuple[tuple[SeatDecision, ...], ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class NativeObservation:
    run_id: str
    seat_id: str
    round_index: int
    global_action_index: int
    round_turn: int
    journal: tuple[NativeEvent, ...]
    public_digest: str
    legal: tuple[Any, ...]
    own_cards: tuple[str, ...] = field(repr=False)
    own_completed_hands: tuple[SeatHand, ...] = field(repr=False)
    own_auction_value: int | None = field(default=None, repr=False)
    current_game_json: str = field(default="{}", repr=False)
    own_decision_history: tuple[SeatDecision, ...] = field(default=(), repr=False)


def _cards(cards: object) -> tuple[str, ...]:
    if not isinstance(cards, list) or any(
        type(c) is not str or len(c) != 2 or c[0] not in "23456789TJQKA" or c[1] not in "CDHS"
        for c in cards
    ):
        raise ValueError("invalid typed native card projection")
    return tuple(cards)


class NativeRoundArena:
    """One state machine. Unit-rule application and boundary settlement are one transition."""

    def __init__(
        self, profile: NativeProfile, run_id: str, *, auction_authority: bytes | None = None,
        private_authority: bytes | None = None,
    ) -> None:
        if not run_id or len(run_id) > 64 or not run_id.replace("-", "").isalnum():
            raise ValueError("invalid local run id")
        self.profile = profile
        self.run_id = run_id
        self.rules = _GAMES[profile.arena_id]() if profile.arena_id in _GAMES else registry.create(
            profile.arena_id
        )
        self.auction_rules: NativeSealedBidAuction | None = None
        self._auction_authority: bytes | None = None
        if private_authority is not None and (
            type(private_authority) is not bytes or len(private_authority) < 32
        ):
            raise ValueError("private match authority requires at least 32 bytes")
        self._private_authority = private_authority
        if profile.arena_id == NativeSealedBidAuction.id:
            if type(auction_authority) is not bytes or len(auction_authority) < 32:
                raise ValueError("native sealed-bid setup requires private authority")
            self._auction_authority = auction_authority
            self.auction_rules = NativeSealedBidAuction()
            self.rules = self.auction_rules
        elif auction_authority is not None:
            raise ValueError("auction authority is only accepted for the native auction")
        self.adapter = NATIVE_SCOPE[profile.arena_id]
        self.seats = self.rules.players
        if len(self.seats) != self.adapter.seats:
            raise ValueError("native seat contract mismatch")
        self.matrix = self.adapter.history_gate == "sealed_action_reveal"
        self.poker = self.adapter.history_gate == "poker_allowlist"
        if profile.rotate_positions and not (self.matrix or self.poker):
            raise ValueError("generic seat rotation requires a game-specific role profile")

    def _deal(self, round_index: int) -> tuple[ArenaState, tuple[str, ...]]:
        if self.auction_rules is not None:
            assert self._auction_authority is not None
            unit = self.auction_rules.deal(
                self._auction_authority, self.run_id, self.profile.seed, round_index,
            )
            return unit, self.seats
        seed = sha256_json({
            "domain": "eslams.native-rounds-demo.private-seed.v1",
            "run_id": self.run_id, "arena_id": self.rules.id, "rules": self.rules.version,
            "seed": self.profile.seed, "unit": round_index,
        })
        if self._private_authority is None:
            value = int(seed.split(":")[-1][:32], 16)
        else:
            domain = ("eslams.native-private-deck.v1:" + seed).encode()
            word = hmac.digest(self._private_authority, domain, "sha256")[:16]
            value = int.from_bytes(word, "big")
        # Native Dou Dizhu landlord and Bridge declarer are chosen by seed residue.
        # Keep roles deterministic without shifting a player's stable identity/partnership.
        role_count = {"dou-dizhu": 3, "bridge": 4}.get(self.rules.id)
        if role_count is not None:
            value = value - value % role_count + (round_index - 1) % role_count
        unit = self.rules.initial_state(value)
        start = (round_index - 1) % len(self.seats) if self.profile.rotate_positions else 0
        return unit, self.seats[start:] + self.seats[:start]

    def _public_table(
        self, unit: ArenaState, bind: tuple[str, ...]
    ) -> dict[str, Any]:
        if not self.poker:
            return {}
        # Timed native observation; read only allowlisted table facts, never its hole field.
        obs = self.rules.observation_for(unit, unit.active_player)
        to_pos = {s: self.seats[i] for i, s in enumerate(bind)}
        pot = obs["pot"]
        stacks = tuple(obs["stacks"][to_pos[s]] for s in self.seats)
        committed = tuple(obs["committed"][to_pos[s]] for s in self.seats)
        if any(type(n) is not int or n < 0 for n in (pot, *stacks, *committed)):
            raise ValueError("invalid public Poker account")
        return {
            "pot": pot, "board": _cards(obs["board"]), "stacks": stacks,
            "committed": committed, "folded": tuple(bind[self.seats.index(s)]
                                                  for s in obs["folded"]),
        }

    def start(self) -> NativeState:
        unit, seats = self._deal(1)
        event = NativeEvent(0, "round_opened", 1, 0, 0, actor=self._bound_active_seat(unit, seats),
                            game_facts_json=self._facts("round_opened", unit),
                            **self._public_table(unit, seats))
        return NativeState(unit, 1, 0, seats, (0,) * len(seats), (event,),
                           tuple(() for _ in seats), _seat_history=tuple(() for _ in seats))

    def _facts(self, kind: str, unit: ArenaState, action: object = None) -> str:
        return closed_fact_bytes(shared_facts(self.rules.id, kind, unit, action))

    def _bound_active_seat(self, unit: ArenaState, binding: tuple[str, ...]) -> str:
        return binding[self.seats.index(unit.active_player)]

    def active_seat(self, state: NativeState) -> str:
        return self._bound_active_seat(state.unit, state.seat_for_position)

    def observe(self, state: NativeState, seat_id: str, *, history: bool) -> NativeObservation:
        if seat_id != self.active_seat(state) or state.finalized or state.invalid:
            raise ValueError("observation unavailable for this active seat")
        p = state.unit.active_player
        legal = tuple(deepcopy(self.rules.legal_actions_for(state.unit, p)))
        if not legal or (
            (self.matrix or self.poker)
            and any(type(a) is not str or a not in _ACTIONS for a in legal)
        ):
            raise ValueError("unexpected native legal action")
        cards = _cards(self.rules.observation_for(state.unit, p)["hole"]) if self.poker else ()
        # Memoryless control retains only public facts from the current hand.
        events = state.events if history else tuple(
            e for e in state.events if e.round_index == state.round_index
        )
        digest = sha256_json([e.public_document() for e in events])
        return NativeObservation(
            self.run_id, seat_id, state.round_index, state.global_actions, state.unit.turn,
            events, digest, legal, cards,
            state.own_prior[self.seats.index(seat_id)] if history else (),
            int(state.unit.private_state_by_player[p]["valuation"])
            if self.auction_rules is not None else None,
            seat_facts(self.rules, state.unit, p),
            tuple(entry for entry in state._seat_history[self.seats.index(seat_id)]
                  if history or entry.round_index == state.round_index),
        )

    def transition(self, state: NativeState, seat: str, action: Any) -> NativeState:
        if state.finalized or state.invalid or seat != self.active_seat(state):
            raise ValueError("transition unavailable")
        p = state.unit.active_player
        if not self.rules.is_legal(state.unit, p, action):
            raise ValueError("illegal native action")
        pre: dict[str, Any] = {}
        if self.poker:
            pre = self.rules.observation_for(state.unit, p)
            if pre["street"] not in _STREETS:
                raise ValueError("invalid Poker street")
        nxt = self.rules.apply_action(state.unit, p, action)
        g = state.global_actions + 1
        r = state.round_index
        audit = state._audit_actions + (canonical_json([seat, action]),)
        seat_history = tuple(
            entries + (SeatDecision(r, g, state.unit.turn,
                                    seat_facts(self.rules, state.unit, p),
                                    closed_fact_bytes(action)),) if owner == seat else entries
            for owner, entries in zip(self.seats, state._seat_history)
        )
        if self.matrix or self.auction_rules is not None:
            ev = NativeEvent(len(state.events), "sealed_action", r, g, nxt.turn, actor=seat)
        elif self.poker:
            ev = NativeEvent(len(state.events), "action", r, g, nxt.turn, actor=seat, action=action,
                             street=pre["street"], **self._public_table(nxt,
                                                                        state.seat_for_position))
        else:
            ev = NativeEvent(len(state.events), "redacted_unit_action", r, g, nxt.turn, actor=seat,
                             game_facts_json=self._facts("redacted_unit_action", nxt, action))
        events = state.events + (ev,)
        if not nxt.terminal:
            return replace(state, unit=nxt, global_actions=g, events=events, _audit_actions=audit,
                           _seat_history=seat_history)
        if not nxt.outcome:
            raise ValueError("native rules produced no settlement")
        # Rule-specific score is for one hand; final_score is called only for the whole match.
        scaled = self._unit_scores(nxt, state.seat_for_position)
        revealed: tuple[str, ...] = ()
        own = state.own_prior
        reason = nxt.outcome["reason"]
        if self.matrix:
            if reason not in {"beats", "draw", "payoff_matrix"}:
                raise ValueError("unexpected matrix outcome")
            both = nxt.public_state["revealed_actions"]
            revealed = tuple(both[self.seats[state.seat_for_position.index(s)]] for s in self.seats)
            allowed = _ACTIONS | {"cooperate", "defect"}
            if any(type(a) is not str or a not in allowed for a in revealed):
                raise ValueError("unexpected matrix reveal")
        elif self.poker:
            if reason not in {"fold", "showdown"}:
                raise ValueError("unexpected Poker outcome")
            # Only call each seat's timed observation lane; do not copy either raw state map.
            own = tuple(
                previous + (SeatHand(r, _cards(
                    self.rules.observation_for(nxt, self.seats[state.seat_for_position.index(s)])[
                        "hole"
                    ]
                )),)
                for s, previous in zip(self.seats, state.own_prior)
            )
        else:
            reason = "settled_native_unit"
        totals = tuple(a + b for a, b in zip(scaled, state.totals))
        events += (NativeEvent(len(events), "round_settled", r, g, nxt.turn, board=ev.board,
                               utility=() if self.auction_rules else scaled,
                               revealed=revealed, reason=reason,
                               game_facts_json=self._facts("round_settled", nxt)),)
        if r == self.profile.round_count:
            events += (NativeEvent(len(events), "match_finalized", r, g, nxt.turn,
                                   utility=() if self.auction_rules else totals),)
            return NativeState(nxt, r, g, state.seat_for_position, totals, events, own, r, True,
                               _audit_actions=audit, _seat_history=seat_history)
        following, seats = self._deal(r + 1)
        events += (NativeEvent(len(events), "round_opened", r + 1, g, 0,
                               actor=self._bound_active_seat(following, seats),
                               game_facts_json=self._facts("round_opened", following),
                               **self._public_table(following, seats)),)
        return NativeState(following, r + 1, g, seats, totals, events, own, r,
                           _audit_actions=audit, _seat_history=seat_history)

    def _unit_scores(
        self, native_state: ArenaState, binding: tuple[str, ...]
    ) -> tuple[int, ...]:
        assert native_state.outcome is not None
        basis = self.adapter.score_basis
        score = self.rules.score(native_state)
        if basis in {"raw_payoff", "native_utility", "signed_utility"}:
            score = native_state.outcome["payoff" if basis == "raw_payoff" else "utilities"]
        lookup = dict(zip(binding, (score[p] for p in self.seats)))
        scale = self.adapter.denominator
        result = tuple(round(lookup[s] * scale) for s in self.seats)
        if any(abs(lookup[s] - n / scale) > 1e-12 for s, n in zip(self.seats, result)):
            raise ValueError("settlement was not exact under its declared score policy")
        if (self.poker or self.rules.id == "rock-paper-scissors") and sum(result) != scale:
            raise ValueError("non-conserving native competitive share")
        return result

    def fail(self, state: NativeState, reason: str) -> NativeState:
        if state.finalized or reason not in {"policy_error", "invalid_action", "interrupted"}:
            raise ValueError("invalid abort")
        event = NativeEvent(len(state.events), "match_invalid", state.round_index,
                            state.global_actions, state.unit.turn, reason=reason)
        return replace(state, events=state.events + (event,), invalid=True)

    def final_score(self, state: NativeState) -> tuple[int, ...] | None:
        if state.finalized and not state.invalid and state.completed == self.profile.round_count:
            return state.totals
        return None


Policy = Callable[[NativeObservation], Any]


@dataclass(frozen=True)
class DemoArtifact:
    run_id: str
    events: tuple[NativeEvent, ...]
    completed: int
    score: tuple[int, ...] | None = field(repr=False)
    contents: bytes


def _archive(files: Mapping[str, str]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_STORED, allowZip64=False) as output:
        for path, value in files.items():
            output.writestr(ZipInfo(path, (1980, 1, 1, 0, 0, 0)), value)
    return buf.getvalue()


def run_native_match(
    arena: NativeRoundArena, policies: Mapping[str, Policy], *, history: bool = True,
    start_state: NativeState | None = None,
    on_boundary: Callable[[NativeState], None] | None = None,
) -> DemoArtifact:
    """Keyless fixture driver, one state-machine start, one final score and one output."""
    if set(policies) != set(arena.seats):
        raise ValueError("policy identity mismatch")
    fixed = {s: policies[s] for s in arena.seats}
    state = arena.start() if start_state is None else start_state
    while not state.finalized and not state.invalid:
        seat = arena.active_seat(state)
        view = arena.observe(state, seat, history=history)
        try:
            action = fixed[seat](view)
        except KeyboardInterrupt:
            state = arena.fail(state, "interrupted")
            break
        except Exception:
            state = arena.fail(state, "policy_error")
            break
        if (arena.auction_rules is not None and type(action) is not int) or not (
            arena.rules.is_legal(state.unit, state.unit.active_player, action)
        ):
            state = arena.fail(state, "invalid_action")
            break
        prior_completed = state.completed
        state = arena.transition(state, seat, action)
        if on_boundary and not state.finalized and state.completed > prior_completed:
            on_boundary(state)
    score = arena.final_score(state)
    stream = "".join(canonical_json(e.public_document()) + "\n" for e in state.events)
    summary = canonical_json({
        "kind": NATIVE_ARTIFACT_KIND, "run_id": arena.run_id,
        "arena_id": arena.rules.id, "rules_version": arena.rules.version,
        "blocks": arena.profile.blocks, "planned_rounds": arena.profile.round_count,
        "completed_rounds": state.completed,
        "status": "complete" if state.finalized else "invalid",
        "score_quanta": None if arena.auction_rules is not None else score,
        "seat_ids": arena.seats, "position_policy": "rotation" if arena.profile.rotate_positions
        else "fixed",
        "utility_policy": arena.adapter.score_basis,
        "utility_quanta_per_point": arena.adapter.denominator,
        "history_gate": arena.adapter.history_gate,
        "history_policy": "full_authorized" if history else "memoryless_across_hands",
        "event_stream_sha256": sha256_text(stream),
    }) + "\n"
    contents = _archive({"manifest.json": summary, "public/events.jsonl": stream})
    return DemoArtifact(arena.run_id, state.events, state.completed, score, contents)


# Source-only compatibility for the prototype verification suite.
run_native_demo = run_native_match
