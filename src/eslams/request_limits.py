"""Host-configurable ASGI body admission before JSON parsing or agent callbacks."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_REQUEST_BYTES = 1024 * 1024


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int = DEFAULT_REQUEST_BYTES) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise ValueError("max_request_bytes must be a positive host resource choice")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declarations = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        declared: int | None = None
        if declarations:
            try:
                if len(declarations) != 1 or len(declarations[0]) > 32:
                    raise ValueError("invalid length")
                raw = declarations[0]
                if not raw or not raw.isdigit():
                    raise ValueError("invalid length")
                declared = int(raw)
            except ValueError:
                await self._reject(send, 400)
                return
            if declared > self.max_bytes:
                await self._reject(send, 413)
                return
        admitted_body = bytearray()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            if message["type"] != "http.request" or not isinstance(body, bytes):
                await self._reject(send, 400)
                return
            size += len(body)
            if size > self.max_bytes:
                await self._reject(send, 413)
                return
            admitted_body.extend(body)
            if not message.get("more_body", False):
                break
        if declared is not None and size != declared:
            await self._reject(send, 400)
            return
        delivered = False

        async def admitted_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(admitted_body), "more_body": False}
            return await receive()

        await self.app(scope, admitted_receive, send)

    @staticmethod
    async def _reject(send: Send, status: int) -> None:
        body = (b'{"detail":"request body exceeds host byte admission policy"}' if status == 413
                else b'{"detail":"invalid request body framing"}')
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
