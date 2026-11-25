import httpx
import pytest
from test_nvidia_provider import agent, transport, wire, _request
from eslams.agents import ProviderCallError

@pytest.mark.parametrize("mode", ["escaped", "plain"])
def test_no_credential_echo(transport, mode):
    _, responses = transport
    data = wire()
    secret = "synthetic-nvidia-primary"
    value = "".join("\\u%04x" % ord(char) for char in secret) if mode == "escaped" else secret
    data["choices"][0]["message"]["content"] = '{"action": 0, "public_explanation": "' + value + '"}'
    responses.append(httpx.Response(200, json=data))
    with pytest.raises(ProviderCallError):
        agent().act(_request())
