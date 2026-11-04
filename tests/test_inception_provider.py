"""Keyless Mercury wire tests; fixture provenance: docs/INCEPTION.md."""

from __future__ import annotations

import copy
import json
import runpy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.inception import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

ALIASES = ("inception", "inception-labs", "inceptionlabs", "INCEPTION_LABS")
FIXTURE = Path(__file__).parent / "fixtures/provider/inception_chat_completions_success.json"
PRIVATE = "synthetic-private-provider-prose"


def wire():
    return json.loads(FIXTURE.read_text())


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="mercury-wire", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="mercury-wire", version="fixture-v1"), active_player="player_1",
        observation={"board": [], "you_are": "player_1"}, legal_actions=[0, 1, 2],
        action_schema={"type": "integer"}, history=[], time_budget_ms=None,
        memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None)},
    )


def agent(**kwargs):
    return ModelProviderAgent("inception", "mercury-2.5", "INCEPTION_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("INCEPTION_API_KEY", "synthetic-mercury-key-never-persisted")


def install_wire(monkeypatch, body=None, status=200, content=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status, **({"content": content} if content is not None else
                       {"json": body if body is not None else wire()}),
            headers={"x-request-id": "req-mercury-wire", "Retry-After": "0"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_cli_preflight_registry_and_dispatch(monkeypatch, capsys, alias):
    calls = install_wire(monkeypatch)
    a = _provider_agent(f"{alias}:mercury-2.5")
    assert a.provider == "inception" and a.api_key_env == "INCEPTION_API_KEY"
    assert a.model == "mercury-2.5" and a.act(request()).action == 0
    direct = ModelProviderAgent(alias, "mercury-2.5", "INCEPTION_API_KEY")
    assert direct.act(request()).metadata["provider_receipt"]["provider"] == "inception"
    assert len(calls) == 2 and all(url == CHAT_COMPLETIONS_ENDPOINT for url, _ in calls)
    assert load_provider_registry().resolve(alias, "mercury-2.5").provider == "inception"
    assert main(["providers", "preflight", "--provider", alias, "--model", "mercury-2.5",
                 "--arena", "tic-tac-toe"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["adapter_available"] and report["ok"]
    assert len(calls) == 2  # Configuration preflight never invokes inference.


def test_core42_stays_separate_and_unknown_model_is_exact(monkeypatch):
    assert _provider_agent("core42:mercury-2") is None
    assert not provider_preflight("core42", "mercury-2", "tic-tac-toe")["ok"]
    assert load_provider_registry().resolve("core42", "mercury-2").provider == "core42"
    calls = install_wire(monkeypatch)
    a = _provider_agent("inception:unlisted:model-id")
    assert a.act(request()).action == 0
    assert calls[0][1]["json"]["model"] == "unlisted:model-id"
    assert a.last_receipt["model"] == "unlisted:model-id"
    assert a.last_receipt["locked_model_id"] == "mercury-2.5"


def test_registry_update_aliases_and_cli_requires_explicit_model():
    updater = runpy.run_path(str(Path(__file__).parents[1] / "scripts/update_provider_registry.py"))
    aliases = updater["PROVIDER_ALIASES"]
    assert aliases.get("inception", "inception") == "inception"
    assert aliases["inception-labs"] == aliases["inceptionlabs"] == "inception"
    with pytest.raises(ValueError, match="explicit nonblank model"):
        _provider_agent("inception")


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("model", ["", " ", "\t\n", None])
def test_model_id_is_required_across_entrypoints(monkeypatch, alias, model):
    calls = install_wire(monkeypatch)
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent(alias, model, "INCEPTION_API_KEY")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        provider_preflight(alias, model, "tic-tac-toe", live=True)
    if model is not None:
        with pytest.raises(ValueError, match="explicit nonblank model"):
            _provider_agent(f"{alias}:{model}")
    assert calls == []


@pytest.mark.parametrize("key", [None, "", "bad key\nvalue"])
def test_missing_or_invalid_key_never_submits(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("INCEPTION_API_KEY")
    else:
        monkeypatch.setenv("INCEPTION_API_KEY", key)
    calls = install_wire(monkeypatch)
    a = agent()
    with pytest.raises(ProviderCallError) as caught:
        a.act(request())
    assert caught.value.error_kind == "provider_auth_failed" and calls == []
    assert not a.last_receipt["usage"]


@pytest.mark.parametrize("control", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_foreign_thinking_budget_is_rejected_before_submission(monkeypatch, control):
    calls = install_wire(monkeypatch)
    a = agent(runtime_config=ProviderRuntimeConfig(**{control: 1024}))
    with pytest.raises(ProviderCallError, match="reasoning_effort"):
        a.act(request())
    assert calls == []


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("control", ["reasoning_budget_tokens", "gemini_thinking_budget"])
def test_preflight_rejects_explicit_foreign_budget_before_discovery(
    monkeypatch, alias, live, control,
):
    calls = install_wire(monkeypatch)
    gets = []
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k: gets.append(1))
    result = provider_preflight(alias, "mercury-2", "tic-tac-toe", live=live,
        runtime_config=ProviderRuntimeConfig(**{control: 0}))
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert "reasoning_effort" in result["error"]["message"]
    assert not result["checks"]["minimal_inference"] and calls == gets == []


def test_defaults_full_history_transport_identity_usage_and_privacy(monkeypatch):
    calls = install_wire(monkeypatch)
    r = replace(request(), history=[
        {"turn_id": i, "public_marker": f"history-{i}"} for i in range(100)
    ])
    a = agent()
    response = a.act(r)
    url, sent = calls[0]
    payload = sent["json"]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {"Authorization": "Bearer synthetic-mercury-key-never-persisted",
                               "Content-Type": "application/json"}
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["stream"] is False
    assert all(f"history-{i}" in payload["messages"][1]["content"] for i in range(100))
    assert sent["timeout"].read is None and not hasattr(sent["timeout"], "deadline")
    receipt = response.metadata["provider_receipt"]
    assert receipt["provider"] == "inception"
    assert receipt["locked_model_id"] == "mercury-2.5"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "inception_chat_completions"
    assert receipt["parser_version"] == "inception-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 20
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["attempt_index"] == 1 and receipt["attempt_kind"] == "primary"
    assert "history-" not in json.dumps(receipt)
    assert "synthetic-mercury-key" not in json.dumps(response.to_dict())


@pytest.mark.parametrize("arena_id", ["tic-tac-toe", "chess"])
@pytest.mark.parametrize("effort", [None, "instant", "low", "medium", "high"])
def test_only_explicit_controls_and_no_arena_reasoning(monkeypatch, arena_id, effort):
    calls = install_wire(monkeypatch)
    a = agent(temperature=0.75, max_output_tokens=9876,
              runtime_config=ProviderRuntimeConfig(reasoning_effort=effort))
    r = replace(request(), arena=ArenaIdentity(id=arena_id, version="1.0.0"))
    a.act(r)
    payload = calls[0][1]["json"]
    assert payload["max_completion_tokens"] == 9876 and payload["temperature"] == 0.75
    assert payload.get("reasoning_effort") == effort
    assert ("reasoning_effort" in payload) is (effort is not None)
    assert not {"provider", "reasoning", "thinking", "max_tokens"} & payload.keys()


@pytest.mark.parametrize("nested", [False, True])
def test_usage_includes_reasoning_and_cache_without_double_counting(monkeypatch, nested):
    body = wire()
    body["usage"] = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
    if nested:
        body["usage"].update(prompt_tokens_details={"cached_tokens": 5},
                              completion_tokens_details={"reasoning_tokens": 3})
    else:
        body["usage"].update(cached_input_tokens=5, reasoning_tokens=3)
    install_wire(monkeypatch, body)
    a = agent()
    a.act(request())
    usage = a.last_receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (12, 8, 20)
    assert usage["reasoning_tokens"] == 3 and usage["cache_read_input_tokens"] == 5
    assert usage["reasoning_included_in_output"] and not usage["usage_validation_errors"]


def test_missing_identity_usage_and_cost_are_not_invented(monkeypatch):
    body = wire()
    del body["usage"], body["model"]
    body["cost"] = 1  # Not an Inception documented cost field.
    install_wire(monkeypatch, body)
    a = agent()
    a.act(request())
    assert a.last_receipt["locked_model_id"] is None
    assert a.last_receipt["model_identity_source"] is None
    assert a.last_receipt["usage"] == {}
    assert a.last_receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("value", [True, -1, "12", 1.5])
def test_invalid_usage_does_not_become_complete_accounting(monkeypatch, value):
    body = wire()
    body["usage"]["prompt_tokens"] = value
    body["usage"]["cost"] = 123
    install_wire(monkeypatch, body)
    a = agent()
    a.act(request())
    assert a.last_receipt["usage"]["input_tokens"] is None
    assert a.last_receipt["usage"]["usage_validation_errors"]
    assert a.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("status,kind", [(400, "provider_request_rejected"),
    (401, "provider_auth_failed"), (402, "provider_request_rejected"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (502, "provider_unavailable"), (503, "provider_unavailable")])
def test_http_errors_sanitized_with_zero_default_retries(monkeypatch, status, kind):
    calls = install_wire(monkeypatch, {"error": {"type": "rate_limit_error",
        "code": "rate_limit_reached", "param": None, "message": PRIVATE}}, status)
    a = agent()
    with pytest.raises(ProviderCallError) as caught:
        a.act(request())
    assert caught.value.error_kind == kind
    assert a.last_receipt["status_code"] == status
    assert len(calls) == len(a.attempt_receipts) == 1
    assert not a.last_receipt["usage"] and a.last_receipt["locked_model_id"] is None
    assert PRIVATE not in str(caught.value) + json.dumps(a.last_receipt)


@pytest.mark.parametrize("reason,kind", [("length", "provider_output_truncated"),
    ("content_filter", "provider_refused"), ("tool_calls", "provider_request_rejected"),
    ("unexpected-private-reason", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch")])
def test_finish_fields_reject_legal_looking_partial_output(monkeypatch, reason, kind):
    body = wire()
    body["choices"][0]["finish_reason"] = reason
    calls = install_wire(monkeypatch, body)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as caught:
        a.act(request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert a.last_receipt["usage"]["total_tokens"] == 20
    assert "unexpected-private-reason" not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("mutation", ["refusal", "error", "no_choices", "tool_calls",
    "reasoning_only", "wrong_role", "wrong_index", "array_content"])
def test_semantic_and_shape_failures_preserve_usage(monkeypatch, mutation):
    body = wire()
    message = body["choices"][0]["message"]
    kind = "provider_response_schema_mismatch"
    if mutation == "refusal":
        message["refusal"] = PRIVATE
        kind = "provider_refused"
    elif mutation == "error":
        body["error"] = {"type": "authentication_error", "message": PRIVATE}
        kind = "provider_auth_failed"
    elif mutation == "no_choices":
        body["choices"] = []
    elif mutation == "tool_calls":
        message["tool_calls"] = [{"function": {"arguments": '{"action":0}'}}]
    elif mutation == "reasoning_only":
        message.update(content=None, reasoning_content='{"action":0}')
    elif mutation == "wrong_role":
        message["role"] = "user"
    elif mutation == "wrong_index":
        body["choices"][0]["index"] = True
    else:
        message["content"] = [{"type": "text", "text": '{"action":0}'}]
    calls = install_wire(monkeypatch, body)
    a = agent()
    with pytest.raises(ProviderCallError) as caught:
        a.act(request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert a.last_receipt["usage"]["total_tokens"] == 20
    assert PRIVATE not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("content", [b"not-json", b"[]", b'{"choices":[],"choices":[]}'])
def test_malformed_json_has_receipt(monkeypatch, content):
    install_wire(monkeypatch, content=content)
    a = agent()
    with pytest.raises(ProviderCallError, match="provider response"):
        a.act(request())
    assert a.last_receipt["outcome"] == "provider_response_schema_mismatch"
    assert a.last_receipt["request_id"] == "req-mercury-wire"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_ambiguous_transport_never_retries(monkeypatch, failure):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise failure(PRIVATE)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((TimeoutError, ProviderCallError)):
        a.act(request())
    assert calls == [1] and len(a.attempt_receipts) == 1
    assert PRIVATE not in json.dumps(a.last_receipt)


@pytest.mark.parametrize("work", [{}, {"id": "observed-generation"},
    {"usage": {"prompt_tokens": 12}}, {"usage": {"prompt_tokens": PRIVATE}}])
def test_explicit_429_retry_requires_definitive_rejection(monkeypatch, work):
    body = {"error": {"type": "rate_limit_error", "code": "rate_limit_reached",
                      "message": PRIVATE, "param": None}, **copy.deepcopy(work)}
    calls = install_wire(monkeypatch, body, 429)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        a.act(request())
    expected = 1 if work else 2
    assert len(calls) == len(a.attempt_receipts) == expected
    assert [row["attempt_index"] for row in a.attempt_receipts] == list(range(1, expected + 1))
    assert PRIVATE not in json.dumps(a.attempt_receipts)


def test_http200_native_rate_error_retries_only_with_explicit_permission(monkeypatch):
    calls = install_wire(monkeypatch, {"error": {"code": "rate_limit_reached",
                                               "message": PRIVATE}})
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as caught:
        a.act(request())
    assert caught.value.error_kind == "provider_rate_limited"
    assert len(calls) == len(a.attempt_receipts) == 2


@pytest.mark.parametrize("alias", ALIASES)
def test_discovery_and_mock_live_preflight(monkeypatch, alias):
    calls = install_wire(monkeypatch)
    gets = []

    def get(url, **kwargs):
        gets.append((url, kwargs))
        return httpx.Response(200, json={"data": [{"id": "mercury-2.5"}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == ["mercury-2.5"]
    result = provider_preflight(alias, "mercury-2.5", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert len(calls) == 1 and len(gets) == 2
    assert all(url == MODELS_ENDPOINT for url, _ in gets)
    assert gets[0][1]["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.parametrize("status,body", [(401, {"error": {"message": PRIVATE}}),
    (429, {"error": {"message": PRIVATE}}), (503, {"error": {"message": PRIVATE}}),
    (200, {"data": [{"id": None}]}), (200, [])])
def test_discovery_failure_is_sanitized(monkeypatch, status, body):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: httpx.Response(status, json=body))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("inception-labs")
    assert PRIVATE not in str(caught.value)


def test_refusal_artifact_never_applies_action_or_leaks_private_body(tmp_path, monkeypatch):
    body = wire()
    body["choices"][0]["message"]["refusal"] = PRIVATE
    body["reasoning_summary"] = {"summary": PRIVATE}
    body["warning"] = PRIVATE
    body["usage"]["prompt"] = PRIVATE
    install_wire(monkeypatch, body)
    result = Runner().run(RunConfig("tic-tac-toe", output_dir=tmp_path,
        on_agent_error="forfeit", agent_1=agent()))
    rows = [json.loads(line) for line in (result.expanded_path /
        "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "provider_refused"
    assert not rows[0]["action_applied"] and not result.score.match_valid_for_scoring
    assert result.score.aggregate_usage["totalCostUsd"] is None
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert PRIVATE.encode() not in data and b"synthetic-mercury-key" not in data


PRIMARY = "opaquePrimaryValue8675309"
SECONDARY = "opaqueSecondaryValue2468135"


@pytest.mark.parametrize("mode", ["success", "http_error", "malformed", "partial_timeout",
    "partial_protocol", "refusal", "truncation", "http200_error"])
@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
def test_credential_echoes_never_enter_receipts(monkeypatch, mode, credential):
    from eslams.protocol import ProtocolError

    monkeypatch.setenv("INCEPTION_API_KEY", PRIMARY)
    monkeypatch.setenv("SECONDARY_PROVIDER_API_KEY", SECONDARY)
    calls = []

    def post(url, **kwargs):
        calls.append(1)
        headers = {"x-request-id": f"req-{credential}",
                   "cf-aig-request-id": f"gateway-{credential}"}
        body = wire()
        body.update(id=f"generation-{credential}", model=f"model-{credential}",
                    warning=credential, reasoning_summary={"summary": credential})
        if mode in {"http_error", "http200_error"}:
            body["error"] = {"type": "rate_limit_error", "code": "rate_limit_reached",
                             "message": credential}
        elif mode == "refusal":
            body["choices"][0]["message"]["refusal"] = credential
        elif mode == "truncation":
            body["choices"][0]["finish_reason"] = "length"
        elif mode in {"partial_timeout", "partial_protocol"}:
            exc = (httpx.ReadTimeout(credential) if mode == "partial_timeout"
                   else ProtocolError("incomplete response"))
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                429, tuple(headers.items()),
            )
            raise exc
        return httpx.Response(429 if mode == "http_error" else 200,
            **({"content": credential.encode()} if mode == "malformed" else {"json": body}),
            headers=headers, request=httpx.Request("POST", url))

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, retry_backoff_ms=0))
    if mode == "success":
        assert a.act(request()).action == 0
    else:
        with pytest.raises(ProviderCallError) as caught:
            a.act(request())
        assert credential not in str(caught.value) + json.dumps(caught.value.receipt)
    assert calls == [1]  # Observed work remains unsafe to replay after redaction.
    receipt = a.last_receipt
    assert receipt["request_id"] is None and receipt["gateway_request_id"] is None
    assert receipt.get("provider_response_id") is None
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert PRIMARY not in json.dumps(a.attempt_receipts)
    assert SECONDARY not in json.dumps(a.attempt_receipts)
    if mode not in {"partial_timeout", "partial_protocol", "malformed"}:
        assert receipt["usage"]["total_tokens"] == 20


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY, 'opaque"quoted\\credential'])
@pytest.mark.parametrize("encoded", [False, True])
def test_credential_in_assistant_text_is_rejected_without_action_or_artifact_leak(
    tmp_path, monkeypatch, credential, encoded,
):
    monkeypatch.setenv("INCEPTION_API_KEY", PRIMARY)
    monkeypatch.setenv("SECONDARY_GATEWAY_TOKEN", credential)
    body = wire()
    body["choices"][0]["message"]["content"] = json.dumps(
        {"action": 0, "public_explanation": credential},
    )
    if encoded:
        body["choices"][0]["message"]["content"] = (
            body["choices"][0]["message"]["content"].replace("opaque", "\\u006fpaque")
        )
    calls = install_wire(monkeypatch, body)
    result = Runner().run(RunConfig("tic-tac-toe", output_dir=tmp_path,
        on_agent_error="forfeit", agent_1=agent()))
    assert len(calls) == 1 and not result.score.match_valid_for_scoring
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert PRIMARY.encode() not in data and SECONDARY.encode() not in data
            assert credential.encode() not in data


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
def test_discovery_does_not_return_echoed_credentials(monkeypatch, credential):
    monkeypatch.setenv("INCEPTION_API_KEY", PRIMARY)
    monkeypatch.setenv("ANOTHER_PROVIDER_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
        httpx.Response(200, json={"data": [{"id": f"model-{credential}"}]}))
    with pytest.raises(ProviderCallError) as caught:
        provider_models_live("inception")
    assert credential not in str(caught.value)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
def test_protocol_failure_message_does_not_echo_credentials(monkeypatch, credential):
    from eslams.protocol import ProtocolError

    monkeypatch.setenv("INCEPTION_API_KEY", PRIMARY)
    monkeypatch.setenv("SECONDARY_PROVIDER_API_KEY", SECONDARY)

    def post(*args, **kwargs):
        raise ProtocolError(f"provider detail {credential}")

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    with pytest.raises(ProviderCallError) as caught:
        agent().act(request())
    assert credential not in str(caught.value) + json.dumps(caught.value.receipt)


@pytest.mark.parametrize("credential", [PRIMARY, SECONDARY])
def test_private_error_message_does_not_disable_definitive_429_retry(monkeypatch, credential):
    monkeypatch.setenv("INCEPTION_API_KEY", PRIMARY)
    monkeypatch.setenv("SECONDARY_PROVIDER_API_KEY", SECONDARY)
    calls = install_wire(monkeypatch, {"error": {"type": "rate_limit_error",
        "code": "rate_limit_reached", "message": credential}}, 429)
    a = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        a.act(request())
    assert len(calls) == len(a.attempt_receipts) == 2
    assert credential not in json.dumps(a.attempt_receipts)


def test_development_secret_flag_is_not_treated_as_a_credential(monkeypatch):
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET", "1")
    body = wire()
    body["choices"][0]["message"]["content"] = '{"action": 1}'
    install_wire(monkeypatch, body)
    assert agent().act(request()).action == 1
