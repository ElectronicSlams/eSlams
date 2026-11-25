"""QA disposition: typed input, intentional no-tool and reasoning boundaries."""
import copy
import json

import httpx
import pytest
from test_model_agents import _request
from test_perplexity_adapter import MODEL, _agent, _wire

from eslams.agents import ProviderCallError
from eslams.contracts.provider import ProviderRuntimeConfig


@pytest.mark.parametrize("item_type", ["search_results", "function_call", "mcp_call",
                                       "skill_call", "reasoning", "unknown_future_item"])
@pytest.mark.parametrize("position", ["before", "after"])
def test_completed_text_does_not_hide_unexpected_search_or_tool_work(
    monkeypatch, item_type, position,
):
    data = _wire()
    unexpected = {"type": item_type, "results": [], "queries": ["external query"]}
    data["output"] = ([unexpected, *data["output"]] if position == "before"
                      else [*data["output"], unexpected])
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=data)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    selected = _agent(monkeypatch, runtime_config=ProviderRuntimeConfig(
        max_retries=2, action_repair_attempts=2))
    with pytest.raises(ProviderCallError) as failure:
        selected.act(_request())
    assert failure.value.error_kind == "provider_response_schema_mismatch"
    assert len(calls) == len(selected.attempt_receipts) == 1
    assert calls[0]["input"][0]["type"] == "message"
    assert calls[0]["tools"] == [] and calls[0]["tool_choice"] == "none"
    assert selected.last_receipt["usage"]
    assert "external query" not in json.dumps(selected.last_receipt)


def test_multiple_completed_message_items_can_supply_split_final_text(monkeypatch):
    data = _wire()
    second = copy.deepcopy(data["output"][0])
    data["output"][0]["content"][0]["text"] = '{"action":'
    second["content"][0]["text"] = '1}'
    data["output"].append(second)
    monkeypatch.setattr("eslams.agents.bounded_post",
                        lambda *a, **k: httpx.Response(200, json=data))
    selected = _agent(monkeypatch)
    assert selected.act(_request()).action == 1
    assert selected.model == MODEL
