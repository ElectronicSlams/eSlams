"""Virtual waits distinguish explicit operator policy from the old five-second floor."""
import httpx
import pytest
from test_model_agents import _request

from eslams import agents
from eslams.contracts.provider import ProviderRuntimeConfig


def test_optional_retry_can_honor_ten_seconds_within_explicit_action_policy(monkeypatch):
    monkeypatch.setenv("ESLAMS_RETRY_WAIT_TEST_KEY", "synthetic-mock-only")
    waits, calls = [], []
    monkeypatch.setattr(agents.time, "sleep", waits.append)
    monkeypatch.setattr(agents, "sleep_with_cancellation", waits.append, raising=False)

    def response(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429}},
                                  headers={"Retry-After": "10"})
        return httpx.Response(200, json={
            "id": "synthetic-retry-result", "model": "synthetic-model",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"action": 1}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    monkeypatch.setattr(agents, "bounded_post", response)
    agent = agents.ModelProviderAgent("openrouter", "synthetic-model", "ESLAMS_RETRY_WAIT_TEST_KEY",
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    assert agent.act(_request()).action == 1
    assert len(calls) == 2 and waits == [10.0]
    assert len(agent.attempt_receipts) == 2


def test_explicit_no_deadline_retry_wait_has_no_fixed_five_second_ceiling(monkeypatch):
    waits = []
    monkeypatch.setattr(agents, "sleep_with_cancellation", waits.append)
    with agents.action_deadline(None):
        agents._sleep_before_retry(ProviderRuntimeConfig(), retry_after_seconds=110)
    assert waits == [110]


@pytest.mark.parametrize("factor", [0.5, 1.5])
def test_explicit_jitter_setting_uses_the_declared_randomized_linear_policy(monkeypatch, factor):
    # This is the implemented policy, not the historical exponential/full-jitter proposal.
    waits = []
    monkeypatch.setattr(agents, "sleep_with_cancellation", waits.append)
    monkeypatch.setattr(agents.random, "uniform", lambda low, high: factor)
    with agents.action_deadline(None):
        agents._sleep_before_retry(ProviderRuntimeConfig(retry_backoff_ms=1000, retry_jitter=True))
    assert waits == [factor]


def test_retry_wait_cannot_override_a_smaller_explicit_operator_deadline(monkeypatch):
    monkeypatch.setattr(agents, "sleep_with_cancellation",
                        lambda delay: pytest.fail("must reject before sleeping"))
    with agents.action_deadline(1), pytest.raises(TimeoutError, match="action deadline"):
        agents._sleep_before_retry(ProviderRuntimeConfig(), retry_after_seconds=110)
