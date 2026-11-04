from __future__ import annotations

import copy
import hashlib
import json
import sys
import traceback
from pathlib import Path

import httpx
import pytest

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)
from eslams.providers.baichuan import (
    CHAT_COMPLETIONS_ENDPOINT,
    normalize_usage,
    request_payload,
)
from eslams.runner import RunConfig, Runner

FIXTURE = Path(__file__).parent / "fixtures/provider/baichuan_chat_completions_success.json"
KEY = "fixture-baichuan-secret"
PRIVATE = "private-reasoning-sentinel"


def fingerprint(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def payload():
    return json.loads(FIXTURE.read_text())


def request(arena="tic-tac-toe"):
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="run_baichuan", episode_id="episode_001",
        turn_id=0, arena=ArenaIdentity(id=arena, version="1.0.0"),
        agent=AgentIdentity(id="baichuan-fixture", version="fixture-v1"),
        active_player="player_1", observation={"board": [], "sentinel": "prompt-private"},
        legal_actions=[0, 1, 2], action_schema={"type": "integer"},
        history=[{"turn": i, "public_event": f"history-{i}"} for i in range(250)],
        time_budget_ms=None, memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None, None)},
    )


def agent(provider="baichuan-ai", model="Baichuan4-Turbo", **kwargs):
    return ModelProviderAgent(provider, model, "BAICHUAN_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("BAICHUAN_API_KEY", KEY)


def stub(monkeypatch, body=None, status=200, headers=None):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status, json=payload() if body is None else body,
            headers=headers or {"X-BC-Request-Id": "bc-request-fixture"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ["baichuan", "baichuan-ai", "baichuan_ai", "BAICHUAN"])
def test_alias_cli_preflight_and_dispatch(monkeypatch, capsys, alias):
    calls = stub(monkeypatch)
    configured = _provider_agent(f"{alias}:Baichuan4-Turbo")
    assert configured.provider == "baichuan-ai"
    assert configured.model == "Baichuan4-Turbo"
    assert main([
        "providers", "preflight", "--provider", alias, "--model", "Baichuan4-Turbo",
    ]) == 0
    offline = json.loads(capsys.readouterr().out)
    assert offline["checks"]["adapter_available"] is True
    assert offline["model_availability"] == "unverified"
    assert calls == []
    assert provider_models_live(alias) is None
    assert agent(provider=alias).act(request()).action == 1
    assert len(calls) == 1
    assert configured.provider == "baichuan-ai"
    live = provider_preflight(alias, "Baichuan4-Turbo", "tic-tac-toe", live=True)
    assert live["ok"] is True
    assert live["checks"]["account_model_visible"] is None
    assert live["checks"]["usage_extraction"] is True
    assert live["readiness"]["usage_complete"] is False
    assert live["receipt_shape"]["usage_complete"] is False


@pytest.mark.parametrize("alias", ["baichuan", "baichuan-ai", "baichuan_ai"])
def test_cli_requires_explicit_model(alias):
    with pytest.raises(ValueError, match="exact provider-native model"):
        _provider_agent(alias)


@pytest.mark.parametrize("arena", ["tic-tac-toe", "connect-four", "chess"])
def test_native_payload_full_history_no_caps_or_game_reasoning(monkeypatch, arena):
    body = payload()
    body["choices"][0]["message"]["reasoning_content"] = PRIVATE
    body["choices"][0]["grounding"] = {"evidence": [{"title": PRIVATE}]}
    body["private_extension"] = {"api_key": KEY, "response": PRIVATE}
    calls = stub(monkeypatch, body)
    response = agent().act(request(arena))
    url, sent = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert sent["headers"] == {
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
    }
    wire = sent["json"]
    assert set(wire) == {"model", "messages", "stream"}
    assert wire["model"] == "Baichuan4-Turbo" and wire["stream"] is False
    assert [item["role"] for item in wire["messages"]] == ["system", "user"]
    assert all(f'"history-{i}"' in wire["messages"][1]["content"] for i in range(250))
    assert sent["timeout"].read is None
    assert not hasattr(sent["timeout"], "deadline")
    receipt = response.metadata["provider_receipt"]
    assert receipt["request_id"] == fingerprint("bc-request-fixture")
    assert receipt["provider_response_id"] == fingerprint("chatcmpl-baichuan-redacted")
    assert receipt["locked_model_id"] == "Baichuan4-Turbo"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "baichuan_chat_completions"
    assert receipt["parser_version"] == "baichuan-chat-completions-raw-v1"
    assert receipt["usage"]["total_tokens"] == 16
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["usage"]["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    serialized = json.dumps(response.to_dict())
    assert all(value not in serialized for value in (KEY, PRIVATE, "prompt-private", "history-0"))


def test_explicit_controls_forwarded_without_clamping(monkeypatch):
    body = payload()
    body["model"] = "Baichuan-M3"
    calls = stub(monkeypatch, body)
    chosen = agent(
        model="Baichuan-M3", temperature=0.3, max_output_tokens=12345,
        runtime_config=ProviderRuntimeConfig(reasoning_budget_tokens=2000),
    )
    chosen.act(request())
    sent = calls[0][1]["json"]
    assert sent["max_tokens"] == 12345
    assert sent["temperature"] == 0.3
    assert sent["thinking"] == {"budget_tokens": 2000}


@pytest.mark.parametrize("model,runtime", [
    ("Baichuan4-Turbo", ProviderRuntimeConfig(reasoning="enabled")),
    ("Baichuan4-Turbo", ProviderRuntimeConfig(reasoning="disabled")),
    ("Baichuan4-Turbo", ProviderRuntimeConfig(reasoning_effort="high")),
    ("Baichuan4-Turbo", ProviderRuntimeConfig(reasoning_budget_tokens=2000)),
    ("Baichuan-M3-Plus", ProviderRuntimeConfig(reasoning_budget_tokens=2000)),
])
def test_unsupported_reasoning_is_explicit_failure(monkeypatch, model, runtime):
    calls = stub(monkeypatch)
    chosen = agent(model=model, runtime_config=runtime)
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "provider_request_rejected"
    assert calls == []
    assert chosen.last_receipt["usage"] == {}
    offline = provider_preflight("baichuan", model, "tic-tac-toe", runtime_config=runtime)
    assert offline["ok"] is False
    assert offline["readiness"]["configuration_ready"] is False
    assert offline["error"]["error_class"] == "provider_request_rejected"
    assert not calls


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
def test_http_errors_keep_receipts_and_do_not_replay(monkeypatch, status, kind):
    calls = stub(monkeypatch, {"error": {"code": status, "message": PRIVATE}}, status)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert len(calls) == 1
    assert caught.value.error_kind == kind
    assert chosen.last_receipt["status_code"] == status
    assert chosen.last_receipt["request_id"] == fingerprint("bc-request-fixture")
    assert chosen.last_receipt["locked_model_id"] is None
    assert chosen.last_receipt["usage"] == {}
    assert PRIVATE not in str(caught.value) + json.dumps(chosen.last_receipt)


@pytest.mark.parametrize("reason,kind", [
    ("content_filter", "provider_refused"), ("refuse_answer", "provider_refused"),
    ("length", "provider_output_truncated"), ("tool_calls", "provider_response_schema_mismatch"),
    (None, "provider_response_schema_mismatch"),
    ("future-finish", "provider_response_schema_mismatch"),
    ({"private": PRIVATE}, "provider_response_schema_mismatch"),
])
def test_noncompletion_never_accepts_legal_partial_text(monkeypatch, reason, kind):
    body = payload()
    body["choices"][0]["finish_reason"] = reason
    calls = stub(monkeypatch, body)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == kind
    assert len(calls) == 1
    assert chosen.last_receipt["usage"]["total_tokens"] == 16
    assert PRIVATE not in json.dumps(chosen.last_receipt)


@pytest.mark.parametrize("change", [
    {"object": "chat.completion.chunk"}, {"choices": []}, {"choices": [{"index": 0}]},
    {"choices": [None]}, {"choices": "bad"}, {"model": "another-model"},
])
def test_malformed_and_wrong_identity_fail_closed(monkeypatch, change):
    body = {**payload(), **change}
    stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert chosen.last_receipt["model"] == "Baichuan4-Turbo"
    if change.get("model"):
        assert chosen.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("raw", [b"not json", b'[]', b'{"id":"a","id":"b"}'])
def test_invalid_wire_json_preserves_header_evidence(monkeypatch, raw):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **kw: httpx.Response(
        200, content=raw, headers={"X-BC-Request-Id": "bc-malformed"},
    ))
    chosen = agent()
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert chosen.last_receipt["request_id"] == fingerprint("bc-malformed")
    assert chosen.last_receipt["usage"] == {}


def test_missing_identity_and_accounting_stay_unknown(monkeypatch):
    body = payload()
    for key in ("model", "id", "usage"):
        body.pop(key)
    stub(monkeypatch, body)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None
    assert receipt["model_identity_source"] is None
    assert receipt["provider_response_id"] is None
    assert receipt["usage"] == {}
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    partial = normalize_usage({"prompt_tokens": 3, "completion_tokens": 2})
    assert partial["total_tokens"] is None
    assert partial["reasoning_tokens"] is None
    assert partial["cached_input_tokens"] is None
    assert normalize_usage({"prompt_tokens": True})["input_tokens"] is None
    assert normalize_usage({"completion_tokens": -1})["usage_validation_errors"]
    assert normalize_usage({"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 9})[
        "usage_validation_errors"
    ] == ["provider_total_tokens_inconsistent"]


@pytest.mark.parametrize("work_observed", [False, True])
def test_429_optional_safe_retry_and_quarantined_work(monkeypatch, work_observed):
    calls = []
    body = {"error": {"code": "rate_limit_exceeded", "message": PRIVATE}}
    if work_observed:
        body.update(id="generation-observed", model="unverified-identity", usage=payload()["usage"])

    def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(
            429 if len(calls) == 1 else 200,
            json=body if len(calls) == 1 else payload(),
            headers={"Retry-After": "0", "X-BC-Request-Id": "bc-429"},
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    chosen = agent(runtime_config=ProviderRuntimeConfig(
        max_retries=1, retry_jitter=False, retry_backoff_ms=0,
    ))
    if work_observed:
        with pytest.raises(ProviderCallError):
            chosen.act(request())
        assert len(calls) == 1
        receipt = chosen.last_receipt
        assert receipt["usage"]["total_tokens"] == 16
        assert receipt["provider_response_id"] == fingerprint("generation-observed")
        assert receipt["locked_model_id"] is None
        assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    else:
        assert chosen.act(request()).action == 1
        assert len(calls) == 2
        assert [r["attempt_index"] for r in chosen.attempt_receipts] == [1, 2]


def test_body_error_is_quarantined_and_redacted(monkeypatch):
    body = {"error": {"code": 429, "message": PRIVATE}, "model": "unverified-identity",
            "id": "error-generation", "usage": payload()["usage"]}
    calls = stub(monkeypatch, body)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "provider_rate_limited"
    assert len(calls) == 1
    assert chosen.last_receipt["locked_model_id"] is None
    assert chosen.last_receipt["usage"]["total_tokens"] == 16
    assert PRIVATE not in str(caught.value) + json.dumps(chosen.last_receipt)


def test_http_200_error_code_alone_never_authorizes_replay(monkeypatch):
    calls = stub(monkeypatch, {"error": {"code": 429}})
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert len(calls) == 1


def test_error_cost_extensions_do_not_invent_usd_accounting(monkeypatch):
    body = {"error": {"code": 429}, "cost": 7.5, "currency": "CNY"}
    calls = stub(monkeypatch, body, status=429)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert len(calls) == 1
    receipt = chosen.last_receipt
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "observed_cost_usd" not in receipt["pricing_provenance"]
    assert receipt["pricing_provenance"]["cost_observation_status"] == "present_currency_unverified"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failure_never_replays(monkeypatch, failure):
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        raise failure(PRIVATE)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)):
        chosen.act(request())
    assert len(calls) == 1
    assert chosen.last_receipt["usage"] == {}
    assert PRIVATE not in json.dumps(chosen.last_receipt)


def test_real_safe_transport_and_public_artifact_privacy(monkeypatch, tmp_path):
    original = httpx.AsyncClient

    def wire(req):
        assert str(req.url) == CHAT_COMPLETIONS_ENDPOINT
        assert req.headers["authorization"] == f"Bearer {KEY}"
        assert req.headers["accept-encoding"] == "identity"
        assert json.loads(req.content)["stream"] is False
        body = payload()
        body["choices"][0]["message"]["reasoning_content"] = PRIVATE
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(body).encode()),
            headers={"X-BC-Request-Id": "bc-transport"},
        )

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kw: original(
        **kw, transport=httpx.MockTransport(wire),
    ))
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1, output_dir=tmp_path,
    ))
    assert result.score.usage_complete is False  # reasoning inclusion is unverified
    report = ArtifactValidator().validate_report(result.artifact_path, profile="official_case")
    assert not report.valid
    receipts = (result.artifact_path / "receipts/provider_receipts.jsonl").read_text()
    assert fingerprint("bc-transport") in receipts
    assert all(x not in receipts for x in (KEY, PRIVATE, "Authorization"))
    for name in ("public", "public_reasoning"):
        for path in (result.artifact_path / name).rglob("*.json*"):
            assert all(x not in path.read_text() for x in (KEY, PRIVATE, "Authorization"))


def test_missing_and_invalid_credentials_do_not_submit(monkeypatch):
    calls = stub(monkeypatch)
    for value in ("", "invalid key"):
        monkeypatch.setenv("BAICHUAN_API_KEY", value)
        chosen = agent()
        with pytest.raises(ProviderCallError) as caught:
            chosen.act(request())
        assert caught.value.error_kind == "provider_auth_failed"
    assert not calls


def test_no_action_repair_by_default(monkeypatch):
    body = copy.deepcopy(payload())
    body["choices"][0]["message"]["content"] = "not an action"
    calls = stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "action_response_unparseable"
    assert len(calls) == 1
    assert chosen.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("model", ["", " ", "\t"])
def test_blank_models_rejected_by_cli_preflight_and_transport(monkeypatch, model):
    calls = stub(monkeypatch)
    with pytest.raises(ValueError, match="exact provider-native model"):
        _provider_agent(f"baichuan:{model}")
    offline = provider_preflight("baichuan", model, "tic-tac-toe")
    assert not offline["ok"]
    with pytest.raises(ProviderCallError) as caught:
        agent(model=model).act(request())
    assert caught.value.error_kind == "provider_request_rejected"
    assert not calls


@pytest.mark.parametrize("path", ["success", "http-error", "malformed", "partial"])
@pytest.mark.parametrize("secret", [KEY, "opaque-secondary-credential"])
def test_echoed_credentials_do_not_enter_identifiers(monkeypatch, path, secret):
    from eslams.http_io import ResponseObservation

    def post(*args, **kwargs):
        headers = {"X-BC-Request-Id": secret, "X-Gateway-Request-Id": secret}
        if path == "partial":
            exc = httpx.ReadError("body interrupted")
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                status_code=200, headers=tuple((k.lower(), v) for k, v in headers.items()),
            )
            raise exc
        if path == "malformed":
            return httpx.Response(200, content=b"{bad", headers=headers)
        if path == "http-error":
            body = {"error": {"code": 429, "message": secret}, "id": secret}
            return httpx.Response(429, json=body, headers=headers)
        body = payload()
        body["id"] = secret
        return httpx.Response(200, json=body, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    chosen = agent()
    if path == "success":
        chosen.act(request())
    else:
        with pytest.raises(ProviderCallError) as caught:
            chosen.act(request())
        assert secret not in str(caught.value) + json.dumps(caught.value.receipt)
    assert secret not in json.dumps(chosen.attempt_receipts)
    assert chosen.last_receipt["request_id"] == (None if secret == KEY else fingerprint(secret))


def test_echoed_credential_in_answer_or_model_is_rejected(monkeypatch):
    body = payload()
    body["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": KEY,
    })
    stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert KEY not in str(caught.value) + json.dumps(chosen.last_receipt)
    body["model"] = "opaque-secondary-credential"
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert body["model"] not in json.dumps(chosen.last_receipt)


@pytest.mark.parametrize("alias", ["baichuan", "baichuan-ai", "baichuan_ai"])
def test_cli_run_routes_alias_to_native_transport(monkeypatch, capsys, tmp_path, alias):
    calls = stub(monkeypatch)
    assert main([
        "run", "--arena", "tic-tac-toe", "--agent", f"{alias}:Baichuan4-Turbo",
        "--max-turns", "1", "--expanded", "--output-dir", str(tmp_path),
    ]) == 0
    capsys.readouterr()
    assert len(calls) == 1
    assert calls[0][0] == CHAT_COMPLETIONS_ENDPOINT
    receipt_path = next(tmp_path.rglob("provider_receipts.jsonl"))
    receipt = json.loads(receipt_path.read_text().splitlines()[0])
    assert receipt["provider"] == "baichuan-ai"
    assert receipt["model"] == "Baichuan4-Turbo"


def unicode_escaped(value):
    return "".join(f"\\u{ord(char):04x}" for char in value)


@pytest.mark.parametrize("wrapping", ["plain", "fenced", "embedded", "nested-escape"])
@pytest.mark.parametrize("secret", [KEY, "sk-secondary-private-123456", "Bearer opaque-secondary"])
def test_escaped_credentials_in_action_text_fail_before_recording(monkeypatch, wrapping, secret):
    encoded = unicode_escaped(secret)
    text = '{"action":1,"public_explanation":"' + encoded + '"}'
    if wrapping == "fenced":
        text = "```json\n" + text + "\n```"
    elif wrapping == "embedded":
        text = "Here is the action: " + text
    elif wrapping == "nested-escape":
        text = text.replace("\\u", "\\\\u")
    assert secret not in text
    body = payload()
    body["choices"][0]["message"]["content"] = text
    calls = stub(monkeypatch, body)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    recorded = json.dumps(chosen.attempt_receipts) + str(caught.value)
    assert all(value not in recorded for value in (secret, encoded, text))
    assert chosen.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("secret", [KEY, "opaque-secondary"])
def test_credential_fields_in_action_extensions_fail_closed(monkeypatch, secret):
    body = payload()
    text = json.dumps({"action": 1, "metadata": {"secondary_api_key": secret}})
    body["choices"][0]["message"]["content"] = text
    calls = stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert len(calls) == 1
    assert secret not in json.dumps(chosen.attempt_receipts)


@pytest.mark.parametrize("path", ["success", "http-error", "malformed", "partial"])
@pytest.mark.parametrize("secret", [KEY, "opaque-secondary"])
def test_json_escaped_identifier_echoes_do_not_escape_receipts(monkeypatch, path, secret):
    from eslams.http_io import ResponseObservation

    encoded = unicode_escaped(secret)

    def post(*args, **kwargs):
        headers = {"X-BC-Request-Id": encoded, "X-Gateway-Request-Id": encoded}
        if path == "partial":
            exc = httpx.ReadError(secret)
            exc.__dict__["_eslams_response_observation"] = ResponseObservation(
                status_code=200, headers=tuple((k.lower(), v) for k, v in headers.items()),
            )
            raise exc
        if path == "malformed":
            return httpx.Response(200, content=b"{bad", headers=headers)
        body = ({"error": {"code": 429, "message": secret}, "id": secret}
                if path == "http-error" else {**payload(), "id": secret})
        wire = json.dumps(body).replace(secret, encoded)
        assert secret not in wire
        return httpx.Response(429 if path == "http-error" else 200,
                              content=wire.encode(), headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    chosen = agent()
    if path == "success":
        response = chosen.act(request())
        public = response.to_dict()
    else:
        with pytest.raises(ProviderCallError) as caught:
            chosen.act(request())
        public = {"error": str(caught.value), "receipt": caught.value.receipt}
    serialized = json.dumps({"public": public, "attempts": chosen.attempt_receipts})
    assert secret not in serialized
    assert encoded not in serialized


@pytest.mark.parametrize("usage", [
    {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 99},
    {"prompt_tokens": True, "completion_tokens": 4, "total_tokens": 16},
    {"prompt_tokens": 12, "completion_tokens": -1, "total_tokens": 16},
    {"prompt_tokens": 12, "completion_tokens": 4},
])
def test_incoherent_usage_is_incomplete_in_preflight_and_artifacts(monkeypatch, tmp_path, usage):
    body = {**payload(), "usage": usage}
    stub(monkeypatch, body)
    preflight = provider_preflight("baichuan", "Baichuan4-Turbo", "tic-tac-toe", live=True)
    assert preflight["ok"] is True  # one legal action remains distinct from accounting
    assert preflight["readiness"]["usage_complete"] is False
    assert preflight["receipt_shape"]["usage_complete"] is False
    assert preflight["checks"]["usage_extraction"] is False
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1, output_dir=tmp_path,
    ))
    assert result.score.usage_complete is False
    receipt = json.loads((result.artifact_path / "receipts/provider_receipts.jsonl").read_text())
    assert receipt["usage_complete"] is False
    assert receipt["cost_complete"] is False


def test_no_discovery_endpoint_means_no_credential_or_wire_echo(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Baichuan discovery must not read credentials or call HTTP")

    monkeypatch.setattr("eslams.provider_preflight.provider_key", forbidden)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", forbidden)
    for alias in ("baichuan", "baichuan-ai", "baichuan_ai"):
        assert provider_models_live(alias) is None
        result = provider_models_result(alias)
        assert result["error"]["error_class"] == "provider_discovery_unavailable"
        assert KEY not in json.dumps(result)


@pytest.mark.parametrize("missing", [None, "", " ", "\t"])
def test_payload_admission_rejects_missing_models(missing):
    with pytest.raises(ProviderCallError) as caught:
        request_payload(missing, "prompt", instructions="instructions", temperature=None,
                        max_tokens=None, runtime=None)
    assert caught.value.error_kind == "provider_request_rejected"


@pytest.mark.parametrize("alias", ["baichuan", "baichuan-ai", "baichuan_ai"])
def test_cli_preflight_requires_model_argument(capsys, alias):
    with pytest.raises(SystemExit) as caught:
        main(["providers", "preflight", "--provider", alias])
    assert caught.value.code == 2
    capsys.readouterr()


@pytest.mark.parametrize("alias", ["baichuan", "baichuan-ai", "baichuan_ai"])
def test_null_model_rejected_before_registry_or_transport(monkeypatch, alias):
    calls = stub(monkeypatch)
    with pytest.raises(ValueError, match="exact provider-native model"):
        agent(provider=alias, model=None)
    with pytest.raises(ValueError, match="exact provider-native model"):
        provider_preflight(alias, None, "tic-tac-toe", live=True)
    assert not calls


@pytest.mark.parametrize("secret", [KEY, "Bearer opaque-secondary", "sk-secondary-private-123456"])
def test_escaped_action_credentials_never_reach_artifact_files(monkeypatch, tmp_path, secret):
    body = payload()
    encoded = unicode_escaped(secret)
    body["choices"][0]["message"]["content"] = (
        '{"action":1,"public_explanation":"' + encoded + '"}'
    )
    calls = stub(monkeypatch, body)
    result = Runner().run(RunConfig(
        arena_id="tic-tac-toe", agents={"player_1": agent()}, max_turns=1, output_dir=tmp_path,
    ))
    assert len(calls) == 1
    assert result.score.match_valid_for_scoring is False
    assert "provider_response_schema_mismatch" in result.score.invalid_reason_codes
    checked = []
    for path in result.artifact_path.rglob("*"):
        if path.suffix in {".json", ".jsonl"}:
            checked.append(path)
            contents = path.read_text()
            assert secret not in contents
            assert encoded not in contents
    assert checked


def test_ordinary_public_explanation_is_preserved(monkeypatch):
    body = payload()
    text = "This legal move keeps the center occupied."
    body["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": text,
    })
    stub(monkeypatch, body)
    response = agent().act(request())
    assert response.action == 1
    assert response.public_explanation == text


def test_deep_non_action_json_is_rejected_with_a_receipt(monkeypatch):
    body = payload()
    depth = sys.getrecursionlimit() * 2
    body["choices"][0]["message"]["content"] = "[" * depth + "0" + "]" * depth
    calls = stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind in {
        "provider_response_schema_mismatch", "action_response_unparseable",
    }
    assert len(calls) == 1
    assert chosen.last_receipt["usage"]["total_tokens"] == 16


@pytest.mark.parametrize("budget", [0, 1, 2000])
@pytest.mark.parametrize("model", ["Baichuan4-Turbo", "Unregistered-model", "Baichuan-M3-Plus"])
def test_explicit_unsupported_budgets_fail_before_discovery_and_transport(
    monkeypatch, budget, model,
):
    calls = stub(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported reasoning must fail before model discovery")

    monkeypatch.setattr("eslams.provider_preflight.provider_models_live", forbidden)
    runtime = ProviderRuntimeConfig(reasoning_budget_tokens=budget)
    for live in (False, True):
        result = provider_preflight("baichuan", model, "tic-tac-toe", live=live,
                                    runtime_config=runtime)
        assert result["ok"] is False
        assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ProviderCallError):
        agent(model=model, runtime_config=runtime).act(request())
    assert not calls


def test_json_quote_backslash_and_slash_credential_escapes_fail_closed(monkeypatch):
    secret = 'opaque"quote\\slash/private-key'
    monkeypatch.setenv("BAICHUAN_API_KEY", secret)
    body = payload()
    text = json.dumps({"action": 1, "public_explanation": secret}).replace("/", "\\/")
    assert secret not in text
    body["choices"][0]["message"]["content"] = text
    calls = stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError):
        chosen.act(request())
    assert len(calls) == 1
    assert secret not in json.dumps(chosen.attempt_receipts)


@pytest.mark.parametrize("secret", [KEY, "opaque-secondary"])
@pytest.mark.parametrize("failure", [httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout])
def test_transport_exception_tracebacks_do_not_echo_credentials(monkeypatch, secret, failure):
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        raise failure(secret)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    chosen = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)) as caught:
        chosen.act(request())
    assert len(calls) == 1
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert secret not in json.dumps(chosen.attempt_receipts)


def test_long_nested_escape_chain_is_inspected_before_action_parsing(monkeypatch):
    body = payload()
    encoded = "\\u005c" + "u005c" * 4000 + "u0066" + KEY[1:]
    text = '{"action":1,"public_explanation":"' + encoded + '"}'
    assert KEY not in text
    body["choices"][0]["message"]["content"] = text
    calls = stub(monkeypatch, body)
    chosen = agent()
    with pytest.raises(ProviderCallError) as caught:
        chosen.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1
    assert encoded not in json.dumps(chosen.attempt_receipts)
