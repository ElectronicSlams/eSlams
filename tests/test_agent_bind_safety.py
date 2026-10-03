import pytest

from eslams.agent import AgentServer
from eslams.cli import main


@pytest.mark.parametrize("port", [-1, 0, 65536, True, 1.5])
def test_agent_server_rejects_bad_ports_before_binding(monkeypatch, port):
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: pytest.fail("must not bind"))
    with pytest.raises(ValueError, match="port must be"):
        AgentServer().run(port=port)


def test_cli_default_loopback_and_explicit_container_bind(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: calls.append(kw))
    assert main(["agent", "serve"]) == 0
    assert calls[-1] == {"host": "127.0.0.1", "port": 8000}
    assert main(["agent", "serve", "--host", "0.0.0.0", "--port", "65535"]) == 0
    assert calls[-1] == {"host": "0.0.0.0", "port": 65535}
    with pytest.raises(SystemExit) as exc:
        main(["agent", "serve", "--port", "65536"])
    assert exc.value.code == 2
    assert len(calls) == 2
