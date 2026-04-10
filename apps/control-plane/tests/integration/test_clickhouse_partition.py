from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_ttl_and_partition_metadata(clickhouse_client) -> None:
    rows = await clickhouse_client.execute_query(
        "SELECT name, engine, partition_key, sorting_key, coalesce(ttl_table, '') AS ttl_table "
        "FROM system.tables "
        "WHERE database = currentDatabase() "
        "AND name IN ('usage_events', 'behavioral_drift', 'fleet_performance', 'self_correction_analytics') "
        "ORDER BY name"
    )
    by_name = {row["name"]: row for row in rows}

    assert "180 DAY" in str(by_name["behavioral_drift"]["ttl_table"])
    assert "365 DAY" in str(by_name["usage_events"]["ttl_table"])
    assert str(by_name["usage_events"]["partition_key"]) == "toYYYYMM(event_time)"
    assert str(by_name["fleet_performance"]["ttl_table"]) == ""
    assert str(by_name["self_correction_analytics"]["ttl_table"]) == ""

    explain_rows = await clickhouse_client.execute_query(
        "EXPLAIN indexes = 1 "
        "SELECT count() FROM usage_events "
        "WHERE event_time >= toDateTime64('2026-04-01 00:00:00', 3) "
        "AND event_time < toDateTime64('2026-05-01 00:00:00', 3)"
    )
    rendered = "\n".join(" ".join(str(value) for value in row.values()) for row in explain_rows)
    assert "event_time" in rendered or "Partition" in rendered
