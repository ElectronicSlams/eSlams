"""Bound hostile action JSON while keeping the received attempt's evidence."""

import json

import httpx
import pytest
from test_krutrim_provider import MODEL, agent, request, wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.providers.krutrim import API_KEY_ENV

PRIMARY = "syntheticKrutrimNestedPrimary123"
SECONDARY = "syntheticKrutrimNestedSecondary456"
USAGE = {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setenv("KRUTRIM_API_KEY", SECONDARY)


def install(monkeypatch, text, *, escaped=False, private_ids=False):
    payload = wire()
    payload["usage"] = USAGE
    payload["choices"][0]["message"]["content"] = text
    if private_ids:
        payload.update(id=SECONDARY, model=PRIMARY)
    body = json.dumps(payload)
    if escaped:
        escaped_text = '"' + "".join(f"\\u{ord(char):04x}" for char in text) + '"'
        body = body.replace(json.dumps(text), escaped_text)
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, content=body.encode(), headers={
            "x-request-id": SECONDARY if private_ids else "nested-request",
            "x-gateway-request-id": PRIMARY if private_ids else "nested-gateway",
        })

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def assert_receipt(native, calls, error=None, *, private_ids=False):
    assert len(calls) == len(native.attempt_receipts) == 1
    receipt = native.last_receipt
    assert receipt["status_code"] == 200
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["request_id"] == (None if private_ids else "nested-request")
    assert receipt["locked_model_id"] == (None if private_ids else MODEL)
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if error is not None:
        assert error.error_kind == "provider_response_schema_mismatch"
        assert error.retry_permitted is False
        assert error.receipt["usage"] == receipt["usage"]
    public = json.dumps([native.attempt_receipts, str(error), getattr(error, "receipt", None)])
    assert PRIMARY not in public and SECONDARY not in public


@pytest.mark.parametrize("depth", [65, 400, 800, 1500])
@pytest.mark.parametrize("shape", ["array", "object"])
@pytest.mark.parametrize("escaped", [False, True])
def test_deep_action_json_is_rejected_with_observed_receipt(monkeypatch, depth, shape, escaped):
    nested = "[" * depth + "0" + "]" * depth
    text = nested if shape == "array" else '{"action":1,"unused":' + nested + "}"
    calls = install(monkeypatch, text, escaped=escaped)
    native = agent(ProviderRuntimeConfig(max_retries=3, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)


@pytest.mark.parametrize("escaped", [False, True])
def test_deep_escaped_credential_payload_keeps_usage_and_sanitizes_ids(monkeypatch, escaped):
    secret = '"' + "".join(f"\\u{ord(char):04x}" for char in SECONDARY) + '"'
    text = '{"action":1,"unused":' + "[" * 1500 + secret + "]" * 1500 + "}"
    calls = install(monkeypatch, text, escaped=escaped, private_ids=True)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value, private_ids=True)


@pytest.mark.parametrize("escaped", [False, True])
@pytest.mark.parametrize("text", [
    '{"action":1,"unused":' + "[" * 63 + "0" + "]" * 63 + "}",
    json.dumps({"action": 1, "unused": "[" * 1500 + "{}" + "]" * 1500}),
    json.dumps({"action": 1, "public_explanation": 'Literal \\"quote\\\\ [ { } ]'}),
    '```json\n{"action":1}\n```',
    'Here is the action: {"action":1}',
])
def test_normal_and_quoted_brackets_remain_valid(monkeypatch, text, escaped):
    calls = install(monkeypatch, text, escaped=escaped)
    native = agent()
    response = native.act(request())
    assert response.action == 1
    assert native.last_receipt["outcome"] == "ok"
    assert_receipt(native, calls)


@pytest.mark.parametrize("prefix", ['"unterminated preamble ', "]" * 80])
def test_fallback_object_candidate_cannot_hide_excessive_depth(monkeypatch, prefix):
    text = prefix + '{"action":1,"unused":' + "[" * 1500 + "0" + "]" * 1500 + "}"
    calls = install(monkeypatch, text)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)


@pytest.mark.parametrize("failure", [ValueError, RecursionError, OverflowError])
def test_decoder_failures_keep_the_received_accounting(monkeypatch, failure):
    calls = install(monkeypatch, '{"action":1}')

    def failed(*args):
        raise failure(SECONDARY)

    monkeypatch.setattr("eslams.providers.krutrim._load_action_json", failed)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)


def test_deep_raw_outer_body_has_unknown_usage_and_safe_header_custody(monkeypatch):
    calls = []
    # Truncation makes the outer envelope unverified regardless of interpreter
    # recursion limits; its apparent counters must not become trusted usage.
    body = '{"usage":{"prompt_tokens":12},"unused":' + "[" * 1500 + "0"

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, content=body.encode(), headers={"x-request-id": SECONDARY})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["status_code"] == 200
    assert native.last_receipt["usage"] == {}
    assert native.last_receipt["request_id"] is None
    assert PRIMARY not in str(caught.value) and SECONDARY not in json.dumps(native.attempt_receipts)
