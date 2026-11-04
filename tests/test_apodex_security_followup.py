"""Independent regression review of Apodex admission and secondary-key custody."""

import json
from dataclasses import replace

import httpx
import pytest
from test_apodex_provider import SECRET, agent, install_post, native_request, wire

from eslams.agents import ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_preflight

SECONDARY = "opaque-secondary-fixture-credential"


@pytest.fixture(params=["APODEX_API_KEY", "OPENAI_API_KEY", "APODEX_API_KEY_SECONDARY",
                        "APODEX_SECONDARY_KEY",
                        "AWS_BEARER_TOKEN_BEDROCK"])
def echoed_key(monkeypatch, request):
    monkeypatch.setenv("APODEX_API_KEY", SECRET)
    if request.param == "APODEX_API_KEY":
        return SECRET
    monkeypatch.setenv(request.param, f"  {SECONDARY}\r\n")
    return SECONDARY


@pytest.mark.parametrize("model", [None, "", " ", "\t\r\n"])
@pytest.mark.parametrize("live", [False, True])
def test_missing_models_fail_preflight_and_dispatch_without_network(monkeypatch, model, live):
    monkeypatch.setenv("APODEX_API_KEY", SECRET)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("no discovery"))
    install_post(monkeypatch, AssertionError("no inference"))
    result = provider_preflight("apodex", model, "tic-tac-toe", live=live)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ValueError, match="nonblank"):
        agent(model=model)
    if model is not None:
        with pytest.raises(ValueError, match="nonblank"):
            _provider_agent(f"apodex:{model}")


@pytest.mark.parametrize("field,value", [
    ("reasoning_budget_tokens", 0), ("reasoning_budget_tokens", 1),
    ("reasoning_budget_tokens", 8192), ("gemini_thinking_budget", -1),
    ("gemini_thinking_budget", 0), ("gemini_thinking_budget", 8192),
    ("reasoning_effort", "high"),
])
@pytest.mark.parametrize("live", [False, True])
def test_explicit_reasoning_controls_fail_preflight_and_reconfigured_agent(
    monkeypatch, field, value, live,
):
    monkeypatch.setenv("APODEX_API_KEY", SECRET)
    subject = agent()
    runtime = replace(subject.runtime_config, **{field: value})
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("no discovery"))
    calls = install_post(monkeypatch, AssertionError("no inference"))
    result = provider_preflight("apodex", "apodex-1.1", "tic-tac-toe", live=live,
                                runtime_config=runtime)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ValueError, match="reasoning controls"):
        agent(runtime_config=runtime)
    subject.runtime_config = runtime
    with pytest.raises(ValueError, match="reasoning controls"):
        subject.act(native_request())
    assert calls == [] and subject.attempt_receipts == []


@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "x-gateway-request-id"])
def test_success_identity_and_header_echoes_become_unknown(monkeypatch, echoed_key, field):
    payload = wire()
    headers = {}
    if field in {"id", "model"}:
        payload[field] = f"prefix-{echoed_key}"
    else:
        headers[field] = f"prefix-{echoed_key}"
    calls = install_post(monkeypatch, httpx.Response(200, json=payload, headers=headers))
    subject = agent()
    if field == "model":
        with pytest.raises(ProviderCallError) as failure:
            subject.act(native_request())
        assert echoed_key not in str(failure.value) + str(failure.value.receipt)
        assert subject.last_receipt["locked_model_id"] is None
    else:
        result = subject.act(native_request())
        assert echoed_key not in json.dumps(result.to_dict())
    assert echoed_key not in json.dumps(subject.attempt_receipts)
    if echoed_key != SECRET:
        outbound = {key: calls[0][1][key] for key in ("headers", "json")}
        assert echoed_key not in json.dumps(outbound)


@pytest.mark.parametrize("body_kind", ["error", "malformed", "partial"])
def test_failure_echoes_never_escape_or_allow_replay(monkeypatch, echoed_key, body_kind):
    headers = {"x-request-id": echoed_key, "x-gateway-request-id": echoed_key}
    if body_kind == "error":
        response = httpx.Response(429, headers=headers, json={
            "id": echoed_key, "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                          "total_tokens": 2},
            "error": {"code": "rate_limited", "type": "rate_limit_error",
                      "message": echoed_key, "metadata": {"id": echoed_key}},
        })
    elif body_kind == "malformed":
        response = httpx.Response(200, headers=headers, text="not JSON " + echoed_key)
    else:
        response = httpx.ReadError(echoed_key)
        response.__dict__["_eslams_response_observation"] = ResponseObservation(
            429, tuple(headers.items()),
        )
    calls = install_post(monkeypatch, response)
    subject = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert len(calls) == 1
    assert echoed_key not in str(failure.value) + json.dumps(failure.value.receipt)
    assert echoed_key not in json.dumps(subject.attempt_receipts)
    assert subject.last_receipt["request_id"] is None
    assert subject.last_receipt["gateway_request_id"] is None


@pytest.mark.parametrize("escaped", [False, True])
def test_action_text_echoes_fail_before_action_publication(monkeypatch, echoed_key, escaped):
    payload = wire()
    value = ''.join(f'\\u{ord(c):04x}' for c in echoed_key) if escaped else echoed_key
    payload["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"' + value + '"}'
    )
    install_post(monkeypatch, httpx.Response(200, json=payload))
    subject = agent()
    with pytest.raises(ProviderCallError) as failure:
        subject.act(native_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert echoed_key not in str(failure.value) + json.dumps(subject.attempt_receipts)


@pytest.mark.parametrize("body_kind", ["model_id", "malformed", "error"])
def test_discovery_cli_does_not_publish_echoes(monkeypatch, capsys, echoed_key, body_kind):
    response = (
        httpx.Response(200, json={"data": [{"id": echoed_key}]}) if body_kind == "model_id" else
        httpx.Response(200, text="not JSON " + echoed_key) if body_kind == "malformed" else
        httpx.Response(401, text=echoed_key)
    )
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: response)
    assert main(["providers", "models", "--provider", "apodex", "--live"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert echoed_key not in json.dumps(result)
    assert not result["ok"]
