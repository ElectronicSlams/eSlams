from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import chess
import pytest

from eslams import RunConfig, Runner, UciChessAgent
from eslams.agents import AgentError, HttpAgent
from eslams.protocol import ActRequest, AgentIdentity, ArenaIdentity
from eslams.runner import RunResult


def _request(*, budget: int | None = None) -> ActRequest:
    return ActRequest(
        protocol_version="eslams-act-v2",
        run_id="uci-test",
        episode_id="episode",
        turn_id=0,
        arena=ArenaIdentity("chess", "1.2.0"),
        agent=AgentIdentity("uci-chess", "1.0.0"),
        active_player="player_1",
        observation={"fen": chess.STARTING_FEN, "san_history": []},
        legal_actions=["e2e4"],
        action_schema={},
        history=[],
        time_budget_ms=budget,
        memory_policy="current_observation_plus_public_history",
    )


def test_uci_is_explicit_and_local(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute executable path"):
        UciChessAgent(Path("stockfish"))
    with pytest.raises(ValueError, match="positive integer"):
        UciChessAgent(Path(sys.executable), depth=0)
    engine = UciChessAgent(Path(sys.executable))
    for context in (
        {"arena_id": "tic-tac-toe"},
        {"arena_id": "chess", "environment": "remote"},
        {"arena_id": "chess", "execution_profile": "official_eval"},
    ):
        with pytest.raises(ValueError, match="local, unofficial chess"):
            Runner().run(RunConfig(agent_1=engine, output_dir=tmp_path, **context))
    with pytest.raises(ValueError, match="local agents on all seats"):
        Runner().run(RunConfig(
            arena_id="chess",
            agent_1=engine,
            agent_2=HttpAgent("https://example.invalid"),
            output_dir=tmp_path,
        ))
    with pytest.raises(AgentError, match="valid chess FEN"):
        engine.act(replace(_request(), observation={"fen": "malformed"}))


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX script and PID checks")
@pytest.mark.parametrize("answer", ["e2e4", "e2e5", "d2d4", "hang", "no-handshake"])
def test_uci_protocol_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str):
    executable = tmp_path / "fake uci engine"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys, time\n"
        "assert 'OPENAI_API_KEY' not in os.environ\n"
        "pathlib.Path('pid').write_text(str(os.getpid()))\n"
        "options = set()\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if line == 'uci':\n"
        f"        if {answer!r} == 'no-handshake':\n"
        "            time.sleep(60)\n"
        "        print('id name fixture')\n"
        "        print('option name Threads type spin default 2 min 1 max 8')\n"
        "        print('option name Hash type spin default 32 min 1 max 128')\n"
        "        print('uciok', flush=True)\n"
        "    elif line.startswith('setoption '):\n"
        "        options.add(line)\n"
        "    elif line == 'isready':\n"
        "        print('readyok', flush=True)\n"
        "    elif line.startswith('go'):\n"
        "        assert line == 'go depth 4'\n"
        "        assert set(['setoption name Threads value 1',\n"
        "                    'setoption name Hash value 16']) <= options\n"
        f"        if {answer!r} == 'hang':\n"
        "            time.sleep(60)\n"
        f"        print('bestmove ' + {answer!r}, flush=True)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret")
    agent = UciChessAgent(executable, depth=4)
    if answer == "e2e4":
        assert agent.act(_request()).action == "e2e4"
    elif answer in {"hang", "no-handshake"}:
        with pytest.raises(TimeoutError, match="action deadline"):
            agent.act(_request(budget=750))
    else:
        with pytest.raises(AgentError, match="UCI engine"):
            agent.act(_request())
    pid = int((tmp_path / "pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX script and PID checks")
@pytest.mark.parametrize("failure", ["operator_cancelled", "provider_timeout"])
def test_runner_waits_for_interrupted_uci_cleanup(tmp_path: Path, failure: str) -> None:
    executable = tmp_path / "engine"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, sys, time\n"
        "for line in sys.stdin:\n"
        "    if line.strip() == 'uci':\n"
        "        print('uciok', flush=True)\n"
        "    elif line.strip() == 'isready':\n"
        "        print('readyok', flush=True)\n"
        "    elif line.startswith('go'):\n"
        "        pathlib.Path('pid').write_text(str(os.getpid()))\n"
        "        time.sleep(60)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    cancelled = threading.Event()
    cleanup_finished = threading.Event()

    class ObservedCleanupAgent(UciChessAgent):
        async def _play(self, board: chess.Board) -> chess.Move | None:
            try:
                return await super()._play(board)
            finally:
                await asyncio.sleep(0.5)
                cleanup_finished.set()

    def interrupt_after_start() -> None:
        deadline = time.monotonic() + 5
        while not (tmp_path / "pid").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        cancelled.set()

    async def run_from_async_caller() -> RunResult:
        return Runner().run(RunConfig(
            arena_id="chess",
            agent_1=ObservedCleanupAgent(executable),
            output_dir=tmp_path / "runs",
            cancellation=cancelled if failure == "operator_cancelled" else None,
            time_budget_ms=750 if failure == "provider_timeout" else None,
        ))

    trigger = None
    if failure == "operator_cancelled":
        trigger = threading.Thread(target=interrupt_after_start)
        trigger.start()
    try:
        result = asyncio.run(run_from_async_caller())
        assert cleanup_finished.is_set()
        assert failure in result.score.invalid_reason_codes
        assert not result.score.match_valid_for_scoring
        pid = int((tmp_path / "pid").read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if trigger is not None:
            trigger.join()
