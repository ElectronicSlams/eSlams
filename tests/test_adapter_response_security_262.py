import pytest
from test_baidu_qianfan import SECRET, agent, install, request, wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


@pytest.mark.parametrize("mode,kind", [
    ("escaped", "provider_response_schema_mismatch"),
    ("encoded_prefix", "provider_response_schema_mismatch"),
    ("function", "provider_request_rejected"),
])
def test_no_credential_echo_or_legacy_function_call(monkeypatch, mode, kind):
    data = wire()
    msg = data["choices"][0]["message"]
    escaped = "".join(f"\\u{ord(char):04x}" for char in SECRET)
    if mode == "escaped":
        msg["content"] = f'{{"action": 1, "public_explanation": "{escaped}"}}'
    elif mode == "encoded_prefix":
        msg["content"] = f'{escaped} {{"action": 1}}'
    else:
        msg["function_call"] = {"name": "legacy", "arguments": "{}"}
    calls = install(monkeypatch, data)
    with pytest.raises(ProviderCallError) as failure:
        agent().act(request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1


def test_http_accepted_is_not_a_completed_action(monkeypatch):
    calls = install(monkeypatch, status=202)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert selected.last_receipt["status_code"] == 202
    assert selected.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert len(calls) == 1
