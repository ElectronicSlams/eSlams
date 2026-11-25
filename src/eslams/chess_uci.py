"""Local chess agent for an explicitly trusted UCI executable."""

from __future__ import annotations

import asyncio
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine

from eslams.agents import AgentError
from eslams.arenas.chess import board_from_fen_and_history
from eslams.deadlines import action_deadline, current_deadline, remaining_seconds
from eslams.protocol import ActRequest, ActResponse


@dataclass(frozen=True)
class UciChessAgent:
    """Launch a fresh local engine for each turn, without a shell or provider environment."""

    executable: Path
    depth: int = 8
    id: str = field(default="uci-chess", init=False)
    version: str = field(default="1.0.0", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.depth, int) or isinstance(self.depth, bool) or self.depth < 1:
            raise ValueError("UCI search depth must be a positive integer")
        executable = Path(self.executable)
        if not executable.is_absolute():
            raise ValueError("UCI engine requires an explicit absolute executable path")
        executable = executable.resolve()
        if (
            not executable.is_file()
            or not os.access(executable, os.X_OK)
            or (os.name == "nt" and executable.suffix.lower() != ".exe")
        ):
            raise ValueError("UCI engine path must identify a local executable file")
        object.__setattr__(self, "executable", executable)

    def act(self, request: ActRequest) -> ActResponse:
        if request.arena.id != "chess":
            raise AgentError("UCI engine supports only the chess arena")
        fen = request.observation.get("fen")
        if not isinstance(fen, str):
            raise AgentError("UCI engine requires a valid chess FEN")
        try:
            board = board_from_fen_and_history(fen, request.observation.get("san_history"))
        except ValueError:
            raise AgentError("UCI engine requires a valid chess FEN") from None
        if not board.is_valid() or board.is_game_over():
            raise AgentError("UCI engine requires a valid, actionable chess position")
        try:
            with action_deadline(min(30_000, request.time_budget_ms or 30_000)):
                move = self._play_sync(board)
        except (TimeoutError, asyncio.TimeoutError):
            raise TimeoutError("UCI engine exceeded the action deadline") from None
        except (chess.engine.EngineError, OSError):
            raise AgentError("UCI engine could not produce a move") from None
        if move is None or move not in board.legal_moves or move.uci() not in request.legal_actions:
            raise AgentError("UCI engine returned no legal move")
        return ActResponse(action=move.uci(), metadata={"uci_search_depth": self.depth})

    def _play_sync(self, board: chess.Board) -> chess.Move | None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._play(board))

        # A synchronous library caller may already own the thread's event loop.
        # Join this worker so even a cancelled run waits for the engine to exit.
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(copy_context().run, asyncio.run, self._play(board)).result()

    async def _play(self, board: chess.Board) -> chess.Move | None:
        deadline = current_deadline()
        assert deadline is not None
        # Windows process creation requires SYSTEMROOT on some hosts.
        env = {key: os.environ[key] for key in ("SYSTEMROOT",) if key in os.environ}
        transport, engine = await asyncio.wait_for(
            chess.engine.UciProtocol.popen(
                [str(self.executable)], env=env, cwd=self.executable.parent,
                stderr=subprocess.DEVNULL,
            ),
            timeout=remaining_seconds(deadline),
        )
        search = asyncio.create_task(self._search(engine, board))
        try:
            while True:
                # Poll for cooperative cancellation as well as the elapsed deadline.
                timeout = min(0.05, remaining_seconds(deadline))
                done, _ = await asyncio.wait({search}, timeout=timeout)
                if done:
                    result = search.result()
                    remaining_seconds(deadline)
                    return result
        finally:
            search.cancel()
            # Closing a subprocess transport kills a running process. Await its exit
            # so a timed-out search cannot leave a child running after cleanup.
            transport.close()
            await engine.returncode
            await asyncio.gather(search, return_exceptions=True)

    async def _search(
        self, engine: chess.engine.UciProtocol, board: chess.Board,
    ) -> chess.Move | None:
        await engine.initialize()
        options = {"Threads": 1, "Hash": 16}
        await engine.configure({name: value for name, value in options.items()
                                if name in engine.options})
        result = await engine.play(board, chess.engine.Limit(depth=self.depth), ponder=False)
        return result.move
