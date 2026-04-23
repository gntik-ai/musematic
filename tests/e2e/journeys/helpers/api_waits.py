from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any
from uuid import UUID


async def _wait_for_json(
    client: Any,
    path: str,
    *,
    description: str,
    pending_statuses: set[int],
    timeout: float,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    last_status: int | None = None
    last_payload: Any = None
    while monotonic() < deadline:
        response = await client.get(path)
        if response.status_code == 200:
            return response.json()
        if response.status_code not in pending_statuses:
            response.raise_for_status()
        last_status = response.status_code
        try:
            last_payload = response.json()
        except ValueError:
            last_payload = response.text
        await asyncio.sleep(0.5)
    raise AssertionError(
        f"{description} did not become available within {timeout:.0f}s; "
        f"last status={last_status}; last payload={last_payload}"
    )


async def wait_for_workspace_access(
    client: Any,
    workspace_id: UUID | str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await _wait_for_json(
        client,
        f"/api/v1/workspaces/{workspace_id}",
        description=f"workspace {workspace_id}",
        pending_statuses={403, 404},
        timeout=timeout,
    )


async def wait_for_policy(
    client: Any,
    policy_id: UUID | str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await _wait_for_json(
        client,
        f"/api/v1/policies/{policy_id}",
        description=f"policy {policy_id}",
        pending_statuses={404},
        timeout=timeout,
    )


async def wait_for_certification(
    client: Any,
    certification_id: UUID | str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    return await _wait_for_json(
        client,
        f"/api/v1/trust/certifications/{certification_id}",
        description=f"certification {certification_id}",
        pending_statuses={404},
        timeout=timeout,
    )
