"""Deterministic native REST cases; no credentials or paid requests are used."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.runner import RunConfig, Runner

SECRET = "nv-synthetic-fixture-credential"


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/provider/"
                       "naver_chat_completions_v3_success.json").read_text())


def request():
    return ActRequest(
        protocol_version="eslams-act-v2", run_id="naver-wire", episode_id="episode_001",
        turn_id=100, arena=ArenaIdentity(id="tic-tac-toe", version="1.0.0"),
        agent=AgentIdentity(id="naver-wire", version="fixture"), active_player="player_1",
        observation={}, legal_actions=[0, 1, 2], action_schema={"type": "integer"},
        history=[{"turn_id": i, "action": 0} for i in range(100)], time_budget_ms=None,
        memory_policy="current_observation_plus_public_history",
        metadata={"model_execution_policy": model_execution_policy(None)},
    )


def agent(model="HCX-007", **kwargs):
    return ModelProviderAgent("naver", model, "CLOVASTUDIO_API_KEY", **kwargs)


def mock_post(monkeypatch, payload=None, status=200, **headers):
    calls = []
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, json=fixture() if payload is None else payload,
                              headers={"x-ncp-clovastudio-request-id": "naver-request", **headers})
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_dispatch_native_payload_full_history_and_usage(monkeypatch):
    calls = mock_post(monkeypatch)
    response = agent().act(request())
    url, wire = calls[0]
    assert url == "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
    assert wire["headers"] == {"Authorization": f"Bearer {SECRET}",
                               "Content-Type": "application/json", "Accept": "application/json"}
    assert set(wire["json"]) == {"messages"}
    assert '"turn_id": 0' in wire["json"]["messages"][1]["content"]
    assert '"turn_id": 99' in wire["json"]["messages"][1]["content"]
    assert wire["timeout"].read is None
    assert response.action == 1
    receipt = response.metadata["provider_receipt"]
    assert receipt["provider"] == "naver" and receipt["model"] == "HCX-007"
    assert receipt["locked_model_id"] == "HCX-007"
    assert receipt["model_identity_source"] == "pinned_endpoint"
    assert receipt["provider_response_id"] is None
    assert receipt["request_id"] == "naver-request"
    assert receipt["endpoint_region"] == "Korea"
    usage = receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (58, 631, 689)
    assert usage["reasoning_tokens"] == 366 and usage["reasoning_included_in_output"] is True
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert SECRET not in json.dumps(response.to_dict())
    assert "Private synthetic" not in json.dumps(response.to_dict())


@pytest.mark.parametrize("mode,effort,expected", [
    ("auto", None, None), ("disabled", None, "none"), ("enabled", None, "low"),
    ("auto", "none", "none"), ("enabled", "low", "low"),
    ("auto", "medium", "medium"), ("auto", "high", "high"),
])
def test_reasoning_is_explicit_and_native(monkeypatch, mode, effort, expected):
    calls = mock_post(monkeypatch)
    config = ProviderRuntimeConfig(reasoning=mode, reasoning_effort=effort)
    agent(runtime_config=config).act(request())
    assert calls[0][1]["json"].get("thinking") == (
        {"effort": expected} if expected is not None else None
    )


@pytest.mark.parametrize("model", ["HCX-007", "HCX-005", "HCX-DASH-002", "Future:Exact/ID"])
def test_exact_model_and_explicit_limits(monkeypatch, model):
    calls = mock_post(monkeypatch)
    response = agent(model, max_output_tokens=3456, temperature=0.3).act(request())
    wire = calls[0][1]["json"]
    field = "maxCompletionTokens" if model == "HCX-007" else "maxTokens"
    assert wire[field] == 3456 and wire["temperature"] == 0.3
    assert response.metadata["model"] == model
    assert response.metadata["provider_receipt"]["locked_model_id"] == model
    if model.startswith("Future"):
        assert calls[0][0].endswith("Future%3AExact%2FID")


@pytest.mark.parametrize("model", [None, "", " ", " HCX-007", "HCX-007 ", ".", ".."])
def test_missing_model_rejected_every_entrypoint(model):
    with pytest.raises(ValueError, match="model ID"):
        agent(model)
    with pytest.raises(ValueError, match="model ID"):
        provider_preflight("naver", model, "tic-tac-toe")


@pytest.mark.parametrize("options", [
    {"reasoning_effort": "minimal"}, {"reasoning_effort": "HIGH"},
    {"reasoning_budget_tokens": 10}, {"gemini_thinking_budget": -1},
    {"reasoning": "enabled", "reasoning_effort": "none"},
])
def test_unsupported_reasoning_rejected(options):
    with pytest.raises(ValueError, match="NAVER"):
        agent(runtime_config=ProviderRuntimeConfig(**options))


@pytest.mark.parametrize("mode", ["disabled", "enabled"])
def test_nonreasoning_model_controls_rejected(mode):
    with pytest.raises(ValueError, match="HCX-007"):
        agent("HCX-005", runtime_config=ProviderRuntimeConfig(reasoning=mode))


def test_gateway_does_not_attest_identity(monkeypatch):
    calls = mock_post(monkeypatch)
    response = agent(runtime_config=ProviderRuntimeConfig(
        gateway_base_url="https://gateway.example.test", gateway_mode="generic_base_url",
    )).act(request())
    assert calls[0][0] == "https://gateway.example.test/v3/chat-completions/HCX-007"
    receipt = response.metadata["provider_receipt"]
    assert receipt["locked_model_id"] is None and receipt["model_identity_source"] is None
    assert receipt["endpoint_region"] is None


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503, 504])
@pytest.mark.parametrize("http_error", [True, False])
def test_errors_no_retry_no_action_no_credential_echo(monkeypatch, status, http_error):
    payload = {"status": {"code": f"{status}00", "message": SECRET}}
    calls = mock_post(monkeypatch, payload, status if http_error else 200,
                      **{"x-request-id": SECRET, "cf-aig-request-id": SECRET})
    adapter = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert len(calls) == 1
    expected = {401: "provider_auth_failed", 403: "provider_permission_failed",
                429: "provider_rate_limited"}.get(status,
                    "provider_unavailable" if status == 404 or status >= 500
                    else "provider_request_rejected")
    assert caught.value.error_kind == expected
    assert not caught.value.retry_permitted
    assert not adapter.last_receipt["usage"]
    assert adapter.last_receipt["locked_model_id"] is None
    assert SECRET not in json.dumps(adapter.attempt_receipts) + str(caught.value)


@pytest.mark.parametrize("reason,kind", [("length", "provider_output_truncated"),
    ("tool_calls", "provider_request_rejected"), (None, "provider_response_schema_mismatch"),
    ("unexpected", "provider_response_schema_mismatch")])
def test_finish_checked_before_parse_preserves_usage(monkeypatch, reason, kind):
    payload = fixture()
    payload["result"]["finishReason"] = reason
    calls = mock_post(monkeypatch, payload)
    adapter = agent(runtime_config=ProviderRuntimeConfig(action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert caught.value.error_kind == kind and len(calls) == 1
    assert adapter.last_receipt["usage"]["total_tokens"] == 689


@pytest.mark.parametrize("field", ["content", "escaped_content", "usage", "headers", "thinking"])
def test_success_credential_echo_never_reaches_public_fields(monkeypatch, field):
    payload = fixture()
    headers = {}
    if field in {"content", "escaped_content"}:
        text = SECRET if field == "content" else "".join(f"\\u{ord(c):04x}" for c in SECRET)
        payload["result"]["message"]["content"] = (
            '{"action":1,"public_explanation":"' + text + '"}'
        )
    elif field == "usage":
        payload["result"]["usage"]["promptTokens"] = SECRET
    elif field == "thinking":
        payload["result"]["message"]["thinkingContent"] = SECRET
    else:
        headers = {"x-ncp-clovastudio-request-id": SECRET, "cf-aig-request-id": SECRET}
    mock_post(monkeypatch, payload, **headers)
    adapter = agent()
    if field in {"content", "escaped_content"}:
        with pytest.raises(ProviderCallError) as caught:
            adapter.act(request())
        public = str(caught.value)
    else:
        public = json.dumps(adapter.act(request()).to_dict())
    assert SECRET not in public + json.dumps(adapter.attempt_receipts)


def test_missing_usage_and_identity_never_fabricated(monkeypatch):
    payload = fixture()
    del payload["result"]["usage"]
    mock_post(monkeypatch, payload)
    response = agent().act(request())
    receipt = response.metadata["provider_receipt"]
    assert receipt["usage"] == {} and receipt["usage_unavailable_reason"] == "provider_usage_absent"
    assert receipt["provider_response_id"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("body", [b"not json", b"{}", b"[]",
    f"invalid JSON containing {SECRET}".encode(),
    b'{"status":{"code":"20000","code":"42900"}}'])
def test_malformed_envelopes_are_safe(monkeypatch, body):
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k:
        httpx.Response(200, content=body, headers={"x-ncp-clovastudio-request-id": SECRET}))
    adapter = agent()
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert SECRET not in json.dumps(adapter.attempt_receipts) + str(caught.value)


def test_deeply_nested_action_json_fails_with_a_receipt(monkeypatch):
    payload = fixture()
    payload["result"]["message"]["content"] = "[" * 1500 + "0" + "]" * 1500
    mock_post(monkeypatch, payload)
    adapter = agent()
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert caught.value.error_kind == "provider_response_schema_mismatch"
    assert adapter.last_receipt["usage"]["total_tokens"] == 689


@pytest.mark.parametrize("status", [200, 429, 503])
@pytest.mark.parametrize("failure", ["timeout", "reset", "oversize"])
def test_actual_partial_reader_receipts_are_safe(monkeypatch, status, failure):
    calls = []
    original_client = httpx.AsyncClient

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('{"secret":"' + SECRET + '",').encode()
            if failure == "timeout":
                raise httpx.ReadTimeout(SECRET)
            if failure == "reset":
                raise httpx.ReadError(SECRET)
            yield b"x" * (1024 * 1024 + 1)

    def respond(req):
        calls.append(req)
        return httpx.Response(status, stream=Stream(), request=req, headers={
            "x-ncp-clovastudio-request-id": "safe-native-request", "cf-aig-request-id": SECRET,
        })

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            async with (original_client(transport=httpx.MockTransport(respond)) as client,
                        client.stream(method, url, **kwargs) as response):
                yield response

    monkeypatch.setattr(http_io.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)
    adapter = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError):
        adapter.act(request())
    receipt = adapter.last_receipt
    assert len(calls) == 1 and receipt["status_code"] == status
    assert receipt["request_id"] == "safe-native-request"
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert SECRET not in json.dumps(adapter.attempt_receipts)


def test_timeout_without_headers_never_retries(monkeypatch):
    calls = []

    def post(*a, **k):
        calls.append(1)
        raise httpx.ReadTimeout(SECRET)
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    adapter = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(TimeoutError):
        adapter.act(request())
    assert len(calls) == 1 and SECRET not in json.dumps(adapter.attempt_receipts)


@pytest.mark.parametrize("case", ["redirect", "native_timeout", "tool", "content_type"])
def test_additional_native_boundaries(monkeypatch, case):
    payload = fixture()
    status = 200
    if case == "redirect":
        status = 302
    elif case == "native_timeout":
        payload["status"]["code"] = "40800"
    elif case == "tool":
        payload["result"]["message"]["toolCalls"] = [{"name": "search"}]
    else:
        payload["result"]["message"]["content"] = [{"text": '{"action":1}'}]
    calls = mock_post(monkeypatch, payload, status)
    with pytest.raises(ProviderCallError) as caught:
        agent().act(request())
    assert len(calls) == 1
    if case == "native_timeout":
        assert caught.value.error_kind == "provider_timeout"


@pytest.mark.parametrize("case", ["echo", "truncated", "error_with_usage", "http_error_with_usage"])
def test_failed_artifacts_retain_receipts_and_never_apply_action(monkeypatch, tmp_path, case):
    payload = fixture()
    if case == "echo":
        payload["result"]["message"]["content"] = json.dumps(
            {"action": 1, "public_explanation": SECRET},
        )
    elif case == "truncated":
        payload["result"]["finishReason"] = "length"
    else:
        payload["status"] = {"code": "42900", "message": SECRET}
    calls = mock_post(monkeypatch, payload, 429 if case == "http_error_with_usage" else 200)
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=agent(),
        on_agent_error="forfeit", output_dir=tmp_path))
    assert len(calls) == 1 and not result.score.match_valid_for_scoring
    receipts = [json.loads(line) for line in (result.expanded_path /
        "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(receipts) == 1 and not receipts[0]["action_applied"]
    assert receipts[0]["usage"]["total_tokens"] == 689
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes()


def test_foreign_error_contract_cannot_enable_retries(monkeypatch):
    calls = mock_post(monkeypatch, {"error": {"code": "rate_limit_exceeded"}}, 429)
    adapter = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert len(calls) == 1 and not caught.value.retry_permitted


def test_cli_and_offline_preflight_never_call_inference(monkeypatch, capsys):
    monkeypatch.delenv("CLOVASTUDIO_API_KEY", raising=False)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("network"))
    assert _provider_agent("naver:HCX-007").model == "HCX-007"
    for name in ("naver", "naver:", "naver: "):
        with pytest.raises(ValueError, match="model ID"):
            _provider_agent(name)
    assert main(["providers", "preflight", "--provider", "naver", "--model", "HCX-007",
                 "--arena", "tic-tac-toe"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["checks"]["adapter_available"]
    assert not result["checks"]["minimal_inference"]
    assert provider_models_live("naver") is None


def test_live_preflight_mock_and_cli_run_artifact(monkeypatch, capsys, tmp_path):
    def post(url, **kwargs):
        prompt = kwargs["json"]["messages"][1]["content"]
        data = json.loads(prompt[prompt.index('{"action_schema"'):])
        payload = fixture()
        payload["result"]["message"]["content"] = json.dumps({"action": data["legal_actions"][0]})
        return httpx.Response(200, json=payload)

    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    result = provider_preflight("naver", "HCX-007", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["usage_extraction"]
    assert result["checks"]["account_model_visible"] is None
    assert main(["run", "--arena", "tic-tac-toe", "--agent", "naver:HCX-007",
                 "--opponent", "first-legal", "--output-dir", str(tmp_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert ArtifactValidator().validate(Path(output["artifact"])) == []
