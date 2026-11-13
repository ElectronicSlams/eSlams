from __future__ import annotations

import json
import zipfile

import pytest

from eslams.agents import MockProviderAgent
from eslams.artifacts import ArtifactValidator
from eslams.continuation import (
    ChessContinuation,
    digest_bytes,
    local_chess_continuation_engine_identity,
    prepare_chess_continuation,
)
from eslams.contracts.versions import CORE_PACKAGE_VERSION, RUNNER_VERSION
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner

MOVES = ["f2f3", "e7e5", "g2g4", "d8h4"]


@pytest.fixture(autouse=True, scope="function")
def synthetic_continuation_runtime(monkeypatch):
    """These synthetic game tests use local targets, even inside an extracted sdist.

    Only this module substitutes runtime identity resolution. Installed-build trust
    and packaged-runtime refusal are exercised without this fixture in
    test_continuation_build.py; production resolution remains unchanged.
    """
    monkeypatch.setattr(
        "eslams.continuation.chess_continuation_engine_identity",
        local_chess_continuation_engine_identity,
    )


class Scripted(MockProviderAgent):
    id = "fixture"
    version = "1"
    provider = "mock"
    model = "fixture-model"

    def __init__(self, fail_at=None, moves=None):
        super().__init__(model="fixture-model")
        self.fail_at = fail_at
        self.moves = moves or MOVES
        self.calls = []

    def _remember_receipt(self, receipt):
        # Platform bridge locks a catalogue version, distinct from provider model ID.
        if receipt.get("outcome") == "ok":
            receipt["locked_model_id"] = "v1"
            receipt["model_identity_source"] = "provider_response"
        super()._remember_receipt(receipt)

    def act(self, request):
        self.calls.append(request)
        self.scenario = "provider_error" if request.turn_id == self.fail_at else "success"
        super().act(request)
        return ActResponse(action=self.moves[request.turn_id])


def source_run(tmp_path, *, fail_at=2, moves=None, run_id="source"):
    agent = Scripted(fail_at, moves)
    result = Runner().run(
        RunConfig(
            arena_id="chess",
            agent_1=agent,
            agent_2=agent,
            max_turns=240,
            seed=7,
            output_dir=tmp_path,
            archive=True,
            run_id=run_id,
            case_id="platform-" + run_id,
        )
    )
    return result, agent


def pins(result):
    manifest = json.loads((result.expanded_path / "manifest.json").read_text())
    source = {
        "matchId": manifest["run_metadata"].get("continuation_match_id", "platform-match"),
        "runId": manifest["run_metadata"]["case_id"],
        "artifactId": manifest["artifact_id"],
        "artifactKey": "private/source.eslams",
        "artifactSha256": digest_bytes(result.artifact_path.read_bytes()),
    }
    execution = {
        "coreVersion": CORE_PACKAGE_VERSION,
        "coreRef": "120847e60ffd3acc06fc17ad71d3b1413665163e",
        "coreSourceSha256": "1" * 64,
        "arenaSlug": "chess",
        "arenaVersion": "1.2.0",
        "variantSlug": "standard",
        "runnerVersion": RUNNER_VERSION,
        "wrapperVersion": "legal_action_v1:1.0.0",
        "scoringPolicyVersion": "chess-score:1.0.0",
        "rulesSha256": "2" * 64,
        "seed": 7,
        "maxTurns": 240,
        "sourcePayloadSha256": "3" * 64,
        "players": [
            {
                "seat": seat,
                "modelId": "model",
                "modelVersionId": "v1",
                "providerModelId": "fixture-model",
                "routeKey": "fixture",
                "routeSha256": "4" * 64,
            }
            for seat in ("player_1", "player_2")
        ],
    }
    lineage_path = result.expanded_path / "continuation/lineage.json"
    if lineage_path.exists():
        engine = json.loads(lineage_path.read_text())["targetEngine"]
        for key in (
            "coreVersion",
            "coreRef",
            "coreSourceSha256",
            "runnerVersion",
            "wrapperVersion",
        ):
            execution[key] = engine[key]
    return source, execution


def continuation(result):
    identity, execution = pins(result)
    descriptor = prepare_chess_continuation(result.artifact_path, identity, execution)
    target = local_chess_continuation_engine_identity(wrapper_version=execution["wrapperVersion"])
    return ChessContinuation(
        result.artifact_path,
        descriptor,
        target,
        child_platform_run_id="next-" + identity["runId"],
        match_id="next-" + identity["matchId"],
    )


def run_child(tmp_path, cont, *, agent=None, run_id="child", **changes):
    agent = agent or Scripted()
    result = Runner().run(
        RunConfig(
            arena_id="chess",
            agent_1=agent,
            agent_2=agent,
            max_turns=240,
            seed=7,
            output_dir=tmp_path,
            archive=True,
            run_id=run_id,
            continuation=cont,
            case_id=cont.child_platform_run_id,
            run_job_id=cont.child_platform_run_id,
            **changes,
        )
    )
    return result, agent


def test_continue_to_checkmate_without_old_calls(tmp_path):
    source, original_agent = source_run(tmp_path / "source")
    before = source.artifact_path.read_bytes()
    cont = continuation(source)
    child, agent = run_child(tmp_path / "child", cont)
    assert [call.turn_id for call in original_agent.calls] == [0, 1, 2]
    assert [call.turn_id for call in agent.calls] == [2, 3]
    assert [row["action"] for row in agent.calls[0].history] == MOVES[:2]
    assert len(child.trace_events) == 4
    assert len(child.replay_events) == 5
    assert child.score.outcome == {"winner": "player_2", "reason": "checkmate"}
    assert child.score.match_valid_for_scoring
    assert child.score.metrics["execution_label"] == "continued"
    assert child.score.model_identity_verified is False
    assert source.artifact_path.read_bytes() == before
    assert ArtifactValidator().validate(child.artifact_path) == []
    assert [row.public["action_provenance"] for row in child.trace_events[:2]] == [
        "reconstructed_action",
        "reconstructed_action",
    ]
    assert (child.expanded_path / "continuation/source_provider_receipts.jsonl").read_bytes() == (
        source.expanded_path / "receipts/provider_receipts.jsonl"
    ).read_bytes()


def test_repeat_interruption_keeps_full_history(tmp_path):
    source, _ = source_run(tmp_path / "source", fail_at=1)
    middle, middle_agent = run_child(
        tmp_path / "middle", continuation(source), agent=Scripted(fail_at=3), run_id="middle"
    )
    assert [r.turn_id for r in middle_agent.calls] == [1, 2, 3]
    assert not middle.score.match_valid_for_scoring
    assert ArtifactValidator().validate(middle.artifact_path) == []
    child, agent = run_child(tmp_path / "child", continuation(middle))
    assert [r.turn_id for r in agent.calls] == [3]
    assert [row["action"] for row in agent.calls[0].history] == MOVES[:3]
    assert child.score.outcome["reason"] == "checkmate"
    assert ArtifactValidator().validate(child.artifact_path) == []


def test_repetition_history_is_reconstructed(tmp_path):
    moves = ["g1f3", "g8f6", "f3g1", "f6g8"] * 2 + ["claim-draw"]
    source, _ = source_run(tmp_path / "source", fail_at=8, moves=moves)
    child, agent = run_child(tmp_path / "child", continuation(source), agent=Scripted(moves=moves))
    assert agent.calls[0].turn_id == 8
    assert "claim-draw" in agent.calls[0].legal_actions
    assert len(agent.calls[0].history) == 8
    assert child.score.outcome["reason"] == "threefold_repetition"
    assert ArtifactValidator().validate(child.artifact_path) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", 8),
        ("maxTurns", 200),
        ("arenaSlug", "checkers"),
        ("variantSlug", "chess960"),
        ("wrapperVersion", "wrong"),
        ("coreVersion", "0.6.0"),
    ],
)
def test_wrong_source_pins_rejected(tmp_path, field, value):
    source, _ = source_run(tmp_path / "source")
    identity, execution = pins(source)
    execution[field] = value
    with pytest.raises(ValueError):
        prepare_chess_continuation(source.artifact_path, identity, execution)


def test_source_hash_and_descriptor_tamper_before_calls(tmp_path):
    source, _ = source_run(tmp_path / "source")
    cont = continuation(source)
    cont.descriptor["prefix"]["acceptedPlyCount"] += 1
    agent = Scripted()
    with pytest.raises(ValueError):
        run_child(tmp_path / "child", cont, agent=agent)
    assert agent.calls == []
    source.artifact_path.write_bytes(source.artifact_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="archive hash mismatch"):
        run_child(tmp_path / "child", cont, agent=agent)
    assert agent.calls == []


def test_terminal_source_and_official_continuation_rejected(tmp_path):
    terminal, _ = source_run(tmp_path / "terminal", fail_at=None)
    with pytest.raises(ValueError, match="not interrupted"):
        continuation(terminal)
    source, _ = source_run(tmp_path / "source")
    with pytest.raises(ValueError, match="official_eval rejects continuation"):
        run_child(tmp_path / "child", continuation(source), execution_profile="official_eval")


def test_invalid_lineage_cannot_hide_behind_rehashed_manifest(tmp_path):
    source, _ = source_run(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", continuation(source))
    from eslams.artifacts import _file_entries
    from eslams.hashing import sha256_json

    path = child.expanded_path / "continuation/lineage.json"
    lineage = json.loads(path.read_text())
    lineage["historicalLedger"]["receiptCount"] += 1
    path.write_text(json.dumps(lineage))
    manifest_path = child.expanded_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = _file_entries(child.expanded_path)
    manifest["artifact_id"] = sha256_json(manifest["files"])
    manifest_path.write_text(json.dumps(manifest))
    assert any("ledger digest" in err for err in ArtifactValidator().validate(child.expanded_path))


def test_duplicate_archive_member_rejected(tmp_path):
    source, _ = source_run(tmp_path / "source")
    identity, execution = pins(source)
    with zipfile.ZipFile(source.artifact_path, "a") as archive, pytest.warns(UserWarning):
        archive.writestr("manifest.json", "{}")
    identity["artifactSha256"] = digest_bytes(source.artifact_path.read_bytes())
    with pytest.raises(ValueError, match="duplicate"):
        prepare_chess_continuation(source.artifact_path, identity, execution)


def test_changed_engine_or_agent_rejected_before_call(tmp_path):
    source, _ = source_run(tmp_path / "source")
    cont = continuation(source)
    cont.target_engine_identity["coreSourceSha256"] = "0" * 64
    agent = Scripted()
    with pytest.raises(ValueError, match="runtime source"):
        run_child(tmp_path / "child", cont, agent=agent)
    assert not agent.calls
    cont = continuation(source)
    agent.model = "wrong-model"
    with pytest.raises(ValueError, match="agent model"):
        run_child(tmp_path / "child", cont, agent=agent)
    assert not agent.calls


def receipt_rows(result, path="receipts/provider_receipts.jsonl"):
    return [json.loads(line) for line in (result.expanded_path / path).read_bytes().splitlines()]


def test_three_executions_keep_all_physical_receipts_once(tmp_path):
    source, _ = source_run(tmp_path / "source", fail_at=1)
    source_bytes = (source.expanded_path / "receipts/provider_receipts.jsonl").read_bytes()
    middle, _ = run_child(
        tmp_path / "middle", continuation(source), agent=Scripted(fail_at=3), run_id="middle"
    )
    middle_bytes = (middle.expanded_path / "receipts/provider_receipts.jsonl").read_bytes()
    child, agent = run_child(tmp_path / "child", continuation(middle))
    assert [call.turn_id for call in agent.calls] == [3]
    historical = (child.expanded_path / "continuation/source_provider_receipts.jsonl").read_bytes()
    assert historical == source_bytes + middle_bytes
    rows = receipt_rows(child, "continuation/source_provider_receipts.jsonl") + receipt_rows(child)
    assert len(rows) == 6  # Four accepted moves, two failed physical calls.
    assert len({row["event_id"] for row in rows}) == 6
    assert sum(row["outcome"] != "ok" for row in rows) == 2
    assert len(receipt_rows(child)) == 1
    assert child.score.aggregate_usage["totalTokens"] == 10  # Only this execution's one call.
    assert ArtifactValidator().validate(child.artifact_path) == []


class LegacyBridge:
    id = "unconfigured-http-fixture"
    version = "1"

    def __init__(self, agent):
        self.agent = agent

    @property
    def last_receipt(self):
        return self.agent.last_receipt

    @property
    def attempt_receipts(self):
        return self.agent.attempt_receipts

    def act(self, request):
        return self.agent.act(request)


class UnknownFailure(Scripted):
    def _remember_receipt(self, receipt):
        if receipt.get("outcome") != "ok":
            receipt.update(
                model="unknown",
                locked_model_id="v1",
                model_identity_source="provider_response",
                status_code=402,
            )
        super()._remember_receipt(receipt)


def test_legacy_false_applied_flags_and_unknown_402_are_never_rewritten(tmp_path):
    agent = LegacyBridge(UnknownFailure(fail_at=2))
    source = Runner().run(
        RunConfig(
            arena_id="chess",
            agent_1=agent,
            agent_2=agent,
            max_turns=240,
            seed=7,
            output_dir=tmp_path / "source",
            archive=True,
            run_id="source",
            case_id="platform-source",
        )
    )
    before = source.artifact_path.read_bytes()
    original = receipt_rows(source)
    assert all(row["action_applied"] is False for row in original)
    assert original[-1]["model"] == "unknown" and original[-1]["status_code"] == 402
    child, _ = run_child(tmp_path / "child", continuation(source))
    assert receipt_rows(child, "continuation/source_provider_receipts.jsonl") == original
    assert all(
        row["action_applied"] is False
        for row in receipt_rows(child, "continuation/source_provider_receipts.jsonl")
    )
    assert source.artifact_path.read_bytes() == before
    assert child.score.outcome["reason"] == "checkmate"
    assert ArtifactValidator().validate(child.artifact_path) == []


@pytest.mark.parametrize("fault", ["missing", "version", "model", "untrusted"])
def test_new_call_without_exact_platform_pins_is_preserved_but_not_applied(tmp_path, fault):
    source, _ = source_run(tmp_path / "source")

    class Faulty(Scripted):
        def act(self, request):
            response = super().act(request)
            if fault == "missing":
                self.attempt_receipts = []
                self.last_receipt = None
            elif fault == "version":
                self.attempt_receipts[-1]["locked_model_id"] = "wrong-version"
            elif fault == "model":
                self.attempt_receipts[-1]["model"] = "wrong-model"
                # Keep the fixture's price-card assertions internally consistent.
                self.attempt_receipts[-1]["estimated_cost"] = {"status": "cost_unavailable"}
            else:
                self.attempt_receipts[-1]["locked_model_id"] = None
                self.attempt_receipts[-1]["model_identity_source"] = None
            return response

    child, agent = run_child(tmp_path / "child", continuation(source), agent=Faulty())
    assert [r.turn_id for r in agent.calls] == [2]
    assert len(child.trace_events) == 2
    assert child.score.outcome is None and not child.score.match_valid_for_scoring
    assert "model_identity_mismatch" in child.score.invalid_reason_codes
    assert all(row["action_applied"] is False for row in receipt_rows(child))
    assert len(receipt_rows(child)) == int(fault != "missing")
    assert ArtifactValidator().validate(child.artifact_path) == []


def test_public_export_omits_private_continuation_evidence(tmp_path):
    from eslams.public_replay import export_public_replay

    source, _ = source_run(tmp_path / "source")
    cont = continuation(source)
    cont.descriptor["source"]["artifactKey"] = "private-custody-canary/source.eslams"
    # The descriptor key is trusted external custody; it does not alter archive bytes.
    child, _ = run_child(tmp_path / "child", cont)
    exported = export_public_replay(child.artifact_path, tmp_path / "public")
    contents = b"\n".join(path.read_bytes() for path in exported.rglob("*") if path.is_file())
    assert b"private-custody-canary" not in contents
    assert b"source_provider_receipts" not in contents
    assert b"sourceLogicalActionId" not in contents
    assert b"reconstructed_action" in contents
    public = (child.expanded_path / "traces/public_trace.jsonl").read_bytes()
    assert b"sourceLogicalActionId" not in public


def test_resume_at_ply_88_with_89_states_and_no_prefix_calls(tmp_path):
    import random

    from eslams.arenas.chess import ChessArena

    arena = ChessArena()
    for seed in range(100):
        rng = random.Random(seed)
        state = arena.initial_state(7)
        moves = []
        while not state.terminal and len(moves) < 90:
            action = rng.choice(
                [
                    a
                    for a in arena.legal_actions_for(state, state.active_player)
                    if not a.startswith("claim-draw")
                ]
            )
            moves.append(action)
            state = arena.apply_action(state, state.active_player, action)
        if len(moves) == 90:
            break
    assert len(moves) == 90
    source, _ = source_run(tmp_path / "source", fail_at=88, moves=moves)
    assert len(source.trace_events) == 88 and len(source.replay_events) == 89
    child, agent = run_child(
        tmp_path / "child", continuation(source), agent=Scripted(fail_at=89, moves=moves)
    )
    assert [r.turn_id for r in agent.calls] == [88, 89]
    assert len(agent.calls[0].history) == 88
    assert len(child.trace_events) == 89 and len(child.replay_events) == 90
    assert len(receipt_rows(child)) == 2
    assert len(receipt_rows(child, "continuation/source_provider_receipts.jsonl")) == 89
    assert ArtifactValidator().validate(child.artifact_path) == []


def rearchive(result):
    from eslams.artifacts import _file_entries, _write_archive
    from eslams.hashing import sha256_json

    manifest_path = result.expanded_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = _file_entries(result.expanded_path)
    manifest["artifact_id"] = sha256_json(manifest["files"])
    manifest_path.write_text(json.dumps(manifest))
    replacement = result.artifact_path.with_suffix(".replacement")
    _write_archive(result.expanded_path, replacement)
    replacement.replace(result.artifact_path)


@pytest.mark.parametrize(
    "fault", ["fallback", "duplicate_trace", "duplicate_receipt", "receipt_model", "case_id"]
)
def test_source_semantic_tampering_is_rejected_after_full_rehash(tmp_path, fault):
    source, _ = source_run(tmp_path / "source")
    if fault in {"fallback", "duplicate_trace"}:
        path = source.expanded_path / "traces/auditor_trace.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        if fault == "fallback":
            rows[0]["action_provenance"] = "fallback_action"
        else:
            rows[1]["event_id"] = rows[0]["event_id"]
    elif fault in {"duplicate_receipt", "receipt_model"}:
        path = source.expanded_path / "receipts/provider_receipts.jsonl"
        rows = receipt_rows(source)
        if fault == "duplicate_receipt":
            rows[1]["event_id"] = rows[0]["event_id"]
        else:
            rows[0]["model"] = "contradictory-model"
    else:
        identity, execution = pins(source)
        identity["runId"] = "wrong-platform-run"
        with pytest.raises(ValueError, match="case ID"):
            prepare_chess_continuation(source.artifact_path, identity, execution)
        return
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    rearchive(source)
    with pytest.raises(ValueError):
        continuation(source)


def test_child_cannot_reuse_any_ancestor_identity(tmp_path):
    source, _ = source_run(tmp_path / "source", fail_at=1)
    middle, _ = run_child(
        tmp_path / "middle", continuation(source), agent=Scripted(fail_at=3), run_id="middle"
    )
    cont = continuation(middle)
    agent = Scripted()
    with pytest.raises(ValueError, match="source identity"):
        run_child(tmp_path / "child", cont, agent=agent, run_id="source")
    assert agent.calls == []
    from dataclasses import replace

    with pytest.raises(ValueError, match="new match"):
        run_child(tmp_path / "child", replace(cont, match_id="platform-match"), agent=agent)
    assert agent.calls == []


def test_target_wrapper_and_overwrite_rejected_before_call(tmp_path):
    source, _ = source_run(tmp_path / "source")
    cont = continuation(source)
    agent = Scripted()
    cont.target_engine_identity.update(
        local_chess_continuation_engine_identity(wrapper_version="wrong-wrapper")
    )
    with pytest.raises(ValueError, match="target engine"):
        run_child(tmp_path / "child", cont, agent=agent)
    assert agent.calls == []
    with pytest.raises(ValueError, match="overwrite"):
        run_child(tmp_path / "child", continuation(source), agent=agent, overwrite=True)
    assert agent.calls == []


def test_changed_time_budget_rejected_before_call(tmp_path):
    source, _ = source_run(tmp_path / "source")
    agent = Scripted()
    with pytest.raises(ValueError, match="time budget"):
        run_child(tmp_path / "child", continuation(source), agent=agent, time_budget_ms=500)
    assert agent.calls == []


def test_source_alias_is_rejected_and_private_pins_do_not_enter_requests(tmp_path):
    source, _ = source_run(tmp_path / "source")
    identity, execution = pins(source)
    alias = tmp_path / "alias.eslams"
    alias.symlink_to(source.artifact_path)
    with pytest.raises(ValueError, match="non-symlink"):
        prepare_chess_continuation(alias, identity, execution)
    from eslams.continuation import digest_json
    from eslams.public_replay import export_public_replay

    cont = continuation(source)
    cont.descriptor["execution"]["players"][0]["private_custody_extension"] = "private-route-canary"
    cont.descriptor["executionSpecSha256"] = digest_json(cont.descriptor["execution"])
    child, agent = run_child(tmp_path / "child", cont)
    assert all("continuation_player_pin" not in call.metadata for call in agent.calls)
    assert all("routeSha256" not in json.dumps(call.to_dict()) for call in agent.calls)
    assert all("private-route-canary" not in json.dumps(call.to_dict()) for call in agent.calls)
    exported = export_public_replay(child.artifact_path, tmp_path / "public-canary")
    assert all(
        b"private-route-canary" not in path.read_bytes()
        for path in exported.rglob("*")
        if path.is_file()
    )
    assert child.score.outcome["reason"] == "checkmate"


def test_continued_source_platform_identity_is_bound_to_existing_lineage(tmp_path):
    source, _ = source_run(tmp_path / "source", fail_at=1)
    middle, _ = run_child(
        tmp_path / "middle", continuation(source), agent=Scripted(fail_at=3), run_id="middle"
    )
    identity, execution = pins(middle)
    identity["matchId"] = "unrelated-platform-match"
    with pytest.raises(ValueError, match="Platform identity"):
        prepare_chess_continuation(middle.artifact_path, identity, execution)


@pytest.mark.parametrize("field", ["coreVersion", "runnerVersion", "wrapperVersion"])
def test_rehashed_target_engine_cannot_disagree_with_artifact_versions(tmp_path, field):
    from eslams.continuation import digest_json

    source, _ = source_run(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", continuation(source))
    path = child.expanded_path / "continuation/lineage.json"
    lineage = json.loads(path.read_text())
    lineage["targetEngine"][field] = "wrong-version"
    lineage["targetEngineSha256"] = digest_json(lineage["targetEngine"])
    path.write_text(json.dumps(lineage))
    rearchive(child)
    assert any(
        "target engine versions" in error
        for error in ArtifactValidator().validate(child.artifact_path)
    )


@pytest.mark.parametrize(
    "field", ["requested_model", "model_version_id", "route_key", "route_sha256"]
)
def test_http_normalization_does_not_erase_contradictory_bridge_identity(tmp_path, field):
    from eslams.agents import _http_provider_receipt
    from eslams.continuation import new_call_matches_pin

    source, _ = source_run(tmp_path / "source")
    row = receipt_rows(source)[0]
    _, execution = pins(source)
    assert new_call_matches_pin([row], execution["players"][0])
    row[field] = "contradiction"
    normalized = _http_provider_receipt(
        row, provider="mock", model="fixture-model", endpoint_metadata={}
    )
    assert normalized[field] == "contradiction"
    assert not new_call_matches_pin([normalized], execution["players"][0])


@pytest.mark.parametrize(
    "fault", [None, "requested_model", "model_version_id", "route_key", "route_sha256"]
)
def test_actual_http_agent_cannot_hide_raw_pin_contradictions(tmp_path, monkeypatch, fault):
    import copy

    import httpx

    from eslams.agents import HttpAgent

    source, _ = source_run(tmp_path / "source")
    template = receipt_rows(source)[0]
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(json)
        receipt = copy.deepcopy(template)
        if fault:
            receipt[fault] = "contradiction"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"action": MOVES[json["turn_id"]], "metadata": {"provider_receipt": receipt}},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", fake_post)
    agent = HttpAgent(url="https://fixture.invalid/act", provider="mock", model="fixture-model")
    child, _ = run_child(tmp_path / "child", continuation(source), agent=agent)
    if fault:
        assert [row["turn_id"] for row in calls] == [2]
        assert child.score.outcome is None and not child.score.match_valid_for_scoring
        assert "model_identity_mismatch" in child.score.invalid_reason_codes
        assert receipt_rows(child)[0][fault] == "contradiction"
        assert receipt_rows(child)[0]["action_applied"] is False
    else:
        assert [row["turn_id"] for row in calls] == [2, 3]
        assert child.score.outcome["reason"] == "checkmate"
    assert ArtifactValidator().validate(child.artifact_path) == []


def test_paid_new_action_cannot_be_relabelled_as_public_reconstruction(tmp_path):
    source, _ = source_run(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", continuation(source))
    for name in ("traces/public_trace.jsonl", "replay/replay_events.jsonl"):
        path = child.expanded_path / name
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[-1].update(action_provenance="reconstructed_action", successful_attempt_event_id=None)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    rearchive(child)
    assert any(
        "new action projection" in error
        for error in ArtifactValidator().validate(child.artifact_path)
    )


@pytest.mark.parametrize("field", ["model_version_id", "route_key", "route_sha256"])
def test_historical_optional_attestation_cannot_contradict_source_pins(tmp_path, field):
    source, _ = source_run(tmp_path / "source")
    path = source.expanded_path / "receipts/provider_receipts.jsonl"
    rows = receipt_rows(source)
    rows[0][field] = "contradiction"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    rearchive(source)
    with pytest.raises(ValueError, match="optional identity mismatch"):
        continuation(source)


@pytest.mark.parametrize("kind", ["orphan_applied", "future_applied", "future_failed"])
def test_incremental_receipts_must_reconcile_with_executed_suffix(tmp_path, kind):
    import copy

    from eslams.contracts.provider import provider_attempt_event_id

    source, _ = source_run(tmp_path / "source")
    child, _ = run_child(tmp_path / "child", continuation(source))
    rows = receipt_rows(child)
    extra = copy.deepcopy(rows[0])
    if kind == "orphan_applied":
        extra.update(attempt=2, attempt_index=2)
        rows.insert(1, extra)
    else:
        extra.update(turn_id=99, logical_action_id="child:episode_001:player_1:000099")
        if kind == "future_failed":
            extra.update(outcome="provider_unavailable", status="failed", action_applied=False)
        rows.append(extra)
    extra["event_id"] = provider_attempt_event_id(
        physical_run_id=extra["physical_run_id"],
        case_id=extra["case_id"],
        case_attempt_index=extra["case_attempt_index"],
        logical_action_id=extra["logical_action_id"],
        attempt_index=extra["attempt_index"],
    )
    path = child.expanded_path / "receipts/provider_receipts.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    rearchive(child)
    assert ArtifactValidator().validate(child.artifact_path)
