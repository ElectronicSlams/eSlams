"""Actual bounded-reader failures retain headers, never inferred generation usage."""
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from eslams import http_io
from eslams.agents import ModelProviderAgent
from eslams.artifacts import ArtifactValidator
from eslams.contracts.provider import ProviderRuntimeConfig
from eslams.runner import RunConfig, Runner


@pytest.mark.parametrize('status', [200, 429, 503])
@pytest.mark.parametrize('partial', [False, True])
@pytest.mark.parametrize('failure', ['timeout', 'reset', 'resource'])
def test_actual_reader_interruption_retains_only_bounded_header_evidence(
    tmp_path, monkeypatch, status, partial, failure,
):
    calls = []
    original_client = httpx.AsyncClient
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if partial:
                yield b'{"private_prompt":"synthetic-secret-body",'
            if failure == 'timeout':
                raise httpx.ReadTimeout('synthetic-secret-timeout')
            if failure == 'reset':
                raise httpx.ReadError('synthetic-secret-reset')
            yield b'x' * (1024 * 1024 + 1)
    def respond(request):
        calls.append(1)
        return httpx.Response(status, stream=Stream(), request=request,
            headers={'x-request-id': 'safe-request', 'cf-aig-request-id': 'safe-gateway'})
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
    monkeypatch.setattr(http_io.httpx, 'AsyncClient', lambda **kwargs: Client())
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=2))
    result = Runner().run(RunConfig('tic-tac-toe', agent_1=agent,
        on_agent_error='forfeit', output_dir=tmp_path))
    receipt_path = result.expanded_path / 'receipts/provider_receipts.jsonl'
    receipts = [json.loads(line) for line in receipt_path.read_text().splitlines()]
    assert calls == [1] and len(receipts) == 1
    receipt = receipts[0]
    expected = {'timeout': 'provider_timeout', 'reset': 'provider_transport_error',
                'resource': 'provider_response_schema_mismatch'}[failure]
    assert receipt['outcome'] == expected
    assert receipt['status_code'] == status
    assert receipt['request_id'] == 'safe-request'
    assert receipt['gateway_request_id'] == 'safe-gateway'
    assert not receipt['action_applied'] and not receipt['usage']
    assert not receipt.get('provider_response_id')
    assert result.score.aggregate_usage['totalCostUsd'] is None
    assert result.score.winner is None and not result.score.match_valid_for_scoring
    assert result.score.fallback_action_count_by_player['player_1'] == 0
    assert ArtifactValidator().validate(result.expanded_path) == []
    for path in result.expanded_path.rglob('*'):
        if path.is_file():
            assert b'synthetic-secret' not in path.read_bytes()
