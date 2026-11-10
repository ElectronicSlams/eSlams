"""QA correction: reject contaminated final text; never substitute an action."""
import json
from dataclasses import replace

import pytest
from test_cohere_provider import agent, fixture, offline, wire  # noqa: F401
from test_provider_wire_v06 import _request

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


@pytest.mark.parametrize("field", ["action", "public_explanation", "nested", "key"])
@pytest.mark.parametrize("encoding", ["raw", "unicode", "mixed"])
@pytest.mark.parametrize("secondary", [False, True])
def test_contaminated_answer_cannot_become_a_redacted_legal_action(
    monkeypatch, field, encoding, secondary,
):
    secret = "opaque-cohere-qa-key"
    monkeypatch.setenv("CO_API_KEY" if secondary else "COHERE_API_KEY", secret)
    payload = {"action": "[REDACTED]"}
    if field in {"action", "public_explanation"}:
        payload[field] = secret
    elif field == "nested":
        payload["extra"] = {"value": secret}
    else:
        payload[secret] = "ignored"
    text = json.dumps(payload)
    if encoding != "raw":
        text = text.replace(secret, "".join(
            f"\\u{ord(c):04x}" if encoding == "unicode" or i % 2 else c
            for i, c in enumerate(secret)))
    data = fixture()
    data["message"]["content"][0]["text"] = text
    calls = wire(monkeypatch, data)
    selected = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2, max_retries=2))
    req = replace(_request(), legal_actions=[secret, "[REDACTED]"],
                  action_schema={"type": "string"})
    with pytest.raises(ProviderCallError) as failure:
        selected.act(req)
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == len(selected.attempt_receipts) == 1
    assert selected.last_receipt["usage"]
    assert secret not in json.dumps(selected.attempt_receipts) + str(failure.value)


def test_clean_answer_bytes_are_not_reserialized(monkeypatch):
    text = '  { "action": 1, "public_explanation": "Clean answer." }\n'
    data = fixture()
    data["message"]["content"][0]["text"] = text
    wire(monkeypatch, data)
    assert agent().act(_request()).metadata["raw_action_text"] == text
