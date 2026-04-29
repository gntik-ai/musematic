"""Prometheus metric assertions.

Contract: specs/085-extended-e2e-journey/contracts/observability-helpers.md
"""

from __future__ import annotations

import asyncio
import time

import httpx


async def assert_metric_value(
    prom_client: httpx.AsyncClient,
    query: str,
    expected: float,
    tolerance: float = 0.01,
    within_seconds: int = 15,
    poll_interval: float = 1.0,
) -> float:
    deadline = time.monotonic() + within_seconds
    last_value: float | None = None
    last_payload: dict | None = None

    while time.monotonic() < deadline:
        response = await prom_client.get("/api/v1/query", params={"query": query})
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        results = payload.get("data", {}).get("result", [])
        if results:
            raw_value = results[0].get("value", [None, None])[1]
            if raw_value is not None:
                last_value = float(raw_value)
                if abs(last_value - expected) <= tolerance:
                    return last_value
        await asyncio.sleep(poll_interval)

    raise AssertionError(
        f"Prometheus query {query!r} did not reach {expected} +/- {tolerance} "
        f"within {within_seconds}s; last_value={last_value!r}; last_payload={last_payload!r}"
    )
