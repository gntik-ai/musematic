from __future__ import annotations

import pytest

from suites.observability._helpers import push_loki_log, query_loki_until, unique_event

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_loki_datasource_exposes_trace_id_derived_field(grafana_client, loki_client) -> None:
    response = await grafana_client.get("/api/datasources/uid/loki")
    assert response.status_code == 200, response.text
    datasource = response.json()
    derived_fields = datasource.get("jsonData", {}).get("derivedFields", [])
    trace_links = [field for field in derived_fields if field.get("name") == "trace_id"]

    assert trace_links, derived_fields
    assert trace_links[0]["datasourceUid"] == "jaeger"
    assert "trace_id" in trace_links[0]["matcherRegex"]

    event_id = unique_event("trace-pivot")
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    await push_loki_log(
        loki_client,
        service="api",
        bounded_context="platform-control",
        level="error",
        message=event_id,
        fields={"trace_id": trace_id, "correlation_id": event_id},
    )
    await query_loki_until(
        loki_client,
        '{service="api",bounded_context="platform-control",level="error"}',
        lambda result: any(trace_id in line and event_id in line for stream in result for _ts, line in stream.get("values", [])),
    )
