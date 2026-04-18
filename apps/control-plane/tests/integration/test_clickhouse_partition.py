from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


async def test_ttl_and_partition_metadata(clickhouse_client) -> None:
    rows = await clickhouse_client.execute_query(
        "SELECT name, engine, partition_key, sorting_key, create_table_query "
        "FROM system.tables "
        "WHERE database = currentDatabase() "
        "AND name IN ("
        "'usage_events', 'behavioral_drift', 'fleet_performance', "
        "'self_correction_analytics'"
        ") "
        "ORDER BY name"
    )
    by_name = {row["name"]: row for row in rows}

    drift_create = str(by_name["behavioral_drift"]["create_table_query"])
    usage_create = str(by_name["usage_events"]["create_table_query"])
    fleet_create = str(by_name["fleet_performance"]["create_table_query"])
    correction_create = str(by_name["self_correction_analytics"]["create_table_query"])

    assert "TTL" in drift_create
    assert "180" in drift_create
    assert "TTL" in usage_create
    assert "365" in usage_create
    assert str(by_name["usage_events"]["partition_key"]) == "toYYYYMM(event_time)"
    assert "TTL" not in fleet_create
    assert "TTL" not in correction_create

    await clickhouse_client.execute_command(
        "INSERT INTO usage_events ("
        "event_id, workspace_id, user_id, agent_id, workflow_id, execution_id, "
        "provider, model, input_tokens, output_tokens, reasoning_tokens, cached_tokens, "
        "estimated_cost, context_quality_score, reasoning_depth, event_time"
        ") VALUES ("
        f"'{uuid4()}', '{uuid4()}', '{uuid4()}', '{uuid4()}', NULL, NULL, "
        "'openai', 'gpt-4o', 10, 5, 0, 0, 0.100000, 0.5, 1, "
        "toDateTime64('2026-04-15 12:00:00', 3)"
        ")"
    )

    explain_rows = await clickhouse_client.execute_query(
        "EXPLAIN indexes = 1 "
        "SELECT count() FROM usage_events "
        "WHERE event_time >= toDateTime64('2026-04-01 00:00:00', 3) "
        "AND event_time < toDateTime64('2026-05-01 00:00:00', 3)"
    )
    rendered = "\n".join(" ".join(str(value) for value in row.values()) for row in explain_rows)
    assert rendered
    assert any(token in rendered for token in ("event_time", "Partition", "MergeTree"))
