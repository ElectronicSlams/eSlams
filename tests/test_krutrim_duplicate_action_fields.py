"""Reject ambiguous action objects before any original response can escape."""

import json

import pytest
from test_krutrim_nested_responses import PRIMARY, SECONDARY, assert_receipt, install
from test_krutrim_provider import agent, request

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.providers.krutrim import API_KEY_ENV


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, PRIMARY)
    monkeypatch.setenv("KRUTRIM_API_KEY", SECONDARY)


def escaped(value):
    return "".join(f"\\u{ord(char):04x}" for char in value)


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("field", ["action", "public_explanation", "unused"])
@pytest.mark.parametrize("escaped_key", [False, True])
def test_overwritten_unicode_credential_is_rejected_before_action_or_text(
    monkeypatch, secret, field, escaped_key,
):
    first = json.dumps(field)
    second = '"' + escaped(field) + '"' if escaped_key else first
    replacement = "1" if field == "action" else '"safe"'
    fields = first + ':"' + escaped(secret) + '",' + second + ":" + replacement
    text = "{" + ("" if field == "action" else '"action":1,') + fields + "}"
    calls = install(monkeypatch, text)
    native = agent(ProviderRuntimeConfig(max_retries=3, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)
    assert native.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert "raw_action_text" not in json.dumps(native.attempt_receipts)
    assert escaped(secret) not in str(caught.value)


@pytest.mark.parametrize("depth", [0, 62, 65])
@pytest.mark.parametrize("wrapper", ["plain", "fence", "preamble"])
def test_nested_duplicate_fields_in_escaped_wire_keep_usage(monkeypatch, depth, wrapper):
    node = '{"k":"' + escaped(SECONDARY) + '","\\u006b":0}'
    text = '{"action":1,"unused":' + "[" * depth + node + "]" * depth + "}"
    if wrapper == "fence":
        text = "```json\n" + text + "\n```"
    elif wrapper == "preamble":
        text = "Here is the action: " + text
    calls = install(monkeypatch, text, escaped=True, private_ids=True)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value, private_ids=True)


@pytest.mark.parametrize("text", [
    '{"action":1,"action":1}',
    '{"action":1,"\\u0061ction":1}',
    '{"action":1,"unused":{"v":0,"v":0}}',
])
def test_duplicate_fields_are_rejected_even_without_credentials(monkeypatch, text):
    calls = install(monkeypatch, text)
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)


@pytest.mark.parametrize("escaped_wire", [False, True])
@pytest.mark.parametrize("text", [
    '{"action":1,"unused":[{"v":1},{"v":2}]}',
    '{"\\u0061ction":1,"unused":0}',
    json.dumps({"action": 1, "unused": '{"k":1,"k":2}'}),
    '```json\n{"action":1,"public_explanation":"A legal move."}\n```',
])
def test_normal_controls_are_valid_and_original_text_is_not_published(
    monkeypatch, text, escaped_wire,
):
    calls = install(monkeypatch, text, escaped=escaped_wire)
    native = agent()
    response = native.act(request())
    assert response.action == 1
    assert "raw_action_text" not in response.metadata
    assert_receipt(native, calls)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_action_fields_are_rejected_with_receipt(monkeypatch, constant):
    calls = install(monkeypatch, '{"action":1,"unused":' + constant + "}")
    native = agent()
    with pytest.raises(ProviderCallError) as caught:
        native.act(request())
    assert_receipt(native, calls, caught.value)


def test_ignored_escaped_preamble_never_enters_public_action_metadata(monkeypatch):
    text = escaped(SECONDARY) + ' {"action":1}'
    calls = install(monkeypatch, text)
    native = agent()
    response = native.act(request())
    assert response.action == 1
    assert "raw_action_text" not in response.metadata
    assert SECONDARY not in json.dumps(response.to_dict())
    assert escaped(SECONDARY) not in json.dumps(response.to_dict())
    assert_receipt(native, calls)
