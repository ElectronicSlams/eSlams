"""Opt-in native sealed-bid policy; the registered historical rules remain untouched."""

from __future__ import annotations

import hmac

from eslams.arenas.strategic_games import FirstPriceSealedBidAuctionArena
from eslams.hashing import canonical_json
from eslams.state import ArenaState


class NativeSealedBidAuction(FirstPriceSealedBidAuctionArena):
    version = "2.0.0-native"

    def initial_state(self, seed: int) -> ArenaState:
        raise ValueError("native sealed-bid setup requires private authority")

    def apply_action(self, state: ArenaState, player_id: str, action: object) -> ArenaState:
        if type(action) is not int:
            raise ValueError("native bid requires an exact integer")
        return super().apply_action(state, player_id, action)

    def deal(
        self, authority: bytes, run_id: str, public_seed: int, round_index: int,
    ) -> ArenaState:
        if type(authority) is not bytes or len(authority) < 32:
            raise ValueError("native sealed-bid setup requires private authority")

        def draw(label: str, width: int) -> int:
            context = canonical_json([
                "eslams.native-sealed-bid.v2", run_id, public_seed, round_index, label,
            ]).encode()
            # Unbiased finite-width draws; each seat and allocation tie break has its own domain.
            threshold = (1 << 256) // width * width
            for i in range(16):
                tagged = context + i.to_bytes(1, "big")
                n = int.from_bytes(hmac.digest(authority, tagged, "sha256"), "big")
                if n < threshold:
                    return n % width
            raise ValueError("native sealed-bid draw unavailable")

        valuations = {seat: 6 + draw("valuation:" + seat, 5) for seat in self.players}
        return self._state(
            turn=0,
            active=self.players[0],
            seed=draw("allocation:tie", 2),
            valuations=valuations,
            pending_bid=None,
            revealed=None,
            outcome=None,
        )
