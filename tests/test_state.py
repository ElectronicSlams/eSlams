import pytest

from eslams.arenas.connect_four import ConnectFourArena
from eslams.state import ArenaState


def test_state_hash_is_deterministic():
    state_a = ConnectFourArena().initial_state(1)
    state_b = ConnectFourArena().initial_state(1)
    assert state_a.state_hash == state_b.state_hash


def test_state_hash_rejects_tampering():
    state = ConnectFourArena().initial_state(1)
    with pytest.raises(ValueError):
        ArenaState(
            state_id=state.state_id,
            state_hash="sha256:not-real",
            turn=state.turn,
            active_player=state.active_player,
            public_state=state.public_state,
            private_state_by_player=state.private_state_by_player,
            legal_actions_by_player=state.legal_actions_by_player,
            scores=state.scores,
            terminal=state.terminal,
            outcome=state.outcome,
            rng_commitment=state.rng_commitment,
            render_hints=state.render_hints,
            metadata=state.metadata,
        )


def test_public_view_does_not_expose_private_metadata_seed():
    state = ConnectFourArena().initial_state(1)

    public = state.public_view()

    assert "metadata" not in public
    assert "seed" not in str(public)
