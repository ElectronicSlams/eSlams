"""Current-head QA regressions; synthetic credentials and no endpoint calls."""
import json
from urllib.parse import quote

import pytest
from test_model_agents import _request
from test_tencent_hunyuan import agent, credentials, fixture, wire  # noqa: F401

from eslams.agents import ProviderCallError
from eslams.protocol import ProtocolError

SECRET = "OpaqueTencentSecondaryQANovember"


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("source", ["TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY",
                                    "TENCENTCLOUD_TOKEN"])
def test_unobserved_protocol_diagnostic_excludes_credential_and_exception_context(
    monkeypatch, encoded, source,
):
    monkeypatch.setenv(source, SECRET)
    echo = "".join(f"\\u{ord(c):04x}" for c in SECRET) if encoded else SECRET
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise ProtocolError("private diagnostic " + echo)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    current = agent()
    with pytest.raises(ProviderCallError) as caught:
        current.act(_request())
    assert len(calls) == 1
    assert SECRET not in str(caught.value) and echo not in str(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert SECRET not in json.dumps(current.attempt_receipts)


def test_url_encoded_sts_echo_is_rejected_before_action_parsing(monkeypatch):
    token = SECRET + "/+?=="
    monkeypatch.setenv("TENCENTCLOUD_TOKEN", token)
    data = fixture()
    data["Response"]["Choices"][0]["Message"]["Content"] = json.dumps(
        {"action": 1, "public_explanation": quote(token, safe="")})
    calls = wire(monkeypatch, data)
    monkeypatch.setattr("eslams.agents._parse_model_action",
                        lambda *a, **k: pytest.fail("encoded STS token reached action parsing"))
    with pytest.raises(ProviderCallError):
        agent().act(_request())
    assert len(calls) == 1


@pytest.mark.parametrize("source", ["TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY",
                                    "TENCENTCLOUD_TOKEN"])
@pytest.mark.parametrize("encoded", [False, True])
def test_current_head_rejects_raw_and_decoded_action_credentials_with_usage(
    monkeypatch, source, encoded,
):
    monkeypatch.setenv(source, SECRET)
    echo = "".join(f"\\u{ord(c):04X}" for c in SECRET) if encoded else SECRET
    data = fixture()
    data["Response"]["Choices"][0]["Message"]["Content"] = (
        '{"action":1,"public_explanation":"' + echo + '"}')
    calls = wire(monkeypatch, data)
    monkeypatch.setattr("eslams.agents._parse_model_action",
                        lambda *a, **k: pytest.fail("credential reached action parsing"))
    current = agent()
    with pytest.raises(ProviderCallError):
        current.act(_request())
    assert len(calls) == 1
    assert current.last_receipt["usage"]["total_tokens"] == 113
    assert SECRET not in json.dumps(current.attempt_receipts)
