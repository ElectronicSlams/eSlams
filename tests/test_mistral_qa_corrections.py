"""Review claims reproduced against the current Mistral head, without network."""
import json

import httpx
import pytest
from test_mistral_provider import KEY, _agent, _post, _success
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_preflight

SECRET = "OpaqueMistralQASecondaryNovember"


def test_unicode_escaped_protocol_error_diagnostic_does_not_publish_credential(monkeypatch):
    monkeypatch.setenv(KEY, "OpaqueMistralPrimaryNovember")
    monkeypatch.setenv("QA_SECONDARY_API_KEY", SECRET)
    escaped = "".join(f"\\u{ord(c):04x}" for c in SECRET)
    def post(*args, **kwargs):
        raise ProtocolError("private diagnostic " + escaped)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    current = _agent()
    with pytest.raises(ProviderCallError) as caught:
        current.act(_request())
    assert SECRET not in str(caught.value) and escaped not in str(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize("encoded", [False, True])
def test_previous_action_leak_repro_is_rejected_at_current_head(monkeypatch, encoded):
    data = _success()
    echo = "".join(f"\\u{ord(c):04x}" for c in SECRET) if encoded else SECRET
    data["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"' + echo + '"}')
    calls = _post(monkeypatch, httpx.Response(200, json=data))
    monkeypatch.setenv("QA_SECONDARY_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents._parse_model_action",
                        lambda *a, **k: pytest.fail("credential reached action parser"))
    current = _agent()
    with pytest.raises(ProviderCallError):
        current.act(_request())
    assert len(calls) == 1 and current.last_receipt["usage"]["total_tokens"] == 16
    assert SECRET not in json.dumps(current.attempt_receipts)


@pytest.mark.parametrize("model,effort", [
    ("mistral-small-2603", "low"), ("mistral-large-4-0", "none"),
    ("mistral-large-4", "max"), ("zai-glm-5-3", "none"),
    ("zai-glm-5-3-flash", "medium"),
])
def test_documented_model_effort_restrictions_fail_before_discovery_or_transport(
    monkeypatch, model, effort,
):
    monkeypatch.setenv(KEY, "OpaqueMistralPrimaryNovember")
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    runtime = ProviderRuntimeConfig(reasoning_effort=effort)
    for live in (False, True):
        result = provider_preflight("mistral", model, "tic-tac-toe",
                                    runtime_config=runtime, live=live)
        assert not result["ok"] and not result["readiness"]["configuration_ready"]
    with pytest.raises(ProviderCallError):
        ModelProviderAgent("mistral", model, KEY, runtime_config=runtime).act(_request())


def test_cli_explains_dated_identity_policy(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["run", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "mistral-small-2603" in help_text
    assert "exact" in help_text and "alias" in help_text


@pytest.mark.parametrize("model,effort", [
    ("mistral-small-2603", "none"), ("mistral-small-2603", "high"),
    ("mistral-medium-3-5", "none"), ("mistral-large-4-0", "medium"),
    ("mistral-large-4", "low"), ("zai-glm-5-3", "max"),
    ("zai-glm-5-3-flash", "high"),
])
def test_documented_supported_effort_is_forwarded_unchanged(monkeypatch, model, effort):
    data = _success()
    data["model"] = model
    calls = _post(monkeypatch, httpx.Response(200, json=data))
    current = ModelProviderAgent("mistral", model, KEY,
                                runtime_config=ProviderRuntimeConfig(reasoning_effort=effort))
    assert current.act(_request()).action == 1
    assert calls[0][1]["json"]["model"] == model
    assert calls[0][1]["json"]["reasoning_effort"] == effort
