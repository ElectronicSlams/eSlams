"""Keyless Core preflight and CLI contracts for reviewed PR06/PR12 records."""
import re
from pathlib import Path

import httpx
import pytest
from test_model_agents import _openai_wire

from eslams.cli import main
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.provider_preflight import provider_preflight


def _live_mock(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
        lambda *a, **kw: httpx.Response(200, json={"data": [{"id": "gpt-5-mini"}]}))
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json=_openai_wire('{"action":0}',
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}))
    monkeypatch.setattr("eslams.agents.bounded_post", post)
    return calls


def test_live_preflight_native_defaults_have_no_hidden_token_time_or_reasoning_policy(monkeypatch):
    calls = _live_mock(monkeypatch)
    result = provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True)
    assert result["ok"] and len(calls) == 1
    assert result["model_execution_policy"]["thinking"] == {"mode": "unbounded"}
    assert result["model_execution_policy"]["output"] == {"mode": "provider_default"}
    assert "max_output_tokens" not in calls[0]["json"] and "reasoning" not in calls[0]["json"]
    assert calls[0]["timeout"].read is None


def test_live_preflight_explicit_operator_choices_are_preserved(monkeypatch):
    calls = _live_mock(monkeypatch)
    result = provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True,
        time_budget_ms=1800000, max_output_tokens=5000,
        runtime_config=ProviderRuntimeConfig(reasoning_effort="minimal"))
    assert result["ok"] and len(calls) == 1
    assert result["model_execution_policy"]["thinking"]["duration_ms"] == 1800000
    assert result["model_execution_policy"]["output"]["max_tokens"] == 5000
    assert calls[0]["json"]["max_output_tokens"] == 5000
    assert calls[0]["json"]["reasoning"] == {"effort": "minimal"}
    assert 1790 < calls[0]["timeout"].read <= 1800


@pytest.mark.parametrize("field", ["time_budget_ms", "max_output_tokens"])
@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_invalid_preflight_policies_fail_before_discovery_or_inference(monkeypatch, field, bad):
    monkeypatch.setattr("eslams.provider_preflight.httpx.get",
                        lambda *a, **kw: pytest.fail("invalid policy reached discovery"))
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **kw: pytest.fail("invalid policy reached inference"))
    with pytest.raises(ValueError):
        provider_preflight("openai", "gpt-5-mini", "tic-tac-toe", live=True, **{field: bad})


@pytest.mark.parametrize("command", ["validate", "replay"])
def test_cli_missing_artifact_explains_not_found_without_traceback(tmp_path, capsys, command):
    missing = tmp_path / "absent.eslams"
    assert main([command, str(missing)]) == 1
    error = capsys.readouterr().err
    assert "not found" in error and str(missing) in error and "Traceback" not in error


def test_cli_file_output_names_correct_kind_and_existing_overwrite_flag(tmp_path, capsys):
    file = tmp_path / "golden.json"
    args = ["core", "golden", "--games", "tic-tac-toe", "--out", str(file)]
    assert main(args) == 0
    original = file.read_bytes()
    capsys.readouterr()
    assert main(args) == 1
    error = capsys.readouterr().err
    assert "output file already exists" in error and "--overwrite" in error
    assert "new output directory" not in error and "overwrite=True" not in error
    assert file.read_bytes() == original
    assert main([*args, "--overwrite"]) == 0


def test_cli_default_demo_is_explicit_in_help_and_packaged_readme(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "connect-four" in help_text and "random (default)" in help_text
    assert "first-legal (default)" in help_text
    readme = (Path(__file__).parents[1] / "README.md").read_text()
    assert "`eslams run` without flags runs a local Connect Four demo" in readme
    links = re.findall(r'\]\(([^)\s]+)\)', readme)
    assert all(link.startswith(("https://", "http://", "mailto:", "#")) for link in links)


@pytest.mark.parametrize("field", ["max_retries", "action_repair_attempts", "retry_backoff_ms",
    "rate_limit_per_minute", "reasoning_budget_tokens", "gemini_thinking_budget"])
def test_operator_integer_fields_never_accept_fractional_values(field):
    with pytest.raises(ValueError):
        ProviderRuntimeConfig(**{field: 1.5})


@pytest.mark.parametrize("kind", ["http", "native"])
def test_nonfinite_request_metadata_fails_before_any_transport_callback(monkeypatch, kind):
    from dataclasses import replace

    from test_model_agents import _request

    from eslams.agents import HttpAgent, ModelProviderAgent
    from eslams.protocol import ProtocolError
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []
    monkeypatch.setattr("eslams.agents.bounded_post", lambda *a, **kw: calls.append(1))
    bad = replace(_request(), metadata={"untrusted": float("nan")})
    agent = (HttpAgent("https://synthetic.invalid/act") if kind == "http" else
             ModelProviderAgent("openai", "synthetic-model", "OPENAI_API_KEY"))
    with pytest.raises(ProtocolError):
        agent.act(bad)
    assert calls == []
