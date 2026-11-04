"""Reject credential-bearing actions before Core can decode, parse or repair them."""

import json
from dataclasses import replace

import httpx
import pytest
from test_mistral_provider import KEY, MODEL, _agent, _post, _success
from test_mistral_provider_security import PRIMARY, SECONDARY, _assert_scrubbed
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


def _encoded(secret, encoding):
    if encoding == "literal":
        return secret
    def escape(character):
        codepoint = ord(character)
        units = [codepoint] if codepoint <= 0xFFFF else [
            0xD800 + ((codepoint - 0x10000) >> 10), 0xDC00 + ((codepoint - 0x10000) & 0x3FF),
        ]
        return "".join(f"\\u{unit:04X}" if encoding == "upper_unicode"
                       else f"\\u{unit:04x}" for unit in units)

    return "".join(
        escape(character)
        if encoding != "mixed_unicode" or index % 2 == 0 else character
        for index, character in enumerate(secret)
    )


def _rejected(monkeypatch, content, *, custom_primary=False, chunks=False, secondary=SECONDARY):
    payload = _success()
    cut = content.index(r"\u") + 3 if chunks else 0
    payload["choices"][0]["message"]["content"] = (
        [{"type": "text", "text": content[:cut]}, {"type": "text", "text": content[cut:]}]
        if chunks else content
    )
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    key_env = "CUSTOM_MISTRAL_VALUE" if custom_primary else KEY
    monkeypatch.setenv(key_env, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", secondary)
    monkeypatch.setattr(
        "eslams.agents._parse_model_action",
        lambda *a, **k: pytest.fail("credential-bearing action reached Core parsing"),
    )
    agent = ModelProviderAgent("mistral", MODEL, key_env, runtime_config=ProviderRuntimeConfig(
        max_retries=3, action_repair_attempts=2,
    ))
    request = replace(_request(), history=[{"turn": index} for index in range(50)])
    with pytest.raises(ProviderCallError) as failure:
        agent.act(request)
    assert failure.value.error_kind == "provider_request_rejected"
    assert len(calls) == 1 and len(agent.attempt_receipts) == 1
    assert agent.last_receipt["usage"]["total_tokens"] == 16
    assert agent.last_receipt["locked_model_id"] == MODEL
    assert agent.last_receipt["outcome"] == "provider_request_rejected"
    assert agent.attempt_receipts[0]["attempt_kind"] == "primary"
    assert failure.value.__context__ is None and failure.value.__cause__ is None
    _assert_scrubbed(failure.value.__dict__, (PRIMARY, secondary))
    _assert_scrubbed(agent.attempt_receipts, (PRIMARY, secondary))
    prompt = calls[0][1]["json"]["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == request.history


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("encoding", ["literal", "mixed_unicode", "all_unicode", "upper_unicode"])
@pytest.mark.parametrize("wrapper", ["plain", "fenced", "prose", "escaped_field"])
def test_plain_mixed_and_fully_unicode_encoded_credentials_are_rejected(
    monkeypatch, secret, encoding, wrapper,
):
    content = '{"action":1,"public_explanation":"' + _encoded(secret, encoding) + '"}'
    # Establish that this vector really becomes the credential on Core's decode.
    assert json.loads(content)["public_explanation"] == secret
    if wrapper == "fenced":
        content = "```json\n" + content + "\n```"
    elif wrapper == "prose":
        content = "Answer follows:\n" + content + "\nEnd."
    elif wrapper == "escaped_field":
        content = content.replace("public_explanation", r"\u0070ublic_explanation")
    _rejected(monkeypatch, content)


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("location", [
    "nested_value", "nested_key", "list", "double_encoded_string",
])
def test_decoded_json_keys_values_and_nested_strings_are_scanned(monkeypatch, secret, location):
    encoded = _encoded(secret, "mixed_unicode")
    extra = {
        "nested_value": '{"note":"' + encoded + '"}',
        "nested_key": '{"' + encoded + '":"value"}',
        "list": '[{"note":"' + encoded + '"}]',
        "double_encoded_string": json.dumps(encoded),
    }[location]
    _rejected(monkeypatch, '{"action":1,"metadata":{"note":' + extra + '}}')


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
@pytest.mark.parametrize("encoding", ["mixed_unicode", "all_unicode"])
def test_malformed_action_with_unicode_credential_is_rejected_before_repair(
    monkeypatch, secret, encoding,
):
    _rejected(monkeypatch, '{"action":1,"public_explanation":"' + _encoded(secret, encoding))


@pytest.mark.parametrize("secret", [PRIMARY, SECONDARY])
def test_escape_sequence_split_between_text_chunks_is_rejected(monkeypatch, secret):
    content = '{"action":1,"public_explanation":"' + _encoded(secret, "all_unicode") + '"}'
    _rejected(monkeypatch, content, chunks=True)


@pytest.mark.parametrize("encoding", ["literal", "mixed_unicode", "all_unicode"])
def test_custom_primary_environment_name_is_protected(monkeypatch, encoding):
    content = '{"action":1,"public_explanation":"' + _encoded(PRIMARY, encoding) + '"}'
    _rejected(monkeypatch, content, custom_primary=True)


@pytest.mark.parametrize("content,explanation", [
    (r'{"action":1,"public_explanation":"s\u0061fe"}', "safe"),
    ('```json\n{"action":1,"public_explanation":"safe"}\n```', "safe"),
    ('Prose\n{"action":1,"public_explanation":"safe"}', "safe"),
])
def test_uncontaminated_action_text_is_returned_without_rewriting(
    monkeypatch, content, explanation,
):
    payload = _success()
    payload["choices"][0]["message"]["content"] = content
    calls = _post(monkeypatch, httpx.Response(200, json=payload))
    monkeypatch.setenv(KEY, PRIMARY)
    monkeypatch.setenv("SECONDARY_API_KEY", SECONDARY)
    response = _agent().act(_request())
    assert response.action == 1 and response.public_explanation == explanation
    assert response.metadata["raw_action_text"] == content
    assert len(calls) == 1


@pytest.mark.parametrize("encoding", ["literal", "mixed_unicode", "all_unicode"])
def test_unicode_secondary_credentials_and_surrogate_pairs_are_rejected(monkeypatch, encoding):
    secret = "私密凭据🚀/x"
    content = '{"action":1,"public_explanation":"' + _encoded(secret, encoding) + '"}'
    assert json.loads(content)["public_explanation"] == secret
    _rejected(monkeypatch, content, secondary=secret)


@pytest.mark.parametrize("error_type", [ValueError, RecursionError, TimeoutError])
def test_failed_json_inspection_retains_usage_and_does_not_retry_or_repair(monkeypatch, error_type):
    def cannot_inspect(*a, **k):
        raise error_type("synthetic JSON inspection failure")

    monkeypatch.setattr("eslams.model_actions.extract_json", cannot_inspect)
    calls = _post(monkeypatch, httpx.Response(200, json=_success()))
    agent = _agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        agent.act(_request())
    assert failure.value.error_kind == (
        "provider_timeout" if error_type is TimeoutError else "provider_response_schema_mismatch"
    )
    assert len(calls) == 1 and agent.last_receipt["usage"]["total_tokens"] == 16
    assert failure.value.__context__ is None and failure.value.__cause__ is None
