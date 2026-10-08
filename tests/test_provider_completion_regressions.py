import json

import httpx
import pytest
from test_provider_wire_v06 import PROVIDER_CASES, _agent, _fixture, _request

from eslams.agents import ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.runner import RunConfig, Runner


def _set_finish(payload, provider, reason):
    if provider == "openai":
        payload.update(status="incomplete", incomplete_details={"reason": reason})
    elif provider == "anthropic":
        payload["stop_reason"] = reason
    elif provider == "gemini":
        payload["candidates"][0]["finishReason"] = reason
    elif provider == "openrouter":
        payload["choices"][0]["finish_reason"] = reason
    else:
        payload["stopReason"] = reason


def test_provider_finish_fields_survive_success_and_reject_parseable_truncation(monkeypatch):
    limits = ["max_output_tokens", "max_tokens", "MAX_TOKENS", "length", "max_tokens"]
    success = [None, "end_turn", "STOP", "stop", "end_turn"]
    for (provider, model, key, fixture), limit, stopped in zip(
        PROVIDER_CASES, limits, success, strict=True
    ):
        monkeypatch.setenv(key, "fake-key")
        payload = _fixture(fixture)
        monkeypatch.setattr(
            "eslams.agents.bounded_post",
            lambda *a, payload=payload, **k: httpx.Response(200, json=payload),
        )
        agent = _agent(provider, model, key)
        assert agent.act(_request()).action == 1
        assert agent.last_receipt["finish_reason"] == stopped
        _set_finish(payload, provider, limit)
        calls = []

        def post(*args, calls=calls, payload=payload, **kwargs):
            calls.append(1)
            return httpx.Response(200, json=payload)

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        with pytest.raises(ProviderCallError, match="incomplete") as failure:
            agent.act(_request())
        assert failure.value.error_kind == "provider_request_rejected"
        assert calls == [1]  # No action-repair or retry on a known incomplete response.
        assert agent.last_receipt["finish_reason"] == limit
        assert agent.last_receipt["finish_status"] == "incomplete"
        assert agent.last_receipt["usage"]["total_tokens"] == 16
        assert agent.last_receipt["status_code"] == 200


def test_refusal_is_distinct_from_wire_or_action_parse_failure_without_prose_leak(monkeypatch):
    for provider, model, key, fixture in PROVIDER_CASES:
        monkeypatch.setenv(key, "fake-key")
        payload = _fixture(fixture)
        private = "private-refusal-content-test"
        if provider == "openai":
            payload["output"][1]["content"].append({"type": "refusal", "refusal": private})
        elif provider == "anthropic":
            payload["stop_details"] = {"type": "refusal", "explanation": private}
        elif provider == "gemini":
            payload["promptFeedback"] = {"blockReason": "SAFETY", "blockReasonMessage": private}
        elif provider == "openrouter":
            payload["choices"][0]["message"]["refusal"] = private
        else:
            payload["stopReason"] = "guardrail_intervened"
        calls = []

        def post(*a, calls=calls, payload=payload, **k):
            calls.append(1)
            return httpx.Response(200, json=payload)

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        agent = _agent(
            provider,
            model,
            key,
            runtime_config=ProviderRuntimeConfig(max_retries=1, reasoning="disabled"),
        )
        with pytest.raises(ProviderCallError, match="refused") as failure:
            agent.act(_request())
        assert calls == [1] and failure.value.error_kind == "provider_request_rejected"
        assert agent.last_receipt["finish_status"] == "refused"
        assert private not in str(failure.value) and private not in json.dumps(agent.last_receipt)
        assert agent.last_receipt["usage"]["total_tokens"] == 16


def test_http200_body_errors_follow_the_http_retry_policy_and_preserve_attempts(monkeypatch):
    cases = [
        (
            "openai",
            "gpt-5-mini",
            "OPENAI_API_KEY",
            {"status": "failed", "error": {"code": "rate_limit_exceeded"}},
            "provider_rate_limited",
        ),
        (
            "anthropic",
            "claude-sonnet-4-6",
            "ANTHROPIC_API_KEY",
            {"type": "error", "error": {"type": "overloaded_error"}},
            "provider_unavailable",
        ),
        (
            "openrouter",
            "openai/gpt-5-mini",
            "OPENROUTER_API_KEY",
            {"error": {"code": 429}},
            "provider_rate_limited",
        ),
        (
            "openrouter",
            "openai/gpt-5-mini",
            "OPENROUTER_API_KEY",
            {"choices": [{"error": {"code": 502}, "finish_reason": "error"}]},
            "provider_unavailable",
        ),
    ]
    monkeypatch.setattr("eslams.agents.time.sleep", lambda *a: None)
    for provider, model, key, payload, kind in cases:
        monkeypatch.setenv(key, "fake-key")
        calls = []

        def post(*a, calls=calls, payload=payload, **k):
            calls.append(1)
            return httpx.Response(200, json=payload)

        monkeypatch.setattr("eslams.agents.bounded_post", post)
        agent = _agent(
            provider,
            model,
            key,
            runtime_config=ProviderRuntimeConfig(max_retries=1, reasoning="disabled"),
        )
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        assert failure.value.error_kind == kind and calls == [1, 1]
        assert len(agent.attempt_receipts) == 2
        assert all(
            row["outcome"] == kind and row["finish_status"] == "failed"
            for row in agent.attempt_receipts
        )
        assert all(row["status_code"] == 200 for row in agent.attempt_receipts)


def test_incomplete_provider_action_is_not_applied_and_artifact_retains_usage(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    payload = _fixture("openrouter_chat_completions_success.json")
    _set_finish(payload, "openrouter", "length")
    monkeypatch.setattr(
        "eslams.agents.bounded_post",
        lambda *a, payload=payload, **k: httpx.Response(200, json=payload),
    )
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe",
            agents={"player_1": _agent("openrouter", "openai/gpt-5-mini", "OPENROUTER_API_KEY")},
            output_dir=tmp_path,
        )
    )
    assert not result.score.match_valid_for_scoring
    receipts = [
        json.loads(row)
        for row in (result.artifact_path / "receipts/provider_receipts.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(receipts) == 1
    assert receipts[0]["finish_status"] == "incomplete" and receipts[0]["finish_reason"] == "length"
    assert not receipts[0]["action_applied"]
    assert receipts[0]["usage"]["total_tokens"] == 16
    assert ArtifactValidator().validate(result.artifact_path) == []
