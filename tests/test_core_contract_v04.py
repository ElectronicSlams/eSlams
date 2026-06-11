from pathlib import Path

import eslams.arenas  # noqa: F401
from eslams.arena import registry
from eslams.arena_transport import serialize_state
from eslams.bench import arena_step_benchmark
from eslams.contracts.json_schema import export_schemas
from eslams.contracts.security import (
    SeedDerivationError,
    derive_seed,
    sign_runner_request,
    verify_runner_request_signature,
)
from eslams.contracts.versions import (
    CORE_PACKAGE_VERSION,
    CORE_STEP_REQUEST_SCHEMA_VERSION,
    CORE_STEP_RESPONSE_SCHEMA_VERSION,
)
from eslams.core_contract import (
    CORE_CONTRACT_VERSION,
    core_step,
    engine_capabilities,
    prompt_package,
)
from eslams.golden import golden_fixture_bundle
from eslams.model_actions import (
    InvalidModelAction,
    action_output_schema,
    parse_model_action,
    streaming_action_status,
)
from eslams.observation_budgets import observation_budget_report
from eslams.runner_session import RunnerSessionStore


def test_core_step_v2_returns_hashes_timings_and_compact_views():
    arena = registry.create("tic-tac-toe")
    state = arena.initial_state(seed=1)

    response = core_step(
        {
            "coreContractVersion": CORE_CONTRACT_VERSION,
            "gameId": "tic-tac-toe",
            "rulesetVersion": "standard",
            "state": serialize_state(state),
            "action": {"actionId": "4"},
            "actorId": "player_1",
            "requestId": "req_v04",
            "includeObservation": True,
            "includeLegalActions": "compact",
            "includeReplayEvent": True,
        }
    )

    assert response["ok"] is True
    assert response["coreVersion"] == "0.4.0"
    assert response["coreContractVersion"] == "2.0"
    assert response["previousStateHash"] == state.state_hash
    assert response["nextStateHash"] != state.state_hash
    assert response["legalActionHashBefore"].startswith("sha256:")
    assert response["legalActionHashAfter"].startswith("sha256:")
    assert response["actionHash"].startswith("sha256:")
    assert response["timingsMs"]["receivedAt"].endswith("Z")
    assert "totalMs" in response["timingsMs"]
    assert response["observation"]["view"] == "public_compact"
    assert response["legalActions"]["include"] == "compact"
    assert response["replayEvent"]["type"] == "action_applied"


def test_core_step_v2_rejects_wrong_actor_with_taxonomy():
    arena = registry.create("tic-tac-toe")
    state = arena.initial_state(seed=1)

    response = core_step(
        {
            "coreContractVersion": CORE_CONTRACT_VERSION,
            "gameId": "tic-tac-toe",
            "rulesetVersion": "standard",
            "state": serialize_state(state),
            "action": {"actionId": "4"},
            "actorId": "player_2",
            "requestId": "req_wrong_actor",
        }
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "action_valid_but_wrong_actor"
    assert response["error"]["recoverable"] is True


def test_prompt_package_is_cache_friendly_and_schema_first():
    arena = registry.create("connect-four")
    state = arena.initial_state(seed=1)

    package = prompt_package(arena=arena, state=state, actor_id=state.active_player)

    assert package["promptVersion"] == "eslams.core.prompt.v2"
    assert package["stablePrefix"][0]["cacheRecommended"] is True
    assert package["dynamicTurn"]["currentObservation"]
    assert package["outputSchema"]["properties"]["action"]["required"] == ["action_id"]
    assert package["promptHash"].startswith("sha256:")
    assert package["tokenEstimate"] > 0


def test_shared_model_action_parser_accepts_action_id_and_streaming_status():
    parsed = parse_model_action(
        '{"action": {"action_id": "2"}, "public_explanation": "Blocks."}',
        [0, 1, 2],
    )

    assert parsed.action == 2
    assert parsed.action_id == "2"
    assert action_output_schema([0, 1, 2])["properties"]["action"]["properties"]["action_id"][
        "enum"
    ] == ["0", "1", "2"]
    assert streaming_action_status('{"action": {"action_id": "1"', [0, 1, 2]) == {
        "status": "action_ready",
        "action": {"action_id": "1"},
    }

    try:
        parse_model_action('{"action": {"action_id": "99"}}', [0, 1, 2])
    except InvalidModelAction as exc:
        assert exc.code == "unknown_action_id"
    else:
        raise AssertionError("invalid action id should fail")


def test_runner_session_store_keeps_hot_state_and_snapshots():
    store = RunnerSessionStore()
    created = store.create(game_id="tic-tac-toe", session_id="arena_test", initial_seed=1)
    stepped = store.step(session_id="arena_test", action={"actionId": "4"})
    snapshot = store.snapshot("arena_test")

    assert created["stateHash"] != stepped["nextStateHash"]
    assert stepped["ok"] is True
    assert stepped["session"]["turn"] == 1
    assert snapshot["state"]["turn"] == 1
    assert store.close("arena_test")["message"] == "closed"


def test_security_seed_derivation_fails_closed_and_signs_runner_requests():
    try:
        derive_seed(namespace="official", public_seed=1, secret=None, production=True)
    except SeedDerivationError:
        pass
    else:
        raise AssertionError("production seed derivation must require a secret")

    derived = derive_seed(
        namespace="dev",
        public_seed=1,
        secret=None,
        production=False,
        allow_development_fallback=True,
    )
    assert derived.mode == "development_public_fallback"

    signature = sign_runner_request(
        secret="secret",
        method="POST",
        path="/runner/session/arena_test/step",
        body={"action": {"actionId": "4"}},
        timestamp="2026-06-11T00:00:00Z",
        nonce="nonce",
        request_id="req",
        key_id="key-1",
    )
    assert verify_runner_request_signature(secret="secret", signature_payload=signature)
    assert not verify_runner_request_signature(secret="other", signature_payload=signature)


def test_benchmark_budgets_golden_schemas_and_generated_contracts(tmp_path: Path):
    rows = arena_step_benchmark(games=["tic-tac-toe"], iterations=2)
    assert rows[0]["gameId"] == "tic-tac-toe"
    assert rows[0]["timingsMs"]["totalP95"] >= 0

    budget = observation_budget_report(game_id="tic-tac-toe")
    assert budget["ok"] is True

    golden = golden_fixture_bundle(game_ids=["tic-tac-toe", "connect-four"])
    assert golden["coreVersion"] == CORE_PACKAGE_VERSION
    assert len(golden["fixtures"]) == 2
    assert all(row["stateHash"].startswith("sha256:") for row in golden["fixtures"])

    written = export_schemas(tmp_path / "schemas")
    names = {path.name for path in written}
    assert f"{CORE_STEP_REQUEST_SCHEMA_VERSION}.schema.json" in names
    assert f"{CORE_STEP_RESPONSE_SCHEMA_VERSION}.schema.json" in names

    generated = Path("packages/core-contracts/src/generated/core-step.ts")
    assert "CoreStepRequest" in generated.read_text(encoding="utf-8")
    assert Path("packages/core-lite/src/index.ts").exists()


def test_engine_capabilities_gate_core_lite_and_precompute():
    tic_tac_toe = engine_capabilities("tic-tac-toe")
    poker = engine_capabilities("poker")

    assert tic_tac_toe["engines"]["core_lite_ts"]["arenaInteractive"] is True
    assert tic_tac_toe["speculativePrecompute"]["safe"] is True
    assert poker["speculativePrecompute"]["hiddenInfo"] is True
    assert poker["engines"]["core_lite_ts"]["arenaInteractive"] is False
