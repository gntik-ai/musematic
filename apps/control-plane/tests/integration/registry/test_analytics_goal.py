from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from platform.analytics import clickhouse_setup
from platform.analytics.repository import AnalyticsRepository
from platform.common.config import PlatformSettings
from uuid import UUID, uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

REPO_ROOT = Path(__file__).resolve().parents[5]
MIGRATION_FILE = REPO_ROOT / "deploy" / "clickhouse" / "init" / "007-add-goal-id.sql"


def _migration_statements() -> list[str]:
    return [
        statement.strip()
        for statement in MIGRATION_FILE.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]


async def _apply_goal_id_migration(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    for statement in _migration_statements():
        await clickhouse_client.execute_command(statement)


def _usage_row(
    *,
    workspace_id,
    execution_id,
    goal_id,
    input_tokens,
    timestamp: datetime,
):  # type: ignore[no-untyped-def]
    return {
        "event_id": uuid4(),
        "execution_id": execution_id,
        "workspace_id": workspace_id,
        "goal_id": goal_id,
        "agent_fqn": "planner:daily",
        "model_id": "gpt-4o",
        "provider": "openai",
        "timestamp": timestamp,
        "input_tokens": input_tokens,
        "output_tokens": 5,
        "execution_duration_ms": 25,
        "self_correction_loops": 0,
        "reasoning_tokens": 0,
        "cost_usd": Decimal("1.0"),
        "pipeline_version": "1",
        "ingested_at": timestamp,
    }


async def test_usage_events_has_goal_id_column(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    await clickhouse_setup.run_setup(client=clickhouse_client, settings=PlatformSettings())
    await _apply_goal_id_migration(clickhouse_client)

    columns = await clickhouse_client.execute_query("DESCRIBE TABLE analytics_usage_events")
    goal_column = next(column for column in columns if column["name"] == "goal_id")

    assert goal_column["type"] == "Nullable(UUID)"


async def test_insert_usage_event_with_goal_id(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    await clickhouse_setup.run_setup(client=clickhouse_client, settings=PlatformSettings())
    await _apply_goal_id_migration(clickhouse_client)
    repository = AnalyticsRepository(clickhouse_client)
    workspace_id = uuid4()
    goal_id = uuid4()
    execution_id = uuid4()
    timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    await repository.insert_usage_events_batch(
        [
            _usage_row(
                workspace_id=workspace_id,
                execution_id=execution_id,
                goal_id=goal_id,
                input_tokens=10,
                timestamp=timestamp,
            )
        ]
    )

    rows = await clickhouse_client.execute_query(
        "SELECT goal_id FROM analytics_usage_events WHERE execution_id = {execution_id:UUID}",
        params={"execution_id": execution_id},
    )

    assert rows == [{"goal_id": goal_id}]


async def test_group_by_goal_id_yields_two_buckets(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    await clickhouse_setup.run_setup(client=clickhouse_client, settings=PlatformSettings())
    await _apply_goal_id_migration(clickhouse_client)
    repository = AnalyticsRepository(clickhouse_client)
    workspace_id = uuid4()
    goal_a = uuid4()
    goal_b = uuid4()
    timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    await repository.insert_usage_events_batch(
        [
            _usage_row(
                workspace_id=workspace_id,
                execution_id=uuid4(),
                goal_id=goal_a,
                input_tokens=10,
                timestamp=timestamp,
            ),
            _usage_row(
                workspace_id=workspace_id,
                execution_id=uuid4(),
                goal_id=goal_a,
                input_tokens=20,
                timestamp=timestamp,
            ),
            _usage_row(
                workspace_id=workspace_id,
                execution_id=uuid4(),
                goal_id=goal_b,
                input_tokens=30,
                timestamp=timestamp,
            ),
        ]
    )

    rows = await clickhouse_client.execute_query(
        """
        SELECT
            goal_id,
            sumMerge(input_tokens_state) AS total_input_tokens
        FROM analytics_usage_hourly_v2
        WHERE workspace_id = {workspace_id:UUID}
        GROUP BY goal_id
        ORDER BY goal_id ASC
        """,
        params={"workspace_id": workspace_id},
    )

    assert {(UUID(str(row["goal_id"])), row["total_input_tokens"]) for row in rows} == {
        (goal_a, 30),
        (goal_b, 30),
    }


async def test_null_goal_id_bucket(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    await clickhouse_setup.run_setup(client=clickhouse_client, settings=PlatformSettings())
    await _apply_goal_id_migration(clickhouse_client)
    repository = AnalyticsRepository(clickhouse_client)
    workspace_id = uuid4()
    timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    await repository.insert_usage_events_batch(
        [
            _usage_row(
                workspace_id=workspace_id,
                execution_id=uuid4(),
                goal_id=None,
                input_tokens=10,
                timestamp=timestamp,
            )
        ]
    )

    rows = await clickhouse_client.execute_query(
        "SELECT count() AS total FROM analytics_usage_events WHERE goal_id IS NULL"
    )

    assert rows == [{"total": 1}]


async def test_migration_idempotent(clickhouse_client) -> None:  # type: ignore[no-untyped-def]
    await clickhouse_setup.run_setup(client=clickhouse_client, settings=PlatformSettings())

    await _apply_goal_id_migration(clickhouse_client)
    await _apply_goal_id_migration(clickhouse_client)
