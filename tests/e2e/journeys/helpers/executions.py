from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any


async def wait_for_execution(
    client,
    execution_id: str,
    timeout: float = 60.0,
    expected_states: Iterable[str] = ("completed",),
) -> dict[str, Any]:
    expected = {state for state in expected_states}
    deadline = asyncio.get_running_loop().time() + timeout
    last_payload: dict[str, Any] | None = None
    last_state = "unknown"

    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/v1/executions/{execution_id}")
        response.raise_for_status()
        last_payload = response.json()
        last_state = str(last_payload.get("status", "unknown"))
        if last_state in expected:
            return last_payload
        await asyncio.sleep(1.0)

    raise AssertionError(
        f"execution {execution_id} did not reach {sorted(expected)} before timeout; "
        f"last state={last_state}, last payload={last_payload}"
    )


async def assert_checkpoint_resumed(client, execution_id: str, checkpoint_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/executions/{execution_id}")
    response.raise_for_status()
    payload = response.json()
    checkpoint = (
        payload.get("last_checkpoint_id")
        or payload.get("checkpoint_id")
        or payload.get("resume_checkpoint_id")
    )
    if str(checkpoint) != str(checkpoint_id):
        raise AssertionError(
            f"execution {execution_id} did not resume from checkpoint {checkpoint_id}; "
            f"observed checkpoint={checkpoint}"
        )
    return payload
