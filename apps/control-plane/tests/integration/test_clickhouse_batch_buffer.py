from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from platform.common.clients.clickhouse import BatchBuffer
from tests.integration.test_clickhouse_basic import USAGE_EVENT_COLUMNS, _usage_event


pytestmark = pytest.mark.asyncio


async def test_batch_buffer_size_and_stop_flush(clickhouse_client) -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    buffer = BatchBuffer(
        client=clickhouse_client,
        table="usage_events",
        column_names=USAGE_EVENT_COLUMNS,
        max_size=50,
        flush_interval=10.0,
    )

    for index in range(120):
        await buffer.add(_usage_event(workspace_id, agent_id, index))

    await buffer.stop()

    rows = await clickhouse_client.execute_query(
        "SELECT count() AS cnt FROM usage_events WHERE workspace_id = {ws:UUID}",
        params={"ws": workspace_id},
    )
    assert int(rows[0]["cnt"]) == 120


async def test_batch_buffer_timer_flush_and_concurrent_add(clickhouse_client) -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    buffer = BatchBuffer(
        client=clickhouse_client,
        table="usage_events",
        column_names=USAGE_EVENT_COLUMNS,
        max_size=1000,
        flush_interval=0.1,
    )
    await buffer.start()

    await asyncio.gather(
        *[buffer.add(_usage_event(workspace_id, agent_id, index)) for index in range(10)]
    )
    await asyncio.sleep(0.2)
    await buffer.stop()

    rows = await clickhouse_client.execute_query(
        "SELECT count() AS cnt FROM usage_events WHERE workspace_id = {ws:UUID}",
        params={"ws": workspace_id},
    )
    assert int(rows[0]["cnt"]) == 10
