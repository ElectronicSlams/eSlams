"""Bounded non-streaming JSON responses for agent and provider HTTP calls."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any

import httpx

from eslams.deadlines import current_deadline, remaining_seconds
from eslams.protocol import MAX_RESPONSE_BYTES, ProtocolError


class TotalTimeout(httpx.Timeout):
    """HTTP phase limits plus a genuine elapsed request deadline."""

    def __init__(self, seconds: float, *, connect: float, read: float, deadline: float):
        super().__init__(
            timeout=seconds,
            connect=min(connect, seconds),
            read=min(read, seconds),
            write=min(read, seconds),
            pool=min(connect, seconds),
        )
        self.deadline = deadline


_LOOP_LOCK = threading.Lock()
_NETWORK_LOOP: asyncio.AbstractEventLoop | None = None
_NETWORK_CAPACITY: asyncio.Semaphore | None = None


def _network_loop() -> asyncio.AbstractEventLoop:
    global _NETWORK_LOOP
    with _LOOP_LOCK:
        if _NETWORK_LOOP is None:
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name="eslams-http", daemon=True)
            thread.start()
            _NETWORK_LOOP = loop
        return _NETWORK_LOOP


def bounded_post(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout: Any,
) -> httpx.Response:
    if isinstance(timeout, TotalTimeout):
        deadline = timeout.deadline
    elif isinstance(timeout, (int, float)):
        deadline = time.monotonic() + float(timeout)
    else:
        phases = [value for value in timeout.as_dict().values() if value is not None]
        deadline = time.monotonic() + max(phases, default=60.0)
    action = current_deadline()
    if action is not None:
        deadline = min(deadline, action)
    remaining_seconds(deadline)
    coroutine = _bounded_post(url, headers=headers, json=json, timeout=timeout)
    try:
        future = asyncio.run_coroutine_threadsafe(coroutine, _network_loop())
    except BaseException:
        coroutine.close()
        raise
    try:
        return future.result(timeout=remaining_seconds(deadline))
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise httpx.ReadTimeout("HTTP total elapsed deadline expired") from exc
    except BaseException:
        future.cancel()
        raise


async def _bounded_post(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout: Any,
) -> httpx.Response:
    global _NETWORK_CAPACITY
    if _NETWORK_CAPACITY is None:
        _NETWORK_CAPACITY = asyncio.Semaphore(32)
    async with _NETWORK_CAPACITY:
        request_headers = {**headers, "Accept-Encoding": "identity"}
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", url, headers=request_headers, json=json) as response,
        ):
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise ProtocolError("compressed agent/provider responses are unsupported")
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    length = int(declared)
                except ValueError as exc:
                    raise ProtocolError("invalid response Content-Length") from exc
                if length < 0 or length > MAX_RESPONSE_BYTES:
                    raise ProtocolError("agent/provider response exceeds 1 MiB limit")
            body = bytearray()
            async for block in response.aiter_raw(chunk_size=64 * 1024):
                if len(body) + len(block) > MAX_RESPONSE_BYTES:
                    raise ProtocolError("agent/provider response exceeds 1 MiB limit")
                body.extend(block)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )
