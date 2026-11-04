import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from test_model_agents import _openai_wire, _request

from eslams.agents import ModelProviderAgent, ProviderCallError, _retry_after_seconds
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_preflight
from eslams.providers import load_provider_registry


def test_pasted_provider_key_whitespace_is_trimmed_and_error_echo_is_redacted(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "  pasted-test-key\r\n")
    headers_seen = []

    def response(url, *, headers, **kwargs):
        headers_seen.append(headers["Authorization"])
        return httpx.Response(401, text="Credential pasted-test-key failed")

    monkeypatch.setattr("eslams.agents.bounded_post", response)
    agent = ModelProviderAgent("openai", "gpt-test", "OPENAI_API_KEY")
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert headers_seen == ["Bearer pasted-test-key"]
    assert "pasted-test-key" not in str(failure.value)
    assert agent.last_receipt["outcome"] == "provider_auth_failed"
    assert "pasted-test-key" not in str(agent.last_receipt)

    monkeypatch.setattr(
        "eslams.agents.bounded_post",
        lambda *a, **k: httpx.Response(
            200,
            json=_openai_wire('{"action": 1}'),
        ),
    )
    assert agent.act(_request()).action == 1


def test_invalid_provider_credentials_fail_before_network_without_revealing_the_value(monkeypatch):
    def network(*args, **kwargs):
        raise AssertionError("invalid credential must not reach the network")

    monkeypatch.setattr("eslams.agents.bounded_post", network)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", network)
    for key in ("bad\tkey", "bad key", "unicode-☃-key", "", " \r\n "):
        monkeypatch.setenv("OPENAI_API_KEY", key)
        agent = ModelProviderAgent("openai", "gpt-5-mini", "OPENAI_API_KEY")
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        assert failure.value.error_kind == "provider_auth_failed"
        assert agent.last_receipt["outcome"] == "provider_auth_failed"
        assert not key.strip() or key.strip() not in str(failure.value)
        result = provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True)
        assert not result["ok"]
        assert result["error"]["error_class"] == "provider_auth_failed"
        assert not key.strip() or key.strip() not in str(result)


def test_preflight_distinguishes_catalogue_namespaces_from_available_adapters(monkeypatch):
    def network(*args, **kwargs):
        raise AssertionError("unsupported adapter must not make network calls")

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", network)
    model = load_provider_registry().list_models(provider="together-ai")[0].model
    for live in (False, True):
        result = provider_preflight("together-ai", model, "tic-tac-toe", live=live)
        assert result["checks"]["registry_entry"]
        assert not result["checks"]["adapter_available"]
        assert not result["ok"]
        assert result["error"]["error_class"] == "provider_adapter_unavailable"
        assert "unknown" not in result["error"]["message"]


def test_retry_after_beyond_explicit_deadline_preserves_receipt_without_sleeping(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("eslams.agents.time.sleep", lambda *a: pytest.fail("must not sleep"))
    for value in ("86400", "1e300", "Thu, 31 Dec 2099 23:59:59 GMT"):
        calls = []

        def response(*args, calls=calls, value=value, **kwargs):
            calls.append(1)
            return httpx.Response(
                429, json={"error": {"code": 429}}, headers={"Retry-After": value},
            )

        monkeypatch.setattr("eslams.agents.bounded_post", response)
        agent = ModelProviderAgent(
            "openai",
            "gpt-test",
            "OPENAI_API_KEY",
            runtime_config=ProviderRuntimeConfig(max_retries=1),
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            attempt = executor.submit(agent.act, _request())
            with pytest.raises(TimeoutError, match="action deadline"):
                attempt.result(timeout=2)
        assert calls == [1]
        assert len(agent.attempt_receipts) == 1
        assert agent.last_receipt["outcome"] == "provider_rate_limited"
        assert agent.last_receipt["retry_after_ms"] <= 86_400_000
    for value in ("nan", "inf", "-inf", "nonsense"):
        assert _retry_after_seconds(httpx.Response(429, headers={"Retry-After": value})) is None


@pytest.mark.parametrize("status", [None, 200, 429, 503])
def test_timeout_exception_preserves_observed_receipt_without_replay(monkeypatch, status):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(1)
        failure = httpx.ReadTimeout("private transport diagnostic")
        if status is not None:
            failure._eslams_response_observation = ResponseObservation(
                status, (("x-request-id", "safe-request"),
                         ("cf-aig-request-id", "safe-gateway")),
            )
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", interrupted)
    agent = ModelProviderAgent("openai", "gpt-test", "OPENAI_API_KEY",
                              runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(TimeoutError if status is None else ProviderCallError) as error:
        agent.act(_request())
    assert calls == [1]
    assert len(agent.attempt_receipts) == 1
    receipt = agent.last_receipt
    assert receipt["outcome"] == "provider_timeout"
    assert receipt["attempt_index"] == 1
    assert not receipt["usage"]
    assert "private transport diagnostic" not in str(error.value)
    if status is not None:
        assert error.value.error_kind == "provider_timeout"
        assert not error.value.retry_permitted
        assert error.value.receipt["request_id"] == "safe-request"
        assert receipt["status_code"] == status
        assert receipt["request_id"] == "safe-request"
        assert receipt["gateway_request_id"] == "safe-gateway"


@pytest.mark.parametrize("wait", ["concurrency", "rate"])
def test_provider_admission_deadline_expires_without_submitting_or_replaying(monkeypatch, wait):
    from eslams import agents

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(agents, "_PROVIDER_SEMAPHORES", {})
    monkeypatch.setattr(agents, "_PROVIDER_RATE_RESERVATIONS", {})
    monkeypatch.setattr(agents, "bounded_post", lambda *a, **k: pytest.fail("must not submit"))
    runtime = ProviderRuntimeConfig(timeout_ms=20, max_retries=2, rate_limit_per_minute=1)
    key = "openai:gpt-test"
    semaphore = agents._provider_semaphore(runtime, key)
    if wait == "concurrency":
        semaphore.acquire()
    else:
        agents._PROVIDER_RATE_RESERVATIONS[key] = time.monotonic() + 60
    agent = ModelProviderAgent("openai", "gpt-test", "OPENAI_API_KEY", runtime_config=runtime)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            agent.act(_request())
    finally:
        if wait == "concurrency":
            semaphore.release()
    assert time.monotonic() - started < 1
    assert len(agent.attempt_receipts) == 1
    assert agent.last_receipt["outcome"] == "provider_timeout"
