from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


SUCCESS = {200, 201, 202, 204}


def unique_name(prefix: str) -> str:
    return f"test-{prefix}-{uuid4().hex[:8]}"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def assert_status(response, expected: set[int] | None = None) -> dict[str, Any]:
    expected_codes = expected or SUCCESS
    assert response.status_code in expected_codes, response.text
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


async def assert_eventually(
    probe: Callable[[], Awaitable[Any]],
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 20.0,
    interval: float = 0.5,
    message: str = "condition was not met",
) -> Any:
    deadline = asyncio.get_running_loop().time() + timeout
    last_value: Any = None
    while asyncio.get_running_loop().time() < deadline:
        last_value = await probe()
        if predicate(last_value):
            return last_value
        await asyncio.sleep(interval)
    raise AssertionError(f"{message}: {last_value!r}")


async def post_json(http_client, path: str, payload: dict[str, Any], expected=None):
    return assert_status(await http_client.post(path, json=payload), expected)


async def patch_json(http_client, path: str, payload: dict[str, Any], expected=None):
    return assert_status(await http_client.patch(path, json=payload), expected)


async def get_json(http_client, path: str, expected=None, **kwargs):
    return assert_status(await http_client.get(path, **kwargs), expected)


async def delete_ok(http_client, path: str, expected=None) -> dict[str, Any]:
    return assert_status(await http_client.delete(path), expected or {200, 202, 204, 404})


async def wait_for_state(
    http_client,
    path: str,
    states: set[str],
    *,
    field: str = "state",
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await assert_eventually(
        lambda: get_json(http_client, path),
        lambda payload: payload.get(field) in states,
        timeout=timeout,
        message=f"{path} did not enter {sorted(states)}",
    )


def append_performance_measurement(
    report_path: Path,
    *,
    test: str,
    measured: float,
    threshold: float,
    unit: str,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    else:
        payload = {"runs": []}
    payload["runs"].append(
        {
            "test": test,
            "measured": measured,
            "threshold": threshold,
            "passed": measured <= threshold,
            "unit": unit,
        }
    )
    report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
