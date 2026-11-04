"""Keyless raw-wire tests. Provenance: docs/SHANGHAI_AI_LAB.md.

Success uses the documented non-streaming field paths; values are synthetic.
Fault payloads deliberately inject unsupported/malformed fields, never SDK output.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.contracts.usage import aggregate_provider_receipts
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers.shanghai_ai_lab import CHAT_COMPLETIONS_ENDPOINT

SECRET = "atr_plain_credential_with_no_generic_secret_pattern"
SECONDARY = "plain_secondary_credential_without_a_label"


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "shanghai_ai_lab_atria_success.json").read_text())


def agent(**kwargs):
    return ModelProviderAgent(provider="shanghai-ai-lab", model="Atria-Dawn",
                              api_key_env="ATRIA_API_KEY", **kwargs)


def install(monkeypatch, response):
    calls = []
    monkeypatch.setenv("ATRIA_API_KEY", SECRET)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_raw_wire_dispatch_full_history_and_no_implicit_controls(monkeypatch):
    calls = install(monkeypatch, httpx.Response(200, json=wire()))
    request = replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                      metadata={"model_execution_policy": model_execution_policy(None)},
                      history=[{"turn": i, "marker": f"history-{i}"} for i in range(40)])
    target = _provider_agent("shanghai-ai-lab:Atria-Dawn")
    result = target.act(request)
    assert result.action == 1
    url, kwargs = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
    payload = kwargs["json"]
    assert set(payload) == {"model", "messages"}
    assert payload["model"] == "Atria-Dawn"
    assert len(payload["messages"]) == 1 and payload["messages"][0]["role"] == "user"
    for i in range(40):
        assert f'"history-{i}"' in payload["messages"][0]["content"]
    assert kwargs["timeout"].read is None
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "shanghai-ai-lab"
    assert receipt["model"] == "Atria-Dawn"
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["endpoint_kind"] == "shanghai_ai_lab_atria_chat_completions"
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["output_tokens"] == 4
    assert receipt["usage"]["total_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["usage_complete"] is False
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    summary, cost = aggregate_provider_receipts([receipt])
    assert summary["usageComplete"] is False and summary["totalTokens"] is None
    assert cost["costComplete"] is False
    assert SECRET not in json.dumps(result.to_dict())
    assert len(calls) == 1


@pytest.mark.parametrize("model", [None, "", " ", "intern-s2", "Atria-Dawn-Preview",
                                   "atria-dawn", " Atria-Dawn"])
def test_exact_explicit_model_required_everywhere(model):
    with pytest.raises(ValueError):
        ModelProviderAgent(provider="shanghai-ai-lab", model=model, api_key_env="ATRIA_API_KEY")
    with pytest.raises(ValueError):
        provider_preflight("shanghai-ai-lab", model, "tic-tac-toe")


@pytest.mark.parametrize("value", ["shanghai-ai-lab", "shanghai-ai-lab:", "shanghai-ai-lab: "])
def test_cli_does_not_supply_a_default_model(value):
    with pytest.raises(ValueError, match="explicit nonblank"):
        _provider_agent(value)


@pytest.mark.parametrize("config", [
    {"reasoning": "enabled"}, {"reasoning": "disabled"}, {"reasoning_effort": "high"},
    {"reasoning_budget_tokens": 1000}, {"gemini_thinking_budget": -1},
    {"history_window_turns": 1}, {"gateway_base_url": "https://router.example"},
    {"gateway_mode": "generic_base_url"}, {"openrouter_provider_order": ("test",)},
])
def test_unsupported_settings_fail_before_transport(config, monkeypatch):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    runtime = ProviderRuntimeConfig(**config)
    with pytest.raises(ValueError):
        agent(runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("shanghai-ai-lab", "Atria-Dawn", "tic-tac-toe",
                           runtime_config=runtime)


@pytest.mark.parametrize("maximum", [0, True, 65537])
def test_provider_documented_output_limit_is_validated(maximum):
    with pytest.raises(ValueError):
        agent(max_output_tokens=maximum)


def test_explicit_output_limit_and_deadline_are_forwarded(monkeypatch):
    calls = install(monkeypatch, httpx.Response(200, json=wire()))
    target = agent(max_output_tokens=65536,
                   runtime_config=ProviderRuntimeConfig(timeout_ms=1500))
    target.act(_request())
    assert calls[0][1]["json"]["max_completion_tokens"] == 65536
    assert 0 < calls[0][1]["timeout"].read <= 1.5
    with pytest.raises(ValueError):
        agent(temperature=0.5)


def test_configuration_and_mocked_live_preflight_cli(monkeypatch, capsys):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("undocumented Models API"))
    calls = install(monkeypatch, httpx.Response(200, json=wire()))
    assert provider_models_live("shanghai-ai-lab") is None
    assert main(["providers", "preflight", "--provider", "shanghai-ai-lab", "--model",
                 "Atria-Dawn"]) == 0
    assert json.loads(capsys.readouterr().out)["readiness"]["inference"] == "not_attempted"
    assert calls == []
    assert main(["providers", "preflight", "--provider", "shanghai-ai-lab", "--model",
                 "Atria-Dawn", "--live"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["response_parsing"] is True
    assert payload["readiness"]["usage_complete"] is False
    assert payload["checks"]["account_model_visible"] is None
    assert SECRET not in json.dumps(payload)
    assert len(calls) == 1


@pytest.mark.parametrize(("status", "kind"), [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_error_matrix_is_redacted_and_never_replayed(status, kind, monkeypatch):
    response = httpx.Response(status, json={"id": SECRET, "error": {
        "type": "rate_limit_exceeded", "message": SECRET,
    }}, headers={"x-request-id": SECRET, "x-gateway-request-id": f"prefix-{SECRET}",
                "Retry-After": "42"})
    calls = install(monkeypatch, response)
    target = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.error_kind == kind
    assert caught.value.status_code == status
    assert target.last_receipt["outcome"] == kind
    assert SECRET not in str(caught.value) + json.dumps(caught.value.receipt)
    assert SECRET not in json.dumps(target.attempt_receipts)
    assert len(calls) == 1


@pytest.mark.parametrize("body", ["invalid", "[]", '{"choices":[],"choices":[]}',
                                  '{"choices": [', '{"usage":NaN}'])
def test_malformed_body_with_echoed_headers(monkeypatch, body):
    install(monkeypatch, httpx.Response(200, text=body + " ",
                                       headers={"x-request-id": SECRET}))
    target = agent()
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert SECRET not in json.dumps(target.attempt_receipts) + str(caught.value)


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ReadError])
def test_transport_and_partial_observations_do_not_echo_credentials(
    monkeypatch, observed, error_type,
):
    exc = error_type(SECRET)
    if observed:
        exc._eslams_response_observation = ResponseObservation(
            200, (("x-request-id", SECRET), ("x-gateway-request-id", SECRET)),
        )
    calls = install(monkeypatch, exc)
    target = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        target.act(_request())
    assert SECRET not in str(caught.value) + json.dumps(target.attempt_receipts)
    assert len(calls) == 1


@pytest.mark.parametrize("position", ["model", "id", "text", "explanation", "action", "key"])
def test_json_escaped_plain_credential_echoes_cannot_reach_action_fields(monkeypatch, position):
    data = wire()
    if position in {"model", "id"}:
        data[position] = SECRET
    elif position == "key":
        data[SECRET] = "unused"
    else:
        text = (SECRET if position == "text" else
                json.dumps({"action": SECRET if position == "action" else 1,
                            "public_explanation": SECRET if position == "explanation" else ""}))
        data["choices"][0]["message"]["content"] = text
    encoded = json.dumps(data).replace(SECRET, "".join(f"\\u{ord(c):04x}" for c in SECRET))
    install(monkeypatch, httpx.Response(200, text=encoded))
    target = agent()
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert SECRET not in json.dumps(target.attempt_receipts) + str(caught.value)


@pytest.mark.parametrize("reason", [None, "length", "content_filter", "tool_calls", {}, "other"])
def test_legal_looking_partial_output_is_not_accepted(monkeypatch, reason):
    data = wire()
    data["choices"][0]["finish_reason"] = reason
    install(monkeypatch, httpx.Response(200, json=data))
    target = agent()
    with pytest.raises(ProviderCallError):
        target.act(_request())
    assert target.last_receipt["outcome"] != "ok"
    assert target.last_receipt["usage"]["input_tokens"] == 12


@pytest.mark.parametrize("mutation", ["model", "tool", "search", "choices", "content", "error"])
def test_mismatched_identity_tools_search_and_wrong_envelopes_fail(monkeypatch, mutation):
    data = wire()
    if mutation == "model":
        data["model"] = "Atria-Dawn-Preview"
    elif mutation == "tool":
        data["choices"][0]["message"]["tool_calls"] = [{"function": {"name": "search"}}]
    elif mutation == "search":
        data["metadata"] = {"search_used": True}
    elif mutation == "choices":
        data["choices"] = []
    elif mutation == "content":
        data["choices"][0]["message"]["content"] = [{"type": "output_text", "text": "hi"}]
    else:
        data["error"] = {"message": "private diagnostic"}
    install(monkeypatch, httpx.Response(200, json=data))
    with pytest.raises(ProviderCallError):
        agent().act(_request())


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 10},
                                   {"prompt_tokens": True, "completion_tokens": 4}])
def test_missing_partial_and_malformed_accounting_stays_incomplete(monkeypatch, usage):
    data = wire()
    data["usage"] = usage
    data["model"] = "Atria-Dawn"
    install(monkeypatch, httpx.Response(200, json=data))
    result = agent().act(_request())
    receipt = result.metadata["provider_receipt"]
    assert receipt["locked_model_id"] == "Atria-Dawn"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["usage_complete"] is False
    assert receipt["usage"].get("total_tokens") is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_header_echo_on_success_does_not_invent_request_identity(monkeypatch):
    install(monkeypatch, httpx.Response(200, json=wire(), headers={"x-request-id": SECRET}))
    result = agent().act(_request())
    assert result.metadata["provider_receipt"]["request_id"] is None
    assert SECRET not in json.dumps(result.to_dict())


def test_even_a_clean_rate_rejection_is_not_replayed_without_a_verified_contract(monkeypatch):
    calls = install(monkeypatch, httpx.Response(429, json={"error": {
        "type": "rate_limit_exceeded", "message": "wait",
    }}, headers={"Retry-After": "42"}))
    target = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.retry_permitted is False
    assert caught.value.retry_after_seconds == 42
    assert target.last_receipt["retry_after_ms"] == 42000
    assert len(calls) == 1


@pytest.mark.parametrize("status", [202, 302])
def test_pending_and_redirect_are_not_success_or_fallback(monkeypatch, status):
    calls = install(monkeypatch, httpx.Response(status, json=wire(),
                                               headers={"Location": "https://elsewhere.example"}))
    with pytest.raises(ProviderCallError):
        agent().act(_request())
    assert len(calls) == 1


def test_bare_timeout_diagnostic_cannot_echo_a_credential(monkeypatch):
    install(monkeypatch, TimeoutError(SECRET))
    target = agent()
    with pytest.raises(TimeoutError) as caught:
        target.act(_request())
    assert SECRET not in str(caught.value) + json.dumps(target.attempt_receipts)


def test_error_usage_is_quarantined_without_a_fabricated_total(monkeypatch):
    install(monkeypatch, httpx.Response(503, json={
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        "error": {"message": "private error"},
    }))
    target = agent()
    with pytest.raises(ProviderCallError):
        target.act(_request())
    receipt = target.last_receipt
    assert receipt["usage"]["input_tokens"] == 12
    assert receipt["usage"]["total_tokens"] is None
    assert receipt["usage_complete"] is False
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"


def test_undocumented_accounting_extensions_do_not_invent_complete_usage(monkeypatch):
    data = wire()
    data["usage"].update(total_tokens=16, reasoning_tokens=0,
                         reasoning_included_in_output=True, cost=0,
                         prompt_tokens_details={"cached_tokens": 10})
    install(monkeypatch, httpx.Response(200, json=data))
    receipt = agent().act(_request()).metadata["provider_receipt"]
    assert receipt["usage"]["total_tokens"] is None
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["cached_input_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_cli_run_missing_model_fails_without_fallback(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    assert main(["run", "--agent", "shanghai-ai-lab", "--output-dir", str(tmp_path)]) == 1
    assert "explicit nonblank model ID" in capsys.readouterr().err


@pytest.mark.parametrize("environment", ["ATRIA_API_KEY_SECONDARY", "OPENAI_API_KEY"])
@pytest.mark.parametrize("position", ["id", "model", "action", "explanation", "key"])
def test_secondary_credential_echoes_fail_before_action_publication(
    monkeypatch, environment, position,
):
    monkeypatch.setenv(environment, SECONDARY)
    data = wire()
    if position in {"id", "model"}:
        data[position] = SECONDARY
    elif position == "key":
        data[SECONDARY] = "unused"
    else:
        data["choices"][0]["message"]["content"] = json.dumps({
            "action": SECONDARY if position == "action" else 1,
            "public_explanation": SECONDARY if position == "explanation" else "legal",
        })
    encoded = json.dumps(data).replace(
        SECONDARY, "".join(f"\\u{ord(char):04x}" for char in SECONDARY),
    )
    calls = install(monkeypatch, httpx.Response(200, text=encoded))
    target = agent()
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    public = (str(caught.value) + json.dumps(caught.value.receipt)
              + json.dumps(target.attempt_receipts))
    assert SECRET not in public and SECONDARY not in public
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1


@pytest.mark.parametrize("body_kind", ["success", "error", "malformed", "partial"])
@pytest.mark.parametrize("swap", [False, True])
def test_both_credentials_are_scrubbed_from_all_observed_receipt_ids(monkeypatch, body_kind, swap):
    monkeypatch.setenv("ATRIA_API_KEY_SECONDARY", SECONDARY)
    first, second = (SECRET, SECONDARY) if swap else (SECONDARY, SECRET)
    headers = {"x-request-id": f"request-{first}", "x-gateway-request-id": f"gateway-{second}"}
    if body_kind == "partial":
        response = httpx.ReadError(SECONDARY)
        response._eslams_response_observation = ResponseObservation(200, tuple(headers.items()))
    elif body_kind == "malformed":
        response = httpx.Response(200, text='{"id": "' + SECONDARY, headers=headers)
    elif body_kind == "error":
        response = httpx.Response(503, json={"id": SECONDARY, "error": {
            "message": f"private {SECRET} {SECONDARY}",
        }}, headers=headers)
    else:
        response = httpx.Response(200, json=wire(), headers=headers)
    calls = install(monkeypatch, response)
    target = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    if body_kind == "success":
        result = target.act(_request())
        public = json.dumps(result.to_dict())
    else:
        with pytest.raises(ProviderCallError) as caught:
            target.act(_request())
        public = str(caught.value) + json.dumps(caught.value.receipt)
    public += json.dumps(target.attempt_receipts)
    assert SECRET not in public and SECONDARY not in public
    assert target.last_receipt["request_id"] is None
    assert target.last_receipt["gateway_request_id"] is None
    assert target.last_receipt.get("provider_response_id") is None
    assert len(calls) == 1


def test_custom_active_key_also_protects_default_key_and_snapshots_before_transport(monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", SECONDARY)
    monkeypatch.setenv("CUSTOM_ATRIA_AUTH", SECRET)

    def post(*args, **kwargs):
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        monkeypatch.delenv("ATRIA_API_KEY")
        return httpx.Response(200, json=wire(), headers={"x-request-id": SECONDARY})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    target = ModelProviderAgent(provider="shanghai-ai-lab", model="Atria-Dawn",
                                api_key_env="CUSTOM_ATRIA_AUTH")
    result = target.act(_request())
    assert result.metadata["provider_receipt"]["request_id"] is None
    assert SECRET not in json.dumps(result.to_dict())
    assert SECONDARY not in json.dumps(result.to_dict())


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("provider", ["shanghai-ai-lab", "shanghai_ai_lab", " Shanghai_AI_Lab "])
@pytest.mark.parametrize("model", [None, "", " \t"])
def test_normalized_preflight_spelling_cannot_bypass_model_validation(
    monkeypatch, live, provider, model,
):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    with pytest.raises(ValueError, match="explicit nonblank"):
        provider_preflight(provider, model, "tic-tac-toe", live=live)


@pytest.mark.parametrize("setting", ["reasoning_budget_tokens", "gemini_thinking_budget"])
@pytest.mark.parametrize("value", [0, 1000])
def test_explicit_budgets_fail_in_normalized_preflight_and_at_transport_boundary(
    monkeypatch, setting, value,
):
    monkeypatch.setenv("ATRIA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    runtime = ProviderRuntimeConfig(**{setting: value})
    with pytest.raises(ValueError, match="reasoning controls are not verified"):
        provider_preflight("shanghai_ai_lab", "Atria-Dawn", "tic-tac-toe",
                           runtime_config=runtime)
    target = agent()
    target.runtime_config = runtime
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.error_kind == "provider_request_rejected"


@pytest.mark.parametrize("mode", ["success", "error"])
def test_secondary_echoes_do_not_enter_live_preflight_or_discovery(monkeypatch, mode):
    monkeypatch.setenv("ATRIA_API_KEY_SECONDARY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("undocumented discovery"))
    assert provider_models_live("shanghai-ai-lab") is None
    response = (httpx.Response(200, json=wire(), headers={"x-request-id": SECONDARY})
                if mode == "success" else httpx.Response(503, json={
                    "id": SECONDARY, "error": {"message": f"private {SECONDARY} {SECRET}"},
                }, headers={"x-request-id": SECONDARY}))
    calls = install(monkeypatch, response)
    result = provider_preflight("shanghai-ai-lab", "Atria-Dawn", "tic-tac-toe", live=True)
    assert SECRET not in json.dumps(result) and SECONDARY not in json.dumps(result)
    assert result["checks"]["account_model_visible"] is None
    assert result["ok"] is (mode == "success")
    assert len(calls) == 1


@pytest.mark.parametrize("model", [None, "", " \t"])
def test_model_revalidated_at_transport_boundary(monkeypatch, model):
    monkeypatch.setenv("ATRIA_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    target = agent()
    target.model = model
    with pytest.raises(ProviderCallError) as caught:
        target.act(_request())
    assert caught.value.error_kind == "provider_request_rejected"
