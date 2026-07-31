from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from eslams.contracts.json_schema import schema_for_version
from eslams.contracts.provider import (
    ProviderAttemptEvent,
    no_secret_examples,
    provider_attempt_event_id,
    provider_receipt_validation_errors,
)
from eslams.contracts.versions import schema_versions

SCHEMA_VERSION = "eslams.provider-attempt.v2"


def test_every_exported_schema_is_valid_draft_2020_12():
    for version in schema_versions():
        Draft202012Validator.check_schema(schema_for_version(version))


def test_started_completed_and_failed_attempt_events_validate():
    validator = Draft202012Validator(schema_for_version(SCHEMA_VERSION))
    started = _event()
    completed = replace(
        started,
        status="completed",
        request_completed_at="2026-07-31T12:00:01Z",
        latency_ms=1000,
        resolved_model="gpt-fixture-2026-07-01",
        model_identity_source="provider_response",
        usage={
            "input_tokens": 10,
            "cached_input_tokens": 0,
            "output_tokens": 2,
            "reasoning_tokens": 1,
            "total_tokens": 12,
        },
        reasoning_included_in_output=True,
        usage_source="provider",
        usage_complete=True,
        estimated_cost_usd=0.0001,
        cost_source="reviewed_rate_card",
        cost_complete=True,
        rate_card_id="openai-reviewed-v1",
        wire_parse_status="ok",
        action_parse_status="ok",
        action_applied=True,
        case_valid_for_scoring=True,
    )
    failed = replace(
        started,
        status="failed",
        request_completed_at="2026-07-31T12:00:01Z",
        latency_ms=1000,
        http_status=429,
        error_class="provider_rate_limited",
        wire_parse_status="not_attempted",
        action_parse_status="not_attempted",
    )

    validator.validate(started.to_dict())
    validator.validate(completed.to_dict())
    validator.validate(failed.to_dict())


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"case_attempt_index": 0}, "case_attempt_index"),
        ({"attempt_index": 0}, "attempt_index"),
        ({"latency_ms": -1}, "latency_ms"),
        (
            {
                "status": "failed",
                "request_completed_at": "2026-07-31T12:00:01Z",
                "latency_ms": 1000,
            },
            "error_class",
        ),
        ({"status": "completed"}, "request_completed_at"),
        ({"estimated_cost_usd": float("nan")}, "estimated_cost_usd"),
        ({"estimated_cost_usd": float("inf")}, "estimated_cost_usd"),
    ],
)
def test_malformed_attempt_events_are_rejected(
    changes: dict[str, Any],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        replace(_event(), **changes)


def test_attempt_schema_is_closed_and_enforces_terminal_state():
    validator = Draft202012Validator(schema_for_version(SCHEMA_VERSION))
    started = _event().to_dict()
    started["secretPrompt"] = "must never be accepted"

    with pytest.raises(ValidationError):
        validator.validate(started)

    invalid_terminal = _event().to_dict()
    invalid_terminal.update(
        {
            "status": "completed",
            "requestCompletedAt": None,
            "latencyMs": None,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(invalid_terminal)

    invalid_scoring = replace(
        _event(),
        status="completed",
        request_completed_at="2026-07-31T12:00:01Z",
        latency_ms=1000,
    ).to_dict()
    invalid_scoring["caseValidForScoring"] = True
    with pytest.raises(ValidationError):
        validator.validate(invalid_scoring)


def test_attempt_python_contract_rejects_incoherent_complete_usage():
    with pytest.raises(ValueError, match="incoherent total_tokens"):
        replace(
            _event(),
            status="completed",
            request_completed_at="2026-07-31T12:00:01Z",
            latency_ms=1000,
            usage={
                "input_tokens": 10,
                "cached_input_tokens": 2,
                "output_tokens": 3,
                "reasoning_tokens": 1,
                "total_tokens": 99,
            },
            reasoning_included_in_output=True,
            usage_source="provider",
            usage_complete=True,
        )


def test_started_attempt_rejects_terminal_usage_and_cost_claims():
    with pytest.raises(ValueError, match="started events cannot contain terminal usage or cost"):
        replace(
            _event(),
            usage={
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_tokens": 0,
                "total_tokens": 2,
            },
            reasoning_included_in_output=True,
            usage_source="provider",
            usage_complete=True,
        )

    invalid_schema_payload = _event().to_dict()
    invalid_schema_payload.update(
        {
            "inputTokens": 1,
            "outputTokens": 1,
            "totalTokens": 2,
            "reasoningIncludedInOutput": True,
            "usageSource": "provider",
            "usageComplete": True,
        }
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema_for_version(SCHEMA_VERSION)).validate(
            invalid_schema_payload
        )


def test_attempt_event_id_is_deterministic_and_case_retry_scoped():
    values = {
        "physical_run_id": "physical_run_001",
        "case_id": "case_001",
        "logical_action_id": "logical_001",
        "attempt_index": 1,
    }

    first = provider_attempt_event_id(case_attempt_index=1, **values)
    replayed = provider_attempt_event_id(case_attempt_index=1, **values)
    case_retry = provider_attempt_event_id(case_attempt_index=2, **values)

    assert first == replayed
    assert first.startswith("sha256:")
    assert first != case_retry


def test_case_retry_attempt_kind_is_explicit_in_python_and_schema():
    with pytest.raises(ValueError, match="retried cases must begin"):
        replace(_event(), case_attempt_index=2)

    retry = replace(
        _event(),
        case_attempt_index=2,
        attempt_kind="case_retry",
    )
    Draft202012Validator(schema_for_version(SCHEMA_VERSION)).validate(retry.to_dict())


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:password@api.openai.com/v1/responses",
        "https://api.openai.com/v1/responses?key=secret-value",
        "https://api.openai.com/v1/responses?X-Amz-Signature=secret-value",
        "https://api.openai.com/v1/responses?mode=fast;access_token=secret-value",
        "https://api.openai.com/v1/responses#token=secret-value",
        "https://api.openai.com/v1/responses#",
        "https://api.openai.com:not-a-port/v1/responses",
        "http://api.openai.com/v1/responses",
    ],
)
def test_attempt_rejects_sensitive_or_insecure_provider_endpoint(endpoint: str):
    with pytest.raises(ValueError, match="provider_endpoint"):
        replace(_event(), provider_endpoint=endpoint)


def test_attempt_accepts_safe_literal_model_id_path():
    event = replace(
        _event(),
        provider="bedrock",
        requested_model="amazon.nova-micro-v1:0",
        provider_endpoint=(
            "https://bedrock-runtime.us-east-1.amazonaws.com/"
            "model/amazon.nova-micro-v1:0/converse"
        ),
    )

    assert event.provider_endpoint.endswith("amazon.nova-micro-v1:0/converse")


def test_external_receipt_validation_rejects_nested_credentials_and_secret_urls():
    receipt = copy.deepcopy(no_secret_examples()["eslams.provider.receipt.v2"])
    assert provider_receipt_validation_errors(receipt) == []
    receipt["endpoint_metadata"] = {
        "region": "eu-west-2",
        "nested": [
            {"authorization": "Bearer receipt-secret"},
            {"session_token": "nested-secret"},
            {"safe_url": "https://gateway.example/route?api_key=query-secret"},
            {"oauth_url": "https://gateway.example/callback#access_token=fragment-secret"},
            {"note": "Bearer inline-secret"},
        ],
    }

    errors = provider_receipt_validation_errors(receipt)

    assert any("sensitive field" in error for error in errors)
    assert any("sensitive URL query" in error for error in errors)
    assert any("sensitive URL fragment" in error for error in errors)
    assert any("bearer credential" in error for error in errors)


def _event() -> ProviderAttemptEvent:
    return ProviderAttemptEvent(
        event_id="sha256:" + "a" * 64,
        environment="production",
        physical_run_id="physical_run_001",
        official_run_id="official_run_001",
        model_lane_id="openai-gpt-fixture",
        run_job_id="run_job_001",
        shard_index=0,
        case_id="case_001",
        case_attempt_index=1,
        turn_index=0,
        seat_id="player_1",
        logical_action_id="official_run_001:case_001:player_1:000000",
        attempt_index=1,
        attempt_kind="primary",
        provider="openai",
        requested_model="gpt-fixture",
        resolved_model=None,
        model_identity_source=None,
        provider_endpoint="https://api.openai.com/v1/responses",
        status="started",
        endpoint_kind="responses",
        parser_version="openai-responses-raw-v2",
        wrapper_version="legal_action_v1:1.0.0",
        request_started_at="2026-07-31T12:00:00Z",
    )
