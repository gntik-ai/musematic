from __future__ import annotations

from datetime import datetime
from time import perf_counter
from uuid import uuid4

import pytest

from tests.integration.test_clickhouse_basic import USAGE_EVENT_COLUMNS, _usage_event


pytestmark = pytest.mark.asyncio


async def test_materialized_view_rollup_updates_automatically(clickhouse_client) -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    agent_id = uuid4()
    hour = datetime(2026, 4, 10, 14, 0, 0)

    first_batch = []
    for index in range(100):
        event = _usage_event(workspace_id, agent_id, index)
        event["event_time"] = hour
        event["input_tokens"] = 100
        first_batch.append(event)

    await clickhouse_client.insert_batch("usage_events", first_batch, USAGE_EVENT_COLUMNS)

    started_at = perf_counter()
    first_rows = await clickhouse_client.execute_query(
        "SELECT sum(total_input_tokens) AS input_sum, sum(event_count) AS event_count "
        "FROM usage_hourly WHERE workspace_id = {ws:UUID} AND agent_id = {agent:UUID}",
        params={"ws": workspace_id, "agent": agent_id},
    )
    duration = perf_counter() - started_at

    assert int(first_rows[0]["event_count"]) == 100
    assert int(first_rows[0]["input_sum"]) == 10000
    assert duration < 0.2

    second_batch = []
    for index in range(50):
        event = _usage_event(workspace_id, agent_id, 1000 + index)
        event["event_time"] = hour
        event["input_tokens"] = 100
        second_batch.append(event)
    await clickhouse_client.insert_batch("usage_events", second_batch, USAGE_EVENT_COLUMNS)

    other_event = _usage_event(other_workspace_id, uuid4(), 2000)
    other_event["event_time"] = hour
    await clickhouse_client.insert_batch("usage_events", [other_event], USAGE_EVENT_COLUMNS)

    updated_rows = await clickhouse_client.execute_query(
        "SELECT sum(total_input_tokens) AS input_sum, sum(event_count) AS event_count "
        "FROM usage_hourly WHERE workspace_id = {ws:UUID} AND agent_id = {agent:UUID}",
        params={"ws": workspace_id, "agent": agent_id},
    )
    isolated_rows = await clickhouse_client.execute_query(
        "SELECT sum(event_count) AS event_count FROM usage_hourly WHERE workspace_id = {ws:UUID}",
        params={"ws": other_workspace_id},
    )

    assert int(updated_rows[0]["event_count"]) == 150
    assert int(updated_rows[0]["input_sum"]) == 15000
    assert int(isolated_rows[0]["event_count"]) == 1
