import pytest
from test_byteplus_provider import _request, agent, fixture, wire
from eslams.agents import ProviderCallError

def test_no_legacy_function_call(monkeypatch):
    data = fixture()
    data["choices"][0]["message"]["function_call"] = {"name": "legacy", "arguments": "{}"}
    wire(monkeypatch, data)
    with pytest.raises(ProviderCallError):
        agent().act(_request())
