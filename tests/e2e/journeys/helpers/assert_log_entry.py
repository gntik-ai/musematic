from __future__ import annotations

import asyncio
import time

import httpx

from journeys.helpers.observability_readiness import LOKI_READY_PATH


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _selector(labels: dict[str, str]) -> str:
    if not labels:
        raise ValueError("at least one Loki label is required")
    parts = [f'{key}="{_escape_label_value(value)}"' for key, value in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


async def assert_log_contains(
    loki_client: httpx.AsyncClient,
    labels: dict[str, str],
    substring: str,
    within_seconds: int = 30,
    poll_interval: float = 1.0,
) -> dict:
    ready = await loki_client.get(LOKI_READY_PATH)
    if ready.status_code != 200:
        raise AssertionError(f"Loki at {loki_client.base_url} not ready: {ready.status_code} {ready.text}")

    query = _selector(labels)
    deadline = time.monotonic() + within_seconds
    start_ns = int((time.time() - within_seconds) * 1_000_000_000)
    last_volume = 0
    last_line = ""

    while time.monotonic() < deadline:
        response = await loki_client.get(
            "/loki/api/v1/query_range",
            params={"query": query, "start": start_ns, "limit": 1000},
        )
        response.raise_for_status()
        payload = response.json()
        streams = payload.get("data", {}).get("result", [])
        last_volume = sum(len(stream.get("values", [])) for stream in streams)
        for stream in streams:
            for timestamp, line in stream.get("values", []):
                last_line = str(line)
                if substring in last_line:
                    return {
                        "timestamp": timestamp,
                        "line": last_line,
                        "stream": stream.get("stream", {}),
                        "query": query,
                    }
        await asyncio.sleep(poll_interval)

    raise AssertionError(
        f"Loki query {query} did not contain {substring!r} within {within_seconds}s; "
        f"last volume={last_volume}; last line={last_line[:240]!r}"
    )
