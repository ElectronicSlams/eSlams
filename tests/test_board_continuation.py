"""Current public-board continuation, deliberately not a legacy archive migration."""
from __future__ import annotations

import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest
from test_chess_continuation import Scripted, pins, rearchive, receipt_rows

from eslams.arenas import registry
from eslams.artifacts import ArtifactValidator
from eslams.catalogue import game_catalogue_rows
from eslams.continuation import (
    BOARD_ARENAS,
    BOARD_DESCRIPTOR_VERSION,
    BOARD_LINEAGE_VERSION,
    BoardContinuation,
    ChessContinuation,
    _reconstruct,
    board_continuation_child_execution,
    board_continuation_engine_identity,
    chess_continuation_child_execution,
    digest_json,
    local_board_continuation_engine_identity,
    prepare_board_continuation,
    prepare_chess_continuation,
    verify_board_continuation,
)
from eslams.contracts.board_continuation import (
    board_continuation_examples,
    board_continuation_schemas,
)
from eslams.protocol import ActResponse
from eslams.runner import RunConfig, Runner

ARENAS = sorted(BOARD_ARENAS)


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    # Synthetic sdist tests may exercise the rules. Separate tests below never
    # substitute the actual installed-runtime refusal.
    monkeypatch.setattr("eslams.continuation.board_continuation_engine_identity",
                        local_board_continuation_engine_identity)


class BoardAgent(Scripted):
    def act(self, request):
        self.calls.append(request)
        self.scenario = "provider_error" if request.turn_id == self.fail_at else "success"
        # Keep mock transport receipt behavior but use the requested arena's legal action.
        from eslams.agents import MockProviderAgent
        MockProviderAgent.act(self, request)
        return ActResponse(action=request.legal_actions[0])


def source_run(tmp_path, arena_id, *, fail_at=2, max_turns=None):
    agent = BoardAgent(fail_at=fail_at)
    result = Runner().run(RunConfig(
        arena_id=arena_id, agent_1=agent, agent_2=agent, seed=7, max_turns=max_turns,
        output_dir=tmp_path, archive=True, run_id="source", case_id="platform-source",
    ))
    return result, agent


def board_pins(result):
    source, execution = pins(result)
    arena = registry.create(result.score.arena_id)
    execution.update(arenaSlug=arena.id, arenaVersion=arena.version,
                     scoringPolicyVersion=f"{arena.id}-score:1.0.0")
    execution["rulesSha256"] = digest_json(next(
        row["public_rules"] for row in game_catalogue_rows() if row["game_id"] == arena.id
    ))
    return source, execution


def continuation(result, *, native=False):
    source, execution = board_pins(result)
    descriptor = prepare_board_continuation(result.artifact_path, source, execution)
    return BoardContinuation(
        result.artifact_path, descriptor,
        local_board_continuation_engine_identity(wrapper_version=execution["wrapperVersion"]),
        child_platform_run_id="next-" + source["runId"], match_id="next-" + source["matchId"],
        child_execution=board_continuation_child_execution(
            descriptor, turn_limit_policy="native-arena-horizon" if native else "preserve-source"
        ),
    )


def run_child(tmp_path, cont, *, agent=None, **changes):
    agent = agent or BoardAgent()
    result = Runner().run(RunConfig(
        arena_id=changes.pop("arena_id", cont.descriptor["execution"]["arenaSlug"]),
        agent_1=agent, agent_2=agent, seed=7,
        max_turns=changes.pop("max_turns", cont.child_execution["maxTurns"]),
        output_dir=tmp_path, archive=True, run_id=changes.pop("run_id", "child"),
        case_id=cont.child_platform_run_id, run_job_id=cont.child_platform_run_id,
        continuation=cont, **changes,
    ))
    return result, agent


@pytest.mark.parametrize("arena_id", ARENAS)
def test_complete_from_exact_prefix_without_old_calls(tmp_path, arena_id):
    source, old_agent = source_run(tmp_path / "source", arena_id)
    original = source.artifact_path.read_bytes()
    cont = continuation(source)
    child, agent = run_child(tmp_path / "child", cont)
    assert [r.turn_id for r in old_agent.calls] == [0, 1, 2]
    assert agent.calls[0].turn_id == 2
    assert len(agent.calls[0].history) == 2
    assert child.replay_events[-1].terminal
    assert child.score.match_valid_for_scoring
    assert child.score.metrics["execution_label"] == "continued"
    assert not child.score.model_identity_verified
    assert source.artifact_path.read_bytes() == original
    assert ArtifactValidator().validate(child.artifact_path) == []
    assert (child.expanded_path / "continuation/source_provider_receipts.jsonl").read_bytes() == (
        source.expanded_path / "receipts/provider_receipts.jsonl").read_bytes()
    lineage = json.loads((child.expanded_path / "continuation/lineage.json").read_bytes())
    assert lineage["schemaVersion"] == BOARD_LINEAGE_VERSION
    jsonschema.validate(lineage, board_continuation_schemas()[BOARD_LINEAGE_VERSION])
    assert all(e.public["action_provenance"] == "reconstructed_action"
               for e in child.trace_events[:2])
    manifest = json.loads((child.expanded_path / "manifest.json").read_bytes())
    assert not manifest["aggregate_leaderboard_eligible"]
    # Identical native terminal state, including Othello legal pass actions.
    baseline, _ = source_run(tmp_path / "baseline", arena_id, fail_at=None)
    assert child.replay_events[-1].state_hash == baseline.replay_events[-1].state_hash
    assert child.score.outcome == baseline.score.outcome


@pytest.mark.parametrize("arena_id", ARENAS)
def test_repeat_interruption_preserves_segments_and_accounting(tmp_path, arena_id):
    source, _ = source_run(tmp_path / "source", arena_id, fail_at=1)
    middle, _ = run_child(tmp_path / "middle", continuation(source),
                          agent=BoardAgent(fail_at=3), run_id="middle")
    child, agent = run_child(tmp_path / "child", continuation(middle))
    assert agent.calls[0].turn_id == 3
    assert len(agent.calls[0].history) == 3
    history = (child.expanded_path / "continuation/source_provider_receipts.jsonl").read_bytes()
    assert history == b"".join((r.expanded_path / "receipts/provider_receipts.jsonl").read_bytes()
                               for r in (source, middle))
    assert len({r["event_id"] for r in receipt_rows(child)}) == len(agent.calls)
    assert child.score.aggregate_usage["totalTokens"] == 10 * len(agent.calls)
    assert ArtifactValidator().validate(child.artifact_path) == []


@pytest.mark.parametrize("arena_id", ARENAS)
def test_native_horizon_is_arena_owned_and_original_pin_unchanged(tmp_path, arena_id):
    source, _ = source_run(tmp_path / "source", arena_id, max_turns=4)
    cont = continuation(source, native=True)
    assert cont.descriptor["execution"]["maxTurns"] == 4
    assert cont.child_execution["maxTurns"] == registry.create(arena_id).max_turns
    child, _ = run_child(tmp_path / "child", cont)
    assert child.replay_events[-1].terminal
    assert ArtifactValidator().validate(child.artifact_path) == []
    bad = copy.deepcopy(cont.descriptor)
    bad["execution"]["rulesSha256"] = "0" * 64
    bad["executionSpecSha256"] = digest_json(bad["execution"])
    with pytest.raises(ValueError, match="rules mismatch"):
        board_continuation_child_execution(bad, turn_limit_policy="native-arena-horizon")


@pytest.mark.parametrize("arena_id", ARENAS)
def test_terminal_official_wrong_arena_and_tamper_fail_before_calls(tmp_path, arena_id):
    terminal, _ = source_run(tmp_path / "terminal", arena_id, fail_at=None)
    with pytest.raises(ValueError, match="not interrupted"):
        continuation(terminal)
    source, _ = source_run(tmp_path / "source", arena_id)
    cont = continuation(source)
    agent = BoardAgent()
    for changes in ({"execution_profile": "official_eval"}, {"arena_id": "chess"},
                    {"time_budget_ms": 123}, {"overwrite": True}):
        with pytest.raises(ValueError):
            run_child(tmp_path / "child", cont, agent=agent, **changes)
        assert not agent.calls
    cont.target_engine_identity["coreSourceSha256"] = "0" * 64
    with pytest.raises(ValueError, match="runtime source"):
        run_child(tmp_path / "child", cont, agent=agent)
    assert not agent.calls
    cont = continuation(source)
    cont.descriptor["prefix"]["acceptedPlyCount"] += 1
    with pytest.raises(ValueError):
        run_child(tmp_path / "child", cont, agent=agent)
    assert not agent.calls


@pytest.mark.parametrize("arena_id", ARENAS)
@pytest.mark.parametrize("fault", ["illegal", "fallback", "receipt", "legacy_failure"])
def test_rehashed_source_cannot_forge_eligibility(tmp_path, arena_id, fault):
    source, _ = source_run(tmp_path / "source", arena_id)
    if fault == "receipt":
        path = source.expanded_path / "receipts/provider_receipts.jsonl"
        rows = receipt_rows(source)
        rows[0]["locked_model_id"] = "other-version"
    elif fault == "legacy_failure":
        path = source.expanded_path / "scores/score.json"
        score = json.loads(path.read_bytes())
        score["invalid_reason_codes"] = ["agent_error", "agent_crash"]
        path.write_text(json.dumps(score))
        rearchive(source)
        with pytest.raises(ValueError):
            continuation(source)
        return
    else:
        path = source.expanded_path / "traces/auditor_trace.jsonl"
        rows = [json.loads(x) for x in path.read_bytes().splitlines()]
        if fault == "illegal":
            rows[0]["action"] = "impossible-move"
        else:
            rows[0]["action_provenance"] = "fallback_action"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    rearchive(source)
    with pytest.raises(ValueError):
        continuation(source)


@pytest.mark.parametrize("arena_id", ARENAS)
def test_prefix_reconstruction_rejects_illegal_and_postterminal_actions(tmp_path, arena_id):
    source, _ = source_run(tmp_path / "source", arena_id)
    verified = verify_board_continuation(continuation(source))
    bad = copy.deepcopy(verified.prefix)
    bad[0]["action"] = "impossible"
    with pytest.raises(ValueError, match="illegal prefix"):
        _reconstruct(bad, verified.descriptor["execution"])
    baseline, _ = source_run(tmp_path / "baseline", arena_id, fail_at=None)
    from eslams.continuation import _normalize_prefix
    prefix = _normalize_prefix([json.loads(x) for x in
        (baseline.expanded_path / "traces/auditor_trace.jsonl").read_bytes().splitlines()])
    with pytest.raises(ValueError, match="terminal prefix"):
        _reconstruct(prefix + [prefix[-1]], verified.descriptor["execution"])


@pytest.mark.parametrize("fault", ["model", "version", "route", "receipt_missing"])
def test_unattested_new_actions_are_never_applied(tmp_path, fault):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")

    class BadAgent(BoardAgent):
        def act(self, request):
            response = super().act(request)
            if fault == "receipt_missing":
                self.attempt_receipts = []
                self.last_receipt = None
            else:
                key = {"model": "model", "version": "locked_model_id", "route": "route_key"}[fault]
                self.attempt_receipts[-1][key] = "wrong"
                if fault == "model":
                    self.attempt_receipts[-1]["estimated_cost"] = {"status": "cost_unavailable"}
            return response

    child, agent = run_child(tmp_path / "child", continuation(source), agent=BadAgent())
    assert len(agent.calls) == 1
    assert len(child.trace_events) == 2
    assert not child.score.match_valid_for_scoring
    assert "model_identity_mismatch" in child.score.invalid_reason_codes
    assert all(not row["action_applied"] for row in receipt_rows(child))
    assert ArtifactValidator().validate(child.artifact_path) == []


def test_chess_and_board_namespaces_cannot_be_substituted(tmp_path):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")
    cont = continuation(source)
    with pytest.raises(ValueError, match="chess"):
        prepare_chess_continuation(source.artifact_path, *board_pins(source))
    with pytest.raises(ValueError, match="chess"):
        chess_continuation_child_execution(cont.descriptor)
    with pytest.raises(ValueError, match="API arena"):
        ChessContinuation(source.artifact_path, cont.descriptor, cont.target_engine_identity,
                          cont.child_platform_run_id, cont.match_id)
    with pytest.raises(ValueError, match="unsupported descriptor"):
        replace(cont, descriptor={**cont.descriptor, "schemaVersion": "chess-continuation/v1"})
    with pytest.raises(ValueError, match="unsupported target engine"):
        replace(cont, target_engine_identity={**cont.target_engine_identity,
                                              "schemaVersion": "chess-continuation-engine/v1"})


def test_installed_and_packaged_runtime_cannot_claim_local_board_support(tmp_path, monkeypatch):
    # Imported alias deliberately bypasses the synthetic runtime fixture above.
    from eslams import _build_provenance, continuation_build
    monkeypatch.setattr(_build_provenance, "PACKAGED_CORE_COMMIT", "1" * 40)
    with pytest.raises(ValueError, match="source checkout"):
        board_continuation_engine_identity(wrapper_version="fixture")
    monkeypatch.setattr(_build_provenance, "PACKAGED_CORE_COMMIT", None)
    installed = tmp_path / "build.json"
    installed.write_text("{}")
    monkeypatch.setattr(continuation_build, "BUILD_PATH", installed)
    with pytest.raises(ValueError, match="source checkout"):
        board_continuation_engine_identity(wrapper_version="fixture")
    installed.unlink()
    installed.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="source checkout"):
        board_continuation_engine_identity(wrapper_version="fixture")


def test_public_export_does_not_leak_board_custody(tmp_path):
    from eslams.public_replay import export_public_replay
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")
    cont = continuation(source)
    cont.descriptor["source"]["artifactKey"] = "private-board-custody-canary"
    child, agent = run_child(tmp_path / "child", cont)
    exported = export_public_replay(child.artifact_path, tmp_path / "public")
    for path in exported.rglob("*"):
        if path.is_file():
            assert b"private-board-custody-canary" not in path.read_bytes()
            assert b"sourceLogicalActionId" not in path.read_bytes()
    assert all("routeSha256" not in json.dumps(call.to_dict()) for call in agent.calls)


def test_board_schemas_examples_and_typescript_are_coordinated():
    schemas = board_continuation_schemas()
    typescript = (Path(__file__).parents[1] /
                  "packages/core-contracts/src/generated/board-continuation.ts").read_text()
    for version, example in board_continuation_examples().items():
        jsonschema.Draft202012Validator.check_schema(schemas[version])
        jsonschema.validate(example, schemas[version])
        assert f'"{version}"' in typescript
    for arena_id in ARENAS:
        assert f'"{arena_id}"' in typescript
    assert schemas[BOARD_DESCRIPTOR_VERSION]["properties"]["execution"]["properties"][
        "arenaSlug"]["enum"] == ["tic-tac-toe", "connect-four", "othello"]


def test_othello_pass_in_prefix_is_reconstructed_not_recalled(tmp_path):
    source, _ = source_run(tmp_path / "source", "othello", fail_at=19)
    assert source.trace_events[18].public["action"] == "pass"
    child, agent = run_child(tmp_path / "child", continuation(source))
    assert agent.calls[0].turn_id == 19
    assert agent.calls[0].history[18]["action"] == "pass"
    assert child.trace_events[18].public["action_provenance"] == "reconstructed_action"
    assert child.score.match_valid_for_scoring
    assert ArtifactValidator().validate(child.artifact_path) == []


@pytest.mark.parametrize("field,value", [
    ("arenaSlug", "checkers"), ("variantSlug", "custom"), ("arenaVersion", "0.0.1"), ("seed", 8),
])
def test_board_source_rejects_unsupported_or_inconsistent_execution(tmp_path, field, value):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")
    identity, execution = board_pins(source)
    execution[field] = value
    with pytest.raises(ValueError):
        prepare_board_continuation(source.artifact_path, identity, execution)


def test_runtime_without_checkout_is_not_local_identity_authorization(tmp_path, monkeypatch):
    import eslams.continuation as module
    from eslams import _build_provenance, continuation_build

    monkeypatch.setattr(module, "__file__", str(tmp_path / "installed/src/eslams/continuation.py"))
    monkeypatch.setattr(_build_provenance, "PACKAGED_CORE_COMMIT", None)
    monkeypatch.setattr(continuation_build, "BUILD_PATH", tmp_path / "absent-build.json")
    with pytest.raises(ValueError, match="source checkout"):
        board_continuation_engine_identity(wrapper_version="fixture")


def _rewrite_lineage(result, mutate):
    path = result.expanded_path / "continuation/lineage.json"
    lineage = json.loads(path.read_bytes())
    mutate(lineage)
    # Rehash every parent object to demonstrate semantic checks, not stale checksums.
    def rehash(node):
        if node["parentLineage"] is not None:
            rehash(node["parentLineage"])
        node["parentLineageSha256"] = digest_json(node["parentLineage"])
    rehash(lineage)
    path.write_text(json.dumps(lineage))
    rearchive(result)


@pytest.mark.parametrize("chess", [False, True])
@pytest.mark.parametrize("fault", [
    "arena", "namespace", "engine", "descriptor_digest", "engine_digest", "ledger_digest",
    "checkpoint", "seed", "route", "child_budget", "source_engine", "verification",
])
def test_every_parent_lineage_is_validated_after_outer_rehash(tmp_path, chess, fault, monkeypatch):
    if chess:
        from test_chess_continuation import continuation as prepare
        from test_chess_continuation import run_child as resume
        from test_chess_continuation import source_run as start

        from eslams.continuation import local_chess_continuation_engine_identity
        monkeypatch.setattr("eslams.continuation.chess_continuation_engine_identity",
                            local_chess_continuation_engine_identity)
        source, _ = start(tmp_path / "source", fail_at=1)
        middle, _ = resume(tmp_path / "middle", prepare(source),
                           agent=Scripted(fail_at=2), run_id="middle")
        child, _ = resume(tmp_path / "child", prepare(middle), agent=Scripted(fail_at=3))
    else:
        prepare, resume = continuation, run_child
        source, _ = source_run(tmp_path / "source", "tic-tac-toe", fail_at=1)
        middle, _ = resume(tmp_path / "middle", prepare(source),
                           agent=BoardAgent(fail_at=2), run_id="middle")
        child, _ = resume(tmp_path / "child", prepare(middle), agent=BoardAgent(fail_at=3))

    def mutate(lineage):
        parent = lineage["parentLineage"]
        descriptor = parent["descriptor"]
        if fault == "arena":
            descriptor["execution"]["arenaSlug"] = "connect-four"
        elif fault == "namespace":
            parent["schemaVersion"] = (
                "chess-continuation-lineage/v2" if not chess else BOARD_LINEAGE_VERSION
            )
        elif fault == "engine":
            parent["targetEngine"]["schemaVersion"] = "unsupported-engine"
            parent["targetEngineSha256"] = digest_json(parent["targetEngine"])
        elif fault == "descriptor_digest":
            parent["descriptorSha256"] = "0" * 64
            return
        elif fault == "engine_digest":
            parent["targetEngineSha256"] = "0" * 64
        elif fault == "ledger_digest":
            parent["historicalLedger"]["sha256"] = "0" * 64
        elif fault == "checkpoint":
            descriptor["prefix"]["checkpointStateSha256"] = "0" * 64
            parent["prefix"] = descriptor["prefix"]
        elif fault == "seed":
            descriptor["execution"]["seed"] = 999
        elif fault == "route":
            descriptor["execution"]["players"][0]["routeSha256"] = "0" * 64
        elif fault == "child_budget":
            parent["childExecution"]["maxTurns"] += 1
            parent["childExecutionSha256"] = digest_json(parent["childExecution"])
        elif fault == "source_engine":
            parent["targetEngine"]["coreSourceSha256"] = "0" * 64
            parent["targetEngineSha256"] = digest_json(parent["targetEngine"])
        else:
            parent["sourceVerification"]["archiveBytesVerifiedAtPreparation"] = False
        descriptor["executionSpecSha256"] = digest_json(descriptor["execution"])
        parent["descriptorSha256"] = digest_json(descriptor)

    _rewrite_lineage(child, mutate)
    assert ArtifactValidator().validate(child.artifact_path)
    with pytest.raises(ValueError):
        prepare(child)


def test_deep_parent_checks_preserve_opaque_extensions_and_reject_nested_forgery(tmp_path):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe", fail_at=1)
    latest = source
    for stop in (2, 3, 4):
        latest, _ = run_child(tmp_path / str(stop), continuation(latest),
                              agent=BoardAgent(fail_at=stop), run_id=f"child-{stop}")

    def extension(lineage):
        ancestor = lineage["parentLineage"]["parentLineage"]
        ancestor["descriptor"]["custodyExtension"] = {"opaque": "preserved"}
        ancestor["descriptorSha256"] = digest_json(ancestor["descriptor"])
    _rewrite_lineage(latest, extension)
    assert ArtifactValidator().validate(latest.artifact_path) == []

    def tamper(lineage):
        lineage["parentLineage"]["parentLineage"]["descriptorSha256"] = "0" * 64
    _rewrite_lineage(latest, tamper)
    assert any("ancestor descriptor digest" in error for error in
               ArtifactValidator().validate(latest.artifact_path))
    with pytest.raises(ValueError):
        continuation(latest)


def test_zero_action_prefix_still_binds_initial_replay_seed(tmp_path):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe", fail_at=0)
    child, _ = run_child(tmp_path / "child", continuation(source), agent=BoardAgent(fail_at=2))

    def mutate(lineage):
        descriptor = lineage["descriptor"]
        descriptor["execution"]["seed"] = 999
        descriptor["executionSpecSha256"] = digest_json(descriptor["execution"])
        descriptor["prefix"]["checkpointStateSha256"] = registry.create(
            "tic-tac-toe").initial_state(999).state_hash[7:]
        lineage["prefix"] = descriptor["prefix"]
        lineage["descriptorSha256"] = digest_json(descriptor)
    _rewrite_lineage(child, mutate)
    assert any("initial state differs" in error for error in
               ArtifactValidator().validate(child.artifact_path))
    with pytest.raises(ValueError):
        continuation(child)


@pytest.mark.parametrize("fault", ["engine_extension", "verification_flag"])
def test_board_runtime_rejects_schema_invalid_engine_and_verification(tmp_path, fault):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")
    child, _ = run_child(tmp_path / "child", continuation(source))

    def mutate(lineage):
        if fault == "engine_extension":
            lineage["targetEngine"]["unsupportedAttestation"] = True
            lineage["targetEngineSha256"] = digest_json(lineage["targetEngine"])
        else:
            lineage["sourceVerification"]["archiveBytesVerifiedAtPreparation"] = False
    _rewrite_lineage(child, mutate)
    lineage = json.loads((child.expanded_path / "continuation/lineage.json").read_bytes())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(lineage, board_continuation_schemas()[BOARD_LINEAGE_VERSION])
    assert ArtifactValidator().validate(child.artifact_path)


@pytest.mark.parametrize("arena_id", [*ARENAS, "chess"])
def test_provider_history_uses_fresh_child_identity_not_source_ids(tmp_path, arena_id, monkeypatch):
    if arena_id == "chess":
        from test_chess_continuation import continuation as prepare
        from test_chess_continuation import run_child as resume
        from test_chess_continuation import source_run as start

        from eslams.continuation import local_chess_continuation_engine_identity
        monkeypatch.setattr("eslams.continuation.chess_continuation_engine_identity",
                            local_chess_continuation_engine_identity)
        source, _ = start(tmp_path / "source", run_id="private-source-identity-canary")
    else:
        prepare, resume = continuation, run_child
        source, _ = source_run(tmp_path / "source", arena_id)
    child, agent = resume(tmp_path / "child", prepare(source))
    request = agent.calls[0]
    assert f'{source.run_id}:episode_001:' not in json.dumps(request.to_dict())
    assert all(row["action_provenance"] == "reconstructed_action" for row in request.history)
    assert all(row["logical_action_id"].startswith(child.run_id + ":episode_001:")
               for row in request.history)
    private = (child.expanded_path / "continuation/source_prefix.json").read_text()
    assert source.run_id + ":episode_001:" in private


def test_generated_board_types_and_compile_fixtures_have_no_schema_drift():
    source = Path(__file__).resolve().parents[1] / "scripts/generate_board_continuation_types.py"
    spec = importlib.util.spec_from_file_location("board_type_generator_fixture", source)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    for path, expected in generator.generated_files().items():
        assert path.read_text() == expected


@pytest.mark.parametrize("fault", ["historical", "segment_receipts", "segment_accepted"])
def test_boolean_ledger_counts_are_not_integer_counts(tmp_path, fault):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe", fail_at=0)
    child, _ = run_child(tmp_path / "child", continuation(source))

    def mutate(lineage):
        historical = lineage["historicalLedger"]
        if fault == "historical":
            historical["receiptCount"] = True
        elif fault == "segment_receipts":
            historical["segments"][0]["receiptCount"] = True
        else:
            historical["segments"][0]["acceptedPlyCount"] = False
    _rewrite_lineage(child, mutate)
    assert ArtifactValidator().validate(child.artifact_path)


def test_missing_explicit_parent_lineage_is_rejected(tmp_path):
    source, _ = source_run(tmp_path / "source", "tic-tac-toe")
    child, _ = run_child(tmp_path / "child", continuation(source))
    path = child.expanded_path / "continuation/lineage.json"
    lineage = json.loads(path.read_bytes())
    del lineage["parentLineage"]
    path.write_text(json.dumps(lineage))
    rearchive(child)
    assert ArtifactValidator().validate(child.artifact_path)


def test_preserve_source_budget_above_othello_horizon_is_not_rewritten(tmp_path):
    source, _ = source_run(tmp_path / "source", "othello", max_turns=128)
    cont = continuation(source)
    assert cont.descriptor["execution"]["maxTurns"] == 128
    assert cont.child_execution["maxTurns"] == 128
    with pytest.raises(ValueError, match="cannot reduce source budget"):
        board_continuation_child_execution(
            cont.descriptor, turn_limit_policy="native-arena-horizon"
        )
    child, _ = run_child(tmp_path / "child", cont)
    assert child.replay_events[-1].terminal
    assert child.replay_events[-1].turn_id <= registry.create("othello").max_turns
    assert child.score.match_valid_for_scoring
    assert ArtifactValidator().validate(child.artifact_path) == []
