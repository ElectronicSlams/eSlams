"""Namazu raw-wire contract and adversarial custody checks; no live API calls."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_provider_wire_v06 import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.sakana import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

FIXTURE = Path(__file__).parent / "fixtures/provider/sakana_namazu_chat_success.json"
SECRET = "fixture-secret-with-no-standard-key-prefix"
SECONDARY = "alternate-credential-with-an-unrecognized-prefix"


def wire():
    return json.loads(FIXTURE.read_text())


def agent(**kwargs):
    return ModelProviderAgent("sakana", "sakana-namazu-v1.0", "SAKANA_API_KEY", **kwargs)


def mock_wire(monkeypatch, data=None, *, status=200, headers=None):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=wire() if data is None else data, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_direct_success_wire_accounting_history_and_native_defaults(monkeypatch):
    calls = mock_wire(monkeypatch)
    native = agent()
    history = [{"turn_id": index, "action": index % 3} for index in range(30)]
    response = native.act(replace(
        _request(), protocol_version="eslams-act-v2", time_budget_ms=None, history=history,
        metadata={"model_execution_policy": model_execution_policy(None)},
    ))
    url, kwargs = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
    payload = kwargs["json"]
    assert payload["model"] == "sakana-namazu-v1.0"
    assert payload["tools"] == [] and payload["tool_choice"] == "none"
    assert payload["stream"] is False
    assert all(key not in payload for key in (
        "max_tokens", "max_completion_tokens", "reasoning", "reasoning_effort",
        "chat_template_kwargs", "temperature", "provider", "fallbacks",
    ))
    assert json.dumps(history, sort_keys=True) in payload["messages"][1]["content"]
    assert kwargs["timeout"].read is None and kwargs["timeout"].pool is None
    assert response.action == 1
    receipt = native.last_receipt
    assert receipt["provider"] == "sakana"
    assert receipt["locked_model_id"] == "sakana-namazu-v1.0"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "sakana_chat_completions"
    assert receipt["usage"]["total_tokens"] == 20
    assert receipt["usage"]["cached_input_tokens"] == 3
    assert receipt["usage"]["reasoning_tokens"] == 4
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(native.attempt_receipts) == 1
    assert "Synthetic private thinking" not in str(response.to_dict())
    assert SECRET not in str(response.to_dict())


@pytest.mark.parametrize("mode,thinking", [("enabled", True), ("disabled", False)])
def test_operator_controls_forwarded_exactly(monkeypatch, mode, thinking):
    calls = mock_wire(monkeypatch)
    native = agent(runtime_config=ProviderRuntimeConfig(reasoning=mode), max_output_tokens=123)
    native.act(_request())
    assert calls[0][1]["json"]["chat_template_kwargs"] == {"thinking": thinking}
    assert calls[0][1]["json"]["max_completion_tokens"] == 123


@pytest.mark.parametrize("model", [None, "", " ", "fugu", "fugu-ultra", "sakana-namazu "])
def test_bad_or_routed_model_rejected_before_network(model):
    with pytest.raises(ValueError):
        ModelProviderAgent("sakana", model, "SAKANA_API_KEY")


@pytest.mark.parametrize("config", [
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=100),
    ProviderRuntimeConfig(gemini_thinking_budget=0),
    ProviderRuntimeConfig(gateway_base_url="https://example.invalid"),
    ProviderRuntimeConfig(gateway_mode="generic_base_url"),
    ProviderRuntimeConfig(history_window_turns=1),
    ProviderRuntimeConfig(openrouter_provider_order=("Sakana",)),
])
def test_unsupported_controls_rejected_locally(config):
    with pytest.raises(ValueError):
        agent(runtime_config=config)
    with pytest.raises(ValueError):
        provider_preflight("sakana", "sakana-namazu", "tic-tac-toe", runtime_config=config)


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_failures_no_replay_no_echo(monkeypatch, status, kind):
    calls = mock_wire(monkeypatch, {"error": {"message": SECRET, "code": 429}},
                      status=status, headers={"x-request-id": SECRET, "Retry-After": "0"})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == kind
    assert len(calls) == 1 and len(native.attempt_receipts) == 1
    assert SECRET not in str(native.last_receipt) + str(failure.value.receipt) + str(failure.value)
    assert native.last_receipt["locked_model_id"] is None
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("field", ["id", "model", "header", "content", "escaped_content"])
def test_success_credential_echo_suppression(monkeypatch, field):
    data = wire()
    headers = {"x-request-id": f"prefix-{SECRET}", "x-gateway-request-id": SECRET}
    if field in {"id", "model"}:
        data[field] = f"prefix-{SECRET}"
    elif field in {"content", "escaped_content"}:
        text = json.dumps({"action": 1, "public_explanation": SECRET})
        if field == "escaped_content":
            text = text.replace(SECRET, "".join(f"\\u{ord(char):04x}" for char in SECRET))
        data["choices"][0]["message"]["content"] = text
    mock_wire(monkeypatch, data, headers=headers)
    native = agent()
    if field in {"content", "escaped_content", "model"}:
        with pytest.raises(ProviderCallError) as failure:
            native.act(_request())
        assert failure.value.error_kind == "provider_response_schema_mismatch"
    else:
        response = native.act(_request())
        assert SECRET not in str(response.to_dict())
    assert SECRET not in str(native.last_receipt)
    if field == "model":
        assert native.last_receipt["locked_model_id"] is None
        assert native.last_receipt["model_identity_source"] is None


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ReadError, ProtocolError])
@pytest.mark.parametrize("observed", [True, False])
def test_partial_transport_receipts_are_scrubbed_and_never_retried(
    monkeypatch, error_type, observed,
):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        exc = error_type(SECRET)
        if observed:
            exc._eslams_response_observation = ResponseObservation(
                200, (("x-request-id", SECRET), ("x-gateway-request-id", SECRET)),
            )
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as failure:
        native.act(_request())
    assert calls == [1]
    assert SECRET not in str(native.last_receipt) + str(failure.value)
    assert native.last_receipt["usage"] == {}


@pytest.mark.parametrize("body", ["not-json", "[]", '{"choices":[],"choices":[]}', '{"secret":'])
def test_malformed_body_does_not_echo_headers(monkeypatch, body):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, text=body + SECRET, headers={"x-request-id": SECRET},
    ))
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(_request())
    assert SECRET not in str(native.last_receipt)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("content_filter", "provider_refused"),
    ("tool_calls", "provider_request_rejected"), ("unknown", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"), ({}, "provider_response_schema_mismatch"),
])
def test_noncomplete_envelopes_never_accept_legal_looking_text(monkeypatch, reason, kind):
    data = wire()
    data["choices"][0]["finish_reason"] = reason
    calls = mock_wire(monkeypatch, data)
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == kind
    assert native.last_receipt["usage"]["total_tokens"] == 20
    assert len(calls) == 1


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 12},
    {"prompt_tokens": True, "completion_tokens": -1, "total_tokens": "20"}])
def test_absent_partial_and_invalid_accounting_not_fabricated(monkeypatch, usage):
    data = wire()
    data.pop("model")
    data["usage"] = usage
    mock_wire(monkeypatch, data)
    native = agent()
    native.act(_request())
    assert native.last_receipt["locked_model_id"] is None
    normalized = native.last_receipt["usage"]
    assert normalized.get("output_tokens") is None
    assert normalized.get("total_tokens") is None
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_cli_requires_explicit_model_and_dispatches_native_adapter(monkeypatch, capsys):
    for value in ("sakana", "sakana:", "sakana: "):
        with pytest.raises(ValueError):
            _provider_agent(value)
    native = _provider_agent("sakana:sakana-namazu")
    assert native.model == "sakana-namazu" and native.api_key_env == "SAKANA_API_KEY"
    calls = mock_wire(monkeypatch)
    native.act(_request())
    assert calls[0][1]["json"]["model"] == "sakana-namazu"
    assert main(["providers", "preflight", "--provider", "sakana", "--model",
                 "sakana-namazu", "--arena", "tic-tac-toe"]) == 0
    assert json.loads(capsys.readouterr().out)["preflight_mode"] == "configuration_only"


def test_preflight_no_implicit_network_then_explicit_discovery_and_inference(monkeypatch):
    calls = mock_wire(monkeypatch)
    gets = []

    def get(url, **kwargs):
        gets.append(url)
        assert url == MODELS_ENDPOINT
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"data": [{"id": "sakana-namazu-v1.0"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    result = provider_preflight("sakana", "sakana-namazu-v1.0", "tic-tac-toe")
    assert result["ok"] and result["checks"]["adapter_available"]
    assert calls == [] and gets == []
    result = provider_preflight("sakana", "sakana-namazu-v1.0", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert len(calls) == len(gets) == 1


def test_discovery_credential_echo_rejected(monkeypatch):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": SECRET}]},
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("sakana")
    assert SECRET not in str(failure.value)


def test_error_observations_quarantined_and_secret_ids_dropped(monkeypatch):
    data = {"error": {"message": SECRET, "id": SECRET,
                      "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                      "cost": 100}}
    mock_wire(monkeypatch, data, status=500)
    native = agent()
    with pytest.raises(ProviderCallError):
        native.act(_request())
    receipt = native.last_receipt
    assert receipt["provider_response_id"] is None
    assert receipt["usage"]["total_tokens"] == 20
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in str(receipt)


def test_refusal_tool_calls_and_multiple_choices_rejected(monkeypatch):
    original = wire()
    mutations = [
        {"refusal": SECRET}, {"tool_calls": [{"id": SECRET}]}, {"content": None},
    ]
    for changes in mutations:
        data = copy.deepcopy(original)
        data["choices"][0]["message"].update(changes)
        mock_wire(monkeypatch, data)
        native = agent()
        with pytest.raises(ProviderCallError):
            native.act(_request())
        assert SECRET not in str(native.last_receipt)
    data = copy.deepcopy(original)
    data["choices"].append(copy.deepcopy(data["choices"][0]))
    mock_wire(monkeypatch, data)
    with pytest.raises(ProviderCallError):
        agent().act(_request())


@pytest.mark.parametrize("credential", ["", " \r\n", "bad key", "bad\tkey", "snowman-☃"])
def test_invalid_or_missing_auth_never_reaches_transport(monkeypatch, credential):
    monkeypatch.setenv("SAKANA_API_KEY", credential)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == "provider_auth_failed"
    assert native.last_receipt["usage"] == {}


@pytest.mark.parametrize("body", ["[]", "null", '{"choices":[],"choices":[]}'])
def test_valid_nonobject_and_duplicate_json_envelopes_rejected(monkeypatch, body):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, text=body, headers={"x-request-id": SECRET},
    ))
    native = agent()
    with pytest.raises(ProviderCallError) as failure:
        native.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert SECRET not in str(native.last_receipt)


def test_untrusted_cost_extensions_do_not_supply_measured_cost(monkeypatch):
    data = wire()
    data["usage"]["cost"] = 12.34
    data["cost"] = 12.34
    mock_wire(monkeypatch, data)
    native = agent()
    native.act(_request())
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_receipts_sanitized_before_invocation_publication_and_runner_artifacts(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    calls = []

    class ObservedAgent(ModelProviderAgent):
        def _publish_receipts(self, rows):
            assert SECRET not in str(rows)
            super()._publish_receipts(rows)

    def post(url, **kwargs):
        calls.append(1)
        visible = json.loads(kwargs["json"]["messages"][1]["content"].splitlines()[-1])
        data = wire()
        data["id"] = SECRET
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": visible["legal_actions"][0],
        })
        data["choices"][0]["message"]["reasoning_content"] = SECRET
        return httpx.Response(200, json=data, headers={"x-request-id": SECRET})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ObservedAgent("sakana", "sakana-namazu-v1.0", "SAKANA_API_KEY")
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=native, output_dir=tmp_path))
    assert calls
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*.json*"):
        assert SECRET not in path.read_text()


@pytest.mark.parametrize("echo", [SECRET, SECONDARY])
@pytest.mark.parametrize("path", ["ids", "http_error", "malformed", "partial", "action"])
def test_primary_and_secondary_credentials_never_enter_published_fields(monkeypatch, echo, path):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setenv("SAKANA_SECONDARY_API_KEY", f"  {SECONDARY}\r\n")
    published = []

    class ObservedAgent(ModelProviderAgent):
        def _publish_receipts(self, rows):
            published.append(copy.deepcopy(rows))
            super()._publish_receipts(rows)

    def post(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        assert SECONDARY not in str(kwargs)
        headers = {"x-request-id": f"prefix-{echo}", "x-gateway-request-id": echo}
        data = wire()
        data["id"] = echo
        if path == "http_error":
            return httpx.Response(500, json={"error": {"id": echo, "message": echo}},
                                  headers=headers)
        if path == "malformed":
            return httpx.Response(200, text=f"{{invalid {echo}", headers=headers)
        if path == "partial":
            failure = ProtocolError(echo)
            failure._eslams_response_observation = ResponseObservation(200, tuple(headers.items()))
            raise failure
        if path == "action":
            escaped = "".join(f"\\u{ord(char):04x}" for char in echo)
            data["choices"][0]["message"]["content"] = (
                '{"action":1,"public_explanation":"' + escaped + '"}'
            )
        return httpx.Response(200, json=data, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ObservedAgent("sakana", "sakana-namazu-v1.0", "SAKANA_API_KEY")
    if path == "ids":
        result = native.act(_request())
        assert SECRET not in str(result.to_dict()) and SECONDARY not in str(result.to_dict())
        assert native.last_receipt["provider_response_id"] is None
    else:
        with pytest.raises(ProviderCallError) as failure:
            native.act(_request())
        public = str(failure.value) + str(failure.value.receipt)
        assert SECRET not in public and SECONDARY not in public
    assert len(native.attempt_receipts) == 1
    assert SECRET not in str(published) and SECONDARY not in str(published)


@pytest.mark.parametrize("echo", [SECRET, SECONDARY])
def test_discovery_rejects_both_configured_credentials(monkeypatch, echo):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setenv("SAKANA_SECONDARY_API_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": f"prefix-{echo}"}]},
    ))
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("sakana")
    assert SECRET not in str(failure.value) and SECONDARY not in str(failure.value)


@pytest.mark.parametrize("model", [None, "", " \t\n"])
@pytest.mark.parametrize("live", [False, True])
def test_missing_and_blank_models_fail_before_preflight_network(monkeypatch, model, live):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("inference"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    with pytest.raises(ValueError, match="explicit nonblank model ID"):
        provider_preflight("sakana", model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("field,budget", [
    ("reasoning_budget_tokens", 0), ("reasoning_budget_tokens", 1),
    ("gemini_thinking_budget", -1), ("gemini_thinking_budget", 0),
])
def test_explicit_unsupported_budgets_fail_preflight_and_before_transport(
    monkeypatch, field, budget,
):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("inference"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    config = ProviderRuntimeConfig(**{field: budget})
    for live in (False, True):
        with pytest.raises(ValueError, match="without effort or budget"):
            provider_preflight("sakana", "sakana-namazu", "tic-tac-toe",
                               live=live, runtime_config=config)
    with pytest.raises(ValueError, match="without effort or budget"):
        agent(runtime_config=config)
    native = agent()
    native.runtime_config = config
    with pytest.raises(ValueError, match="without effort or budget"):
        native.act(_request())
    assert native.attempt_receipts == []


@pytest.mark.parametrize("echo", [SECRET, SECONDARY])
def test_custom_active_key_and_standard_key_both_scrubbed(monkeypatch, echo):
    monkeypatch.setenv("CUSTOM_SELECTED_KEY", SECRET)
    monkeypatch.setenv("SAKANA_API_KEY", SECONDARY)

    def post(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        data = wire()
        data["id"] = echo
        # Redaction uses values snapshotted before transport, even if rotated.
        monkeypatch.delenv("SAKANA_API_KEY")
        return httpx.Response(200, json=data, headers={"x-request-id": echo})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = ModelProviderAgent("sakana", "sakana-namazu-v1.0", "CUSTOM_SELECTED_KEY")
    result = native.act(_request()).to_dict()
    assert SECRET not in str(result) and SECONDARY not in str(result)


@pytest.mark.parametrize("path", ["error", "malformed", "transport"])
@pytest.mark.parametrize("echo", [SECRET, SECONDARY])
def test_discovery_failures_never_expose_either_configured_credential(monkeypatch, echo, path):
    monkeypatch.setenv("SAKANA_API_KEY", SECRET)
    monkeypatch.setenv("SAKANA_SECONDARY_API_KEY", SECONDARY)

    def get(*args, **kwargs):
        if path == "transport":
            raise httpx.ReadError(echo)
        if path == "malformed":
            return httpx.Response(200, text=f"{{invalid {echo}")
        return httpx.Response(500, json={"error": {"message": echo}},
                              headers={"x-request-id": echo})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    with pytest.raises(ProviderCallError) as failure:
        provider_models_live("sakana")
    assert SECRET not in str(failure.value) and SECONDARY not in str(failure.value)
