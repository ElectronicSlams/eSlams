"""Provider diagnostic privacy and optional atomic nonce backend regressions."""
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from eslams.agents import HttpAgent, ModelProviderAgent
from eslams.artifacts import ArtifactValidator
from eslams.nonce_store import MemoryNonceStore, NonceStoreError, SQLiteNonceStore
from eslams.runner import RunConfig, Runner


def rows(result):
    return [json.loads(x) for x in (result.expanded_path /
        "receipts/provider_receipts.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("status", [400, 401, 429, 502, 504])
def test_native_http_failure_keeps_header_custody_and_never_echoes_provider_body(
    tmp_path, monkeypatch, status,
):
    private = "synthetic-private-prompt-error-content"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kw):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": private, "prompt": private}},
            headers={"x-request-id": "synthetic-request", "cf-aig-request-id": "synthetic-gateway"},
            request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig("tic-tac-toe",
        agent_1=ModelProviderAgent("openai", "synthetic-model", "OPENAI_API_KEY"),
        on_agent_error="forfeit", output_dir=tmp_path))
    receipt = rows(result)
    assert len(calls) == len(receipt) == 1
    assert receipt[0]["request_id"] == "synthetic-request"
    assert receipt[0]["gateway_request_id"] == "synthetic-gateway"
    assert not receipt[0]["action_applied"] and result.score.winner is None
    assert not result.score.match_valid_for_scoring
    assert result.score.aggregate_usage["totalCostUsd"] is None
    for file in result.expanded_path.rglob("*"):
        if file.is_file():
            assert private.encode() not in file.read_bytes(), file
    assert ArtifactValidator().validate(result.expanded_path) == []


@pytest.mark.parametrize("kind", ["http", "native", "invalid_action"])
def test_untrusted_transport_or_action_error_prose_is_not_a_public_diagnostic(
    tmp_path, monkeypatch, kind,
):
    private = "synthetic-private-error-content"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    def post(url, **kwargs):
        if kind != "invalid_action":
            raise httpx.ConnectError(private)
        return httpx.Response(200, json={"output": [{"content": [{"type": "output_text",
            "text": json.dumps({"action": private})}]}]}, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = (HttpAgent("https://synthetic.invalid/act") if kind == "http" else
             ModelProviderAgent("openai", "synthetic-model", "OPENAI_API_KEY"))
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent, output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring
    for file in result.expanded_path.rglob("*"):
        if file.is_file():
            assert private.encode() not in file.read_bytes(), file


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_nonce_claim_is_atomic_across_independent_callers(tmp_path, backend):
    memory = MemoryNonceStore()
    def claim(_):
        store = memory if backend == "memory" else SQLiteNonceStore(tmp_path / "nonces.sqlite")
        return store.claim("same", expires_at=200, now=100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(claim, range(12)))
    assert result.count(True) == 1 and result.count(False) == 11


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_nonce_expiry_boundary_and_full_backend_fail_closed(tmp_path, backend):
    store = (MemoryNonceStore(max_entries=1) if backend == "memory" else
             SQLiteNonceStore(tmp_path / "nonces.sqlite", max_entries=1))
    assert store.claim("first", expires_at=110, now=100)
    assert not store.claim("first", expires_at=120, now=110)
    with pytest.raises(NonceStoreError, match="capacity"):
        store.claim("second", expires_at=120, now=110)
    assert store.claim("second", expires_at=120, now=111)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("bad", [True, 1.5, 0])
def test_nonce_capacity_is_an_exact_positive_integer(tmp_path, backend, bad):
    with pytest.raises(ValueError):
        if backend == "memory":
            MemoryNonceStore(max_entries=bad)
        else:
            SQLiteNonceStore(tmp_path / "nonces.sqlite", max_entries=bad)


def test_nonce_storage_failure_is_not_an_authorization_success(tmp_path):
    with pytest.raises(NonceStoreError, match="unavailable"):
        SQLiteNonceStore(tmp_path).claim("valid", expires_at=200, now=100)
