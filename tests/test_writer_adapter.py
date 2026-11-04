"""Writer raw REST contract and deterministic fault injection; never live inference."""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.cli import _provider_agent, main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.execution_policy import model_execution_policy
from eslams.http_io import bounded_post
from eslams.provider_preflight import provider_models_live, provider_preflight
from eslams.providers import load_provider_registry
from eslams.providers.writer import API_KEY_ENV, CHAT_ENDPOINT, MODELS_ENDPOINT
from eslams.runner import RunConfig, Runner


@pytest.fixture
def wire():
    return json.loads((Path(__file__).parent / "fixtures/provider/writer_chat_success.json")
                      .read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, "synthetic-writer-key")
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: pytest.fail("unexpected network call"))
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: pytest.fail("unexpected model discovery"))


def request():
    return replace(_request(), protocol_version="eslams-act-v2", time_budget_ms=None,
                   metadata={"model_execution_policy": model_execution_policy(None)})


def agent(**kwargs):
    return ModelProviderAgent("writer", "palmyra-x5", API_KEY_ENV, **kwargs)


def respond(monkeypatch, payload, status=200, headers=None):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(status, content=(payload if isinstance(payload, bytes) else
                              json.dumps(payload).encode()), headers=headers,
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", ["writer", "writer-ai", "writerai", "WRITER"])
def test_alias_cli_registry_preflight_and_dispatch(monkeypatch, wire, alias):
    calls = respond(monkeypatch, wire)
    native = _provider_agent(f"{alias}:palmyra-x5")
    assert native.provider == "writer" and native.model == "palmyra-x5"
    assert native.api_key_env == API_KEY_ENV
    assert load_provider_registry().resolve(alias, "palmyra-x5").provider == "writer"
    assert provider_preflight(alias, "palmyra-x5", "connect-four")["ok"]
    assert ModelProviderAgent(alias, "palmyra-x5", API_KEY_ENV).act(request()).action == 0
    assert calls[0][0] == CHAT_ENDPOINT
    assert native.act(request()).action == 0
    assert native.last_receipt["provider"] == "writer"


def test_request_exact_model_full_history_native_defaults(monkeypatch, wire):
    calls = respond(monkeypatch, wire)
    native = ModelProviderAgent("writer", "org/model:Exact-ID", API_KEY_ENV)
    req = replace(request(), history=[{"turn_id": i, "action": i % 3} for i in range(180)])
    assert native.act(req).action == 0
    url, args = calls[0]
    assert url == CHAT_ENDPOINT
    assert args["headers"] == {"Authorization": "Bearer synthetic-writer-key",
                               "Content-Type": "application/json"}
    body = args["json"]
    assert set(body) == {"model", "messages", "stream"}
    assert body["model"] == "org/model:Exact-ID" and body["stream"] is False
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    public = json.loads(body["messages"][1]["content"].splitlines()[-1])
    assert public["history"] == req.history
    assert args["timeout"].read is None
    assert native.last_receipt["model"] == "org/model:Exact-ID"
    assert native.last_receipt["locked_model_id"] == "palmyra-x5"


def test_explicit_operator_controls_and_gateway(monkeypatch, wire):
    calls = respond(monkeypatch, wire)
    native = agent(temperature=0.2, max_output_tokens=777,
                   runtime_config=ProviderRuntimeConfig(timeout_ms=25000,
                       gateway_base_url="https://gateway.example/writer"))
    native.act(request())
    assert calls[0][0] == "https://gateway.example/writer/v1/chat"
    assert calls[0][1]["json"]["temperature"] == 0.2
    assert calls[0][1]["json"]["max_tokens"] == 777
    assert calls[0][1]["timeout"].read <= 25


@pytest.mark.parametrize("runtime", [ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=4000),
    ProviderRuntimeConfig(gemini_thinking_budget=100),
    ProviderRuntimeConfig(reasoning="enabled"), ProviderRuntimeConfig(reasoning="disabled")])
def test_unsupported_reasoning_control_fails_before_submission(runtime):
    native = agent(runtime_config=runtime)
    with pytest.raises(ProviderCallError, match="no documented reasoning control"):
        native.act(request())
    assert native.last_receipt["locked_model_id"] is None


def test_success_receipt_usage_identity_and_privacy(monkeypatch, wire):
    wire["choices"][0]["message"]["reasoning_content"] = "private-reasoning-marker"
    wire["choices"][0]["message"]["llm_data"] = {"prompt": "private-prompt-marker"}
    respond(monkeypatch, wire, headers={"x-request-id": "writer-request-1",
                                     "set-cookie": "private-cookie-marker"})
    native = agent()
    assert native.act(request()).action == 0
    receipt = native.last_receipt
    assert receipt["endpoint_kind"] == "writer_chat"
    assert receipt["parser_version"] == "writer-chat-raw-v1"
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["request_id"] == "writer-request-1"
    assert receipt["provider_response_id"] == wire["id"]
    assert receipt["finish_reason"] == "stop" and receipt["finish_status"] == "completed"
    usage = receipt["usage"]
    assert [usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")] == [40,300,340]
    assert usage["cached_input_tokens"] == usage["reasoning_tokens"] == 0
    assert usage["reasoning_included_in_output"] is None
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert len(native.attempt_receipts) == 1
    serialized = json.dumps(receipt)
    for secret in ("synthetic-writer-key", "private-reasoning-marker", "private-prompt-marker",
                   "private-cookie-marker", "Authorization", "Select a legal action"):
        assert secret not in serialized


@pytest.mark.parametrize("detail_key", ["completion_token_details", "completion_tokens_details"])
def test_reasoning_details_no_double_count_or_invented_inclusion(monkeypatch, wire, detail_key):
    wire["usage"].pop("completion_token_details")
    wire["usage"][detail_key] = {"reasoning_tokens": 100}
    wire["usage"]["prompt_token_details"] = {"cached_tokens": 7}
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    usage = native.last_receipt["usage"]
    assert usage["reasoning_tokens"] == 100 and usage["total_tokens"] == 340
    assert usage["cached_input_tokens"] == 7
    assert usage["reasoning_included_in_output"] is None
    assert "reasoning_inclusion_unknown" in usage["usage_validation_errors"]


@pytest.mark.parametrize("missing", ["usage", "model", "id"])
def test_absent_accounting_or_identity_remains_unknown(monkeypatch, wire, missing):
    wire.pop(missing)
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    receipt = native.last_receipt
    if missing == "usage":
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    elif missing == "model":
        assert receipt["locked_model_id"] is receipt["model_identity_source"] is None
    else:
        assert receipt["provider_response_id"] is None


@pytest.mark.parametrize("reason,refusal,kind", [
    ("length", None, "provider_output_truncated"),
    ("content_filter", None, "provider_refused"),
    ("stop", "private-refusal-marker", "provider_refused"),
    ("tool_calls", None, "provider_request_rejected"),
    ("future_reason", None, "provider_response_schema_mismatch"),
    (None, None, "provider_response_schema_mismatch"),
])
def test_finish_rejects_even_parseable_action_retains_usage(
    monkeypatch, wire, reason, refusal, kind,
):
    wire["choices"][0]["finish_reason"] = reason
    wire["choices"][0]["message"]["refusal"] = refusal
    calls = respond(monkeypatch, wire)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == native.last_receipt["outcome"] == kind
    assert native.last_receipt["usage"]["total_tokens"] == 340 and len(calls) == 1
    assert "private-refusal-marker" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("status,kind", [(400,"provider_request_rejected"),
    (401,"provider_auth_failed"), (403,"provider_permission_failed"),
    (404,"provider_unavailable"), (429,"provider_rate_limited"),
    (500,"provider_unavailable"), (503,"provider_unavailable")])
def test_documented_http_error_envelope_sanitized_no_retry(monkeypatch, status, kind):
    calls = respond(monkeypatch, {"tpe": "TooManyRequests" if status == 429 else "BadRequest",
        "errors": [{"description": "private-error-marker synthetic-writer-key",
                    "key": "error.message.key", "extras": {}}], "extras": {}},
        status=status, headers={"Retry-After": "2", "x-request-id": "writer-error-1"})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == kind and len(calls) == 1
    receipt = native.last_receipt
    assert receipt["request_id"] == "writer-error-1"
    assert receipt["retry_after_ms"] == 2000
    assert receipt["locked_model_id"] is None and receipt["usage"] == {}
    assert "private-error-marker" not in str(exc.value) + json.dumps(receipt)
    assert "synthetic-writer-key" not in str(exc.value) + json.dumps(receipt)


def test_200_error_is_not_success_or_verified_identity(monkeypatch):
    respond(monkeypatch, {"tpe": "InternalServerError", "errors": [], "extras": {},
                         "model": "unverified-model"})
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_unavailable"
    assert native.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("payload", [b'not-json', b'{"choices": [], "choices": []}',
    b'[]', b'{"object":"chat.completion","choices":[]}',
    b'{"object":"chat.completion","choices":[{"message":{"role":"assistant","content":[]}}]}'])
def test_malformed_raw_bodies_fail_closed(monkeypatch, payload):
    respond(monkeypatch, payload)
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch"
    assert len(native.attempt_receipts) == 1


@pytest.mark.parametrize("error,kind", [(httpx.ReadTimeout("private-timeout"), "provider_timeout"),
    (httpx.ConnectError("private-transport"), "provider_transport_error")])
def test_transport_failures_never_replayed(monkeypatch, error, kind):
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises((ProviderCallError, TimeoutError)):
        native.act(request())
    assert len(calls) == 1 and native.last_receipt["outcome"] == kind
    assert "private-" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("alias", ["writer", "writer-ai", "writerai"])
def test_models_discovery_and_mock_live_preflight(monkeypatch, wire, alias):
    discovered = []
    def get(url, **kwargs):
        discovered.append((url, kwargs))
        return httpx.Response(200, json={"models": [{"id":"palmyra-x5", "name":"Palmyra X5"}]})
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    assert provider_models_live(alias) == ["palmyra-x5"]
    assert discovered[0][0] == MODELS_ENDPOINT
    assert discovered[0][1]["headers"]["Authorization"] == "Bearer synthetic-writer-key"
    # Preflight tic-tac-toe actions are objects, so use its observed legal action.
    offline = provider_preflight(alias, "palmyra-x5", "tic-tac-toe")
    wire["choices"][0]["message"]["content"] = json.dumps(
        {"action": offline["sample_legal_action"]})
    respond(monkeypatch, wire)
    result = provider_preflight(alias, "palmyra-x5", "tic-tac-toe", live=True)
    assert result["ok"] and result["checks"]["account_model_visible"]
    assert result["checks"]["usage_extraction"]


def test_cli_configuration_is_offline_and_default_is_documented(monkeypatch, capsys):
    monkeypatch.delenv(API_KEY_ENV)
    with pytest.raises(ValueError, match="explicit nonempty model"):
        _provider_agent("writer")
    assert _provider_agent("writer:palmyra-x6").model == "palmyra-x6"
    assert main(["providers", "preflight", "--provider", "writer-ai", "--model", "palmyra-x5",
                 "--arena", "connect-four"]) == 0
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"]


def test_conflicting_reasoning_details_are_not_silently_selected(monkeypatch, wire):
    wire["usage"]["completion_tokens_details"] = {"reasoning_tokens": 80}
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    assert native.last_receipt["usage"]["reasoning_tokens"] is None
    assert "reasoning_tokens_invalid" in native.last_receipt["usage"]["usage_validation_errors"]


def test_missing_usage_never_learns_from_private_message(monkeypatch, wire):
    wire.pop("usage")
    wire["choices"][0]["message"]["usage"] = {"prompt_tokens": 5, "completion_tokens": 2}
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    assert native.last_receipt["usage"] == {}


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_failed_generation_is_receipted_but_never_applied_or_scored(
    monkeypatch, wire, tmp_path, reason,
):
    wire["choices"][0]["finish_reason"] = reason
    wire["choices"][0]["message"]["refusal"] = "private-refusal-marker"
    respond(monkeypatch, wire)
    result = Runner().run(RunConfig("connect-four", agent_1=agent(), output_dir=tmp_path))
    rows = [json.loads(line) for line in (result.expanded_path /
            "receipts/provider_receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["usage"]["total_tokens"] == 340
    assert all(event.action is None for event in result.replay_events)
    assert not result.score.match_valid_for_scoring and result.score.winner is None
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert b"private-refusal-marker" not in data and b"synthetic-writer-key" not in data


@pytest.mark.parametrize("raw", [b"not-json", b"[]", b'{"data": []}',
                               b'{"models": [{"name":"missing-id"}]}'])
def test_malformed_model_discovery_is_not_account_visibility(monkeypatch, raw):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **k: httpx.Response(200, content=raw))
    with pytest.raises(ProviderCallError) as exc:
        provider_models_live("writer-ai")
    assert exc.value.error_kind == "provider_response_schema_mismatch"


def test_missing_or_invalid_credential_never_submits(monkeypatch):
    for value in ("", "bad key"):
        monkeypatch.setenv(API_KEY_ENV, value)
        native = agent()
        with pytest.raises(ProviderCallError) as exc:
            native.act(request())
        assert exc.value.error_kind == "provider_auth_failed"
        assert native.last_receipt["locked_model_id"] is None


@pytest.mark.parametrize("case,kind", [("success", None), ("refusal", "provider_refused"),
    ("truncated", "provider_output_truncated"), ("429", "provider_rate_limited"),
    ("error", "provider_unavailable"), ("oversized", "provider_response_schema_mismatch")])
def test_raw_wire_through_real_bounded_transport(monkeypatch, wire, case, kind):
    calls = []
    status = 429 if case == "429" else 503 if case == "error" else 200
    if case == "refusal":
        wire["choices"][0]["message"]["refusal"] = "private-refusal-marker"
    if case == "truncated":
        wire["choices"][0]["finish_reason"] = "length"
    payload = (wire if status == 200 else {"tpe": "TooManyRequests", "errors": [
        {"description": "private-error-marker", "key": "error", "extras": {}}], "extras": {}})
    raw = b"x" * (1024 * 1024 + 1) if case == "oversized" else json.dumps(payload).encode()

    class RawStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield raw

    def handler(req):
        calls.append(req)
        assert req.url == CHAT_ENDPOINT
        assert req.headers["authorization"] == "Bearer synthetic-writer-key"
        assert req.headers["accept-encoding"] == "identity"
        assert json.loads(req.content)["model"] == "palmyra-x5"
        return httpx.Response(status, stream=RawStream(), headers={"x-request-id": "wire-1"})

    original = httpx.AsyncClient
    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr("eslams.agents.bounded_post", bounded_post)
    native = agent()
    if kind is None:
        assert native.act(request()).action == 0
    else:
        with pytest.raises(ProviderCallError) as exc:
            native.act(request())
        assert exc.value.error_kind == kind
    assert len(calls) == 1 and native.last_receipt["request_id"] == "wire-1"
    assert "private-" not in json.dumps(native.last_receipt)


@pytest.mark.parametrize("value", [True, -1, "40", 1.5])
def test_invalid_usage_is_flagged_and_never_becomes_a_cost(monkeypatch, wire, value):
    wire["usage"]["prompt_tokens"] = value
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    usage = native.last_receipt["usage"]
    assert usage["input_tokens"] is None
    assert "input_tokens_invalid" in usage["usage_validation_errors"]
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_private_or_undocumented_usage_fields_do_not_fabricate_accounting(monkeypatch, wire):
    wire["usage"] = {"input_tokens": 123, "output_tokens": 456, "cost": 0.99,
                     "reasoning_included_in_output": True}
    respond(monkeypatch, wire)
    native = agent()
    native.act(request())
    assert native.last_receipt["usage"] == {}
    assert native.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize("model", [None, "", " ", "\n\t"])
@pytest.mark.parametrize("alias", ["writer", "writer-ai", "writerai"])
def test_model_must_be_explicit_and_nonblank_at_every_entry(model, alias):
    with pytest.raises(ValueError, match="explicit nonempty model"):
        ModelProviderAgent(alias, model, API_KEY_ENV)
    with pytest.raises(ValueError, match="explicit nonempty model"):
        provider_preflight(alias, model, "connect-four", live=True)
    if model is not None:
        with pytest.raises(ValueError, match="explicit nonempty model"):
            _provider_agent(f"{alias}:{model}")


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("alias", ["writer", "writer-ai", "writerai"])
@pytest.mark.parametrize("runtime", [ProviderRuntimeConfig(reasoning_effort="high"),
    ProviderRuntimeConfig(reasoning_budget_tokens=0),
    ProviderRuntimeConfig(reasoning_budget_tokens=4000),
    ProviderRuntimeConfig(gemini_thinking_budget=100),
    ProviderRuntimeConfig(reasoning="enabled"), ProviderRuntimeConfig(reasoning="disabled")])
def test_preflight_rejects_unsupported_controls_before_discovery(alias, live, runtime):
    result = provider_preflight(alias, "palmyra-x5", "connect-four",
                                live=live, runtime_config=runtime)
    assert not result["ok"] and not result["readiness"]["configuration_ready"]
    assert result["error"]["error_class"] == "provider_request_rejected"
    assert result["readiness"]["inference"] == "not_attempted"


@pytest.fixture
def configured_credentials(monkeypatch):
    values = ("primaryPlainOpaque-123", "secondaryPlainOpaque-456", "customPlainOpaque-789")
    monkeypatch.setenv(API_KEY_ENV, values[0])
    monkeypatch.setenv("WRITER_API_KEY_SECONDARY", values[1])
    monkeypatch.setenv("CUSTOM_INFERENCE_CREDENTIAL", values[2])
    return values


@pytest.mark.parametrize("credential_index", [0, 1, 2])
def test_echoed_credentials_are_removed_from_ids_and_public_response(
    monkeypatch, wire, configured_credentials, credential_index,
):
    secret = configured_credentials[credential_index]
    wire.update(id=f"response-{secret}", model=f"model-{secret}")
    respond(monkeypatch, wire, headers={"x-request-id": f"request-{secret}",
                                       "cf-aig-request-id": f"gateway-{secret}"})
    native = agent()
    result = native.act(request())
    receipt = native.last_receipt
    for key in ("request_id", "gateway_request_id", "provider_response_id", "locked_model_id",
                "model_identity_source"):
        assert receipt[key] is None
    serialized = json.dumps(result.to_dict()) + json.dumps(native.attempt_receipts)
    assert all(value not in serialized for value in configured_credentials)


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 429, 503])
@pytest.mark.parametrize("malformed", [False, True])
def test_error_and_malformed_receipts_scrub_all_configured_credentials(
    monkeypatch, configured_credentials, status, malformed,
):
    import traceback
    first, second, custom = configured_credentials
    body = ({"tpe":"BadRequest", "errors":[{"description": f"{first} {second} {custom}",
            "key": "error", "extras": {}}], "extras": {}, "id": f"response-{second}"}
            if not malformed else f'{{"private": "{custom}"'.encode())
    respond(monkeypatch, body, status=status, headers={"x-request-id": f"request-{first}",
                                                      "cf-aig-request-id": f"gateway-{custom}"})
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    public = (str(exc.value) + repr(exc.value.model) + traceback.format_exception_only(exc.value)[0]
              + json.dumps(native.attempt_receipts) + json.dumps(exc.value.receipt))
    assert all(value not in public for value in configured_credentials)
    assert len(native.attempt_receipts) == 1


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("credential_index", [0, 1, 2])
def test_credential_in_action_text_is_rejected_before_parsing_or_publication(
    monkeypatch, wire, configured_credentials, encoded, credential_index,
):
    secret = configured_credentials[credential_index]
    text = json.dumps({"action": 0, "public_explanation": f"echo {secret}"})
    if encoded:
        text = text.replace(secret, "".join(f"\\u{ord(char):04x}" for char in secret))
        assert secret not in text
    wire["choices"][0]["message"]["content"] = text
    respond(monkeypatch, wire)
    native = agent()
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    assert exc.value.error_kind == "provider_response_schema_mismatch"
    public = str(exc.value) + json.dumps(native.attempt_receipts)
    assert all(value not in public for value in configured_credentials)
    assert native.last_receipt["usage"]["total_tokens"] == 340


@pytest.mark.parametrize("credential_index", [0, 1, 2])
def test_discovery_rejects_credential_ids_without_exposing_partial_results(
    monkeypatch, configured_credentials, credential_index,
):
    from eslams.provider_preflight import provider_models_result
    secret = configured_credentials[credential_index]
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", lambda *a, **k:
        httpx.Response(200, json={"models": [{"id":"safe-model"}, {"id": f"echo-{secret}"}]}))
    result = provider_models_result("writer-ai")
    assert not result["ok"] and result["models"] == []
    assert all(value not in json.dumps(result) for value in configured_credentials)


@pytest.mark.parametrize("case", ["malformed", "http-error", "timeout", "transport"])
def test_discovery_failures_do_not_echo_primary_or_secondary_credentials(
    monkeypatch, configured_credentials, case,
):
    from eslams.provider_preflight import provider_models_result
    def get(*args, **kwargs):
        private = " ".join(configured_credentials)
        if case == "timeout":
            raise httpx.ReadTimeout(private)
        if case == "transport":
            raise httpx.ReadError(private)
        return httpx.Response(503 if case == "http-error" else 200, content=private.encode())
    monkeypatch.setattr("eslams.provider_preflight.httpx.get", get)
    result = provider_models_result("writer")
    assert not result["ok"]
    assert all(value not in json.dumps(result) for value in configured_credentials)


@pytest.mark.parametrize("kind", ["timeout", "transport"])
def test_partial_wire_failure_scrubs_ids_and_exception_chain(
    monkeypatch, configured_credentials, kind,
):
    import traceback
    first, second, custom = configured_credentials

    class PartialStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield f'{{"private":"{custom}'.encode()
            if kind == "timeout":
                raise httpx.ReadTimeout(f"partial {first} {second} {custom}")
            raise httpx.ReadError(f"partial {first} {second} {custom}")

    def handler(req):
        return httpx.Response(200, stream=PartialStream(), headers={
            "x-request-id": f"request-{first}", "cf-aig-request-id": f"gateway-{second}"})

    original = httpx.AsyncClient
    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", lambda **kwargs:
        original(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr("eslams.agents.bounded_post", bounded_post)
    native = agent(runtime_config=ProviderRuntimeConfig(max_retries=3))
    with pytest.raises(ProviderCallError) as exc:
        native.act(request())
    public = "".join(traceback.format_exception(exc.value)) + json.dumps(native.attempt_receipts)
    assert all(value not in public for value in configured_credentials)
    assert len(native.attempt_receipts) == 1


def test_custom_primary_key_and_standard_secondary_are_both_scrubbed(
    monkeypatch, wire, configured_credentials,
):
    first, second, custom = configured_credentials
    wire.update(id=f"response-{first}", model=f"model-{second}")
    respond(monkeypatch, wire, headers={"x-request-id": f"request-{custom}"})
    native = ModelProviderAgent("writer", "palmyra-x5", "CUSTOM_INFERENCE_CREDENTIAL")
    result = native.act(request())
    assert all(value not in json.dumps(result.to_dict()) for value in configured_credentials)


@pytest.mark.parametrize("case", ["action", "http-error", "malformed"])
def test_credentials_never_enter_persisted_artifacts(
    monkeypatch, wire, configured_credentials, tmp_path, case,
):
    first, second, custom = configured_credentials
    if case == "action":
        wire["choices"][0]["message"]["content"] = json.dumps(
            {"action": 0, "public_explanation": f"{first} {second} {custom}"})
        body = wire
    elif case == "http-error":
        body = {"tpe": "BadRequest", "errors": [{"description": f"{first} {second} {custom}",
                "key": "error", "extras": {}}], "extras": {}, "id": f"response-{second}"}
    else:
        body = f'{{"private":"{custom}"'.encode()
    respond(monkeypatch, body, status=400 if case == "http-error" else 200,
            headers={"x-request-id": f"request-{first}", "cf-aig-request-id": f"gateway-{second}"})
    result = Runner().run(RunConfig("connect-four", agent_1=agent(), output_dir=tmp_path))
    assert not result.score.match_valid_for_scoring
    assert all(event.action is None for event in result.replay_events)
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob("*"):
        if path.is_file():
            public = path.read_bytes()
            assert all(value.encode() not in public for value in configured_credentials)
