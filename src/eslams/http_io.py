"""Bounded non-streaming JSON responses for agent and provider HTTP calls."""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from eslams.deadlines import check_cancelled, current_deadline, remaining_seconds
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


@dataclass(frozen=True)
class ResponseObservation:
    """Private, bounded header evidence; never a claim about body or billing."""

    status_code: int
    headers: tuple[tuple[str, str], ...]


def response_observation(exc: BaseException) -> ResponseObservation | None:
    value = getattr(exc, "_eslams_response_observation", None)
    return value if isinstance(value, ResponseObservation) else None


def _attach_observation(exc: BaseException, observed: list[ResponseObservation]) -> None:
    if observed:
        exc.__dict__["_eslams_response_observation"] = observed[0]


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
    json: dict[str, Any] | None,
    timeout: Any,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    deadline: float | None
    if isinstance(timeout, TotalTimeout):
        deadline = timeout.deadline
    elif isinstance(timeout, (int, float)):
        deadline = time.monotonic() + float(timeout)
    else:
        # HTTP phase limits (notably connect/write) are not total thinking limits.
        deadline = None
    action = current_deadline()
    if action is not None:
        deadline = min(deadline, action) if deadline is not None else action
    remaining_seconds(deadline)
    observed: list[ResponseObservation] = []
    coroutine = _bounded_post(
        url, headers=headers, json=json, timeout=timeout, data=data, _observed=observed,
    )
    try:
        future = asyncio.run_coroutine_threadsafe(coroutine, _network_loop())
    except BaseException:
        coroutine.close()
        raise
    try:
        while True:
            check_cancelled()
            remaining = remaining_seconds(deadline)
            try:
                return future.result(timeout=0.1 if remaining is None else min(0.1, remaining))
            except concurrent.futures.TimeoutError:
                if future.done():
                    return future.result()
    except TimeoutError as exc:
        future.cancel()
        failure = httpx.ReadTimeout("HTTP total elapsed deadline expired")
        _attach_observation(failure, observed)
        raise failure from exc
    except BaseException as exc:
        future.cancel()
        _attach_observation(exc, observed)
        raise


async def _bounded_post(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None,
    timeout: Any,
    data: dict[str, str] | None = None,
    _observed: list[ResponseObservation] | None = None,
) -> httpx.Response:
    global _NETWORK_CAPACITY
    if _NETWORK_CAPACITY is None:
        _NETWORK_CAPACITY = asyncio.Semaphore(32)
    async with _NETWORK_CAPACITY:
        request_headers = {**headers, "Accept-Encoding": "identity"}
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", url, headers=request_headers, json=json, data=data) as response,
        ):
            if _observed is not None:
                allowed = (
                    "x-request-id", "request-id", "x-amzn-requestid", "x-global-transaction-id",
                    "cf-aig-request-id", "x-gateway-request-id",
                )
                _observed.append(ResponseObservation(
                    status_code=response.status_code,
                    headers=tuple(
                        (key, response.headers[key])
                        for key in allowed
                        if key in response.headers and len(response.headers[key]) <= 256
                    ),
                ))
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
