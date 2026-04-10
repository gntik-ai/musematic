from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from platform.common.exceptions import ClickHouseQueryError


pytestmark = pytest.mark.asyncio


USAGE_EVENT_COLUMNS = [
    "event_id",
    "workspace_id",
    "user_id",
    "agent_id",
    "workflow_id",
    "execution_id",
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "estimated_cost",
    "context_quality_score",
    "reasoning_depth",
    "event_time",
]


def _usage_event(workspace_id, agent_id, offset: int) -> dict[str, object]:
    return {
        "event_id": uuid4(),
        "workspace_id": workspace_id,
        "user_id": uuid4(),
        "agent_id": agent_id,
        "workflow_id": None,
        "execution_id": None,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "input_tokens": 100 + offset,
        "output_tokens": 50 + offset,
        "reasoning_tokens": offset % 4,
        "cached_tokens": offset % 3,
        "estimated_cost": round(0.001 + offset / 100000, 6),
        "context_quality_score": 0.8,
        "reasoning_depth": offset % 5,
        "event_time": datetime.now(tz=UTC) + timedelta(seconds=offset),
    }


async def test_insert_query_workspace_isolation_and_health(clickhouse_client) -> None:
    workspace_ids = [uuid4() for _ in range(3)]
    agent_ids = [uuid4() for _ in range(3)]
    rows: list[dict[str, object]] = []
    for index in range(100):
        bucket = index % 3
        rows.append(_usage_event(workspace_ids[bucket], agent_ids[bucket], index))

    await clickhouse_client.insert_batch("usage_events", rows, USAGE_EVENT_COLUMNS)

    scoped = await clickhouse_client.execute_query(
        "SELECT workspace_id, count() AS cnt FROM usage_events "
        "WHERE workspace_id = {ws:UUID} GROUP BY workspace_id",
        params={"ws": workspace_ids[0]},
    )
    all_rows = await clickhouse_client.execute_query("SELECT count() AS cnt FROM usage_events")
    health = await clickhouse_client.health_check()

    assert scoped
    assert len(scoped) == 1
    assert int(scoped[0]["cnt"]) == 34
    assert int(all_rows[0]["cnt"]) == 100
    assert health["status"] == "ok"


async def test_invalid_sql_and_wrong_insert_shape_raise(clickhouse_client) -> None:
    with pytest.raises(ClickHouseQueryError):
        await clickhouse_client.execute_query("SELECT definitely_not_valid FROM")

    with pytest.raises(ClickHouseQueryError):
        await clickhouse_client.insert_batch(
            "usage_events",
            [{"event_id": uuid4()}],
            USAGE_EVENT_COLUMNS,
        )
