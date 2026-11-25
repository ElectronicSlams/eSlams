"""Deterministic Qianfan REST envelopes; no credentials or paid inference.

Provenance and redactions: docs/BAIDU_QIANFAN.md. Fault injections preserve
the documented envelope; they are not assertions about live availability.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
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
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.baidu import CHAT_COMPLETIONS_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner

MODEL = "deepseek-v3.1-250821"
ALIASES = ("baidu", "qianfan", "baidu-qianfan")
SECRET = "fixture-secret-not-for-public-contracts"


def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "baidu_qianfan_chat_completions_success.json").read_text())


def request(arena="tic-tac-toe"):
    return replace(_request(arena_id=arena), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


def agent(provider="baidu", model=MODEL, **kwargs):
    return ModelProviderAgent(provider, model, "QIANFAN_API_KEY", **kwargs)


def install(monkeypatch, payload=None, status=200, headers=None):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    calls = []
    body = wire() if payload is None else payload

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=body, headers=headers or {"X-Request-Id": "qianfan-req"})

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ALIASES)
def test_aliases_reach_registry_cli_preflight_and_native_dispatch(monkeypatch, alias, capsys):
    calls = install(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("offline preflight must not discover"))
    assert load_provider_registry().resolve(alias, MODEL).provider == "baidu"
    native = _provider_agent(f"{alias}:{MODEL}")
    assert native.provider == "baidu" and native.model == MODEL
    assert agent(alias).act(request()).action == 1
    assert native.act(request()).metadata["provider"] == "baidu"
    preflight = provider_preflight(alias, MODEL, "tic-tac-toe")
    assert preflight["checks"]["adapter_available"] is True
    assert preflight["checks"]["api_key_configured"] is True
    assert len(calls) == 2
    assert main(["providers", "preflight", "--provider", alias, "--model", MODEL,
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"] is True


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_requires_explicit_model_and_preserves_versioned_service_name(alias):
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent(alias)
    model = "custom-service:version-id"
    assert _provider_agent(f"{alias}:{model}").model == model


@pytest.mark.parametrize("alias", ALIASES)
def test_cli_run_alias_submits_exact_provider_model_and_records_refusal(
    monkeypatch, tmp_path, alias, capsys,
):
    payload = wire()
    payload["choices"][0]["finish_reason"] = "content_filter"
    calls = install(monkeypatch, payload)
    code = main(["run", "--arena", "tic-tac-toe", "--agent", f"{alias}:{MODEL}",
                 "--output-dir", str(tmp_path), "--require-scoring-valid"])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["summary"]["winner"] is None
    assert len(calls) == 1 and calls[0][1]["json"]["model"] == MODEL


def test_default_wire_keeps_full_history_native_controls_and_no_model_time_limit(monkeypatch):
    calls = install(monkeypatch)
    req = replace(request(), history=[{"turn_id": n, "action": n % 3} for n in range(80)])
    native = agent()
    result = native.act(req)
    url, kwargs = calls[0]
    assert url == CHAT_COMPLETIONS_ENDPOINT
    assert kwargs["headers"] == {
        "Authorization": f"Bearer {SECRET}", "Content-Type": "application/json",
    }
    payload = kwargs["json"]
    assert set(payload) == {"model", "messages", "stream"}
    assert payload["model"] == MODEL and payload["stream"] is False
    prompt = payload["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == req.history
    assert kwargs["timeout"].read is None
    assert getattr(kwargs["timeout"], "deadline", None) is None
    assert native.runtime_config.max_retries == native.runtime_config.action_repair_attempts == 0
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "baidu" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == "baidu_qianfan_chat_completions"
    assert receipt["parser_version"] == "baidu-qianfan-chat-completions-raw-v1"
    assert receipt["request_id"] == "qianfan-req"
    assert receipt["usage"]["input_tokens"] == 11
    assert receipt["usage"]["output_tokens"] == 15
    assert receipt["usage"]["total_tokens"] == 26
    assert receipt["usage"]["reasoning_tokens"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["finish_status"] == "completed"
    assert prompt not in json.dumps(receipt)


@pytest.mark.parametrize("arena", ["tic-tac-toe", "chess", "connect-four"])
def test_arena_never_selects_reasoning_or_output_controls(monkeypatch, arena):
    calls = install(monkeypatch)
    agent(model="ernie-5.0-thinking-preview").act(request(arena))
    assert set(calls[0][1]["json"]) == {"model", "messages", "stream"}


def test_operator_output_timeout_and_history_choices_are_exact(monkeypatch):
    calls = install(monkeypatch)
    runtime = ProviderRuntimeConfig(timeout_ms=32100, read_timeout_ms=12300,
                                    history_window_turns=2)
    native = agent(runtime_config=runtime, max_output_tokens=1234, temperature=0.7)
    req = replace(request(), history=[{"turn_id": n} for n in range(5)])
    native.act(req)
    payload = calls[0][1]["json"]
    assert payload["max_tokens"] == 1234 and payload["temperature"] == 0.7
    assert json.loads(payload["messages"][1]["content"].splitlines()[-1])["history"] == (
        req.history[-2:]
    )
    assert calls[0][1]["timeout"].read <= 12.3
    assert calls[0][1]["timeout"].deadline is not None


@pytest.mark.parametrize("model,config,expected", [
    ("deepseek-v3.2", {"reasoning": "enabled"}, {"thinking": {"type": "enabled"}}),
    ("ernie-5.0-thinking-preview", {"reasoning": "enabled"}, {"enable_thinking": True}),
    ("deepseek-v4-pro", {"reasoning_effort": "max"}, {"reasoning_effort": "max"}),
    ("ernie-5.1", {"reasoning_budget_tokens": 1234}, {"thinking_budget": 1234}),
    ("deepseek-v3.2", {"reasoning": "disabled"}, {}),
])
def test_explicit_reasoning_controls_are_documented_and_unmodified(
    monkeypatch, model, config, expected,
):
    calls = install(monkeypatch)
    agent(model=model, runtime_config=ProviderRuntimeConfig(**config)).act(request())
    payload = calls[0][1]["json"]
    controls = {k: v for k, v in payload.items() if k not in {"model", "messages", "stream"}}
    assert controls == expected
    assert payload["model"] == model


@pytest.mark.parametrize("model,config", [
    ("unverified-model", {"reasoning": "enabled"}),
    ("unverified-model", {"reasoning_effort": "max"}),
    ("deepseek-v4-pro", {"reasoning_effort": "low"}),
    ("deepseek-v4-pro", {"reasoning_budget_tokens": 1234}),
    ("ernie-5.1", {"reasoning_budget_tokens": 99}),
    ("ernie-5.1", {"gemini_thinking_budget": 1234}),
])
def test_unsupported_controls_fail_before_submission(monkeypatch, model, config):
    calls = install(monkeypatch)
    native = agent(model=model, runtime_config=ProviderRuntimeConfig(**config))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_request_rejected" and calls == []


def test_reasoning_usage_is_inclusive_private_and_not_an_action_source(monkeypatch):
    payload = wire()
    payload["usage"] = {"prompt_tokens": 2, "completion_tokens": 544, "total_tokens": 546,
                        "completion_tokens_details": {"reasoning_tokens": 446}}
    payload["choices"][0]["message"]["reasoning_content"] = 'private-reasoning {"action": 2}'
    install(monkeypatch, payload)
    result = agent().act(request())
    assert result.action == 1
    usage = result.metadata["provider_receipt"]["usage"]
    assert usage["reasoning_included_in_output"] is True
    assert usage["output_tokens"] == 544 and usage["total_tokens"] == 546
    assert usage["reasoning_tokens"] == 446
    assert "private-reasoning" not in json.dumps(result.to_dict())
    payload["choices"][0]["message"]["content"] = ""
    with pytest.raises(ProviderCallError) as exc:
        agent().act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch"


@pytest.mark.parametrize("field", ["model", "usage", "id"])
def test_missing_identity_or_accounting_is_never_invented(monkeypatch, field):
    payload = wire()
    payload.pop(field)
    install(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    if field == "model":
        assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    elif field == "usage":
        assert receipt["usage"] == {}
        assert receipt["usage_unavailable_reason"] == "provider_usage_absent"
    else:
        assert receipt["provider_response_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_requested_and_attested_service_version_remain_distinct(monkeypatch):
    payload = wire()
    payload["model"] = "custom-service:version-id"
    install(monkeypatch, payload)
    receipt = agent(model="custom-service").act(request()).metadata["provider_receipt"]
    assert receipt["model"] == "custom-service"
    assert receipt["locked_model_id"] == "custom-service:version-id"


@pytest.mark.parametrize("status,kind", [
    (400, "provider_request_rejected"), (401, "provider_auth_failed"),
    (403, "provider_permission_failed"), (404, "provider_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"),
])
@pytest.mark.parametrize("retries", [0, 3])
def test_http_errors_keep_sanitized_receipts_without_ambiguous_retry(
    monkeypatch, status, kind, retries,
):
    payload = {"error": {"code": "rpm_rate_limit_exceeded", "type": "rate_limit_exceeded",
                         "message": f"private-error {SECRET}"}, "id": "as-error"}
    calls = install(monkeypatch, payload, status, {"Retry-After": "2", "X-Request-Id": "req-error"})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=retries))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == kind and len(calls) == 1
    receipt = native.last_receipt
    assert receipt["provider"] == "baidu" and receipt["model"] == MODEL
    assert receipt["request_id"] == "req-error" and receipt["status_code"] == status
    assert receipt["provider_response_id"] == "as-error"
    assert receipt["locked_model_id"] is None and receipt["usage"] == {}
    assert receipt["retry_after_ms"] == 2000
    assert exc.value.retry_after_seconds == 2
    assert "private-error" not in str(exc.value) + json.dumps(receipt)
    assert SECRET not in str(exc.value) + json.dumps(receipt)


@pytest.mark.parametrize("reason,flag,kind", [
    ("content_filter", 0, "provider_refused"), ("length", 0, "provider_output_truncated"),
    ("tool_calls", 0, "provider_request_rejected"), ("stop", 1, "provider_refused"),
    ("stop", 2, "provider_refused"), ("stop", 3, "provider_refused"),
    ("stop", 4, "provider_refused"),
])
def test_semantic_failure_cannot_accept_legal_looking_text(monkeypatch, reason, flag, kind):
    payload = wire()
    payload["choices"][0].update(finish_reason=reason, flag=flag)
    calls = install(monkeypatch, payload)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == kind and len(calls) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 26
    assert native.last_receipt["finish_reason"] == reason


@pytest.mark.parametrize("changes", [
    {"finish_reason": None}, {"finish_reason": "private-unknown-stop"}, {"finish_reason": 4},
    {"flag": True}, {"flag": 9}, {"message": {"role": "assistant", "content": []}},
    {"message": {"role": "user", "content": '{"action": 1}'}},
    {"index": True}, {"index": 1}, {"error": {"message": "private-choice-error"}},
])
def test_malformed_completion_fails_closed(monkeypatch, changes):
    payload = wire()
    payload["choices"][0].update(changes)
    calls = install(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1
    assert "private-unknown-stop" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"choices": [], "choices": []}'])
def test_invalid_json_and_duplicate_keys_preserve_header_evidence(monkeypatch, body):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k:
                        httpx.Response(200, content=body, headers={"X-Request-Id": "req-invalid"}))
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch"
    assert native.last_receipt["request_id"] == "req-invalid"
    assert native.last_receipt["usage"] == {}


@pytest.mark.parametrize("fault,kind", [
    (httpx.ReadTimeout, "provider_timeout"), (httpx.ConnectError, "provider_transport_error"),
])
def test_transport_faults_are_not_replayed(monkeypatch, fault, kind):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    calls = []

    def post(*a, **k):
        calls.append(1)
        raise fault(f"private-transport {SECRET}")

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((TimeoutError, ProviderCallError)) as exc:
        native.act(request())
    assert native.last_receipt["outcome"] == kind and calls == [1]
    assert SECRET not in str(exc.value) + json.dumps(native.last_receipt)


def test_200_body_error_quarantines_observations_and_never_becomes_an_action(monkeypatch):
    payload = wire()
    payload["error"] = {"type": "rate_limit_exceeded", "code": "rpm_rate_limit_exceeded",
                        "message": "private-error"}
    calls = install(monkeypatch, payload)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_rate_limited" and len(calls) == 1
    receipt = native.last_receipt
    assert receipt["locked_model_id"] is None
    assert receipt["usage"]["total_tokens"] == 26
    assert receipt["pricing_provenance"]["accounting_status"] == "quarantined"
    assert "private-error" not in str(exc.value) + json.dumps(receipt)


@pytest.mark.parametrize("key", [None, "", "invalid\nkey", "nonascii-秘密"])
def test_missing_or_invalid_credentials_never_submit(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("QIANFAN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("QIANFAN_API_KEY", key)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("submission"))
    with pytest.raises(ProviderCallError) as exc:
        agent().act(request())
    assert exc.value.error_kind == "provider_auth_failed"


@pytest.mark.parametrize("alias", ALIASES)
def test_models_discovery_and_explicit_live_preflight_use_exact_qianfan_names(monkeypatch, alias):
    calls = install(monkeypatch)
    discoveries = []

    def get(url, **kwargs):
        discoveries.append(url)
        assert url == MODELS_ENDPOINT
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        return httpx.Response(200, json={"object": "list", "data": [{"id": MODEL}]})

    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == [MODEL]
    result = provider_preflight(alias, MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"] is True
    assert len(discoveries) == 2 and len(calls) == 1


@pytest.mark.parametrize("reason", ["stop", "content_filter", "length"])
def test_runner_artifacts_keep_receipts_and_do_not_publish_private_wire(
    monkeypatch, tmp_path, reason,
):
    payload = wire()
    payload["choices"][0]["finish_reason"] = reason
    payload["choices"][0]["message"]["reasoning_content"] = "private-reasoning-marker"
    payload["private_extension"] = "private-wire-marker"
    calls = install(monkeypatch, payload)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(), output_dir=tmp_path))
    receipt_file = result.expanded_path / "receipts/provider_receipts.jsonl"
    receipts = [json.loads(line) for line in receipt_file.read_text().splitlines()]
    assert len(receipts) == len(calls) and receipts
    assert all(item["provider"] == "baidu" for item in receipts)
    assert all(item["locked_model_id"] == MODEL for item in receipts)
    assert all(item["usage"]["total_tokens"] == 26 for item in receipts)
    if reason != "stop":
        assert result.score.match_valid_for_scoring is False
        assert all(event.action is None for event in result.replay_events)
    assert ArtifactValidator().validate(result.expanded_path) == []
    public = "\n".join(path.read_text() for path in result.expanded_path.rglob("*")
                       if path.is_file() and path.suffix in {".json", ".jsonl", ".html"})
    for forbidden in (SECRET, "private-reasoning-marker", "private-wire-marker", "Authorization"):
        assert forbidden not in public


@pytest.mark.parametrize("missing", ["prompt_tokens", "completion_tokens", "total_tokens"])
def test_missing_individual_token_counts_remain_unknown(monkeypatch, missing):
    payload = wire()
    payload["usage"].pop(missing)
    install(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    target = {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens",
              "total_tokens": "total_tokens"}[missing]
    assert receipt["usage"][target] is None


def test_usage_projects_only_documented_fields_and_never_copies_native_cost(monkeypatch):
    payload = wire()
    payload["usage"].update(
        prompt_tokens_details={"cached_tokens": 4, "private_extension": "private-usage"},
        completion_tokens_details={"reasoning_tokens": 5},
        cost=1234, private_extension="private-usage",
    )
    install(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert receipt["usage"]["cached_input_tokens"] == 4
    assert receipt["usage"]["reasoning_tokens"] == 5
    assert receipt["usage"]["total_tokens"] == 26
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert "private-usage" not in json.dumps(receipt)


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_tokens": True, "completion_tokens": 15, "total_tokens": 26}, "input_tokens_invalid"),
    ({"prompt_tokens": -1, "completion_tokens": 15, "total_tokens": 26}, "input_tokens_invalid"),
    ({"prompt_tokens": 11, "completion_tokens": 15, "total_tokens": 27},
     "provider_total_tokens_inconsistent"),
    ({"prompt_tokens": 11, "completion_tokens": 15, "total_tokens": 26,
      "prompt_tokens_details": {"cached_tokens": 12}}, "cached_input_tokens_exceed_input_tokens"),
    ({"prompt_tokens": 11, "completion_tokens": 15, "total_tokens": 26,
      "completion_tokens_details": {"reasoning_tokens": 16}},
     "reasoning_tokens_exceed_inclusive_output_tokens"),
])
def test_invalid_usage_is_diagnosed_without_repairing_provider_counts(monkeypatch, usage, expected):
    payload = wire()
    payload["usage"] = usage
    install(monkeypatch, payload)
    receipt = agent().act(request()).metadata["provider_receipt"]
    assert expected in receipt["usage"]["usage_validation_errors"]


def test_parse_failure_is_not_repaired_by_default_or_replaced_with_legal_action(monkeypatch):
    payload = wire()
    payload["choices"][0]["message"]["content"] = "not an action"
    calls = install(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "action_response_unparseable" and len(calls) == 1
    assert native.last_receipt["usage"]["total_tokens"] == 26


@pytest.mark.parametrize("mode", ["success", "429", "malformed", "partial", "resource"])
def test_actual_bounded_reader_keeps_wire_custody_without_live_network(monkeypatch, mode):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    original_client = httpx.AsyncClient
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if mode == "partial":
                yield b'{"private":"private-body-marker"'
                raise httpx.ReadTimeout("private-timeout-marker")
            elif mode == "resource":
                yield b"x" * (1024 * 1024 + 1)
            elif mode == "malformed":
                yield b"private-body-marker"
            elif mode == "429":
                yield b'{"error":{"type":"rate_limit_exceeded",' \
                      b'"code":"rpm_rate_limit_exceeded","message":"private-error-marker"},' \
                      b'"id":"as-rejected"}'
            else:
                yield json.dumps(wire()).encode()

    def respond(req):
        calls.append(req)
        assert str(req.url) == CHAT_COMPLETIONS_ENDPOINT
        assert req.headers["Authorization"] == f"Bearer {SECRET}"
        assert json.loads(req.content)["model"] == MODEL
        return httpx.Response(429 if mode == "429" else 200, stream=Stream(), request=req,
                              headers={"X-Request-Id": "bounded-qianfan"})

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (
                original_client(transport=httpx.MockTransport(respond)) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                yield response

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs: Client())
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    if mode == "success":
        assert native.act(request()).action == 1
    else:
        with pytest.raises(ProviderCallError) as exc:
            native.act(request())
        expected = {"429": "provider_rate_limited", "partial": "provider_timeout"}.get(
            mode, "provider_response_schema_mismatch",
        )
        assert exc.value.error_kind == expected
        assert native.last_receipt["usage"] == {}
        assert native.last_receipt["locked_model_id"] is None
    assert len(calls) == len(native.attempt_receipts) == 1
    assert native.last_receipt["request_id"] == "bounded-qianfan"
    public = json.dumps(native.last_receipt)
    assert "private-" not in public and SECRET not in public
