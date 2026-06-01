"""Small FastAPI server wrapper for building /act agents."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException

from eslams.protocol import ActRequest, ActResponse, ProtocolError


class AgentServer:
    def __init__(
        self,
        *,
        title: str = "eSlams Agent",
        agent_id: str = "custom-agent",
        version: str = "1",
    ) -> None:
        self.title = title
        self.agent_id = agent_id
        self.version = version
        self.app = FastAPI(title=title)
        self._handler: Callable[[ActRequest], Any] | None = None
        self.app.post("/act")(self._act)
        self.app.get("/health")(self._health)

    def act(self, func: Callable[[ActRequest], Any]) -> Callable[[ActRequest], Any]:
        self._handler = func
        return func

    async def _health(self) -> dict[str, str]:
        return {"status": "ok", "agent_id": self.agent_id, "version": self.version}

    async def _act(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._handler is None:
            raise HTTPException(status_code=503, detail="No /act handler registered")
        try:
            request = ActRequest.from_mapping(payload)
            value = self._handler(request)
            if isinstance(value, ActResponse):
                response = value
            elif isinstance(value, dict):
                response = ActResponse.from_mapping(value)
            else:
                response = ActResponse(action=value)
            return response.to_dict()
        except ProtocolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def run(self, *, host: str = "0.0.0.0", port: int = 8000) -> None:
        import uvicorn

        uvicorn.run(self.app, host=host, port=port)
