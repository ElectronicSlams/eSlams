from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import ResponseObservation
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.huawei import API_KEY_ENV, CHAT_COMPLETIONS_ENDPOINT, PANGU_MODELS

SECRET = "fixture-8e9a29c4-bc9b-43fb-a87f-f48f689e1738"
MODEL = "openpangu-2.0-flash"
FIXTURE = Path(__file__).parent / "fixtures/provider/huawei_maas_success.json"


def body():
    return json.loads(FIXTURE.read_text())


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_huawei", episode_id="episode_001",
        turn_id=20, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="huawei-fixture", version="fixture"), active_player="player_1",
        observation={"board": []}, legal_actions=[0, 1, 2], action_schema={"type": "integer"},
        history=[{"turn": turn, "action": 0} for turn in range(20)], time_budget_ms=None,
        memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None)},
    )


def agent(**kwargs):
    return ModelProviderAgent(provider="huawei", model=MODEL, api_key_env=API_KEY_ENV, **kwargs)


def wire(monkeypatch, payload=None, status=200, headers=None):
    calls = []
    monkeypatch.setenv(API_KEY_ENV, SECRET)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=body() if payload is None else payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("model", PANGU_MODELS)
def test_dispatch_and_wire_preserve_identity_history_and_native_defaults(monkeypatch, model):
    payload = body()
    payload["model"] = model
    calls = wire(monkeypatch, payload)
    selected = _provider_agent(f"huawei:{model}")
    result = selected.act(request())
    assert result.action == 1
    url, args = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert args["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    sent = args["json"]
    assert set(sent) == {"model", "stream", "messages"}
    assert sent["model"] == model
    assert sent["stream"] is False
    sent_history = json.loads(sent["messages"][1]["content"].splitlines()[-1])["history"]
    assert sent_history == request().history
    assert args["timeout"].read is None
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "huawei"
    assert receipt["model"] == receipt["locked_model_id"] == model
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "huawei_maas_chat_completions"
    assert receipt["parser_version"] == "huawei-maas-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 24
    assert receipt["usage"]["reasoning_tokens"] == 1
    assert receipt["usage"]["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "Private fixture reasoning" not in json.dumps(result.to_dict())
    assert len(calls) == 1


@pytest.mark.parametrize("mode,thinking", [("enabled", True), ("disabled", False)])
def test_explicit_controls(monkeypatch, mode, thinking):
    calls = wire(monkeypatch)
    agent(runtime_config=ProviderRuntimeConfig(reasoning=mode), max_output_tokens=100,
          temperature=0.3).act(request())
    sent = calls[0][1]["json"]
    assert sent["chat_template_kwargs"] == {"thinking": thinking}
    assert sent["max_completion_tokens"] == 100
    assert sent["temperature"] == 0.3
    assert "max_tokens" not in sent


@pytest.mark.parametrize("model", [None, "", " ", "\t", " model "])
def test_missing_model_is_rejected_everywhere(model):
    with pytest.raises(ValueError, match="model ID"):
        ModelProviderAgent(provider="huawei", model=model, api_key_env=API_KEY_ENV)
    with pytest.raises(ValueError, match="model ID"):
        provider_preflight("huawei", model, "tic-tac-toe")


@pytest.mark.parametrize("value", ["huawei", "huawei:", "huawei: "])
def test_cli_does_not_choose_default_model(value):
    with pytest.raises(ValueError, match="model ID"):
        _provider_agent(value)


@pytest.mark.parametrize("runtime", [
    ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=10),
    ProviderRuntimeConfig(gemini_thinking_budget=10),
    ProviderRuntimeConfig(history_window_turns=1),
    ProviderRuntimeConfig(gateway_base_url="https://example.invalid"),
    ProviderRuntimeConfig(openrouter_provider_order=("other",)),
])
def test_unsupported_configuration_is_rejected_before_transport(runtime):
    with pytest.raises(ValueError):
        agent(runtime_config=runtime)
    with pytest.raises(ValueError):
        provider_preflight("huawei", MODEL, "tic-tac-toe", runtime_config=runtime)


def test_unknown_explicit_id_is_forwarded_without_alias_or_assumed_thinking(monkeypatch):
    payload = body()
    payload["model"] = "operator-exact-model"
    calls = wire(monkeypatch, payload)
    selected = ModelProviderAgent(
        provider="huawei", model=payload["model"], api_key_env=API_KEY_ENV,
    )
    selected.act(request())
    assert calls[0][1]["json"]["model"] == "operator-exact-model"
    with pytest.raises(ValueError, match="verified only"):
        ModelProviderAgent(provider="huawei", model=payload["model"], api_key_env=API_KEY_ENV,
                           runtime_config=ProviderRuntimeConfig(reasoning="enabled"))


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_errors_never_echo_credentials_or_retry(monkeypatch, status, kind):
    payload = {"error_code": "ModelArts.81001", "error_msg": SECRET, "id": SECRET,
               "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
    calls = wire(monkeypatch, payload, status, {"x-request-id": f"prefix-{SECRET}"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as raised:
        selected.act(request())
    assert raised.value.error_kind == kind
    assert SECRET not in json.dumps(raised.value.receipt)
    assert SECRET not in json.dumps(selected.attempt_receipts)
    assert SECRET not in str(raised.value)
    assert selected.last_receipt["status_code"] == status
    assert len(calls) == 1


def test_generic_rate_envelope_does_not_establish_huawei_replay_permission(monkeypatch):
    calls = wire(monkeypatch, {"error": {"code": 429, "type": "rate_limit_error"}}, 429)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as raised:
        selected.act(request())
    assert raised.value.error_kind == "provider_rate_limited"
    assert not raised.value.retry_permitted
    assert len(calls) == 1


@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "x-gateway-request-id"])
def test_credential_echoes_in_success_identifiers_are_discarded(monkeypatch, field):
    payload = body()
    headers = {}
    if field.startswith("x-"):
        headers[field] = f"prefix-{SECRET}"
    else:
        payload[field] = f"prefix-{SECRET}"
    wire(monkeypatch, payload, headers=headers)
    selected = agent()
    if field == "model":
        with pytest.raises(ProviderCallError):
            selected.act(request())
    else:
        result = selected.act(request())
        assert SECRET not in json.dumps(result.to_dict())
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("malformed", [b"not-json", b'{"id":', b'{"choices":[],"choices":[]}'])
def test_malformed_body_receipts_scrub_header_echo(monkeypatch, malformed):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: httpx.Response(
        200, content=malformed, headers={"x-request-id": SECRET},
    ))
    selected = agent()
    with pytest.raises(ProviderCallError, match="valid JSON") as raised:
        selected.act(request())
    assert SECRET not in json.dumps(raised.value.receipt)
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("exception", [httpx.ReadError, httpx.ReadTimeout])
def test_partial_transport_retains_status_without_echo_or_replay(monkeypatch, exception):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    def fail(*a, **k):
        calls.append(1)
        exc = exception("private transport detail")
        exc._eslams_response_observation = ResponseObservation(
            200, (("x-request-id", SECRET), ("x-gateway-request-id", f"prefix-{SECRET}")),
        )
        raise exc

    monkeypatch.setattr("eslams.agents.bounded_post", fail)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as raised:
        selected.act(request())
    assert len(calls) == 1
    assert SECRET not in json.dumps(raised.value.receipt)
    assert SECRET not in json.dumps(selected.last_receipt)
    assert selected.last_receipt["status_code"] == 200
    assert selected.last_receipt["usage"] == {}


@pytest.mark.parametrize("case", ["content", "explanation", "reasoning", "escaped", "fenced"])
def test_credential_content_never_enters_action_fields(monkeypatch, case):
    payload = body()
    message = payload["choices"][0]["message"]
    if case == "reasoning":
        message["reasoning_content"] = SECRET
    elif case == "explanation":
        message["content"] = json.dumps({"action": 1, "public_explanation": SECRET})
    elif case in {"escaped", "fenced"}:
        encoded = "".join(f"\\u{ord(char):04x}" for char in SECRET)
        message["content"] = '{"action":1,"public_explanation":"' + encoded + '"}'
        if case == "fenced":
            message["content"] = "```json\n" + message["content"] + "\n```"
    else:
        message["content"] = SECRET
    wire(monkeypatch, payload)
    selected = agent()
    if case == "reasoning":
        assert SECRET not in json.dumps(selected.act(request()).to_dict())
    else:
        with pytest.raises(ProviderCallError):
            selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)


@pytest.mark.parametrize("reason,kind", [
    ("length", "provider_output_truncated"), ("tool_calls", "provider_request_rejected"),
    ("content_filter", "provider_refused"), (None, "provider_response_schema_mismatch"),
    ({"private": SECRET}, "provider_response_schema_mismatch"),
])
def test_noncomplete_output_never_becomes_action(monkeypatch, reason, kind):
    payload = body()
    payload["choices"][0]["finish_reason"] = reason
    calls = wire(monkeypatch, payload)
    selected = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as raised:
        selected.act(request())
    assert raised.value.error_kind == kind
    assert selected.last_receipt["usage"]["total_tokens"] == 24
    assert len(calls) == 1


@pytest.mark.parametrize("case", ["error", "wrong-model", "tools", "reasoning-only", "empty",
                                  "choices", "object", "role", "index"])
def test_semantic_and_shape_failures(monkeypatch, case):
    payload = body()
    choice = payload["choices"][0]
    if case == "error":
        payload["error_code"] = "ModelArts.81001"
        payload["error_msg"] = SECRET
    elif case == "wrong-model":
        payload["model"] = "different-model"
    elif case == "tools":
        choice["message"]["tool_calls"] = [{"id": SECRET}]
    elif case == "reasoning-only":
        del choice["message"]["content"]
    elif case == "empty":
        choice["message"]["content"] = " "
    elif case == "choices":
        payload["choices"].append(copy.deepcopy(choice))
    elif case == "object":
        payload["object"] = "chat.completion.chunk"
    elif case == "role":
        choice["message"]["role"] = "tool"
    else:
        choice["index"] = True
    wire(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError):
        selected.act(request())
    assert SECRET not in json.dumps(selected.attempt_receipts)


def test_missing_identity_and_usage_are_unknown(monkeypatch):
    payload = body()
    del payload["model"], payload["usage"]
    wire(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["usage"] == {}
    assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_missing_total_is_not_invented_and_wrong_accounting_is_marked(monkeypatch):
    payload = body()
    del payload["usage"]["total_tokens"]
    payload["usage"]["completion_tokens_details"]["reasoning_tokens"] = 99
    wire(monkeypatch, payload)
    usage = agent().act(request()).metadata["provider_receipt"]["usage"]
    assert usage["total_tokens"] is None
    assert usage["total_tokens_source"] == "unavailable"
    assert "reasoning_tokens_exceed_inclusive_output_tokens" in usage["usage_validation_errors"]


@pytest.mark.parametrize("invalid", [True, -1, "24", 24.5])
def test_invalid_total_is_not_replaced_with_derived_accounting(monkeypatch, invalid):
    payload = body()
    payload["usage"]["total_tokens"] = invalid
    wire(monkeypatch, payload)
    usage = agent().act(request()).metadata["provider_receipt"]["usage"]
    assert usage["total_tokens"] is None
    assert usage["total_tokens_source"] == "unavailable"
    assert "total_tokens_invalid" in usage["usage_validation_errors"]


def test_preflight_and_cli_are_offline_by_default(monkeypatch, capsys):
    def unexpected(*a, **k):
        pytest.fail("offline preflight performed network I/O")

    monkeypatch.setattr("httpx.get", unexpected)
    monkeypatch.setattr("eslams.agents.bounded_post", unexpected)
    for model in PANGU_MODELS:
        record = load_provider_registry().resolve("huawei", model)
        assert record.known and record.supports_reasoning and record.available_from_api is None
    assert main(["providers", "preflight", "--provider", "huawei", "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True
    assert result["checks"]["account_model_visible"] is None
    assert result["model_availability"] == "unverified"


def test_explicit_live_preflight_dispatch_uses_only_selected_model(monkeypatch):
    calls = wire(monkeypatch)
    def models(url, **kwargs):
        assert url == "https://api.modelarts-maas.com/v2/models"
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("httpx.get", models)
    result = provider_preflight("huawei", MODEL, "tic-tac-toe", live=True)
    assert result["ok"]
    assert result["checks"]["usage_extraction"]
    assert result["checks"]["account_model_visible"] is True
    assert len(calls) == 1


def test_discovery_rejects_credential_echo_in_model_id(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    monkeypatch.setattr("httpx.get", lambda *a, **k: httpx.Response(
        200, json={"data": [{"id": SECRET}]},
    ))
    with pytest.raises(ProviderCallError) as raised:
        provider_models_live("huawei")
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("credential", [None, " ", "bad key"])
def test_missing_or_invalid_key_never_submits(monkeypatch, credential):
    if credential is None:
        monkeypatch.delenv(API_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(API_KEY_ENV, credential)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("no key"))
    with pytest.raises(ProviderCallError) as raised:
        agent().act(request())
    assert raised.value.error_kind == "provider_auth_failed"


@pytest.mark.parametrize("exception,kind", [
    (httpx.ConnectError, "provider_transport_error"),
    (httpx.ReadTimeout, "provider_timeout"),
])
def test_unobserved_transport_failures_have_one_attempt(monkeypatch, exception, kind):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    def fail(*a, **k):
        calls.append(1)
        raise exception(SECRET)

    monkeypatch.setattr("eslams.agents.bounded_post", fail)
    selected = agent()
    with pytest.raises((ProviderCallError, TimeoutError)) as raised:
        selected.act(request())
    assert SECRET not in str(raised.value)
    assert selected.last_receipt["outcome"] == kind
    assert selected.last_receipt["usage"] == {}
    assert len(calls) == 1


def test_real_transport_reads_raw_bytes_without_network(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, SECRET)
    calls = []

    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield FIXTURE.read_bytes()

    def handle(req):
        calls.append(req)
        assert str(req.url) == CHAT_COMPLETIONS_ENDPOINT
        assert req.headers["authorization"] == f"Bearer {SECRET}"
        assert json.loads(req.content)["model"] == MODEL
        return httpx.Response(200, stream=Bytes(), headers={"x-request-id": SECRET})

    original = httpx.AsyncClient
    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handle),
    ))
    result = agent().act(request())
    assert result.action == 1
    assert SECRET not in json.dumps(result.to_dict())
    assert len(calls) == 1


def test_cli_run_dispatch_writes_secret_free_receipt(monkeypatch, tmp_path, capsys):
    wire(monkeypatch)
    assert main(["run", "--arena", "tic-tac-toe", "--agent", f"huawei:{MODEL}",
                 "--max-turns", "1", "--expanded", "--output-dir", str(tmp_path)]) == 0
    capsys.readouterr()
    receipt_files = list(tmp_path.rglob("provider_receipts.jsonl"))
    assert len(receipt_files) == 1
    text = receipt_files[0].read_text()
    assert SECRET not in text
    rows = [json.loads(line) for line in text.splitlines()]
    assert rows[0]["provider"] == "huawei"
    assert rows[0]["model"] == MODEL
