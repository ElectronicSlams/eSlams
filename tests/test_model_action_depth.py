"""Bound action JSON before decoding/scanning while retaining physical-attempt evidence."""
import json

import httpx
import pytest
from test_provider_wire_v06 import PROVIDER_CASES, _agent, _fixture, _request

from eslams.agents import ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.model_actions import (
    InvalidModelAction,
    extract_json,
    parse_model_action,
    streaming_action_status,
)
from eslams.runner import RunConfig, Runner


def _text(depth, container="array"):
    opening, closing = ("[", "]") if container == "array" else ('{"child":', "}")
    return ('{"action":1,"metadata":{"nested":' + opening * depth
            + '"private-depth-leaf"' + closing * depth + '}}')


def _response(provider, fixture, text):
    payload = _fixture(fixture)
    if provider == "openai":
        payload["output"][1]["content"] = [{"type": "output_text", "text": text}]
    elif provider == "anthropic":
        payload["content"] = [{"type": "text", "text": text}]
    elif provider == "gemini":
        payload["candidates"][0]["content"]["parts"] = [{"text": text}]
    elif provider == "openrouter":
        payload["choices"][0]["message"]["content"] = text
    else:
        payload["output"]["message"]["content"] = [{"text": text}]
    return httpx.Response(200, json=payload, headers={"x-request-id": "safe-depth-request"})


def _scan(value):
    """Match adapters that recursively inspect extracted JSON before returning a receipt."""
    if isinstance(value, dict):
        return any(_scan(key) or _scan(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_scan(item) for item in value)
    return isinstance(value, str) and "fixture-depth-key" in value


@pytest.mark.parametrize("depth", [1, 32, 126, 127, 400, 1200, 4000])
@pytest.mark.parametrize("scan_before_receipt", [False, True])
@pytest.mark.parametrize("provider,model,key,fixture", PROVIDER_CASES)
def test_provider_action_depth_preserves_usage_and_never_replays(
    monkeypatch, provider, model, key, fixture, depth, scan_before_receipt,
):
    monkeypatch.setenv(key, "fixture-depth-key")
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return _response(provider, fixture, _text(depth))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(provider, model, key, runtime_config=ProviderRuntimeConfig(
        max_retries=2, action_repair_attempts=2, reasoning="disabled"))
    if scan_before_receipt:
        original = agent._call_provider

        def scanned(api_key, prompt):
            text, receipt = original(api_key, prompt)
            assert not _scan(extract_json(text))
            return text, receipt

        monkeypatch.setattr(agent, "_call_provider", scanned)
    if depth <= 126:  # Root object + metadata object + 126 nested arrays = 128.
        assert agent.act(_request()).action == 1
        assert agent.last_receipt["outcome"] == "ok"
    else:
        with pytest.raises(ProviderCallError) as failure:
            agent.act(_request())
        assert failure.value.error_kind == "action_response_unparseable"
        assert not failure.value.retry_permitted
        assert failure.value.receipt == agent.last_receipt
        assert "private-depth-leaf" not in str(failure.value)
        assert agent.last_receipt["outcome"] == "action_response_unparseable"
        assert "private-depth-leaf" not in json.dumps(agent.last_receipt)
    assert calls == [1]
    assert len(agent.attempt_receipts) == 1
    assert agent.last_receipt["attempt_index"] == 1
    assert agent.last_receipt["status_code"] == 200
    assert agent.last_receipt["request_id"] == "safe-depth-request"
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    if provider == "openrouter":
        assert agent.last_receipt["estimated_cost"]["cost_usd"] == 0.000012


@pytest.mark.parametrize("container", ["array", "object"])
@pytest.mark.parametrize("depth", [127, 400, 1200, 4000])
@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "Answer: {} end."])
def test_extraction_never_exposes_excessive_depth_to_recursive_consumers(container, depth, wrapper):
    text = wrapper.format(_text(depth, container))
    assert extract_json(text) is None
    with pytest.raises(InvalidModelAction) as failure:
        parse_model_action(text, [0, 1, 2])
    assert failure.value.code == "invalid_json"
    assert not failure.value.repair_permitted
    assert "private-depth-leaf" not in str(failure.value)


def test_quotes_escapes_fences_and_prose_keep_normal_extraction_behavior():
    text = json.dumps({"action": 1, "public_explanation": 'quoted " \\ ' + "{[" * 2000})
    for wrapped in (text, f"```json\n{text}\n```", f"Answer: {text} end."):
        assert parse_model_action(wrapped, [0, 1, 2]).action == 1
    assert extract_json("malformed {response}") is None
    assert streaming_action_status('{"action":{"action_id":"1"', [0, 1])["status"] == (
        "action_ready")


def test_depth_exhaustion_never_becomes_streaming_action_ready():
    text = _text(1200).replace('"action":1', '"action":{"action_id":"1"}')
    for buffer in (text, text[:-2]):
        assert streaming_action_status(buffer, [0, 1])["status"] == "invalid"


@pytest.mark.parametrize("shape", ["array", "action", "metadata"])
def test_deep_input_is_not_salvaged_as_an_inner_legal_action(shape):
    nested = "[" * 4000 + '{"action":1}' + "]" * 4000
    text = {"array": nested, "action": '{"action":' + nested + '}',
            "metadata": _text(4000)}[shape]
    assert extract_json(text) is None
    with pytest.raises(InvalidModelAction) as failure:
        parse_model_action(text, [0, 1])
    assert not failure.value.repair_permitted


@pytest.mark.parametrize("failure_type", [RecursionError, ValueError])
def test_decoder_resource_errors_are_sanitized_for_parser_and_extraction(monkeypatch, failure_type):
    def exhausted(text):
        raise failure_type("private decoder diagnostic")

    monkeypatch.setattr("eslams.model_actions.json.loads", exhausted)
    assert extract_json('{"action":1}') is None
    with pytest.raises(InvalidModelAction) as failure:
        parse_model_action('{"action":1}', [0, 1])
    assert not failure.value.repair_permitted
    assert "private decoder diagnostic" not in str(failure.value)


@pytest.mark.parametrize("provider,model,key,fixture", PROVIDER_CASES)
def test_runner_retains_deep_action_receipt_without_fallback_or_private_body(
    tmp_path, monkeypatch, provider, model, key, fixture,
):
    monkeypatch.setenv(key, "fixture-depth-key")
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return _response(provider, fixture, _text(4000))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    agent = _agent(provider, model, key, runtime_config=ProviderRuntimeConfig(
        max_retries=2, action_repair_attempts=2, reasoning="disabled"))
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent, output_dir=tmp_path,
                                   on_agent_error="invalid-match"))
    receipt_path = result.expanded_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert calls == [1] and len(receipts) == 1
    assert receipts[0]["outcome"] == "action_response_unparseable"
    assert receipts[0]["usage"]["total_tokens"] == 16
    assert not receipts[0]["action_applied"]
    assert result.score.winner is None and not result.score.match_valid_for_scoring
    assert result.score.fallback_action_count_by_player["player_1"] == 0
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert b"private-depth-leaf" not in path.read_bytes()
