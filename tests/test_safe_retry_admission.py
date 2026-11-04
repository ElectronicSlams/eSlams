"""Optional retries never replay unknown remote work or accepted generations."""
import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


@pytest.mark.parametrize("failure", ["timeout", "reset", "http503", "http502"])
def test_optional_retries_do_not_repeat_ambiguous_remote_work(monkeypatch, failure):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic body timeout")
        if failure == "reset":
            raise httpx.ReadError("synthetic body reset")
        return httpx.Response(int(failure[4:]), json={"error": "synthetic"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY",
                               runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        native.act(_request())
    assert calls == [1] and len(native.attempt_receipts) == 1
    assert native.attempt_receipts[0]["usage"] == {}


def test_optional_retry_after_definitive_rate_rejection_retains_both_attempts(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    monkeypatch.setattr("eslams.agents.time.sleep", lambda *args: None)
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": 429}},
                                  request=httpx.Request("POST", url))
        return httpx.Response(200, json={"id": "accepted-generation",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"action":0}'}}]},
            request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY",
                               runtime_config=ProviderRuntimeConfig(max_retries=1))
    assert native.act(_request()).action == 0
    assert len(calls) == len(native.attempt_receipts) == 2


@pytest.mark.parametrize("observed", ["generation", "usage"])
def test_even_rate_error_with_observed_work_is_not_replayed(monkeypatch, observed):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        body = {"error": {"code": 429}}
        if observed == "generation":
            body["id"] = "observed-generation"
        else:
            body["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ModelProviderAgent("openrouter", "synthetic-model", "OPENROUTER_API_KEY",
                               runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        native.act(_request())
    assert len(calls) == len(native.attempt_receipts) == 1
