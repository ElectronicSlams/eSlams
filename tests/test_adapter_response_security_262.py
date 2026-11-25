import pytest
from test_baidu_qianfan import agent, install, request, wire, SECRET
from eslams.agents import ProviderCallError

@pytest.mark.parametrize("mode", ["escaped", "function"])
def test_no_credential_echo_or_legacy_function_call(monkeypatch, mode):
    data = wire()
    msg = data["choices"][0]["message"]
    if mode == "escaped":
        escaped = "".join("\\u%04x" % ord(char) for char in SECRET)
        msg["content"] = '{"action": 1, "public_explanation": "' + escaped + '"}'
    else:
        msg["function_call"] = {"name": "legacy", "arguments": "{}"}
    install(monkeypatch, data)
    with pytest.raises(ProviderCallError):
        agent().act(request())
