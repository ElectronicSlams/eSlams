"""Complete error envelopes cannot discard observed work into a retry decision."""
import json

import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.runner import RunConfig, Runner

CASES = {
    'generation': {'id': 'synthetic-observed-generation'},
    'usage': {'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
    'cost': {'usage': {'cost': 0.001}},
    'overflow_cost': {'usage': {'cost': 10**400}},
    'zero_cost': {'usage': {'cost': 0.0}},
    'malformed_id': {'id': {'prompt': 'synthetic-private-prose'}},
    'malformed_usage': {'usage': {'prompt_tokens': 'synthetic-private-prose'}},
    'conflicting_usage': {'usage': {'prompt_tokens': 10, 'total_tokens': 2}},
    'malformed_cost': {'usage': {'cost': 'synthetic-private-prose'}},
    'conflicting_cost': {'cost': 0.001, 'usage': {'cost': 0.002}},
}


@pytest.mark.parametrize('status', [200, 429, 503])
@pytest.mark.parametrize('case', CASES)
def test_observed_or_ambiguous_work_never_replayed(monkeypatch, status, case):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    body = {'error': {'code': 429}, **CASES[case]}
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(status, json=body, request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert calls == [1] and len(agent.attempt_receipts) == 1
    row = agent.attempt_receipts[0]
    if case == 'generation':
        assert row['provider_response_id'] == 'synthetic-observed-generation'
    if case == 'usage':
        assert row['usage']['total_tokens'] == 15
    assert 'synthetic-private-prose' not in json.dumps(row)
    if status != 200:
        assert row['estimated_cost']['status'] == 'cost_unavailable'
        if case in {'cost', 'zero_cost'}:
            assert row['pricing_provenance']['observed_cost_usd'] == CASES[case]['usage']['cost']


@pytest.mark.parametrize('status', [200, 429])
def test_explicit_definitive_rejection_retains_optional_retry(monkeypatch, status):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={'error': {'code': 429}},
                              request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(calls) == len(agent.attempt_receipts) == 2


@pytest.mark.parametrize('body', ['not-json', '{"error":{"code":429},"id":"g","id":null}',
    '{"error":{"code":429},"usage":{"cost":NaN}}', '[]', '{"error":{"code":503}}',
    '{"error":{"code":429,"message":{"usage":{"cost":0}}}}',
    '{"error":{"code":429},"type":{"id":null}}'])
def test_unverifiable_http429_rejection_is_not_retry_permission(monkeypatch, body):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(429, content=body.encode(), request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert calls == [1]


@pytest.mark.parametrize('status', [429, 503])
def test_runner_retains_quarantined_error_custody_without_cost_or_action(
    tmp_path, monkeypatch, status,
):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(status, json={'id': 'observed-generation',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15,
                      'cost': 0.001, 'prompt': 'synthetic-private-prose'},
            'pricing': {'secret': 'synthetic-private-prose'},
            'error': {'code': 429, 'message': 'synthetic-private-prose'}},
            request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    result = Runner().run(RunConfig('tic-tac-toe', output_dir=tmp_path,
        on_agent_error='forfeit', agent_1=ModelProviderAgent('openrouter', 'synthetic-model',
        'OPENROUTER_API_KEY', runtime_config=ProviderRuntimeConfig(max_retries=1))))
    rows = [json.loads(x) for x in (result.expanded_path /
            'receipts/provider_receipts.jsonl').read_text().splitlines()]
    assert calls == [1] and len(rows) == 1
    assert rows[0]['provider_response_id'] == 'observed-generation'
    assert rows[0]['usage']['total_tokens'] == 15
    assert rows[0]['pricing_provenance']['observed_cost_usd'] == 0.001
    assert result.score.aggregate_usage['totalCostUsd'] is None
    assert not rows[0]['action_applied'] and result.score.winner is None
    assert not result.score.match_valid_for_scoring
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob('*'):
        if path.is_file():
            assert b'synthetic-private-prose' not in path.read_bytes()


@pytest.mark.parametrize('field', ['prompt', 'response', 'content', 'message'])
def test_telemetry_inside_content_fields_is_never_custody(tmp_path, monkeypatch, field):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(429, json={'error': {'code': 429}, field: {
            'id': 'synthetic-private-id', 'usage': {'prompt_tokens': 123}, 'cost': 0.009}},
            request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=1))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert calls == [1]
    receipt = agent.attempt_receipts[0]
    assert not receipt.get('provider_response_id') and not receipt['usage']
    assert 'observed_cost_usd' not in receipt['pricing_provenance']
    assert 'synthetic-private-id' not in json.dumps(receipt)
