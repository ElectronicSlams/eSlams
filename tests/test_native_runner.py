from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZipFile

import pytest

from eslams.cli import main
from eslams.hashing import canonical_json, sha256_text
from eslams.native_artifact import verify_native_replay
from eslams.native_rounds_demo import NativeProfile, NativeRoundArena, run_native_match
from eslams.native_runner import run_local_native
from eslams.native_scope_demo import NATIVE_SCOPE

AUCTION = "first-price-sealed-bid-auction"
AUCTION_TEST_KEY = b"fixture authority for sealed auctions"
CUSTODY_TEST_KEY = b"fixture custody for settled checkpoints"


@pytest.mark.parametrize("game", sorted(NATIVE_SCOPE))
@pytest.mark.parametrize("blocks", [1, 2, 3])
def test_native_run_complete_artifact_for_every_arena(game, blocks):
    opts = {"auction_authority": AUCTION_TEST_KEY} if game == AUCTION else {}
    match = run_local_native(NativeProfile(game, blocks), "full-roster", **opts)
    replay = verify_native_replay(match.contents)
    assert match.completed == replay.manifest["completed_rounds"] == 3 * blocks
    assert replay.manifest["status"] == "complete"
    assert replay.events[-1]["kind"] == "match_finalized"
    assert len(replay.events) == len(match.events)
    assert replay.manifest["score_quanta"] is None if game == AUCTION else (
        replay.manifest["score_quanta"] == list(match.score)
    )


@pytest.mark.parametrize("game", ["rock-paper-scissors", "prisoners-dilemma", "leduc-holdem",
                                   "limit-texas-holdem", "no-limit-texas-holdem", AUCTION])
def test_native_installed_console_modes(game, tmp_path, capsys):
    target = tmp_path / "test.eslams"
    options = []
    if game == AUCTION:
        authority = tmp_path / "local-custody"
        authority.write_bytes(AUCTION_TEST_KEY)
        authority.chmod(0o600)
        options = ["--auction-authority-file", str(authority)]
    assert main(["native", "run", "--arena", game, "--run-id", "cli-n",
                 "--blocks", "2", "--out", str(target), *options]) == 0
    assert json.loads(capsys.readouterr().out)["completed_rounds"] == 6
    assert main(["native", "verify", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["verification_scope"] == (
        "public_layout_digest_sequence_not_private_mechanics"
    )
    view = tmp_path / "timeline.html"
    assert main(["native", "replay", str(target), "--out", str(view)]) == 0
    assert "Public event journal" in view.read_text()
    assert main(["validate", str(target)]) == 1  # No ordinary v1 reinterpretation.


@pytest.mark.parametrize("game", ["rock-paper-scissors", "limit-texas-holdem", AUCTION])
def test_runner_boundary_resume_matches_full_output(game):
    prior = []
    profile = NativeProfile(game, 3)
    options = {"auction_authority": AUCTION_TEST_KEY} if game == AUCTION else {}
    full = run_local_native(profile, "resume-cli-boundary", checkpoint_key=CUSTODY_TEST_KEY,
                            save_checkpoint=prior.append, **options)
    assert [checkpoint.settled_rounds for checkpoint in prior] == list(range(1, 9))
    again = run_local_native(profile, "resume-cli-boundary", checkpoint_key=CUSTODY_TEST_KEY,
                             checkpoint=prior[2], **options)
    assert full.contents == again.contents


def test_interrupted_match_has_full_journal_but_no_final_score():
    arena = NativeRoundArena(NativeProfile("rock-paper-scissors", 3), "interrupted")

    def policy(obs):
        if obs.round_index == 3:
            raise KeyboardInterrupt
        return obs.legal[0]

    match = run_native_match(arena, dict.fromkeys(arena.seats, policy))
    check = verify_native_replay(match.contents)
    assert check.manifest["completed_rounds"] == 2
    assert check.manifest["score_quanta"] is None
    assert check.events[-1]["reason"] == "interrupted"
    assert len(check.events) == len(match.events)


def test_verifier_refuses_unknown_fields_even_with_matching_public_digest():
    match = run_local_native(NativeProfile("rock-paper-scissors"), "changed-fields")
    with ZipFile(BytesIO(match.contents)) as z:
        m = json.loads(z.read("manifest.json"))
        events = [json.loads(line) for line in z.read("public/events.jsonl").splitlines()]
    events[0]["private_field"] = "not permitted"
    stream = "".join(canonical_json(e) + "\n" for e in events)
    m["event_stream_sha256"] = sha256_text(stream)
    out = BytesIO()
    with ZipFile(out, "w") as z:
        z.writestr("manifest.json", canonical_json(m) + "\n")
        z.writestr("public/events.jsonl", stream)
    with pytest.raises(ValueError, match="native replay contract"):
        verify_native_replay(out.getvalue())


@pytest.mark.parametrize("game,key", [
    ("hanabi", "visible_partner_hand"),
    ("bridge", "hand"),
    ("bargaining", "private_reserve_share"),
    ("goofspiel", "remaining_hand"),
    ("liars-dice", "your_dice"),
    ("limit-texas-holdem", "hole"),
])
def test_supported_plugin_gets_owned_actual_current_facts_and_full_chronology(game, key):
    profile = NativeProfile(game, 2)
    arena = NativeRoundArena(profile, "policy-view")
    seen: dict[str, list[tuple[int, str]]] = {s: [] for s in arena.seats}
    authority = b"a test-only independent private authority"
    secret_keys = {"seed", "rng_commitment", "private_state_by_player", "pending_bid", "deck",
                   "reserves", "unmet_reserves", "authority"}

    def callback(observation):
        facts = json.loads(observation.current_game_json)
        assert key in facts and not secret_keys.intersection(facts)
        previous = seen[observation.seat_id]
        accepted = [(entry.global_action_index, entry.observation_json)
                    for entry in observation.own_decision_history]
        assert accepted == previous
        previous.append((observation.global_action_index + 1, observation.current_game_json))
        return observation.legal[-1] if observation.round_index == 4 else observation.legal[0]

    ids = {s: "review.policy.r1:" + s for s in arena.seats}
    policies = dict.fromkeys(arena.seats, callback)
    with pytest.raises(ValueError, match="private match authority"):
        run_local_native(profile, "plugin", seat_policies=policies, policy_ids=ids)
    result = run_local_native(profile, "plugin", private_authority=authority,
                              seat_policies=policies, policy_ids=ids)
    assert verify_native_replay(result.contents).manifest["completed_rounds"] == 6
    assert all(n for n in seen.values())


def test_supported_plugin_resume_rejects_changed_agent_identity_and_mode():
    profile = NativeProfile("prisoners-dilemma", 3)
    arena = NativeRoundArena(profile, "plugin-resume")
    receipt = []
    ids = {s: "stable.v1:" + s for s in arena.seats}

    def policy(obs):
        return ("defect" if obs.round_index > 3 and len(obs.own_decision_history) >= 3
                else "cooperate")

    policies = dict.fromkeys(arena.seats, policy)
    result = run_local_native(profile, "plugin-resume", seat_policies=policies, policy_ids=ids,
                              checkpoint_key=CUSTODY_TEST_KEY, save_checkpoint=receipt.append)
    again = run_local_native(profile, "plugin-resume", seat_policies=policies, policy_ids=ids,
                             checkpoint_key=CUSTODY_TEST_KEY, checkpoint=receipt[2])
    assert result.contents == again.contents
    control = run_local_native(profile, "plugin-resume", history=False,
                               seat_policies=policies, policy_ids=ids)
    assert result.score != control.score
    for override in ({"history": False}, {"policy_ids": dict.fromkeys(arena.seats, "different")}):
        opts = {"policy_ids": ids, **override}
        with pytest.raises(ValueError, match="unsupported private checkpoint metadata"):
            run_local_native(profile, "plugin-resume", seat_policies=policies,
                             checkpoint_key=CUSTODY_TEST_KEY, checkpoint=receipt[2], **opts)
