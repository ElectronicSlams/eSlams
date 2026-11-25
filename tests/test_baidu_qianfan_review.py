"""Cross-adapter review regressions for Qianfan admission and credential custody."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
import pytest
from test_baidu_qianfan import ALIASES, MODEL, SECRET, agent, install, request, wire

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.runner import RunConfig, Runner

SECONDARY = "secondary-credential-must-not-be-published"


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("model", [None, "", " ", "\t\n", 123])
def test_model_must_be_nonblank_before_registry_preflight_or_transport(monkeypatch, alias, model):
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    with pytest.raises(ValueError, match="explicit nonblank model"):
        ModelProviderAgent(alias, model, "QIANFAN_API_KEY")
    with pytest.raises(ValueError, match="explicit nonblank model"):
        provider_preflight(alias, model, "tic-tac-toe", live=True)


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("suffix", ["", ":", ": ", ":\t"])
def test_cli_never_defaults_missing_or_blank_models(alias, suffix):
    with pytest.raises(ValueError, match="explicit.*model"):
        _provider_agent(alias + suffix)


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("model,config", [
    (MODEL, {"reasoning_budget_tokens": 1024}),
    ("deepseek-v4-pro", {"reasoning_budget_tokens": 1024}),
    ("ernie-5.1", {"reasoning_budget_tokens": 0}),
    ("ernie-5.1", {"reasoning_budget_tokens": 99}),
    ("ernie-5.1", {"gemini_thinking_budget": 1024}),
])
def test_preflight_rejects_unsupported_budget_before_discovery_or_inference(
    monkeypatch, alias, live, model, config,
):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    runtime = ProviderRuntimeConfig(**config)
    result = provider_preflight(alias, model, "tic-tac-toe", live=live, runtime_config=runtime)
    assert result["ok"] is False
    assert result["readiness"]["configuration_ready"] is False
    assert result["readiness"]["inference"] == "not_attempted"
    assert result["error"]["error_class"] == "provider_request_rejected"
    with pytest.raises(ProviderCallError) as exc:
        agent(alias, model, runtime_config=runtime).act(request())
    assert exc.value.error_kind == "provider_request_rejected"


def test_supported_budget_remains_exact_and_preflight_admits_it(monkeypatch):
    calls = install(monkeypatch)
    runtime = ProviderRuntimeConfig(reasoning_budget_tokens=1537)
    result = provider_preflight("qianfan", "ernie-5.1", "tic-tac-toe", runtime_config=runtime)
    assert result["ok"] is True and calls == []
    agent(model="ernie-5.1", runtime_config=runtime).act(request())
    assert calls[0][1]["json"]["thinking_budget"] == 1537


@pytest.mark.parametrize("field", ["id", "model", "x-request-id", "cf-aig-request-id",
                                   "x-gateway-request-id"])
@pytest.mark.parametrize("credential", [SECRET, SECONDARY])
@pytest.mark.parametrize("mode", ["success", "http_error", "body_error", "malformed"])
def test_echoed_identifiers_never_enter_success_or_error_receipts(
    monkeypatch, field, credential, mode,
):
    payload = wire()
    headers = {"x-request-id": "safe-request", "cf-aig-request-id": "safe-gateway"}
    echoed = f"prefix-{credential}-suffix"
    if field in {"id", "model"}:
        payload[field] = echoed
    else:
        headers.pop("cf-aig-request-id", None)
        headers[field] = echoed
    if mode in {"http_error", "body_error"}:
        payload["error"] = {"type": "rate_limit_exceeded", "code": "rpm_rate_limit_exceeded",
                            "message": f"private-error {SECRET} {SECONDARY}"}
    elif mode == "malformed":
        payload["choices"] = "malformed"
    calls = install(monkeypatch, payload, 429 if mode == "http_error" else 200, headers)
    monkeypatch.setenv("QIANFAN_SECRET_KEY", SECONDARY)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    if mode == "success":
        result = native.act(request())
        assert result.action == 1
        public = json.dumps(result.to_dict())
    else:
        with pytest.raises(ProviderCallError) as exc:
            native.act(request())
        public = str(exc.value) + json.dumps(exc.value.receipt)
    public += json.dumps(native.last_receipt) + json.dumps(native.attempt_receipts)
    assert SECRET not in public and SECONDARY not in public
    assert len(calls) == len(native.attempt_receipts) == 1
    target = {"id": "provider_response_id", "model": "locked_model_id",
              "x-request-id": "request_id", "cf-aig-request-id": "gateway_request_id",
              "x-gateway-request-id": "gateway_request_id"}[field]
    assert native.last_receipt.get(target) is None
    if field == "model":
        assert native.last_receipt["model_identity_source"] is None
    assert native.last_receipt["usage"]["total_tokens"] == 26


@pytest.mark.parametrize("mode", ["invalid_json", "partial_timeout", "partial_reset", "oversize"])
@pytest.mark.parametrize("credential", [SECRET, SECONDARY])
def test_actual_reader_failures_scrub_headers_before_receipt_publication(
    monkeypatch, mode, credential,
):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    monkeypatch.setenv("QIANFAN_SECRET_KEY", SECONDARY)
    original_client = httpx.AsyncClient
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"private":'
            if mode == "partial_timeout":
                raise httpx.ReadTimeout(f"private {credential}")
            if mode == "partial_reset":
                raise httpx.ReadError(f"private {credential}")
            if mode == "oversize":
                yield b"x" * (1024 * 1024 + 1)

    def respond(req):
        calls.append(req)
        return httpx.Response(200, stream=Stream(), request=req, headers={
            "x-request-id": f"prefix-{credential}", "cf-aig-request-id": credential,
        })

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
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    receipt = native.last_receipt
    public = str(exc.value) + json.dumps(exc.value.receipt) + json.dumps(native.attempt_receipts)
    assert SECRET not in public and SECONDARY not in public
    assert receipt["request_id"] is None and receipt["gateway_request_id"] is None
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert receipt["status_code"] == 200 and len(calls) == 1


def test_custom_key_environment_also_protects_the_secondary_standard_key(monkeypatch):
    payload = wire()
    payload["id"] = SECONDARY
    calls = install(monkeypatch, payload, headers={"x-request-id": SECRET})
    monkeypatch.setenv("QIANFAN_API_KEY", SECONDARY)
    monkeypatch.setenv("SELECTED_QIANFAN_KEY", SECRET)
    native = ModelProviderAgent("baidu", MODEL, "SELECTED_QIANFAN_KEY")
    result = native.act(request())
    assert calls[0][1]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in json.dumps(result.to_dict())
    assert SECONDARY not in json.dumps(result.to_dict())
    assert native.last_receipt["request_id"] is None
    assert native.last_receipt["provider_response_id"] is None


@pytest.mark.parametrize("credential", [SECRET, SECONDARY])
def test_credential_in_final_text_is_rejected_before_action_parsing(monkeypatch, credential):
    payload = wire()
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": credential,
    })
    calls = install(monkeypatch, payload)
    monkeypatch.setenv("QIANFAN_SECRET_KEY", SECONDARY)
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1
    assert credential not in str(exc.value) + json.dumps(native.last_receipt)


def test_encoded_secondary_credential_is_scrubbed(monkeypatch):
    secondary = "bce-v3/ALTAK-secondary/secret/value"
    payload = wire()
    payload["choices"][0]["message"]["content"] = json.dumps({
        "action": 1, "public_explanation": quote(secondary, safe=""),
    })
    install(monkeypatch, payload)
    monkeypatch.setenv("QIANFAN_SECRET_KEY", secondary)
    with pytest.raises(ProviderCallError):
        agent().act(request())


@pytest.mark.parametrize("credential", [SECRET, SECONDARY])
def test_discovery_rejects_credential_echo_instead_of_publishing_it(monkeypatch, credential):
    monkeypatch.setenv("QIANFAN_API_KEY", SECRET)
    monkeypatch.setenv("QIANFAN_SECRET_KEY", SECONDARY)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
                        httpx.Response(200, json={"data": [{"id": credential}]}))
    result = provider_models_result("qianfan")
    assert result["ok"] is False and result["models"] == []
    assert result["error"]["error_class"] == "provider_response_schema_mismatch"
    assert credential not in json.dumps(result)


def test_runner_artifacts_contain_neither_primary_nor_secondary_echo(monkeypatch, tmp_path):
    payload = wire()
    payload["model"] = SECRET
    payload["id"] = SECONDARY
    payload["choices"][0]["finish_reason"] = "content_filter"
    install(monkeypatch, payload, headers={"x-request-id": SECONDARY, "cf-aig-request-id": SECRET})
    monkeypatch.setenv("QIANFAN_SECRET_KEY", SECONDARY)
    native = agent()
    result = Runner().run(RunConfig("tic-tac-toe", agent_1=native, output_dir=tmp_path))
    assert ArtifactValidator().validate(result.expanded_path) == []
    assert result.score.match_valid_for_scoring is False
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            public = path.read_bytes()
            assert SECRET.encode() not in public and SECONDARY.encode() not in public


def test_cli_blank_model_diagnostic_is_ordinary_configuration_error(capsys):
    assert main(["run", "--agent", "qianfan:   "]) == 1
    assert "nonblank model" in capsys.readouterr().err
