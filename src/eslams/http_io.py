"""Bounded non-streaming JSON responses for agent and provider HTTP calls."""

from __future__ import annotations

from typing import Any

import httpx

from eslams.protocol import MAX_RESPONSE_BYTES, ProtocolError


def bounded_post(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout: Any,
) -> httpx.Response:
    # Request identity encoding and refuse compressed replies before a decoder
    # can allocate the expansion of an adversarial gzip/brotli response.
    request_headers = {**headers, "Accept-Encoding": "identity"}
    with httpx.stream("POST", url, headers=request_headers, json=json, timeout=timeout) as response:
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
        for block in response.iter_raw(chunk_size=64 * 1024):
            if len(body) + len(block) > MAX_RESPONSE_BYTES:
                raise ProtocolError("agent/provider response exceeds 1 MiB limit")
            body.extend(block)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=bytes(body),
            request=response.request,
        )
