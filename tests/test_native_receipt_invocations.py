"""Regression contracts for native adapter receipt ownership under cancellation."""
import json
import threading
from dataclasses import replace

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent
from eslams.artifacts import ArtifactValidator
from eslams.deadlines import ExecutionCancelled, ensure_agent_available
from eslams.execution_policy import model_execution_policy
from eslams.runner import RunConfig, Runner


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


def payload(index, action=0):
    return {"id": f"synthetic-generation-{index}", "model": "synthetic-model",
            "choices": [{"finish_reason": "stop", "message": {"content":
                json.dumps({"action": action})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                      "cost": 0.01}}


def receipts(result):
    return [json.loads(line) for line in (result.expanded_path /
        "receipts/provider_receipts.jsonl").read_text().splitlines()]


def agent(cls=ModelProviderAgent):
    return cls("openrouter", "synthetic-model", "OPENROUTER_API_KEY")


def test_pre_cancelled_new_run_never_borrows_prior_native_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(200, json=payload(len(calls)), request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent()
    assert native.act(request()).action == 0
    prior = native.attempt_receipts.copy()
    cancellation = threading.Event()
    cancellation.set()
    result = Runner().run(RunConfig("connect-four", agent_1=native,
        cancellation=cancellation, output_dir=tmp_path))
    assert calls == [1] and receipts(result) == []
    assert native.attempt_receipts == prior  # Clearing unrelated custody is not the fix.
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    assert ArtifactValidator().validate(result.expanded_path) == []


def test_same_match_cancel_before_third_callback_keeps_exactly_two_generation_receipts(
    tmp_path, monkeypatch,
):
    import eslams.runner as module
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    cancellation = threading.Event()
    original = module._request
    def make_request(*args, **kwargs):
        value = original(*args, **kwargs)
        if value.turn_id == 2:
            cancellation.set()
        return value
    monkeypatch.setattr(module, "_request", make_request)
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(200, json=payload(len(calls), [3, 0][len(calls)-1]),
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = Runner().run(RunConfig("connect-four", agent_1=agent(), agent_2=agent(),
                                   cancellation=cancellation, output_dir=tmp_path))
    rows = receipts(result)
    assert len(calls) == len(rows) == 2
    assert [row["provider_response_id"] for row in rows] == [
        "synthetic-generation-1", "synthetic-generation-2"]
    assert result.score.aggregate_usage["totalTokens"] == 30
    assert result.score.aggregate_usage["totalCostUsd"] == pytest.approx(0.02)
    assert sum(event.action is not None for event in result.replay_events) == 2
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    assert ArtifactValidator().validate(result.expanded_path) == []


@pytest.mark.parametrize("after_publication", [False, True])
def test_interruption_at_publication_uses_current_immutable_batch_not_convenience_fields(
    tmp_path, monkeypatch, after_publication,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    calls = []
    cancellation = threading.Event()
    class Interrupted(ModelProviderAgent):
        interrupt = False
        def _publish_receipts(self, rows):
            if self.interrupt:
                if after_publication:
                    super()._publish_receipts(rows)
                cancellation.set()
                raise ExecutionCancelled("synthetic publication interruption")
            super()._publish_receipts(rows)
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(200, json=payload(len(calls)), request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(Interrupted)
    assert native.act(request()).action == 0
    native.interrupt = True
    result = Runner().run(RunConfig("connect-four", agent_1=native,
                                   cancellation=cancellation, output_dir=tmp_path))
    rows = receipts(result)
    assert len(calls) == 2 and len(rows) == int(after_publication)
    if after_publication:
        assert rows[0]["provider_response_id"] == "synthetic-generation-2"
        assert result.score.aggregate_usage["totalCostUsd"] == pytest.approx(0.01)
    else:
        assert result.score.aggregate_usage["totalCostUsd"] is None
    assert all(event.action is None for event in result.replay_events)
    assert not result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.expanded_path) == []


def test_late_native_completion_remains_owned_and_cannot_enter_next_cancelled_invocation(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    entered, release, exited, runner_done = [threading.Event() for _ in range(4)]
    cancellation = threading.Event()
    results, failures, calls = [], [], []
    class Observed(ModelProviderAgent):
        def act(self, req):
            try:
                return super().act(req)
            finally:
                exited.set()
    def post(url, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return httpx.Response(200, json=payload(1), request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(Observed)
    def run():
        try:
            results.append(Runner().run(RunConfig("connect-four", agent_1=native,
                cancellation=cancellation, output_dir=tmp_path / "first")))
        except BaseException as exc:
            failures.append(exc)
        finally:
            runner_done.set()
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(3)
        cancellation.set()
        assert runner_done.wait(3) and not failures
        assert receipts(results[0]) == []
        assert results[0].score.aggregate_usage["totalCostUsd"] is None
        with pytest.raises(TimeoutError, match="unfinished"):
            ensure_agent_available(native)
    finally:
        release.set()
        thread.join(3)
    assert exited.wait(3) and not thread.is_alive()
    assert native.last_receipt["provider_response_id"] == "synthetic-generation-1"
    second = Runner().run(RunConfig("connect-four", agent_1=native,
        cancellation=cancellation, output_dir=tmp_path / "second"))
    assert len(calls) == 1 and receipts(second) == []
    assert second.score.aggregate_usage["totalCostUsd"] is None
    assert ArtifactValidator().validate(results[0].expanded_path) == []
    assert ArtifactValidator().validate(second.expanded_path) == []
