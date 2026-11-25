import pytest
from test_byteplus_provider import _request, agent, fixture, wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


def test_no_legacy_function_call(monkeypatch):
    data = fixture()
    data["choices"][0]["message"]["function_call"] = {"name": "legacy", "arguments": "{}"}
    wire(monkeypatch, data)
    with pytest.raises(ProviderCallError) as failure:
        agent().act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"


def test_http_accepted_is_not_a_completed_action(monkeypatch):
    calls = wire(monkeypatch, status=202)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert selected.last_receipt["status_code"] == 202
    assert selected.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert len(calls) == 1
