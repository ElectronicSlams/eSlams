"""Keyless Fireworks REST regressions; fixture provenance: docs/FIREWORKS.md."""

from __future__ import annotations

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
from eslams.protocol import ProtocolError
from eslams.provider_preflight import provider_models_result, provider_preflight
from eslams.providers import fireworks, load_provider_registry
from eslams.runner import RunConfig, Runner

MODEL = "accounts/fireworks/models/wire-fixture"
SECRET = "synthetic-fireworks-secret"
PRIVATE = "private-reasoning-wire-fixture"
FIXTURE = Path(__file__).parent / "fixtures/provider/fireworks_chat_completions_success.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def request():
    return replace(
        _request(),
        protocol_version="eslams-act-v2",
        time_budget_ms=None,
        metadata={"model_execution_policy": model_execution_policy(None)},
    )


def agent(**kwargs):
    return ModelProviderAgent("fireworks", MODEL, "FIREWORKS_API_KEY", **kwargs)


@pytest.fixture(autouse=True)
def synthetic_key(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", SECRET)


def post_response(monkeypatch, payload=None, *, status=200, body=None, headers=None):
    calls = []
    payload = fixture() if payload is None else payload

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            status,
            **({"json": payload} if body is None else {"content": body}),
            headers=headers or {"x-request-id": "fw-request-fixture"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


@pytest.mark.parametrize("alias", [*fireworks.PROVIDER_ALIASES, "FIREWORKS-AI"])
def test_aliases_preserve_exact_model_through_cli_registry_dispatch_and_preflight(
    monkeypatch, alias
):
    exact = "accounts/Example/models/Exact-v1:0"
    calls = post_response(monkeypatch)
    selected = _provider_agent(f"{alias}:{exact}")
    assert selected.provider == "fireworks" and selected.model == exact
    assert selected.api_key_env == "FIREWORKS_API_KEY"
    assert selected.act(request()).action == 1
    assert calls[0][1]["json"]["model"] == exact
    direct = ModelProviderAgent(alias, exact, "FIREWORKS_API_KEY")
    assert direct.act(request()).metadata["provider"] == "fireworks"
    assert load_provider_registry().resolve(alias, exact).provider == "fireworks"
    calls.clear()
    ready = provider_preflight(alias, exact, "tic-tac-toe")
    assert ready["ok"] and ready["checks"]["adapter_available"]
    assert not ready["checks"]["minimal_inference"] and calls == []


@pytest.mark.parametrize("alias", fireworks.PROVIDER_ALIASES)
def test_cli_requires_explicit_model_without_choosing_a_default(alias):
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent(alias)
    with pytest.raises(ValueError, match="explicit model"):
        _provider_agent(f"{alias}:")


def test_wire_request_defaults_full_history_and_truthful_receipt(monkeypatch):
    calls = post_response(monkeypatch)
    act = replace(request(), history=[{"turn_id": i, "action": i % 3} for i in range(100)])
    selected = agent()
    result = selected.act(act)
    url, options = calls[0]
    assert len(calls) == 1 and url == fireworks.CHAT_COMPLETIONS_ENDPOINT
    assert options["headers"] == {
        "Authorization": f"Bearer {SECRET}",
        "Content-Type": "application/json",
    }
    assert options["timeout"].read is None and options["timeout"].pool is None
    assert options["json"] == {
        "model": MODEL,
        "messages": options["json"]["messages"],
        "stream": False,
        "context_length_exceeded_behavior": "error",
    }
    prompt = options["json"]["messages"][1]["content"]
    assert json.loads(prompt.splitlines()[-1])["history"] == act.history
    assert "provider" not in options["json"] and "tools" not in options["json"]
    receipt = result.metadata["provider_receipt"]
    assert receipt["provider"] == "fireworks" and receipt["model"] == MODEL
    assert receipt["locked_model_id"] == MODEL
    assert receipt["model_identity_source"] == "provider_response"
    assert receipt["endpoint_kind"] == fireworks.ENDPOINT_KIND
    assert receipt["parser_version"] == fireworks.PARSER_VERSION
    assert receipt["attempt"] == 1 and receipt["attempt_kind"] == "primary"
    assert receipt["request_id"] == "fw-request-fixture"
    assert receipt["finish_reason"] == "stop" and receipt["finish_status"] == "completed"
    usage = receipt["usage"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (12, 4, 16)
    assert usage["reasoning_tokens"] == 2 and usage["reasoning_included_in_output"] is True
    assert usage["cached_input_tokens"] == 3 and usage["cache_read_input_tokens"] == 3
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"
    assert receipt["rate_card_reference"] is None
    serialized = json.dumps(receipt)
    for private in (SECRET, PRIVATE, prompt, "Authorization", "reasoning_content"):
        assert private not in serialized


@pytest.mark.parametrize(
    "runtime,expected",
    [
        (ProviderRuntimeConfig(), None),
        (ProviderRuntimeConfig(reasoning="enabled"), True),
        (ProviderRuntimeConfig(reasoning="disabled"), "none"),
        (ProviderRuntimeConfig(reasoning_effort="high"), "high"),
        (
            ProviderRuntimeConfig(reasoning_effort="future-provider-choice"),
            "future-provider-choice",
        ),
        (ProviderRuntimeConfig(reasoning_budget_tokens=12345), 12345),
    ],
)
def test_reasoning_uses_only_explicit_controls_independent_of_arena(monkeypatch, runtime, expected):
    calls = post_response(monkeypatch)
    selected = agent(runtime_config=runtime)
    for arena_id in ("tic-tac-toe", "chess", "connect-four"):
        selected.act(replace(request(), arena=replace(request().arena, id=arena_id)))
    assert [options["json"].get("reasoning_effort") for _, options in calls] == [expected] * 3
    assert all("thinking" not in options["json"] for _, options in calls)


@pytest.mark.parametrize(
    "runtime",
    [
        ProviderRuntimeConfig(reasoning_effort="high", reasoning_budget_tokens=1024),
        ProviderRuntimeConfig(reasoning_budget_tokens=0),
        ProviderRuntimeConfig(gemini_thinking_budget=0),
    ],
)
def test_conflicting_or_foreign_reasoning_controls_fail_before_transport(monkeypatch, runtime):
    calls = post_response(monkeypatch)
    selected = agent(runtime_config=runtime)
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_request_rejected" and not calls


def test_reasoning_is_not_billed_twice_and_undocumented_cost_is_ignored(monkeypatch):
    payload = fixture()
    payload["usage"]["cost"] = 999
    post_response(monkeypatch, payload)
    selected = agent()
    selected.capabilities = replace(
        selected.capabilities,
        pricing={
            "input_cost_per_token": 0.001,
            "output_cost_per_token": 0.002,
            "cache_read_input_token_cost": 0.0005,
            "output_cost_per_reasoning_token": 0.1,
        },
    )
    selected.act(request())
    cost = selected.last_receipt["estimated_cost"]
    assert cost["source"] == "registry_rate_card_estimate"
    assert cost["cost_usd"] == 0.0185 and cost["reasoning_cost_usd"] == 0
    assert selected.last_receipt["rate_card_reference"] is None


@pytest.mark.parametrize(
    "content,valid",
    [
        (f'<think>{PRIVATE} {{"action":2}}</think>{{"action":1}}', True),
        (f'<think>{PRIVATE} {{"action":1}}', False),
        (f'<think>{PRIVATE} {{"action":1}}</think>', False),
    ],
)
def test_inline_thinking_cannot_be_used_as_an_action_or_leak_into_metadata(
    monkeypatch,
    content,
    valid,
):
    payload = fixture()
    payload["choices"][0]["message"]["content"] = content
    calls = post_response(monkeypatch, payload)
    selected = agent()
    if valid:
        result = selected.act(request())
        assert result.action == 1 and PRIVATE not in json.dumps(result.to_dict())
    else:
        with pytest.raises(ProviderCallError) as failure:
            selected.act(request())
        assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == 1 and PRIVATE not in json.dumps(selected.last_receipt)


def test_real_shared_transport_sends_raw_json_and_uses_bounded_nonstreaming_io(monkeypatch):
    client_type = httpx.AsyncClient
    calls = []

    def wire(request):
        calls.append(request)
        assert str(request.url) == fireworks.CHAT_COMPLETIONS_ENDPOINT
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert request.headers["Accept-Encoding"] == "identity"
        assert json.loads(request.content)["model"] == MODEL
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(fixture()).encode()))

    def client(**kwargs):
        assert kwargs["timeout"].read is None
        return client_type(transport=httpx.MockTransport(wire), **kwargs)

    monkeypatch.setattr("eslams.http_io.httpx.AsyncClient", client)
    assert agent().act(request()).action == 1
    assert len(calls) == 1


def test_operator_limits_and_temperature_are_forwarded_exactly(monkeypatch):
    calls = post_response(monkeypatch)
    selected = agent(
        max_output_tokens=9876,
        temperature=0.37,
        runtime_config=ProviderRuntimeConfig(timeout_ms=240000, read_timeout_ms=190000),
    )
    selected.act(request())
    options = calls[0][1]
    assert options["json"]["max_tokens"] == 9876 and options["json"]["temperature"] == 0.37
    assert options["timeout"].read == 190 and options["timeout"].connect == 10


@pytest.mark.parametrize(
    "key,value", [("model", None), ("model", "other-model"), ("usage", None), ("usage", {})]
)
def test_missing_accounting_and_identity_are_never_fabricated(monkeypatch, key, value):
    payload = fixture()
    payload[key] = value
    post_response(monkeypatch, payload)
    selected = agent()
    assert selected.act(request()).action == 1
    receipt = selected.last_receipt
    if key == "model":
        assert receipt["locked_model_id"] == value
        assert receipt["model_identity_source"] == ("provider_response" if value else None)
    else:
        assert receipt["usage"] == {} and receipt["usage_unavailable_reason"]
    assert receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("prompt_tokens", -1, "input_tokens"),
        ("completion_tokens", True, "output_tokens"),
        ("completion_tokens", "4", "output_tokens"),
        ("total_tokens", 999, "total_tokens"),
        ("prompt_tokens_details", {"cached_tokens": 13}, "cached_input_tokens"),
        ("completion_tokens_details", {"reasoning_tokens": 5}, "reasoning_tokens"),
        ("completion_tokens_details", [], "completion_tokens_details"),
        ("output_tokens_details", {"reasoning_tokens": 3}, "conflicting_reasoning_tokens"),
    ],
)
def test_invalid_usage_is_diagnostic_and_cannot_create_complete_cost(
    monkeypatch,
    field,
    value,
    diagnostic,
):
    payload = fixture()
    payload["usage"][field] = value
    post_response(monkeypatch, payload)
    selected = agent()
    selected.act(request())
    assert diagnostic in json.dumps(selected.last_receipt["usage"]["usage_validation_errors"])
    assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


def test_alternate_reasoning_detail_and_absent_counters_stay_truthful(monkeypatch):
    payload = fixture()
    payload["usage"]["output_tokens_details"] = payload["usage"].pop("completion_tokens_details")
    payload["usage"].pop("prompt_tokens_details")
    post_response(monkeypatch, payload)
    selected = agent()
    selected.act(request())
    assert selected.last_receipt["usage"]["reasoning_tokens"] == 2
    assert selected.last_receipt["usage"]["cached_input_tokens"] is None
    payload["usage"].pop("output_tokens_details")
    selected.act(request())
    assert selected.last_receipt["usage"]["reasoning_tokens"] is None


@pytest.mark.parametrize(
    "reason,kind,status",
    [
        ("length", "provider_output_truncated", "incomplete"),
        ("content_filter", "provider_refused", "refused"),
        ("tool_calls", "provider_request_rejected", "incomplete"),
        ("unexpected-private-reason", "provider_response_schema_mismatch", "completed"),
        (None, "provider_response_schema_mismatch", None),
    ],
)
def test_noncomplete_parseable_actions_are_rejected_without_retry_or_repair(
    monkeypatch,
    reason,
    kind,
    status,
):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = reason
    calls = post_response(monkeypatch, payload)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2, action_repair_attempts=1))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == kind and len(calls) == 1
    assert selected.last_receipt["finish_status"] == status
    assert selected.last_receipt["usage"]["total_tokens"] == 16
    assert PRIVATE not in json.dumps(selected.last_receipt)
    assert "unexpected-private-reason" not in json.dumps(selected.last_receipt)


def test_defensive_refusal_field_is_not_parsed_or_published(monkeypatch):
    payload = fixture()
    payload["choices"][0]["message"]["refusal"] = "private-refusal-prose"
    post_response(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_refused"
    assert "private-refusal-prose" not in str(failure.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [None]},
        {"output_text": '{"action":1}'},
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "reasoning_content": '{"action":1}'},
                }
            ]
        },
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": [{"text": '{"action":1}'}]},
                }
            ]
        },
    ],
)
def test_sdk_shortcuts_reasoning_only_and_malformed_envelopes_are_rejected(monkeypatch, payload):
    calls = post_response(monkeypatch, payload)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_response_schema_mismatch" and len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        b"private-invalid-json",
        b"[]",
        b'{"choices":[],"choices":[]}',
        b'{"usage":{"prompt_tokens":NaN}}',
    ],
)
def test_malformed_json_does_not_leak_private_body(monkeypatch, body):
    post_response(monkeypatch, body=body)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert "private-invalid-json" not in str(failure.value) + json.dumps(selected.last_receipt)


@pytest.mark.parametrize(
    "status,kind",
    [
        (400, "provider_request_rejected"),
        (401, "provider_auth_failed"),
        (402, "provider_request_rejected"),
        (403, "provider_permission_failed"),
        (404, "provider_unavailable"),
        (408, "provider_request_rejected"),
        (412, "provider_request_rejected"),
        (413, "provider_request_rejected"),
        (429, "provider_rate_limited"),
        (500, "provider_unavailable"),
        (502, "provider_unavailable"),
        (503, "provider_unavailable"),
        (504, "provider_unavailable"),
    ],
)
def test_http_errors_keep_receipts_without_retry_fallback_or_private_error_text(
    monkeypatch,
    status,
    kind,
):
    calls = post_response(
        monkeypatch,
        {"error": {"code": status, "message": PRIVATE}},
        status=status,
        headers={"Retry-After": "0", "x-request-id": "fw-error"},
    )
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == kind and len(calls) == 1
    receipt = selected.last_receipt
    assert receipt["status_code"] == status and receipt["request_id"] == "fw-error"
    assert receipt["usage"] == {} and receipt["locked_model_id"] is None
    assert PRIVATE not in json.dumps(receipt) + str(failure.value)


@pytest.mark.parametrize("status", [200, 429])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_optional_rate_retries_require_definitive_rejection_and_preserve_attempts(
    monkeypatch,
    status,
    ambiguous,
):
    payload = {"error": {"code": 429, "message": PRIVATE}}
    if ambiguous:
        payload.update(usage=fixture()["usage"], id="observed-generation")
    calls = post_response(monkeypatch, payload, status=status, headers={"Retry-After": "0"})
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    expected = 1 if ambiguous else 2
    assert failure.value.error_kind == "provider_rate_limited" and len(calls) == expected
    assert [row["attempt"] for row in selected.attempt_receipts] == list(range(1, expected + 1))
    assert all(row["provider"] == "fireworks" for row in selected.attempt_receipts)
    if ambiguous:
        assert selected.last_receipt["usage"]["total_tokens"] == 16
        assert selected.last_receipt["estimated_cost"]["status"] == "cost_unavailable"


@pytest.mark.parametrize(
    "error,kind",
    [
        (httpx.ReadTimeout(PRIVATE), "provider_timeout"),
        (httpx.ConnectError(PRIVATE), "provider_transport_error"),
        (
            ProtocolError("agent/provider response exceeds 1 MiB limit"),
            "provider_response_schema_mismatch",
        ),
    ],
)
def test_transport_failures_never_replay_even_when_retries_are_enabled(monkeypatch, error, kind):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = agent(runtime_config=ProviderRuntimeConfig(max_retries=2))
    with pytest.raises((ProviderCallError, TimeoutError)):
        selected.act(request())
    assert calls == [1] and selected.last_receipt["outcome"] == kind
    assert PRIVATE not in json.dumps(selected.last_receipt)


@pytest.mark.parametrize("key", [None, "invalid key", "invalid\nkey"])
def test_missing_or_invalid_credentials_fail_without_network(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("FIREWORKS_API_KEY")
    else:
        monkeypatch.setenv("FIREWORKS_API_KEY", key)
    calls = post_response(monkeypatch)
    selected = agent()
    with pytest.raises(ProviderCallError) as failure:
        selected.act(request())
    assert failure.value.error_kind == "provider_auth_failed" and not calls


def test_models_discovery_is_explicitly_unimplemented_and_live_preflight_is_mocked(monkeypatch):
    calls = post_response(monkeypatch)
    unavailable = provider_models_result("fireworks-ai")
    assert not unavailable["ok"] and not calls
    assert unavailable["error"]["error_class"] == "provider_discovery_unavailable"
    result = provider_preflight("fireworks_ai", MODEL, "tic-tac-toe", live=True)
    assert result["ok"] and len(calls) == 1
    assert result["checks"]["account_model_visible"] is None
    assert result["readiness"]["usage_complete"]


@pytest.mark.parametrize("alias", fireworks.PROVIDER_ALIASES)
def test_cli_run_and_configuration_preflight_use_native_adapter(
    monkeypatch, tmp_path, capsys, alias
):
    calls = post_response(monkeypatch)
    assert (
        main(
            [
                "providers",
                "preflight",
                "--provider",
                alias,
                "--model",
                MODEL,
                "--arena",
                "tic-tac-toe",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["checks"]["adapter_available"] and not calls
    assert (
        main(
            [
                "run",
                "--arena",
                "tic-tac-toe",
                "--agent",
                f"{alias}:{MODEL}",
                "--opponent",
                "first-legal",
                "--max-turns",
                "1",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert ArtifactValidator().validate(Path(output["artifact"])) == []


@pytest.mark.parametrize(
    "reason,kind",
    [
        ("stop", "ok"),
        ("length", "provider_output_truncated"),
        ("content_filter", "provider_refused"),
    ],
)
def test_artifacts_preserve_usage_and_exclude_private_traces(monkeypatch, tmp_path, reason, kind):
    payload = fixture()
    payload["choices"][0]["finish_reason"] = reason
    payload["choices"][0]["message"]["content"] = f'<think>{PRIVATE}</think>{{"action":1}}'
    calls = post_response(monkeypatch, payload)
    result = Runner().run(
        RunConfig(
            arena_id="tic-tac-toe", agents={"player_1": agent()}, output_dir=tmp_path, max_turns=1
        )
    )
    assert not result.score.match_valid_for_scoring and len(calls) == 1
    rows = [
        json.loads(line)
        for line in (result.artifact_path / "receipts/provider_receipts.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(rows) == 1 and rows[0]["action_applied"] == (reason == "stop")
    assert rows[0]["outcome"] == kind
    assert rows[0]["usage"]["total_tokens"] == 16
    assert ArtifactValidator().validate(result.artifact_path) == []
    for path in result.artifact_path.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            assert SECRET.encode() not in content and PRIVATE.encode() not in content
