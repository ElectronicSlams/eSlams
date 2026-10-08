import json
from pathlib import Path

import httpx
import pytest

from eslams.artifacts import ArtifactValidator
from eslams.cli import main


@pytest.mark.parametrize("scenario", ["success", "unreachable", "illegal", "malformed"])
def test_agent_test_exit_and_ok_reflect_the_endpoint_behavior(
    tmp_path, monkeypatch, capsys, scenario
):
    monkeypatch.chdir(tmp_path)

    def post(url, *, json, headers, timeout):
        request = httpx.Request("POST", url)
        if scenario == "unreachable":
            raise httpx.ConnectError("local fixture unreachable", request=request)
        payload = {"action": json["legal_actions"][0]}
        if scenario == "illegal":
            payload = {"action": 999}
        elif scenario == "malformed":
            payload = {"not_action": True}
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr("eslams.agents.bounded_post", post)
    status = main(["agent", "test", "--url", "http://local-fixture.test/act"])
    payload = json.loads(capsys.readouterr().out)
    expected = scenario == "success"
    assert payload["ok"] is expected
    assert status == (0 if expected else 1)
    assert payload["checks"]["tested_actions"] > 0
    assert bool(payload["failure_reason"]) is not expected
    assert ArtifactValidator().validate(Path(payload["artifact"])) == []
