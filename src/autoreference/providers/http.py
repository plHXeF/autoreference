"""Bounded retries for idempotent scholarly searches."""

from __future__ import annotations

import asyncio

import httpx


async def request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> dict:
    for attempt in range(3):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                try:
                    delay = min(5.0, max(0.0, float(response.headers.get("Retry-After", 1))))
                except ValueError:
                    delay = 1.0
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            return data
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    raise RuntimeError("Retry budget exhausted")
