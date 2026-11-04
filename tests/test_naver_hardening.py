"""Cross-adapter regressions applied independently to NAVER's native contract."""

import json
import traceback
from contextlib import asynccontextmanager

import httpx
import pytest
from test_naver_provider import SECRET, agent, fixture, request

from eslams import http_io
from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.protocol import ProtocolError
from eslams.provider_preflight import (
    provider_models_live,
    provider_models_result,
    provider_preflight,
)

CREDENTIALS = {
    "NAVER_FIXTURE_KEY": SECRET,
    "CLOVASTUDIO_API_KEY": "canonicalOpaqueCredential",
    "NCP_CLOVASTUDIO_API_KEY": "legacyOpaqueCredential",
    "NCP_APIGW_API_KEY": "gatewayOpaqueCredential",
}


def configure(monkeypatch):
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)
    return ModelProviderAgent("naver", "HCX-007", "NAVER_FIXTURE_KEY",
        runtime_config=ProviderRuntimeConfig(max_retries=2))


def assert_private(value):
    serialized = json.dumps(value)
    assert all(secret not in serialized for secret in CREDENTIALS.values())


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("options", [
    {"reasoning_budget_tokens": 0}, {"reasoning_budget_tokens": 1024},
    {"gemini_thinking_budget": -1}, {"gemini_thinking_budget": 1024},
])
def test_explicit_budgets_rejected_in_preflight_before_any_network(monkeypatch, live, options):
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", SECRET)
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **k: pytest.fail("transport"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("discovery"))
    config = ProviderRuntimeConfig(**options)
    with pytest.raises(ValueError, match="NAVER does not support reasoning token budgets"):
        provider_preflight("naver", "HCX-007", "tic-tac-toe", live=live, runtime_config=config)
    with pytest.raises(ValueError, match="NAVER does not support reasoning token budgets"):
        agent(runtime_config=config)
    adapter = agent()
    adapter.runtime_config = config
    with pytest.raises(ValueError, match="NAVER does not support reasoning token budgets"):
        adapter.act(request())


@pytest.mark.parametrize("name", CREDENTIALS)
@pytest.mark.parametrize("scenario", ["ids", "action", "escaped_action", "http_error",
                                      "native_error", "malformed", "transport_error"])
def test_every_configured_credential_protected_across_response_paths(monkeypatch, name, scenario):
    adapter = configure(monkeypatch)
    secret = CREDENTIALS[name]
    payload = fixture()
    calls = []
    if scenario in {"action", "escaped_action"}:
        echo = secret if scenario == "action" else "".join(f"\\u{ord(c):04x}" for c in secret)
        payload["result"]["message"]["content"] = '{"action":1,"public_explanation":"' + echo + '"}'
    if scenario in {"http_error", "native_error"}:
        payload["status"] = {"code": "42900", "message": secret}
        payload["id"] = secret

    def post(url, **kwargs):
        calls.append(kwargs)
        assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET}"
        wire = json.dumps({key: kwargs[key] for key in ("headers", "json")})
        assert not any(value in wire for key, value in CREDENTIALS.items()
                       if key != "NAVER_FIXTURE_KEY")
        if scenario == "transport_error":
            raise ProtocolError(secret)
        headers = {"x-request-id": secret, "x-ncp-clovastudio-request-id": secret,
                   "cf-aig-request-id": secret, "x-gateway-request-id": secret}
        if scenario == "malformed":
            return httpx.Response(200, content=f"malformed {secret}", headers=headers)
        return httpx.Response(429 if scenario == "http_error" else 200,
                              json=payload, headers=headers)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    if scenario == "ids":
        assert_private(adapter.act(request()).to_dict())
    else:
        with pytest.raises(ProviderCallError) as caught:
            adapter.act(request())
        assert not caught.value.retry_permitted
        assert_private(str(caught.value))
        assert_private("".join(traceback.format_exception(caught.value)))
    assert len(calls) == 1
    assert_private(adapter.attempt_receipts)


@pytest.mark.parametrize("name", CREDENTIALS)
@pytest.mark.parametrize("status", [200, 429, 503])
def test_partial_native_ids_scrub_all_credentials(monkeypatch, name, status):
    adapter = configure(monkeypatch)
    secret = CREDENTIALS[name]
    original_client = httpx.AsyncClient
    calls = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('{"private":"' + secret + '",').encode()
            raise httpx.ReadError(secret)

    def respond(req):
        calls.append(req)
        return httpx.Response(status, stream=Stream(), request=req,
            headers={"x-request-id": secret, "x-ncp-clovastudio-request-id": secret,
                     "cf-aig-request-id": secret})

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
    with pytest.raises(ProviderCallError) as caught:
        adapter.act(request())
    assert len(calls) == 1 and not caught.value.retry_permitted
    assert adapter.last_receipt["usage"] == {}
    assert adapter.last_receipt["status_code"] == status
    assert_private(adapter.attempt_receipts)
    assert_private(str(caught.value))


def test_discovery_exposes_no_credentials_and_never_uses_network(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("network"))
    assert provider_models_live("naver") is None
    result = provider_models_result("naver")
    assert not result["ok"] and result["models"] == []
    assert result["error"]["error_class"] == "provider_discovery_unavailable"
    assert_private(result)
    assert_private(provider_preflight("naver", "HCX-007", "tic-tac-toe"))
