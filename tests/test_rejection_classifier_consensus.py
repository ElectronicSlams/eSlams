"""Independent code/type agreement, separate from display-class precedence."""
import httpx
import pytest
from test_model_agents import _request

from eslams.agents import ModelProviderAgent, ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig

ABSENT = object()
CODES = [ABSENT, None, False, 429, 503, 401, 504, 'rate_limit_exceeded',
         'timeout_error', 'unknown', 429.0, {'x': 'unknown'}]
TYPES = [ABSENT, None, True, 'rate_limit_error', 'rate_limit_exceeded', 'timeout_error',
         'server_error', 'authentication_error', 'permission_error', 'invalid_request_error',
         'overloaded_error', 'unknown', 429, ['rate_limit_error']]


def cases():
    rows = []
    for status in [200, 429]:
        for ci, code in enumerate(CODES):
            for ti, kind in enumerate(TYPES):
                error = {}
                decisions = []
                if code is not ABSENT:
                    error['code'] = code
                    decisions.append(
                        type(code) is int and code == 429 or isinstance(code, str)
                        and code in {'rate_limit_error', 'rate_limit_exceeded'}
                    )
                if kind is not ABSENT:
                    error['type'] = kind
                    decisions.append(isinstance(kind, str) and
                        kind in {'rate_limit_error', 'rate_limit_exceeded'})
                rows.append({'id': f'http{status}-code{ci}-type{ti}', 'http_status': status,
                    'body': {'error': error},
                    'expected_attempts': 2 if decisions and all(decisions) else 1})
    return rows


@pytest.mark.parametrize('case', cases(), ids=lambda case: case['id'])
def test_every_supplied_classifier_must_agree_before_optional_retry(monkeypatch, case):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-key')
    calls = []
    def post(url, **kwargs):
        calls.append(1)
        return httpx.Response(case['http_status'], json=case['body'],
                              request=httpx.Request('POST', url))
    monkeypatch.setattr('eslams.agents.bounded_post', post)
    agent = ModelProviderAgent('openrouter', 'synthetic-model', 'OPENROUTER_API_KEY',
        runtime_config=ProviderRuntimeConfig(max_retries=1, retry_backoff_ms=0))
    with pytest.raises(ProviderCallError):
        agent.act(_request())
    assert len(calls) == len(agent.attempt_receipts) == case['expected_attempts']
    assert not any(row.get('action_applied') for row in agent.attempt_receipts)
