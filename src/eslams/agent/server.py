"""Small FastAPI server wrapper for building /act agents."""

from __future__ import annotations

from inspect import isawaitable, iscoroutinefunction
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from eslams.protocol import ActRequest, ActResponse, ProtocolError
from eslams.request_limits import DEFAULT_REQUEST_BYTES, RequestBodyLimitMiddleware


class AgentServer:
    def __init__(
        self,
        *,
        title: str = "eSlams Agent",
        agent_id: str = "custom-agent",
        version: str = "1",
        max_request_bytes: int = DEFAULT_REQUEST_BYTES,
    ) -> None:
        self.title = title
        self.agent_id = agent_id
        self.version = version
        self.app = FastAPI(title=title)
        self.app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_request_bytes)
        self._handler: Callable[[ActRequest], Any] | None = None
        self.app.post("/act")(self._act)
        self.app.get("/health")(self._health)

    def act(self, func: Callable[[ActRequest], Any]) -> Callable[[ActRequest], Any]:
        self._handler = func
        return func

    async def _health(self) -> dict[str, Any]:
        return {"status": "ok", "agent_id": self.agent_id, "version": self.version,
                "supported_protocol_versions": ["eslams-act-v1", "eslams-act-v2"]}

    async def _act(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._handler is None:
            raise HTTPException(status_code=503, detail="No /act handler registered")
        try:
            request = ActRequest.from_mapping(payload)
            if iscoroutinefunction(self._handler):
                value = await self._handler(request)
            else:
                value = await run_in_threadpool(self._handler, request)
                if isawaitable(value):
                    value = await value
            if isinstance(value, ActResponse):
                response = value
            elif isinstance(value, dict):
                response = ActResponse.from_mapping(value)
            else:
                response = ActResponse(action=value)
            return ActResponse.from_mapping(response.to_dict()).to_dict()
        except ProtocolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def run(self, *, host: str = "127.0.0.1", port: int = 8000) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("port must be an integer between 1 and 65535")
        import uvicorn

        uvicorn.run(self.app, host=host, port=port)
