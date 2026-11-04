"""Keyless raw-wire StreamLake contracts; provenance in docs/providers/KUAISHOU.md."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.kuaishou import ENDPOINTS

SECRET = "OpaqueCredential/WithoutConventionalPrefix+42"
MODEL = "kat-coder-pro-v2.5"
FIXTURE = Path(__file__).parent / "fixtures/provider/kuaishou_chat_completions_success.json"


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("STREAMLAKE_API_KEY", SECRET)
    monkeypatch.delenv("ESLAMS_STREAMLAKE_REGION", raising=False)


def wire():
    return json.loads(FIXTURE.read_text())


def agent(provider="kwaipilot", **kwargs):
    return ModelProviderAgent(provider, kwargs.pop("model", MODEL), "STREAMLAKE_API_KEY", **kwargs)


def reply(monkeypatch, payload=None, *, status=200, content=None, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=payload, content=content, headers=headers or {},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("provider", ["kuaishou", "kwaipilot"])
@pytest.mark.parametrize("region", ["international", "cn"])
def test_direct_wire_history_identity_accounting_and_no_default_caps(monkeypatch, provider, region):
    monkeypatch.setenv("ESLAMS_STREAMLAKE_REGION", region)
    calls = reply(monkeypatch, wire())
    history = [{"turn": i, "public": f"public-{i}"} for i in range(300)]
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      history=history,
                      metadata={"model_execution_policy": model_execution_policy(None)})
    native = agent(provider, model="ep-EXACT-MixedCase-123")
    result = native.act(request)
    assert result.action == 0
    url, kwargs = calls[0]
    assert len(calls) == 1 and url == ENDPOINTS[region]
    assert kwargs["headers"] == {"Authorization": f"Bearer {SECRET}",
                                 "Content-Type": "application/json"}
    payload = kwargs["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == "ep-EXACT-MixedCase-123" and payload["stream"] is False
    assert [msg["role"] for msg in payload["messages"]] == ["system", "user"]
    assert json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"] == history
    assert kwargs["timeout"].read is None and kwargs["timeout"].connect == 10
    receipt = native.last_receipt
    assert receipt["provider"] == provider and receipt["model"] == "ep-EXACT-MixedCase-123"
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["provider_endpoint"] == url
    assert receipt["endpoint_kind"] == "streamlake_chat_completions"
    assert receipt["parser_version"] == "streamlake-chat-completions-raw-v1"
    assert receipt["usage"]["input_tokens"] == 19 and receipt["usage"]["output_tokens"] == 10
    assert receipt["usage"]["total_tokens"] == 29 and receipt["usage"]["reasoning_tokens"] == 0
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(result.to_dict())


def test_explicit_operator_limits_temperature_and_no_game_reasoning(monkeypatch):
    calls = reply(monkeypatch, wire())
    native = agent(max_output_tokens=41, temperature=0.3,
                   runtime_config=ProviderRuntimeConfig(timeout_ms=2000))
    request = _request()
    native.act(replace(request, arena=replace(request.arena, id="chess")))
    payload = calls[0][1]["json"]
    assert payload["max_tokens"] == 41 and payload["temperature"] == 0.3
    assert calls[0][1]["timeout"].read <= 2
    assert not {"tools", "tool_choice", "reasoning", "enable_thinking", "provider"} & payload.keys()


@pytest.mark.parametrize("model", [None, "", " ", "\t\n"])
def test_missing_model_rejected_in_constructor_cli_and_preflight(monkeypatch, model):
    calls = reply(monkeypatch, wire())
    with pytest.raises(ValueError, match="explicit nonblank"):
        agent(model=model)
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight("kwaipilot", model, "tic-tac-toe")
    if model is not None:
        with pytest.raises(ValueError, match="explicit nonblank"):
            _provider_agent("kwaipilot:" + model)
    assert not calls


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(reasoning="enabled"), ProviderRuntimeConfig(reasoning="disabled"),
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(gemini_thinking_budget=-1), ProviderRuntimeConfig(history_window_turns=2),
    ProviderRuntimeConfig(gateway_base_url="https://proxy.invalid"),
    ProviderRuntimeConfig(openrouter_provider_order=("unverified-route",)),
])
def test_unsupported_configuration_fails_before_network(monkeypatch, runtime):
    calls = reply(monkeypatch, wire())
    with pytest.raises(ValueError):
        agent(runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("kuaishou", MODEL, "tic-tac-toe", runtime_config=runtime)
    assert not calls


def test_region_typo_and_bad_temperature_fail_closed(monkeypatch):
    monkeypatch.setenv("ESLAMS_STREAMLAKE_REGION", "unexpected")
    with pytest.raises(ValueError, match="international or cn"):
        agent()
    monkeypatch.delenv("ESLAMS_STREAMLAKE_REGION")
    for temperature in (True, float("nan"), -1, 1.1):
        with pytest.raises(ValueError, match="temperature"):
            agent(temperature=temperature)


@pytest.mark.parametrize("status", [200, 400])
def test_documented_invalid_key_error_code_and_safe_request_id(monkeypatch, status):
    calls = reply(monkeypatch, {"ResponseMeta": {"RequestId": "req-error-example",
                  "ErrorCode": "InvalidArgument.Authorization", "ErrorMessage": SECRET}},
                  status=status)
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert len(calls) == 1 and failure.value.error_kind == "provider_auth_failed"
    assert native.last_receipt["request_id"] == "req-error-example"
    assert SECRET not in json.dumps(native.attempt_receipts)


def test_no_default_action_repair_or_fake_success_status(monkeypatch):
    data = wire()
    data["choices"][0]["message"]["content"] = '{"action":999}'
    calls = reply(monkeypatch, data)
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1 and len(native.attempt_receipts) == 1
    calls = reply(monkeypatch, wire(), status=201)
    with pytest.raises(ProviderCallError):
        agent().act(_request())
    assert len(calls) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 429, 500, 502, 503])
def test_http_errors_are_sanitized_and_never_replayed(monkeypatch, status):
    calls = reply(monkeypatch, {"ResponseMeta": {"RequestId": SECRET, "ErrorCode": "Forbidden",
                                               "ErrorMessage": "AccessKey:" + SECRET}},
                  status=status, headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET,
                                          "Retry-After": "0"})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert len(calls) == 1 and len(native.attempt_receipts) == 1
    assert native.last_receipt["status_code"] == status
    assert native.last_receipt["locked_model_id"] is None
    assert native.last_receipt["usage"] == {}
    assert SECRET not in json.dumps(native.attempt_receipts) + str(failure.value)


@pytest.mark.parametrize("body", [b"{", b"[]", b'{"id":1,"id":2}', b'null'])
def test_malformed_body_keeps_sanitized_header_receipt(monkeypatch, body):
    calls = reply(monkeypatch, content=body, headers={"request-id": SECRET})
    native = agent()
    with pytest.raises(ProviderCallError, match="StreamLake"):
        native.act(_request())
    assert len(calls) == 1 and native.last_receipt["request_id"] is None
    assert native.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert SECRET not in json.dumps(native.attempt_receipts)


@pytest.mark.parametrize("mutation,kind", [
    (lambda d: d["choices"][0].update(finish_reason="length"), "provider_output_truncated"),
    (lambda d: d["choices"][0].update(finish_reason="content_filter"), "provider_refused"),
    (lambda d: d["choices"][0].update(finish_reason=None), "provider_response_schema_mismatch"),
    (lambda d: d["choices"][0].update(finish_reason=[]), "provider_response_schema_mismatch"),
    (lambda d: d["choices"][0].update(finish_reason="tool_calls"), "provider_request_rejected"),
    (lambda d: d["choices"][0]["message"].update(tool_calls=[{}]),
     "provider_response_schema_mismatch"),
    (lambda d: d.update(choices=[]), "provider_response_schema_mismatch"),
    (lambda d: d.update(choices=[{}, {}]), "provider_response_schema_mismatch"),
    (lambda d: d.update(ResponseMeta={"ErrorCode": []}), "provider_unavailable"),
])
def test_incomplete_and_invalid_envelopes_never_accept_text(monkeypatch, mutation, kind):
    data = wire()
    mutation(data)
    calls = reply(monkeypatch, data)
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert native.last_receipt["outcome"] == kind


@pytest.mark.parametrize("mode", ["missing", "partial", "invalid", "reasoning", "missing-total"])
def test_missing_identity_usage_and_cost_are_never_invented(monkeypatch, mode):
    data = wire()
    data.pop("model")
    if mode == "missing":
        data.pop("usage")
    elif mode == "partial":
        data["usage"] = {"prompt_tokens": 19}
    elif mode == "invalid":
        data["usage"] = {"prompt_tokens": True, "completion_tokens": -3, "total_tokens": "4"}
    elif mode == "missing-total":
        data["usage"].pop("total_tokens")
    else:
        data["usage"]["completion_tokens_details"]["reasoning_tokens"] = 3
    reply(monkeypatch, data)
    native = agent()
    native.act(_request())
    receipt = native.last_receipt
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    if mode == "missing":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    elif mode == "invalid":
        assert receipt["usage"] == {}
    elif mode in {"partial", "missing-total"}:
        assert receipt["usage"]["total_tokens"] is None
    else:
        assert receipt["usage"]["reasoning_tokens"] == 3
        assert receipt["usage"]["reasoning_included_in_output"] is None


def test_success_ids_and_encoded_action_credential_echoes_are_quarantined(monkeypatch):
    data = wire()
    data.update(id=SECRET, model=SECRET)
    reply(monkeypatch, data, headers={"x-request-id": SECRET, "cf-aig-request-id": SECRET})
    result = agent().act(_request())
    assert SECRET not in json.dumps(result.to_dict())
    assert result.metadata["provider_receipt"]["locked_model_id"] is None
    for wrapped in (False, True):
        data = wire()
        escaped = "".join(f"\\u{ord(c):04x}" for c in SECRET)
        text = '{"action":0,"public_explanation":"' + escaped + '"}'
        data["choices"][0]["message"]["content"] = "```json\n" + text + "\n```" if wrapped else text
        reply(monkeypatch, data)
        native = agent()
        with pytest.raises(ProviderCallError):
            native.act(_request())
        assert SECRET not in json.dumps(native.attempt_receipts)


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_and_partial_response_do_not_echo_credentials(monkeypatch, observed, exception):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        failure = exception(SECRET)
        if observed:
            failure._eslams_response_observation = ResponseObservation(
                503, (("x-request-id", SECRET), ("cf-aig-request-id", SECRET)),
            )
        raise failure

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        native.act(_request())
    assert len(calls) == 1 and len(native.attempt_receipts) == 1
    assert SECRET not in str(failure.value) + json.dumps(native.attempt_receipts)


def test_cli_and_offline_live_preflight_dispatch_without_discovery(monkeypatch, capsys):
    calls = reply(monkeypatch, wire())
    for provider in ("kuaishou", "kwaipilot"):
        native = _provider_agent(provider + ":" + MODEL)
        assert native.provider == provider and native.model == MODEL
        assert provider_models_live(provider) is None
        offline = provider_preflight(provider, MODEL, "tic-tac-toe")
        assert offline["ok"] and offline["readiness"]["inference"] == "not_attempted"
    assert not calls
    live = provider_preflight("kwaipilot", MODEL, "tic-tac-toe", live=True)
    assert live["ok"] and live["checks"]["usage_extraction"] is True and len(calls) == 1
    assert main(["providers", "preflight", "--provider", "kwaipilot", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    monkeypatch.delenv("STREAMLAKE_API_KEY")
    failed = provider_preflight("kwaipilot", MODEL, "tic-tac-toe", live=True)
    assert not failed["ok"] and failed["error"]["error_class"] == "provider_auth_failed"
    assert len(calls) == 1


def test_cli_run_dispatches_native_adapter_and_persists_sanitized_receipts(
    monkeypatch, capsys, tmp_path,
):
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        data = wire()
        request = json.loads(kwargs["json"]["messages"][1]["content"].splitlines()[-1])
        data["choices"][0]["message"]["content"] = json.dumps(
            {"action": request["legal_actions"][0]},
        )
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "kwaipilot:" + MODEL,
                 "--opponent", "first-legal", "--output-dir", str(tmp_path),
                 "--run-id", "kat-cli-contract"]) == 0
    output = capsys.readouterr().out
    result = json.loads(output[output.index("{"):])
    receipts = (Path(result["expanded_artifact"]) / "receipts/provider_receipts.jsonl").read_text()
    rows = [json.loads(line) for line in receipts.splitlines()]
    assert len(calls) == len(rows) > 0
    assert all(row["provider"] == "kwaipilot" and row["model"] == MODEL for row in rows)
    assert SECRET not in output + receipts


@pytest.mark.parametrize("provider", ["kuaishou", "kwaipilot"])
@pytest.mark.parametrize("model", [None, "", " ", "\t\n"])
@pytest.mark.parametrize("live", [False, True])
def test_invalid_ids_fail_preflight_without_discovery_or_transport(
    monkeypatch, provider, model, live,
):
    calls = []
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live",
                        lambda *args: calls.append("discovery"))
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *args, **kw: calls.append("post"))
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight(provider, model, "tic-tac-toe", live=live)
    with pytest.raises(ValueError, match="explicit nonblank"):
        _provider_agent(provider if model is None else provider + ":" + model)
    native = agent(provider)
    native.model = model
    with pytest.raises(ValueError, match="explicit nonblank"):
        native.act(_request())
    assert not calls


@pytest.mark.parametrize("provider", ["kuaishou", "kwaipilot"])
@pytest.mark.parametrize("budget,thinking", [(0, None), (500, None), (None, -1),
                                          (None, 0), (None, 500)])
def test_reasoning_budgets_fail_live_preflight_and_reconfigured_agent_before_transport(
    monkeypatch, provider, budget, thinking,
):
    calls = []
    monkeypatch.setattr("eslams.provider_preflight.provider_models_live",
                        lambda *args: calls.append("discovery"))
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *args, **kw: calls.append("post"))
    runtime = ProviderRuntimeConfig(reasoning_budget_tokens=budget, gemini_thinking_budget=thinking)
    for live in (False, True):
        with pytest.raises(ValueError, match="native-default reasoning"):
            provider_preflight(provider, MODEL, "tic-tac-toe", live=live, runtime_config=runtime)
    native = agent(provider)
    native.runtime_config = runtime
    with pytest.raises(ValueError, match="native-default reasoning"):
        native.act(_request())
    assert not calls


@pytest.mark.parametrize("secondary_env", ["STREAMLAKE_API_KEY", "WQ_API_KEY", "OPENAI_API_KEY",
                                         "SECONDARY_API_KEY", "SECONDARY_KEY",
                                         "SECONDARY_AUTH_TOKEN"])
@pytest.mark.parametrize("mode", ["success", "error", "malformed", "partial", "action",
                                "escaped-action", "encoded-action"])
def test_active_and_secondary_credentials_never_enter_receipts_or_actions(
    monkeypatch, secondary_env, mode,
):
    secondary = "OpaqueSecondary/WithoutPrefix+17"
    monkeypatch.setenv("CUSTOM_ACTIVE_API_KEY", SECRET)
    monkeypatch.setenv(secondary_env, secondary)
    calls = []

    def post(url, **kwargs):
        calls.append(1)
        assert kwargs["headers"]["Authorization"] == "Bearer " + SECRET
        assert secondary not in json.dumps({"headers": kwargs["headers"], "json": kwargs["json"]})
        headers = {"x-request-id": SECRET, "cf-aig-request-id": secondary}
        if mode == "partial":
            exc = httpx.ReadTimeout(SECRET + secondary)
            exc._eslams_response_observation = ResponseObservation(200, tuple(headers.items()))
            raise exc
        if mode == "malformed":
            return httpx.Response(200, content=('{"id":"' + secondary).encode(), headers=headers)
        if mode == "error":
            return httpx.Response(429, json={"id": SECRET, "ResponseMeta": {
                "RequestId": secondary, "ErrorCode": "TooManyRequests",
                "ErrorMessage": SECRET + secondary}}, headers=headers)
        data = wire()
        data.update(id=secondary, model=SECRET)
        if "action" in mode:
            explanation = SECRET + " " + secondary
            if mode == "encoded-action":
                explanation = quote(explanation, safe="").replace("%2F", "%2f")
            text = json.dumps({"action": 0, "public_explanation": explanation})
            if mode == "escaped-action":
                text = "```json\n" + text.replace(secondary, "".join(
                    f"\\u{ord(char):04x}" for char in secondary
                )).replace(SECRET, "".join(f"\\u{ord(char):04x}" for char in SECRET)) + "\n```"
            data["choices"][0]["message"]["content"] = text
        return httpx.Response(200, json=data, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ModelProviderAgent("kwaipilot", MODEL, "CUSTOM_ACTIVE_API_KEY",
                                runtime_config=ProviderRuntimeConfig(max_retries=3))
    if mode == "success":
        response = native.act(_request())
        public = json.dumps(response.to_dict())
        assert native.last_receipt["locked_model_id"] is None
        assert native.last_receipt["model_identity_source"] is None
    else:
        with pytest.raises(ProviderCallError) as failure:
            native.act(_request())
        public = str(failure.value) + json.dumps(failure.value.receipt)
    public += json.dumps(native.attempt_receipts)
    assert SECRET not in public and secondary not in public
    assert len(calls) == 1 and len(native.attempt_receipts) == 1
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["gateway_request_id"] is None


def test_discovery_has_no_response_or_credential_echo_path(monkeypatch):
    monkeypatch.setenv("WQ_API_KEY", "OpaqueSecondary/WithoutPrefix+17")
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *args, **kw: pytest.fail("No StreamLake discovery contract exists"))
    from eslams.provider_preflight import provider_models_result

    for provider in ("kuaishou", "kwaipilot"):
        assert provider_models_live(provider) is None
        result = provider_models_result(provider)
        assert not result["ok"]
        assert result["error"]["error_class"] == "provider_discovery_unavailable"
        assert SECRET not in json.dumps(result)
        assert "OpaqueSecondary/WithoutPrefix+17" not in json.dumps(result)
